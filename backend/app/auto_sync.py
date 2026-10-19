import asyncio
import json
import os
import time
import traceback
from datetime import datetime

import sync  # backend/sync.py
from . import models
from .database import SessionLocal

CACHE = "detail_cache"
PAGES = "pages_fb"
TICK = 60  # her dakika kontrol eder, istek sadece süresi dolan işler için atılır

# saniye cinsinden aralıklar
MATCHES_LIVE = 480
MATCHES_IDLE = 7200
LAST_LIVE = 1800
LAST_IDLE = 21600
INCIDENTS_EVERY = 300
STATS_EVERY = 900
LINEUPS_EVERY = 900
STANDINGS_EVERY = sync.STANDINGS_MAX_AGE  # 30 dk

backoff = {}
standings_at = 0


def due(path, every):
    return (not os.path.exists(path)) or time.time() - os.path.getmtime(path) >= every


def guard(key, fn):
    """Hata olursa 5 dakika bekletir, istek yakmasın."""
    if time.time() < backoff.get(key, 0):
        return None
    try:
        return fn()
    except Exception:
        backoff[key] = time.time() + 300
        traceback.print_exc()
        return None


def snapshot():
    now = datetime.now(sync.TR_TZ)
    out = []
    db = SessionLocal()
    try:
        rows = db.query(models.Match).filter(
            models.Match.status != "finished", models.Match.match_date.is_not(None)
        ).all()
        for m in rows:
            if not m.kickoff_time:
                continue
            ko = datetime.combine(m.match_date, m.kickoff_time, tzinfo=sync.TR_TZ)
            out.append({
                "id": m.api_id,
                "status": m.status,
                "d": (now - ko).total_seconds() / 60,  # başlamasından beri dakika
            })
    finally:
        db.close()
    return out


def in_live_window(m):
    # 4 saatten eski "live" kaydı takılı kalmış sayılır, istek yakmasın
    return (m["status"] == "live" and m["d"] <= 240) or -10 <= m["d"] <= 150


def refresh_matches(full):
    for name in (("next_0", "last_0") if full else ("next_0",)):
        p = f"{PAGES}/{name}.json"
        if os.path.exists(p) and time.time() - os.path.getmtime(p) > 120:
            os.remove(p)
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


def refresh_standings():
    # Önbellek tazeyse istek atmaz; yine de tabloyu önbellekten doldurur
    tables = sync.fetch_standings()
    db = SessionLocal()
    try:
        sync.sync_standings(db, tables)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def fetch_kind(api_id, kind):
    data = sync.api_get(f"/match/{api_id}/{kind}")
    os.makedirs(CACHE, exist_ok=True)
    with open(f"{CACHE}/{api_id}_{kind}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def has_ft(data):
    inc = (data.get("data") or {}).get("incidents") or []
    return any(i.get("incidentType") == "period" and i.get("text") == "FT" for i in inc)


def lineups_ready(aid):
    p = f"{CACHE}/{aid}_lineups.json"
    if not os.path.exists(p):
        return False
    try:
        with open(p, encoding="utf-8") as f:
            return bool((json.load(f).get("data") or {}).get("confirmed"))
    except Exception:
        return False


def tick():
    ms = snapshot()
    live = [m for m in ms if in_live_window(m)]
    next_p = f"{PAGES}/next_0.json"
    last_p = f"{PAGES}/last_0.json"

    # 1) maç listesi
    if due(next_p, MATCHES_LIVE if live else MATCHES_IDLE):
        full = due(last_p, LAST_LIVE if live else LAST_IDLE)
        guard("matches", lambda: refresh_matches(full))

    # puan durumu: 30 dakikada bir
    global standings_at
    if time.time() - standings_at >= STANDINGS_EVERY:
        standings_at = time.time()
        guard("standings", refresh_standings)

    for m in ms:
        aid = m["id"]
        if not aid:
            continue

        # 2) ilk 11: başlamadan ~75 dk önce onaylanana kadar
        if -75 <= m["d"] < 5 and not lineups_ready(aid) and due(f"{CACHE}/{aid}_lineups.json", LINEUPS_EVERY):
            guard(f"lin{aid}", lambda a=aid: fetch_kind(a, "lineups"))

        # 3) olaylar ve istatistik: sadece maç başladıysa
        if not in_live_window(m) or (m["d"] < 0 and m["status"] != "live"):
            continue
        if os.path.exists(f"{CACHE}/{aid}_done.flag"):
            continue
        if due(f"{CACHE}/{aid}_incidents.json", INCIDENTS_EVERY):
            data = guard(f"inc{aid}", lambda a=aid: fetch_kind(a, "incidents"))
            if data and has_ft(data):
                guard(f"st{aid}", lambda a=aid: fetch_kind(a, "statistics"))   # final istatistik
                guard("matches", lambda: refresh_matches(True))
                os.makedirs(CACHE, exist_ok=True)
                open(f"{CACHE}/{aid}_done.flag", "w").close()
                continue
        if due(f"{CACHE}/{aid}_statistics.json", STATS_EVERY):
            guard(f"st{aid}", lambda a=aid: fetch_kind(a, "statistics"))


async def sync_loop():
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(TICK)