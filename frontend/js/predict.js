/* Skor tahmin oyunu (12. Adam): açık maçlara tahmin, liderlik tablosu, maçın oyuncusu oylaması.
   Kimlik forumla ortak: cihazda saklanan anahtar (fhOwner) ve takma ad (fhNick). Hesap yok.
   API: /api/predict/open, /api/predict, /api/predict/leaderboard, /api/motm (backend/app/predictions.py) */
(function () {
    const box = document.getElementById("tahmin");
    if (!box) return;
    const $ = id => document.getElementById(id);
    const PCT = x => `%${Math.round((x || 0) * 100)}`;
    let scope = "season";

    function owner() {
        try {
            let t = localStorage.getItem("fhOwner");
            if (!t) {
                t = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
                localStorage.setItem("fhOwner", t);
            }
            return t;
        } catch (e) { return "anonim-" + Math.random().toString(36).slice(2, 10); }
    }
    const nick = () => { try { return localStorage.getItem("fhNick") || ""; } catch (e) { return ""; } };
    const setNick = v => { try { localStorage.setItem("fhNick", v); } catch (e) {} };

    async function post(path, body) {
        const r = await fetch(`${API_BASE}${path}`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        let d = null;
        try { d = await r.json(); } catch (e) {}
        if (!r.ok) throw new Error((d && typeof d.detail === "string") ? d.detail : `HTTP ${r.status}`);
        return d;
    }

    // ---------- Açık maçlar ----------
    function crowdBar(c, m) {
        if (!c || !c.count) return `<p class="pr-note">Henüz tahmin yok, ilk tahmini sen yap.</p>`;
        // Fenerbahçe payı her zaman sarı, rakibinki kırmızı (Fenerbahçe ev sahibi de deplasman da olabilir)
        const fbHome = m.home === "Fenerbahçe";
        return `<div class="pr-crowd" role="img" aria-label="${c.count} taraftar tahmini">
            <i class="${fbHome ? "pr-fb" : "pr-rv"}" style="flex:${c.home}"></i><i class="pr-d" style="flex:${c.draw}"></i><i class="${fbHome ? "pr-rv" : "pr-fb"}" style="flex:${c.away}"></i>
        </div>
        <p class="pr-note">${c.count} taraftar: ${esc(m.home)} ${PCT(c.home)} · beraberlik ${PCT(c.draw)} · ${esc(m.away)} ${PCT(c.away)}</p>`;
    }

    function stepper(side, val) {
        return `<span class="pr-step" data-side="${side}">
            <button type="button" data-d="-1" aria-label="Azalt">−</button>
            <input type="number" min="0" max="20" value="${val}" inputmode="numeric" aria-label="${side === "home" ? "Ev sahibi golü" : "Deplasman golü"}">
            <button type="button" data-d="1" aria-label="Artır">+</button>
        </span>`;
    }

    function matchCard(m) {
        const d = new Date(m.kickoff);
        const when = d.toLocaleString("tr-TR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
        const mine = m.mine || { home: 1, away: 1 };
        const mdl = m.model;
        return `<article class="pr-card" data-id="${m.match_id}">
            <p class="pr-when">${icon(m.competition === "uefa" ? "star" : "trophy")}${esc(COMPETITION_SHORT[m.competition] ?? "")} · ${esc(when)}</p>
            <div class="pr-teams">
                <span class="pr-team">${crest(m.home, "crest-sm")}<b>${esc(m.home)}</b></span>
                <span class="pr-team is-away"><b>${esc(m.away)}</b>${crest(m.away, "crest-sm")}</span>
            </div>
            <div class="pr-score">${stepper("home", mine.home)}<span class="pr-dash">–</span>${stepper("away", mine.away)}</div>
            <div class="pr-actions">
                <button type="button" class="btn btn-primary pr-save">${icon("check")}${m.mine ? "Tahmini güncelle" : "Tahmini kaydet"}</button>
                <span class="pr-msg" role="status">${m.mine ? `Tahminin: ${m.mine.home}-${m.mine.away} (maç başlayana kadar değiştirebilirsin)` : ""}</span>
            </div>
            <p class="pr-model">${icon("chart")}<span>İstatistik modeli: <b>${mdl.home}-${mdl.away}</b> · ${esc(m.home)} ${PCT(mdl.p_home)} · beraberlik ${PCT(mdl.p_draw)} · ${esc(m.away)} ${PCT(mdl.p_away)}</span></p>
            <div class="pr-crowd-wrap">${crowdBar(m.crowd, m)}</div>
        </article>`;
    }

    async function loadOpen() {
        const list = $("prOpen");
        try {
            const r = await fetch(`${API_BASE}/api/predict/open?owner=${encodeURIComponent(owner())}`);
            const matches = await r.json();
            if (typeof rememberTeams === "function") await logosReady;
            list.innerHTML = matches.length ? matches.slice(0, 3).map(matchCard).join("")
                : `<p class="empty-note">${icon("info")}Şu an tahmine açık maç yok.</p>`;
        } catch (e) {
            list.innerHTML = `<p class="empty-note">${icon("info")}Tahmin oyunu şu an yüklenemedi.</p>`;
        }
    }

    box.addEventListener("click", async e => {
        const step = e.target.closest(".pr-step button");
        if (step) {
            const input = step.parentElement.querySelector("input");
            input.value = Math.max(0, Math.min(20, (Number(input.value) || 0) + Number(step.dataset.d)));
            return;
        }
        const save = e.target.closest(".pr-save");
        if (save) {
            const card = save.closest(".pr-card");
            const msg = card.querySelector(".pr-msg");
            const val = side => Math.max(0, Math.min(20, Number(card.querySelector(`[data-side="${side}"] input`).value) || 0));
            let name = nick() || ($("prNick").value || "").trim();
            if (name.length < 2) {
                msg.textContent = "Önce bir takma ad yaz (en az 2 harf).";
                $("prNick").focus();
                return;
            }
            setNick(name);
            save.disabled = true;
            try {
                const d = await post("/api/predict", { match_id: Number(card.dataset.id), owner: owner(), nick: name, home: val("home"), away: val("away") });
                msg.textContent = `Kaydedildi: ${d.home}-${d.away}. Maç başlayana kadar değiştirebilirsin.`;
                save.lastChild.textContent = "Tahmini güncelle";
                const m = { home: card.querySelector(".pr-team b").textContent, away: card.querySelector(".pr-team.is-away b").textContent };
                card.querySelector(".pr-crowd-wrap").innerHTML = crowdBar(d.crowd, m);
                renderNick();
            } catch (err) {
                msg.textContent = err.message;
            } finally {
                save.disabled = false;
            }
            return;
        }
        const tab = e.target.closest("[data-scope]");
        if (tab) {
            scope = tab.dataset.scope;
            box.querySelectorAll("[data-scope]").forEach(b => b.setAttribute("aria-pressed", String(b === tab)));
            loadBoard();
            return;
        }
        const vote = e.target.closest(".pr-vote");
        if (vote && !vote.disabled) {
            try {
                await post("/api/motm", { match_id: Number(vote.dataset.match), owner: owner(), choice: vote.dataset.name });
                loadMotm();
            } catch (err) {
                $("prMotmMsg").textContent = err.message;
            }
        }
    });

    function renderNick() {
        const n = nick();
        $("prNickRow").hidden = !!n;
        $("prWho").textContent = n ? `Oyuncu: ${n}` : "";
    }

    // ---------- Liderlik tablosu ----------
    async function loadBoard() {
        const el = $("prBoard");
        try {
            const r = await fetch(`${API_BASE}/api/predict/leaderboard?scope=${scope}&owner=${encodeURIComponent(owner())}`);
            const b = await r.json();
            const rows = (b.top || []).map(p => `<tr class="${p.me ? "is-me" : ""}">
                <td>${p.rank}</td><td>${esc(p.nick)}${p.me ? " <small>(sen)</small>" : ""}</td>
                <td><b>${p.points}</b></td><td>${p.exact}</td><td>${p.played}</td></tr>`).join("");
            const meRow = b.me && !b.top.some(p => p.me)
                ? `<tr class="is-me"><td>${b.me.rank}</td><td>${esc(b.me.nick)} <small>(sen)</small></td><td><b>${b.me.points}</b></td><td>${b.me.exact}</td><td>${b.me.played}</td></tr>` : "";
            const vs = b.model ? `<div class="pr-vs">
                <span>${icon("users")}Taraftarlar: en iyi <b>${b.fans.best ?? "–"}</b>, ortalama <b>${b.fans.avg_points ?? "–"}</b> puan</span>
                <span>${icon("chart")}İstatistik modeli: <b>${b.model.points}</b> puan (${b.model.played} maç)</span>
            </div>` : "";
            el.innerHTML = rows || meRow ? `${vs}<div class="table-wrap"><table class="pr-table">
                <thead><tr><th>#</th><th>Takma ad</th><th>Puan</th><th title="Tam skor">Tam</th><th title="Puanlanan tahmin">Maç</th></tr></thead>
                <tbody>${rows}${meRow}</tbody></table></div>`
                : `<p class="empty-note">${icon("info")}${scope === "week" ? "Son 7 günde puanlanan maç yok." : "Puanlar ilk tahmin edilen maç bitince görünür."}</p>`;
        } catch (e) {
            el.innerHTML = `<p class="empty-note">${icon("info")}Tablo şu an yüklenemedi.</p>`;
        }
    }

    // ---------- Maçın oyuncusu ----------
    async function loadMotm() {
        const el = $("prMotm");
        try {
            const r = await fetch(`${API_BASE}/api/motm?owner=${encodeURIComponent(owner())}`);
            const d = await r.json();
            if (!d.open || !d.candidates.length) { el.hidden = true; return; }
            el.hidden = false;
            const closes = new Date(d.closes).toLocaleString("tr-TR", { weekday: "short", hour: "2-digit", minute: "2-digit" });
            const max = Math.max(1, ...d.candidates.map(c => c.votes));
            el.innerHTML = `<h3 class="pr-sub">${icon("star")}Maçın oyuncusu <small>${esc(d.home)} ${d.score[0]}-${d.score[1]} ${esc(d.away)} · oylama ${esc(closes)}'e kadar</small></h3>
                <p class="pr-note">${d.mine ? `Oyun: <b>${esc(d.mine)}</b>. ` : "Bir oyuncuya dokunarak oy ver. "}${d.total} oy · SportsAPI'nin seçimi: <b>${esc(d.api_best || "–")}</b></p>
                <div class="pr-motm">${d.candidates.map(c => `<button type="button" class="pr-vote${d.mine === c.name ? " is-mine" : ""}"
                    data-match="${d.match_id}" data-name="${esc(c.name)}" ${d.mine ? "disabled" : ""}>
                    <span class="pr-vname">${esc(c.name)}</span>
                    <span class="pr-vbar"><i style="width:${(c.votes / max) * 100}%"></i></span>
                    <span class="pr-vnum">${d.total ? PCT(c.votes / d.total) : "–"}</span>
                    <span class="pr-rating" title="SportsAPI puanı">${c.rating ? esc(c.rating) : "–"}</span>
                </button>`).join("")}</div>
                <p class="pr-note" id="prMotmMsg" role="status"></p>`;
        } catch (e) {
            el.hidden = true;
        }
    }

    $("prNick").addEventListener("change", e => { const v = e.target.value.trim(); if (v.length >= 2) { setNick(v); renderNick(); } });

    renderNick();
    loadOpen();
    loadBoard();
    loadMotm();
    setInterval(loadOpen, 2 * 60 * 1000);
    setInterval(() => { loadBoard(); loadMotm(); }, 5 * 60 * 1000);
})();
