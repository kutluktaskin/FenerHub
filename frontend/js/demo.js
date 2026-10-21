/* Demo modu: ?demo=live ile geçmiş bir maçın gerçek canlı kaydı hızlandırılmış oynatılır.
   Kayıt (demo/*.json) backend/scripts/build_demo.py ile SportsAPI WebSocket kaydından üretilir
   ve sitenin kendi /ws/live mesaj biçimindedir; simülasyon onu canlı maçla aynı yoldan işler.
   ?hiz=60 ile hız değiştirilebilir (varsayılan 20 kat).
   Saf yardımcılar (dueEvents, shiftedPeriodStart) Node testleri için de dışa açılır. */
(function (root) {
    const DEMO_FILE = "demo/slavia-2026-10-20.json";
    const SPEEDS = [10, 20, 60];

    // (from, to] aralığına düşen olaylar; events sıralı [[saniye, mesaj], ...]
    function dueEvents(events, from, to) {
        return events.filter(([t]) => t > from && t <= to);
    }

    // liveMinute() dakikayı "şimdi - period_start" ile hesaplar. Demoda kaydın sanal saatine
    // göre doğru dakikayı vermesi için period_start gerçek saate kaydırılır.
    function shiftedPeriodStart(origPeriodStart, virtualEpoch, realEpoch) {
        if (origPeriodStart === null || origPeriodStart === undefined) return origPeriodStart;
        return Math.round(realEpoch - (virtualEpoch - origPeriodStart));
    }

    const api = { dueEvents, shiftedPeriodStart, SPEEDS };
    root.Demo = api;
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    if (typeof document === "undefined") return;

    const params = new URLSearchParams(location.search);
    if (params.get("demo") !== "live") return;

    let demo = null, vSec = 0, lastReal = 0, speed = Number(params.get("hiz")) || 20, timer = null;
    let origPeriodStart = null;

    function adjustedMatch(m) {
        origPeriodStart = m.period_start;
        return { ...m, period_start: shiftedPeriodStart(m.period_start, demo.meta.start + vSec, Date.now() / 1000) };
    }

    // Mesajlar /ws/live biçiminde; canlı maçtaki işleyişin aynısı (matchEngine.js onLiveMessage)
    function dispatch(msg) {
        if (msg.type === "state") {
            applyDetail(adjustedMatch(msg.match), msg.incidents, msg.statistics, msg.lineups);
        } else if (msg.kind === "match") {
            applyDetail(adjustedMatch(msg.data));
        } else if (msg.kind === "incidents") {
            applyIncidents(msg.data, feed.m);
            applyScoreboard(feed.m, msg.data);
        } else if (msg.kind === "statistics") {
            applyStats(msg.data);
            renderStatsTab(msg.data, feed.m);
        } else if (msg.kind === "lineups") {
            applyLineups(msg.data);
            renderLineupTab(msg.data, feed.m);
        }
    }

    function tick() {
        if (feed.id !== "demo") return stop();      // kullanıcı gerçek bir maçın simülasyonunu açtı
        const now = performance.now();
        const before = vSec;
        vSec = Math.min(demo.meta.duration, vSec + (now - lastReal) / 1000 * speed);
        lastReal = now;
        dueEvents(demo.events, before, vSec).forEach(([, msg]) => dispatch(msg));
        // Dakika sayacı sanal saate göre aksın
        if (feed.m && origPeriodStart) {
            feed.m.period_start = shiftedPeriodStart(origPeriodStart, demo.meta.start + vSec, Date.now() / 1000);
        }
        updateBar();
        if (vSec >= demo.meta.duration) stop();
    }

    function stop() {
        clearInterval(timer);
        timer = null;
        updateBar();
    }

    function restart() {
        stop();
        if (typeof simStartFeed === "function") simStartFeed(null, null);
        feed = newFeed("demo");
        feed.ws = true;              // REST sorgusu yapılmasın
        vSec = -0.001;
        lastReal = performance.now();
        dispatch(demo.events[0][1]);
        setStatus({ ic: "clock", text: "Demo: maç birazdan başlıyor…" });
        timer = setInterval(tick, 250);
    }

    function mmss(sec) {
        const s = Math.max(0, Math.round(sec));
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }

    function updateBar() {
        const bar = document.getElementById("demoBar");
        if (!bar || !demo) return;
        const left = (demo.meta.duration - vSec) / speed;
        bar.querySelector(".demo-fill").style.width = `${(vSec / demo.meta.duration) * 100}%`;
        bar.querySelector(".demo-left").textContent = timer ? `kalan ${mmss(left)}` : "bitti";
        bar.querySelectorAll("[data-speed]").forEach(b => b.setAttribute("aria-pressed", String(Number(b.dataset.speed) === speed)));
    }

    function buildBar() {
        const card = document.querySelector("#simulasyonWrapper .match-card") || document.getElementById("simulasyonWrapper");
        const d = demo.meta.date ? new Date(demo.meta.date + "T00:00:00") : null;
        const date = d ? `${d.getDate()} ${MONTHS_TR[d.getMonth()]} ${d.getFullYear()}` : "";
        const comp = (typeof COMPETITION_LABEL !== "undefined" && COMPETITION_LABEL[demo.meta.competition]) || "";
        card.insertAdjacentHTML("afterbegin", `<div class="demo-bar" id="demoBar">
            <span class="demo-badge">${icon("radio")}Demo</span>
            <span class="demo-info">${esc(date)} · ${esc(comp)} · gerçek canlı kayıt, ${"hızlandırılmış"}</span>
            <span class="demo-speed" role="group" aria-label="Oynatma hızı">${SPEEDS.map(s =>
                `<button type="button" data-speed="${s}" aria-pressed="false">×${s}</button>`).join("")}</span>
            <button type="button" class="demo-btn" data-act="restart">${icon("swap")}Baştan</button>
            <a class="demo-btn" href="./">${icon("x")}Çık</a>
            <span class="demo-track"><span class="demo-fill"></span></span>
            <span class="demo-left"></span>
        </div>`);
        const bar = document.getElementById("demoBar");
        bar.addEventListener("click", e => {
            const sp = e.target.closest("[data-speed]");
            if (sp) { speed = Number(sp.dataset.speed); updateBar(); }
            if (e.target.closest('[data-act="restart"]')) restart();
        });
    }

    async function start() {
        try {
            const res = await fetch(DEMO_FILE, { cache: "no-cache" });
            demo = await res.json();
        } catch (e) {
            console.warn("Demo kaydı yüklenemedi:", e);
            return;
        }
        const wrapper = document.getElementById("simulasyonWrapper");
        wrapper.classList.add("open", "is-demo");
        switchTab("pitchTab");
        buildBar();
        const league = document.getElementById("simLeagueName");
        if (league && typeof COMPETITION_LABEL !== "undefined") league.textContent = COMPETITION_LABEL[demo.meta.competition] || "";
        restart();
        // Maç kartları yüklenince sayfa yerleşimi değişir: simülasyona bir kez daha kay
        [120, 1500].forEach(ms => setTimeout(() => {
            resizePitch();
            if (typeof ScrollTrigger !== "undefined") ScrollTrigger.refresh();
            scrollToSection("simulasyonWrapper");
        }, ms));
    }

    // Diğer betikler (defer) yüklendikten sonra başla
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
})(typeof window !== "undefined" ? window : globalThis);
