"""Web Push: abonelik, gönderim (gerçek şifreleme, sahte push servisi), mesajlar, canlı maç tetikleri."""
import asyncio
import base64
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from starlette.requests import Request

from app import cache, live, models, push
from app.database import SessionLocal

FCM = "https://fcm.googleapis.com/fcm/send/abc123-test-endpoint"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def browser_keys():
    """Tarayıcının üreteceği gibi geçerli p256dh/auth."""
    k = ec.generate_private_key(ec.SECP256R1()).public_key()
    return {"p256dh": b64(k.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
            "auth": b64(os.urandom(16))}


@pytest.fixture
def vapid(monkeypatch):
    out = subprocess.run([sys.executable, str(Path(__file__).parent.parent / "scripts" / "vapid_keys.py")],
                         capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        k, v = line.split("=", 1)
        monkeypatch.setenv(k, v)
    push._ip_log.clear()
    yield
    with SessionLocal() as db, db.begin():
        db.query(models.PushSubscription).delete()


def req(ip="77.1.1.1"):
    return Request({"type": "http", "method": "POST", "path": "/", "client": ("10.0.0.5", 1),
                    "headers": [(b"x-forwarded-for", ip.encode())]})


def subscribe(endpoint=FCM, ip="77.1.1.1"):
    data = push.SubscribeIn(endpoint=endpoint, keys=push.Keys(**browser_keys()))
    return asyncio.run(push.subscribe(data, req(ip)))


def test_disabled_without_keys(monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    assert push.key() == {"enabled": False, "key": None}
    assert push.broadcast("x", "y", "t") == 0
    with pytest.raises(HTTPException) as e:
        subscribe()
    assert e.value.status_code == 503


@pytest.mark.parametrize("url,ok", [
    (FCM, True), ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
    ("https://web.push.apple.com/abc", True), ("https://db5p.notify.windows.com/w/?token=x", True),
    ("http://fcm.googleapis.com/fcm/send/x", False), ("https://evil.example.com/fcm.googleapis.com", False),
    ("https://fcm.googleapis.com.evil.com/x", False), ("https://127.0.0.1/x", False),
])
def test_endpoint_allowlist(url, ok):
    assert push.allowed_endpoint(url) is ok


def test_subscribe_validates_and_rate_limits(vapid, monkeypatch):
    assert push.key()["enabled"] and push.key()["key"]
    assert subscribe()["ok"]
    subscribe()                                             # aynı uç nokta: güncellenir, çoğalmaz
    with SessionLocal() as db:
        assert db.query(models.PushSubscription).count() == 1
    with pytest.raises(HTTPException) as e:
        subscribe("https://evil.example.com/push")
    assert e.value.status_code == 400
    monkeypatch.setattr(push, "SUBSCRIBES_PER_HOUR", 1)
    push._ip_log.clear()
    subscribe(FCM + "-2", ip="77.2.2.2")
    with pytest.raises(HTTPException) as e:
        subscribe(FCM + "-3", ip="77.2.2.2")
    assert e.value.status_code == 429
    asyncio.run(push.unsubscribe(push.UnsubscribeIn(endpoint=FCM)))
    with SessionLocal() as db:
        assert db.query(models.PushSubscription).filter_by(endpoint=FCM).count() == 0


class FakeResponse:
    def __init__(self, status):
        self.status_code = status
        self.text = ""
        self.reason = "Gone" if status == 410 else "Created"
        self.headers = {}


def test_broadcast_encrypts_dedupes_and_drops_gone(vapid, monkeypatch):
    import pywebpush
    subscribe(FCM)
    subscribe(FCM + "-gone", ip="77.3.3.3")
    sent = []

    def fake_post(url, data=None, headers=None, timeout=None, **kw):
        sent.append({"url": url, "headers": headers, "size": len(data)})
        return FakeResponse(410 if url.endswith("-gone") else 201)
    monkeypatch.setattr(pywebpush.requests, "post", fake_post)

    assert push.broadcast("Gol", "Fenerbahçe 1-0 Rakip", "mac-1", dedupe="test:1:goal:1-0") == 1
    assert len(sent) == 2
    h = sent[0]["headers"]
    assert h["Content-Encoding"] == "aes128gcm" and h["Authorization"].startswith("vapid t=")
    assert int(h["TTL"]) == push.TTL
    with SessionLocal() as db:                               # 410 dönen abonelik silindi
        assert [s.endpoint for s in db.query(models.PushSubscription).all()] == [FCM]
    assert push.broadcast("Gol", "tekrar", "mac-1", dedupe="test:1:goal:1-0") == 0     # aynı gol iki kez gitmez
    assert len(sent) == 2
    cache.delete("push:test:1:goal:1-0")


def test_messages():
    m = {"id": 5, "home": "Fenerbahçe", "away": "Göztepe", "home_score": 2, "away_score": 1}
    title, body, tag, key = push.message_for("goal", m, {"player": "En-Nesyri", "time": 90, "addedTime": 3, "isHome": True})
    assert title.startswith("GOOOL") and body == "Fenerbahçe 2-1 Göztepe (90+3' · En-Nesyri)"
    assert tag == "mac-5" and key == "5:goal:2-1"
    assert push.message_for("goal", m, {"player": "X", "time": 10, "isHome": False})[0] == "Gol"
    away = {**m, "home": "Göztepe", "away": "Fenerbahçe"}
    assert push.message_for("goal", away, {"isHome": False, "time": 5})[0].startswith("GOOOL")
    assert push.message_for("start", m)[3] == "5:start"
    assert push.message_for("end", m)[1] == "Fenerbahçe 2-1 Göztepe"


def test_follower_announces_start_and_end(monkeypatch):
    fired = []
    monkeypatch.setattr(push, "fire", lambda *a: fired.append(a[0]))
    f = live.Follower({"id": 5, "api_id": 1, "kickoff": time.time() - 60})
    base = {"id": 5, "home": "Fenerbahçe", "away": "Göztepe", "home_score": 0, "away_score": 0}
    f.announce({**base, "status": "scheduled"}, {**base, "status": "live"})
    f.announce({**base, "status": "live"}, {**base, "status": "live"})      # değişiklik yok
    f.announce({**base, "status": "live"}, {**base, "status": "finished"})
    assert fired == ["Maç başladı", "Maç bitti"]
    late = live.Follower({"id": 5, "api_id": 1, "kickoff": time.time() - 3600})
    late.announce(None, {**base, "status": "live"})          # sunucu maç ortasında açıldı: "başladı" yok
    assert fired == ["Maç başladı", "Maç bitti"]


def test_routes_registered():
    from app.main import app
    paths = set(app.openapi()["paths"])
    assert {"/api/push/key", "/api/push/subscribe", "/api/push/unsubscribe", "/api/calendar.ics"} <= paths
