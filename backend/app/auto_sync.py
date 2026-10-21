"""Periyodik SportsAPI senkronu: maç listesi, puan durumu ve (canlı WebSocket
izlemiyorsa) maç detayları. Günlük kotayı korumak için her iş kendi aralığıyla çalışır."""
import asyncio
import time
import traceback
from datetime import datetime, timedelta

from . import absences_sync, cache, live, models, predictions, sync
from .database import SessionLocal

TICK = 60  # her dakika uyanır, istek sadece süresi dolan işler için atılır

# Maç saatine yakın değilken (başlamadan 2 sa 10 dk öncesi - 3 sa sonrası dışı) tam kontrol ve
# maç listesi okuması yarım saatte bir yapılır: veritabanı (Neon) boşta uyuyabilsin, ücretsiz
# planın işlem süresi boşa harcanmasın. Maç saatinde her dakika.
IDLE_EVERY = 1800
BUSY_BEFORE, BUSY_AFTER = -130, 180          # dakika (başlamadan önce / sonra)

# saniye cinsinden aralıklar
MATCHES_LIVE = 480
MATCHES_IDLE = 7200
LAST_LIVE = 1800
LAST_IDLE = 21600
INCIDENTS_EVERY = 300
STATS_EVERY = 900


def lineups_every(minutes_since_kickoff):
    """Kadro (ve maç günü eksikleri) sorgu aralığı: maça 24 saatten az kala 3 saatte bir,
    son 2 saatte 30 dakikada bir; kadro onaylanınca durur. Aralık dışında None."""
    d = minutes_since_kickoff
    if -24 * 60 <= d < -120:
        return 3 * 3600
    if -120 <= d < 5:
        return 1800
    return None
STANDINGS_EVERY = sync.STANDINGS_MAX_AGE  # 3 saat

backoff = {}
standings_at = 0


def due(key, every):
    return cache.age(key) >= every


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


_snap = {"at": 0.0, "rows": [], "busy": False}   # bitmemiş maçlar: (api_id, durum, başlama)
_last_full = 0.0


def reset():
    """Bellekteki maç listesini ve son tam kontrol zamanını unutur (sonraki tick DB'yi okur)."""
    global _last_full
    _snap["at"] = 0.0
    _last_full = 0.0


def snapshot():
    """Bitmemiş maçlar ve başlamalarından beri geçen dakika (d). Liste bellekte tutulur:
    maç saatinde dakikada bir, değilse yarım saatte bir veritabanından yenilenir."""
    ttl = TICK if _snap["busy"] else IDLE_EVERY
    if time.time() - _snap["at"] >= ttl:
        with SessionLocal() as db:
            rows = db.query(models.Match).filter(
                models.Match.status != "finished", models.Match.match_date.is_not(None)
            ).all()
            _snap["rows"] = [
                (m.api_id, m.status, datetime.combine(m.match_date, m.kickoff_time, tzinfo=sync.TR_TZ))
                for m in rows if m.kickoff_time
            ]
        _snap["at"] = time.time()
    now = datetime.now(sync.TR_TZ)
    out = [{"id": aid, "status": st, "d": (now - ko).total_seconds() / 60} for aid, st, ko in _snap["rows"]]
    _snap["busy"] = is_busy(out)
    return out


def is_busy(ms):
    """Maç saatine yakın mıyız (kadro, canlı maç, maç sonu özeti için sık kontrol gerekir)?"""
    return any(BUSY_BEFORE <= m["d"] <= BUSY_AFTER or (m["status"] == "live" and m["d"] <= 240) for m in ms)


def in_live_window(m):
    # 4 saatten eski "live" kaydı takılı kalmış sayılır, istek yakmasın
    return (m["status"] == "live" and m["d"] <= 240) or -10 <= m["d"] <= 150


def refresh_matches(full):
    # 2 dakikadan eski sayfalar yeniden istenir; istek başarısız olursa eskisi korunur
    names = ("next_0", "last_0") if full else ("next_0",)
    stale = [n for n in names if cache.age(f"pages:{n}") > 120]
    events = sync.fetch_events(refresh=stale)
    db = SessionLocal()
    try:
        sync.sync_matches(db, events)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    _snap["at"] = 0.0           # maç durumları değişmiş olabilir: listeyi yeniden oku


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
    cache.put(f"detail:{api_id}:{kind}", data)
    if kind == "lineups":
        absences_sync.apply_lineups(api_id, data.get("data"))   # maç günü eksikleri + genel rapor
    return data


def has_ft(data):
    inc = (data.get("data") or {}).get("incidents") or []
    return any(i.get("incidentType") == "period" and i.get("text") == "FT" for i in inc)


def lineups_ready(aid):
    data = cache.get(f"detail:{aid}:lineups") or {}
    return bool((data.get("data") or {}).get("confirmed"))


PREVIEW_DAYS = 7                                 # sıradaki maç bu kadar gün içindeyse maç öncesi çekilir
PREVIEW_EVERY = 24 * 3600                        # günde bir kez
SUMMARY_AFTER = timedelta(hours=2, minutes=15)   # başlamadan bu kadar sonra veriler kesinleşmiş olur
SUMMARY_WINDOW = timedelta(days=2)               # daha eski maçlar için özet çekilmez (kota)
SUMMARY_MIN_QUOTA = live.QUOTA_STOP + 3          # özet 3 istek: günlük %60 sınırını aşmasın


