"""client_ip ve last_post temizliği (Aşama 1). Çalıştırma: backend klasöründe `python -m pytest`"""
from starlette.requests import Request

from app import forum
from app.net import client_ip


def req(peer, xff=None):
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers,
                    "client": (peer, 1234) if peer else None})


def test_render_proxy_gives_real_client():
    # Render iç proxy'si (10.x) bağlanır, gerçek kullanıcı başlığın sonunda
    assert client_ip(req("10.201.4.5", "88.230.1.2")) == "88.230.1.2"


def test_spoofed_header_cannot_bypass():
    # Kullanıcı en sola sahte değer ekler; proxy gerçek adresi sona ekler
    assert client_ip(req("10.201.4.5", "1.2.3.4, 88.230.1.2")) == "88.230.1.2"


def test_cloudflare_hop_is_skipped():
    # Önde Cloudflare varsa son adres Cloudflare kenarıdır; kullanıcı ondan öncekidir
    assert client_ip(req("10.201.4.5", "88.230.1.2, 104.23.12.9")) == "88.230.1.2"


def test_fake_cloudflare_prefix_does_not_help():
    assert client_ip(req("10.201.4.5", "104.16.0.1, 88.230.1.2")) == "88.230.1.2"


def test_direct_public_peer_ignores_header():
    # Proxy olmayan doğrudan bağlantıda başlığa hiç güvenilmez
    assert client_ip(req("88.230.1.2", "1.2.3.4")) == "88.230.1.2"


def test_local_development_without_header():
    assert client_ip(req("127.0.0.1")) == "127.0.0.1"


def test_ipv6_and_garbage_entries():
    assert client_ip(req("10.0.0.7", "çöp, 2a02:ff0::5, 10.0.0.1")) == "2a02:ff0::5"


def test_no_client_info():
    assert client_ip(req(None)) == "unknown"


def test_prune_removes_old_entries():
    forum.last_post.clear()
    forum._last_prune = 0.0
    now = 10_000.0
    forum.last_post.update({"eski": now - 120, "yeni": now - 1})
    forum.prune_last_post(now)
    assert forum.last_post == {"yeni": now - 1}


def test_prune_respects_max_size(monkeypatch):
    forum.last_post.clear()
    forum._last_prune = 0.0
    monkeypatch.setattr(forum, "LAST_POST_MAX", 5)
    now = 10_000.0
    forum.last_post.update({f"ip{i}": now - i * 0.1 for i in range(8)})   # hepsi yeni
    forum.prune_last_post(now)
    assert len(forum.last_post) < 5
    assert "ip0" in forum.last_post            # en yeniler kalır
