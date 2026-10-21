"""Web Push bildirimleri: maç başladı, gol, maç bitti.

Hesap yok: tarayıcı izin verince aboneliğini (uç nokta + anahtarlar) gönderir, sunucu saklar.
Bildirimi canlı maç izleyicisi (app/live.py) tetikler; gönderim arka planda, iş parçacığında yapılır.

Anahtarlar ortam değişkenlerinde (kodda/git'te değil):
  VAPID_PUBLIC_KEY   tarayıcıya verilen açık anahtar (base64url)
  VAPID_PRIVATE_KEY  imza anahtarı (base64url, sadece sunucuda)
  VAPID_SUBJECT      iletişim adresi (varsayılan: site adresi)
Anahtar yoksa özellik kapalıdır (/api/push/key → enabled: false), site normal çalışır.
Üretmek için: python scripts/vapid_keys.py
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import cache, models
from .database import SessionLocal
from .net import client_ip

router = APIRouter(tags=["bildirim"])

MAX_SUBSCRIPTIONS = 20000
SUBSCRIBES_PER_HOUR = 10
TTL = 30 * 60                     # 30 dk içinde ulaşamayan bildirim bayatlamıştır, atılır
# Sunucu sadece bilinen push servislerine istek atar (rastgele adrese POST attırılamasın)
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com",
              "web.push.apple.com", ".push.apple.com", ".notify.windows.com")
_ip_log: dict[str, list[float]] = {}


def public_key():
    return os.getenv("VAPID_PUBLIC_KEY") or None


def enabled() -> bool:
    return bool(public_key() and os.getenv("VAPID_PRIVATE_KEY"))


def allowed_endpoint(url: str) -> bool:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS)


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscribeIn(BaseModel):
    endpoint: str = Field(min_length=20, max_length=600)
    keys: Keys


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=20, max_length=600)


@router.get("/api/push/key")
def key():
    return {"enabled": enabled(), "key": public_key() if enabled() else None}


def save_subscription(data: SubscribeIn) -> None:
    with SessionLocal() as db, db.begin():
        row = db.query(models.PushSubscription).filter_by(endpoint=data.endpoint).first()
        if row:
            row.p256dh, row.auth, row.ts = data.keys.p256dh, data.keys.auth, int(time.time())
            return
        if db.query(models.PushSubscription).count() >= MAX_SUBSCRIPTIONS:
            raise HTTPException(503, "Bildirim kapasitesi dolu.")
        db.add(models.PushSubscription(endpoint=data.endpoint, p256dh=data.keys.p256dh,
                                       auth=data.keys.auth, ts=int(time.time())))


def delete_subscription(endpoint: str) -> None:
    with SessionLocal() as db, db.begin():
        db.query(models.PushSubscription).filter_by(endpoint=endpoint).delete()


@router.post("/api/push/subscribe")
async def subscribe(data: SubscribeIn, request: Request):
    if not enabled():
        raise HTTPException(503, "Bildirimler şu an kapalı.")
    if not allowed_endpoint(data.endpoint):
        raise HTTPException(400, "Geçersiz bildirim adresi.")
    ip, now = client_ip(request), time.time()
    recent = [t for t in _ip_log.get(ip, []) if now - t < 3600]
    if len(recent) >= SUBSCRIBES_PER_HOUR:
        raise HTTPException(429, "Çok fazla deneme, biraz sonra tekrar dene.")
    _ip_log[ip] = recent + [now]
    await run_in_threadpool(save_subscription, data)
    return {"ok": True}


@router.post("/api/push/unsubscribe")
async def unsubscribe(data: UnsubscribeIn):
    await run_in_threadpool(delete_subscription, data.endpoint)
    return {"ok": True}


# ---------- Gönderim ----------
def send_one(sub: dict, payload: str) -> bool:
    """Tek aboneye gönderir. Abonelik artık geçersizse (404/410) False döner."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload, vapid_private_key=os.getenv("VAPID_PRIVATE_KEY"),
                vapid_claims={"sub": os.getenv("VAPID_SUBJECT") or "https://fenerhub.vercel.app"},
                ttl=TTL, timeout=10)
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        return status not in (404, 410)
    except Exception as e:                       # ağ hatası vb.: aboneliği silme
        print(f"Push gönderilemedi: {type(e).__name__}", flush=True)
    return True