def summary_targets(now=None):
    """Özeti çekilecek maçlar: bitmiş, başlamasından 2 saat 15 dk geçmiş, en fazla 2 günlük,
    özeti henüz alınmamış."""
    now = now or datetime.now(sync.TR_TZ)
    out = []
    with SessionLocal() as db:
        rows = db.query(models.Match).filter(
            models.Match.status == "finished", models.Match.api_id.is_not(None),
            models.Match.match_date.is_not(None), models.Match.kickoff_time.is_not(None),
        ).all()
        for m in rows:
            ko = datetime.combine(m.match_date, m.kickoff_time, tzinfo=sync.TR_TZ)
            if ko + SUMMARY_AFTER <= now <= ko + SUMMARY_WINDOW:
                out.append(m.api_id)
    return [a for a in out if not cache.get(f"detail:{a}:summary_done")]


def fetch_summary(api_id):
    """Maç sonu özeti: baskı grafiği, şut haritası, en iyi oyuncular (3 istek, bir kez)."""
    q = sync.quota_remaining
    if q is not None and q < SUMMARY_MIN_QUOTA:
        return
    for kind in ("graph", "shotmap", "best-players"):
        if cache.get(f"detail:{api_id}:{kind}") is None:
            fetch_kind(api_id, kind)
    cache.put(f"detail:{api_id}:summary_done", True)
    print(f"Maç özeti kaydedildi: {api_id}", flush=True)


def tick():
    global _last_full
    ms = snapshot()
    # Maç saatine yakın değilsek tam kontrol yarım saatte bir (önbellek yaşları da DB'de)
    if not is_busy(ms) and time.time() - _last_full < IDLE_EVERY:
        return
    _last_full = time.time()
    live_now = [m for m in ms if in_live_window(m)]
    next_p = "pages:next_0"
    last_p = "pages:last_0"

    # 1) maç listesi
    if due(next_p, MATCHES_LIVE if live_now else MATCHES_IDLE):
        full = due(last_p, LAST_LIVE if live_now else LAST_IDLE)
        guard("matches", lambda: refresh_matches(full))

    # skor tahmin oyunu: biten maçları puanla, yaklaşan maçlara model tahmini (istek atmaz)
    guard("predict", predictions.settle)

    # maç sonu özeti: bitmiş maçlar için bir kez
    for aid in summary_targets():
        guard(f"sum{aid}", lambda a=aid: fetch_summary(a))

    # Maç öncesi: sıradaki maç 7 gün içindeyse h2h + form günde bir kez (2 istek)
    upcoming = [m for m in ms if m["id"] and -PREVIEW_DAYS * 1440 <= m["d"] < 0]
    if upcoming:
        nxt = max(upcoming, key=lambda m: m["d"])          # başlamasına en az kalan
        q = sync.quota_remaining
        if due(f"detail:{nxt['id']}:pregame-form", PREVIEW_EVERY) and (q is None or q > live.QUOTA_STOP + 5):
            guard(f"pre{nxt['id']}", lambda a=nxt["id"]: [fetch_kind(a, k) for k in ("h2h", "pregame-form")])

    # V6 sakatlık listesi: günde 2 kez (genel rapora eklenir); kota bütçesi elverirse
    q = sync.quota_remaining
    if due("absences:v6", absences_sync.V6_EVERY) and (q is None or q > live.QUOTA_STOP + 5):
        guard("v6", absences_sync.apply_v6_injuries)

    # puan durumu: 30 dakikada bir
    global standings_at
    if time.time() - standings_at >= STANDINGS_EVERY:
        standings_at = time.time()
        guard("standings", refresh_standings)

    for m in ms:
        aid = m["id"]
        if not aid:
            continue

        # 2) ilk 11 ve maç günü eksikleri: maça 24 saat kala başlar, kadro onaylanınca durur
        if live.covers(aid):
            continue    # canlı WebSocket bu maçı izliyor: kadro/olay/istatistik oradan gelir (kotasız)
        every = lineups_every(m["d"])
        if every and not lineups_ready(aid) and due(f"detail:{aid}:lineups", every):
            guard(f"lin{aid}", lambda a=aid: fetch_kind(a, "lineups"))

        # 3) olaylar ve istatistik: sadece maç başladıysa
        if not in_live_window(m) or (m["d"] < 0 and m["status"] != "live"):
            continue
        if cache.get(f"detail:{aid}:done"):
            continue
        if due(f"detail:{aid}:incidents", INCIDENTS_EVERY):
            data = guard(f"inc{aid}", lambda a=aid: fetch_kind(a, "incidents"))
            if data and has_ft(data):
                guard(f"st{aid}", lambda a=aid: fetch_kind(a, "statistics"))   # final istatistik
                guard("matches", lambda: refresh_matches(True))
                cache.put(f"detail:{aid}:done", True)
                continue
        if due(f"detail:{aid}:statistics", STATS_EVERY):
            guard(f"st{aid}", lambda a=aid: fetch_kind(a, "statistics"))


async def sync_loop():
    while True:
        try:
            await asyncio.to_thread(tick)
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(TICK)