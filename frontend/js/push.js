/* Gol / maç başladı / maç bitti bildirimleri (Web Push). Hesap gerekmez.
   Akış: izin iste → tarayıcı aboneliği (VAPID açık anahtarıyla) → POST /api/push/subscribe.
   Backend: backend/app/push.py. Bildirimi sw.js gösterir. Backend'de anahtar yoksa düğme görünmez. */
(function () {
    const btn = document.getElementById("pushBtn");
    const note = document.getElementById("pushNote");
    if (!btn || typeof API_BASE === "undefined") return;
    const label = btn.querySelector("span");
    const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent);
    let key = null;

    function say(text) { note.textContent = text || ""; note.hidden = !text; }

    function setOn(on) {
        btn.setAttribute("aria-pressed", String(on));
        label.textContent = on ? "Bildirimler açık" : "Gol bildirimlerini aç";
        btn.title = on ? "Kapatmak için dokun" : "Maç başlayınca, gol olunca ve maç bitince bildirim al";
    }

    function keyBytes(b64) {
        const s = atob((b64 + "=".repeat((4 - b64.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
        return Uint8Array.from(s, c => c.charCodeAt(0));
    }

    async function send(path, body) {
        const r = await fetch(`${API_BASE}${path}`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        if (!r.ok) {
            let d = null;
            try { d = await r.json(); } catch (e) {}
            throw new Error((d && typeof d.detail === "string") ? d.detail : `HTTP ${r.status}`);
        }
    }

    async function registration() {
        // sw.js main.js'te kaydedilir; yerelde (?sw=1 yoksa) hiç kaydedilmez, o zaman düğme gizli kalır
        // ilk ziyarette kayıt yeni başlıyor olabilir: hazır olmasını en fazla 6 sn bekle
        return Promise.race([navigator.serviceWorker.ready, new Promise(r => setTimeout(() => r(null), 6000))]);
    }

    async function toggle() {
        btn.disabled = true;
        say("");
        try {
            const reg = await registration();
            const sub = await reg.pushManager.getSubscription();
            if (sub) {
                await send("/api/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
                await sub.unsubscribe();
                setOn(false);
                say("Bildirimler kapatıldı.");
                return;
            }
            const perm = await Notification.requestPermission();
            if (perm !== "granted") {
                say("Bildirim izni verilmedi. Açmak için tarayıcının site ayarlarından izin ver.");
                return;
            }
            const fresh = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
            try {
                await send("/api/push/subscribe", fresh.toJSON());
            } catch (err) {
                await fresh.unsubscribe();
                throw err;
            }
            setOn(true);
            say("Tamam: Fenerbahçe maçı başlayınca, gol olunca ve maç bitince haber vereceğiz.");
        } catch (err) {
            say(`Bildirim açılamadı: ${err.message}`);
        } finally {
            btn.disabled = false;
        }
    }

    async function init() {
        if (!supported) {
            if (isIOS && !standalone) say("iPhone'da gol bildirimi için: Paylaş › Ana Ekrana Ekle, sonra siteyi ana ekrandan aç.");
            return;
        }
        try {
            const reg = await registration();
            if (!reg) return;
            const r = await fetch(`${API_BASE}/api/push/key`);
            const d = await r.json();
            if (!d.enabled || !d.key) return;
            key = d.key;
            const sub = await reg.pushManager.getSubscription();
            setOn(!!sub && Notification.permission === "granted");
            btn.hidden = false;
            btn.addEventListener("click", toggle);
        } catch (e) { /* bildirim yoksa site normal çalışır */ }
    }

    if (document.readyState === "complete") init();
    else window.addEventListener("load", init);
})();