def broadcast(title: str, body: str, tag: str, dedupe: str | None = None) -> int:
    """Tüm abonelere bildirim. dedupe verilirse aynı bildirim ikinci kez gitmez
    (sunucu yeniden başlarsa maç başladı bildirimi tekrarlanmasın). Gönderilen sayıyı döndürür."""
    if not enabled():
        return 0
    if dedupe:
        key = f"push:{dedupe}"
        if cache.get(key):
            return 0
        cache.put(key, True)
    with SessionLocal() as db:
        subs = [{"endpoint": s.endpoint, "p256dh": s.p256dh, "auth": s.auth}
                for s in db.query(models.PushSubscription).all()]
    if not subs:
        return 0
    payload = json.dumps({"title": title, "body": body, "tag": tag, "url": "/"}, ensure_ascii=False)
    with ThreadPoolExecutor(max_workers=8) as pool:
        alive = list(pool.map(lambda s: send_one(s, payload), subs))
    gone = [s["endpoint"] for s, ok in zip(subs, alive) if not ok]
    for endpoint in gone:
        delete_subscription(endpoint)
    print(f"Push: '{title}' {len(subs) - len(gone)} aboneye gitti, {len(gone)} geçersiz silindi", flush=True)
    return len(subs) - len(gone)


async def notify(title: str, body: str, tag: str, dedupe: str | None = None) -> None:
    """Canlı maç döngüsünü bekletmeden gönderir; hata canlı takibi asla durdurmaz."""
    try:
        await run_in_threadpool(broadcast, title, body, tag, dedupe)
    except Exception as e:
        print(f"Push hatası: {type(e).__name__}", flush=True)


_tasks: set = set()


def fire(title: str, body: str, tag: str, dedupe: str | None = None) -> None:
    """notify'ı arka planda başlatır (çağıran beklemez). Görev referansı tutulur, yarıda toplanmasın."""
    if not enabled():
        return
    import asyncio
    task = asyncio.get_running_loop().create_task(notify(title, body, tag, dedupe))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


# ---------- Mesaj metinleri (live.py çağırır) ----------
def score_line(match: dict) -> str:
    return f"{match['home']} {match.get('home_score') or 0}-{match.get('away_score') or 0} {match['away']}"


def message_for(kind: str, match: dict, incident: dict | None = None):
    """(başlık, metin, etiket, tekrar anahtarı) döndürür. kind: start | goal | end."""
    mid = match["id"]
    if kind == "start":
        return ("Maç başladı", f"{match['home']} - {match['away']} başladı. Canlı takip FenerHub'da.",
                f"mac-{mid}", f"{mid}:start")
    if kind == "end":
        return ("Maç bitti", score_line(match), f"mac-{mid}", f"{mid}:end")
    inc = incident or {}
    scorer = inc.get("player")
    fb_home = match["home"] == "Fenerbahçe"
    fb_goal = inc.get("isHome") is not None and inc.get("isHome") == fb_home
    minute = f"{inc['time']}'" if inc.get("time") else ""
    if inc.get("addedTime"):
        minute = f"{inc['time']}+{inc['addedTime']}'"
    title = "GOOOL! Fenerbahçe" if fb_goal else "Gol"
    detail = " · ".join(x for x in (minute, scorer, "kendi kalesine" if inc.get("incidentClass") == "ownGoal" else None) if x)
    body = score_line(match) + (f" ({detail})" if detail else "")
    return (title, body, f"mac-{mid}", f"{mid}:goal:{match.get('home_score')}-{match.get('away_score')}")
