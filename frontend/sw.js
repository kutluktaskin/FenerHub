/* FenerHub service worker: kurulabilir uygulama + çevrimdışı yedek + bildirimler.
   - Sayfa (navigasyon): önce ağ; ağ yoksa son kaydedilen sayfa, o da yoksa offline.html.
     Böylece yeni sürüm yayınlanınca kullanıcı eski sayfada takılı kalmaz.
   - Aynı kökenden statik dosyalar (css/js/img/demo): stale-while-revalidate.
     Dosyalar ?v= ile sürümlendiği için aynı yolun eski sürümleri önbellekten silinir.
   - API (fenerhub.onrender.com), WebSocket, video ve arka plan kareleri: hiç dokunulmaz (ağdan). */
const VERSION = "fh-v1";
const SHELL = ["/", "/offline.html", "/img/favicon.svg", "/img/icons/icon-192.png", "/manifest.webmanifest"];
const SKIP = /^\/(frames|frames_orijinal_yedek)\/|\.mp4$/;

self.addEventListener("install", e => {
    e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
    e.waitUntil(caches.keys()
        .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
        .then(() => self.clients.claim()));
});

async function pageFirst(req) {
    const cache = await caches.open(VERSION);
    try {
        const res = await fetch(req);
        if (res.ok) cache.put("/", res.clone());
        return res;
    } catch (e) {
        return (await cache.match("/")) || (await cache.match("/offline.html"));
    }
}

async function staleWhileRevalidate(req, event) {
    const cache = await caches.open(VERSION);
    const hit = await cache.match(req);
    const update = fetch(req).then(async res => {
        if (res.ok && res.type === "basic") {
            const url = new URL(req.url);
            // aynı dosyanın eski ?v= sürümlerini temizle
            for (const old of await cache.keys()) {
                const o = new URL(old.url);
                if (o.pathname === url.pathname && o.search !== url.search) cache.delete(old);
            }
            await cache.put(req, res.clone());
        }
        return res;
    }).catch(() => hit || Response.error());
    if (hit) { event.waitUntil(update); return hit; }
    return update;
}

self.addEventListener("fetch", e => {
    const req = e.request;
    if (req.method !== "GET") return;
    const url = new URL(req.url);
    if (url.origin !== self.location.origin || SKIP.test(url.pathname)) return;
    if (req.mode === "navigate") { e.respondWith(pageFirst(req)); return; }
    e.respondWith(staleWhileRevalidate(req, e));
});

// ---------- Bildirimler (backend/app/push.py gönderir, js/push.js abone eder) ----------
self.addEventListener("push", e => {
    let d = {};
    try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data && e.data.text() }; }
    e.waitUntil(self.registration.showNotification(d.title || "FenerHub", {
        body: d.body || "",
        tag: d.tag,                     // aynı maçın bildirimleri üst üste yığılmaz, son durum görünür
        renotify: !!d.tag,
        icon: "/img/icons/icon-192.png",
        badge: "/img/icons/icon-192.png",
        data: { url: d.url || "/" },
    }));
});

self.addEventListener("notificationclick", e => {
    e.notification.close();
    const url = new URL(e.notification.data && e.notification.data.url || "/", self.location.origin).href;
    e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
        const open = list.find(c => new URL(c.url).origin === self.location.origin);
        return open ? open.focus() : self.clients.openWindow(url);
    }));
});
