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


def _trusted_proxy(ip):
    """Render'ın iç ağı (özel adresler) ve Cloudflare: bunlar proxy'dir, kullanıcı değildir."""
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or any(ip in net for net in CLOUDFLARE_NETS))


def client_ip(request):
    """Gerçek kullanıcı IP'si (metin).

    X-Forwarded-For'a her proxy kendi gördüğü adresi SONA ekler; kullanıcı ise başlığa
    sadece en sola sahte değer koyabilir. Bu yüzden liste sağdan okunur, güvenilen proxy
    adresleri atlanır ve ilk güvenilmeyen adres alınır. Böylece sahte başlıkla bekleme
    süresi atlatılamaz. (uvicorn --forwarded-allow-ips="*" en soldakini aldığı için
    sahtelenebilir; o yüzden kullanılmadı.)
    Başlık yoksa (yerel geliştirme) doğrudan bağlantı adresi kullanılır.
    """
    peer = request.client.host if request.client else ""
    peer_ip = _parse(peer)
    # Başlığa sadece bağlantı bir proxy'den geliyorsa güvenilir
    if peer_ip is not None and not _trusted_proxy(peer_ip):
        return str(peer_ip)
    hops = [_parse(p) for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    for ip in reversed(hops):
        if ip is None:
            continue
        if not _trusted_proxy(ip):
            return str(ip)
    # Hepsi proxy ya da başlık yok: en soldaki geçerli adres, o da yoksa bağlantı adresi
    first = next((ip for ip in hops if ip is not None), None)
    return str(first or peer_ip or "unknown")
