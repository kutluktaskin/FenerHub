"""İstemci IP'si ile ilgili yardımcılar.

Render, uygulamanın önünde bir proxy çalıştırır; request.client.host bu yüzden
kullanıcının değil proxy'nin adresidir. Gerçek adres X-Forwarded-For başlığındadır.
"""
import ipaddress


# Cloudflare'in yayımladığı aralıklar (https://www.cloudflare.com/ips/, 2026-10 itibarıyla)
CLOUDFLARE_NETS = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
    "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
)]


def _parse(raw):
    """'1.2.3.4', '1.2.3.4:5678', '[::1]:80' gibi değerlerden IP nesnesi; geçersizse None."""
    value = (raw or "").strip().strip('"')
    if value.startswith("["):                       # [IPv6]:port
        value = value[1:value.find("]")] if "]" in value else value[1:]
    elif value.count(":") == 1:                     # IPv4:port
        value = value.split(":")[0]
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def classify(ip):
    """Teşhis için adres türü: özel / cloudflare / genel / geçersiz."""
    if ip is None:
        return "geçersiz"
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return "özel"
    if any(ip in net for net in CLOUDFLARE_NETS):
        return "cloudflare"
    return "genel"


def mask(ip):
    """Loga tam adres yazılmaz: 203.0.113.7 -> 203.0.x.x, 2001:db8::1 -> 2001:db8::x"""
    if ip is None:
        return "-"
    if ip.version == 4:
        a, b, *_ = str(ip).split(".")
        return f"{a}.{b}.x.x"
    return ":".join(ip.exploded.split(":")[:2]) + "::x"


# ---- Geçici teşhis (Aşama 1): proxy zincirini öğrenmek için ilk N isteği maskeli loglar ----
DIAG_LIMIT = 30
_diag_count = 0


def diagnose(request):
    """Başlık yapısını maskeli olarak loglar; DIAG_LIMIT istekten sonra susar."""
    global _diag_count
    if _diag_count >= DIAG_LIMIT:
        return
    _diag_count += 1
    peer = _parse(request.client.host) if request.client else None
    xff = [_parse(p) for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    extra = {h: ("var" if request.headers.get(h) else "yok")
             for h in ("cf-connecting-ip", "true-client-ip", "x-real-ip", "forwarded")}
    msg = (f"ip-teşhis {_diag_count}/{DIAG_LIMIT}: bağlantı={mask(peer)}({classify(peer)}) "
           f"xff=[{', '.join(f'{mask(i)}({classify(i)})' for i in xff)}] "
           + " ".join(f"{k}={v}" for k, v in extra.items()))
    print(msg, flush=True)   # Render loglarında görünür (uvicorn logger seviyesinden bağımsız)
