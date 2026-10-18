"""Arka plan senkronizasyonu. main.py backend açılırken başlatır.
Maçlar, puan durumu, kadro ve oyuncu istatistikleri kendiliğinden güncellenir.
Maç saatlerinde sık, diğer zamanlarda seyrek istek atar."""
import asyncio
import json
import os
import time
import traceback
from datetime import datetime, timedelta

import sync  # backend/sync.py
from . import models
from .database import SessionLocal

FAST = 180                 # maç penceresinde 3 dk
SLOW = 3600                # normalde en fazla 1 saat
ROSTER_EVERY = 6 * 3600    # kadro + oyuncu istatistikleri 6 saatte bir
SQUAD_MAX_AGE = 5 * 3600
PAGES = "pages_fb"


def _rm(*names):
    """Kayıtlı maç sayfasını siler ki sync yeniden çeksin (90 sn'den yeniyse dokunmaz)."""
    for n in names:
        p = f"{PAGES}/{n}.json"
        if os.path.exists(p) and time.time() - os.path.getmtime(p) > 90:
            os.remove(p)


def window_state():
    """(şu an maç penceresinde mi, bir sonraki pencereye kaç saniye var)
    Pencere: başlamadan 10 dk önce -> başlamadan 150 dk sonra."""
    now = datetime.now(sync.TR_TZ)
    fast = False
    next_start = None
    db = SessionLocal()
    try:
        rows = db.query(models.Match).filter(
            models.Match.status != "finished", models.Match.match_date.is_not(None)
        ).all()
        for m in rows:
            if m.status == "live":
                fast = True
            if not m.kickoff_time:
                continue
            ko = datetime.combine(m.match_date, m.kickoff_time, tzinfo=sync.TR_TZ)
            start, end = ko - timedelta(minutes=10), ko + timedelta(minutes=150)
            if start <= now <= end:
                fast = True
            elif start > now and (next_start is None or start < next_start):
                next_start = start
    finally:
        db.close()
    wait = None if next_start is None else max(30, int((next_start - now).total_seconds()))
    return fast, wait


def run_matches():
    events = sync.fetch_events()
    db = SessionLocal()
    try:
        sync.sync_matches(db, events)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_standings(max_age):
    old = sync.STANDINGS_MAX_AGE
    sync.STANDINGS_MAX_AGE = max_age
    try:
        sync.fetch_standings()
    finally:
        sync.STANDINGS_MAX_AGE = old


def load_squad():
    fn = "squad_raw.json"
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < SQUAD_MAX_AGE:
        with open(fn, encoding="utf-8") as f:
            return json.load(f)["data"]["players"]
    return sync.fetch_squad()


def run_roster(force_stats=False):
    squad = load_squad()
    old = sync.STATS_MAX_AGE
    if force_stats:
        sync.STATS_MAX_AGE = 0
    try:
        stats = sync.fetch_player_stats(squad)
    finally:
        sync.STATS_MAX_AGE = old
    db = SessionLocal()
    try:
        team = sync.sync_squad(db, squad)
        db.flush()
        sync.remove_excluded(db)
        sync.sync_player_stats(db, team, stats)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def sync_loop():
    n = 0
    last_roster = 0.0
    was_fast = False
    while True:
        fast, wait = False, None
        try:
            fast, wait = window_state()
            just_ended = was_fast and not fast   # pencere kapandı: son bir tam yenileme
            n += 1
            _rm("next_0")
            if fast or just_ended:
                _rm("last_0")                    # biten maç last/0'a düşer
            if not fast and n % 6 == 0:
                _rm("next_1", "last_0")
            await asyncio.to_thread(run_matches)
            await asyncio.to_thread(run_standings, 0 if just_ended else (900 if fast else 3600))
            if just_ended or time.time() - last_roster > ROSTER_EVERY:
                await asyncio.to_thread(run_roster, just_ended)
                last_roster = time.time()
            print(f"[auto_sync] tamam, mod: {'CANLI' if fast else 'normal'}")
        except Exception:
            traceback.print_exc()
        was_fast = fast
        if fast:
            delay = FAST
        else:
            delay = min(SLOW, wait) if wait else SLOW   # bir sonraki maç penceresini kaçırma
        await asyncio.sleep(delay)