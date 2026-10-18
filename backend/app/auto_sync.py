import asyncio
import os
import time
import traceback
from datetime import datetime, timedelta

import sync  # backend/sync.py
from . import models
from .database import SessionLocal

FAST = 180    # canlı pencere: 3 dakika
SLOW = 3600   # normal: 1 saat
PAGES = "pages_fb"


def _rm(*names):
    """Önbellek dosyasını siler (90 sn'den yeniyse dokunmaz, sık yeniden başlatmada istek yakmasın)."""
    for n in names:
        p = f"{PAGES}/{n}.json"
        if os.path.exists(p) and time.time() - os.path.getmtime(p) > 90:
            os.remove(p)


def live_window():
    """Canlı maç var mı ya da bir maçın başlamasına 10 dk / başlamasından 150 dk içinde miyiz?"""
    now = datetime.now(sync.TR_TZ)
    db = SessionLocal()
    try:
        rows = db.query(models.Match).filter(
            models.Match.status != "finished", models.Match.match_date.is_not(None)
        ).all()
        for m in rows:
            if m.status == "live":
                return True
            if m.kickoff_time:
                ko = datetime.combine(m.match_date, m.kickoff_time, tzinfo=sync.TR_TZ)
                if ko - timedelta(minutes=10) <= now <= ko + timedelta(minutes=150):
                    return True
        return False
    finally:
        db.close()


def run_once():
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


async def sync_loop():
    n = 0
    while True:
        fast = False
        try:
            fast = live_window()
            n += 1
            _rm("next_0")
            if fast and n % 3 == 0:
                _rm("last_0")                 # biten maç last/0'a düşer
            if not fast and n % 6 == 0:
                _rm("next_1", "last_0")       # 6 saatte bir tam yenileme
            await asyncio.to_thread(run_once)
            print(f"[auto_sync] tamam, mod: {'CANLI' if fast else 'normal'}")
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(FAST if fast else SLOW)