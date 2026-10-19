const IS_LOCAL = ["127.0.0.1", "localhost"].includes(location.hostname);
// Yollar zaten "/api/..." ile başlıyor; buraya "/api" ekleme (çift /api/api olur).
const API_BASE = IS_LOCAL ? "http://127.0.0.1:8000" : "https://fenerhub.onrender.com";

// Yükleme başarısız olursa iskeletin yerine kısa bir not koyar (önceki veri varsa dokunmaz)
function showLoadError(container, colspan) {
    if (!container || !container.querySelector(".skel")) return;
    const msg = `${icon("info")}Veri şu an alınamadı, birazdan tekrar denenecek.`;
    container.innerHTML = colspan
        ? `<tr class="empty-row"><td colspan="${colspan}">${msg}</td></tr>`
        : `<p class="empty-note">${msg}</p>`;
}

async function apiGet(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`API hatası: ${res.status}`);
    return res.json();
}

// ---------- Puan Durumu ----------
// Sıra bölgeleri: lig kuralı değişirse burayı güncelle.
// from/to sıra numarası; last: sondan kaç takım (takım sayısına göre hesaplanır).
// Renkler style.css'teki --z-* token'ları: ŞL sarı, Avrupa açık lacivert/beyaz, küme düşme kırmızı.
// Fenerbahçe satırı sarı olduğu için orada şerit lacivert çizilir (küme düşme hariç).
const ZONES = {
    super_lig: [
        { from: 1, to: 1, color: "var(--z-ucl)",   label: "Şampiyonlar Ligi" },
        { from: 2, to: 2, color: "var(--z-ucl-q)", label: "Şampiyonlar Ligi elemeleri" },
        { from: 3, to: 3, color: "var(--z-uel)",   label: "Avrupa Ligi" },
        { from: 4, to: 4, color: "var(--z-uecl)",  label: "Konferans Ligi elemeleri" },
        { last: 3,        color: "var(--z-rel)",   label: "Küme düşme" },
    ],
    uefa: [
        { from: 1, to: 8,  color: "var(--z-ucl)", label: "Son 16 turu" },
        { from: 9, to: 24, color: "var(--z-uel)", label: "Play-off turu" },
    ],
};

function zoneOf(comp, pos, total) {
    return (ZONES[comp] || []).find(z =>
        z.last ? pos > total - z.last : pos >= z.from && pos <= z.to);
}

function renderZoneLegend(comp) {
    const ul = document.querySelector(`.zone-legend[data-comp="${comp}"]`);
    if (!ul || ul.childElementCount) return;
    ul.innerHTML = (ZONES[comp] || []).map(z =>
        `<li><i style="--zone:${z.color}"></i>${esc(z.label)}</li>`).join("");
}

// Fenerbahçe satırını tablonun ortasına getirir (sadece ilk yüklemede; kullanıcının kaydırmasını bozmaz)
function scrollToFbRow(tbodyEl) {
    const box = tbodyEl.closest(".table-scroll-container");
    const row = tbodyEl.querySelector(".fb-row");
    if (!box || !row || box.dataset.autoScrolled) return;
    box.dataset.autoScrolled = "1";
    const offset = row.getBoundingClientRect().top - box.getBoundingClientRect().top;
    box.scrollTop += offset - box.clientHeight / 2 + row.offsetHeight / 2;
}

function renderStandings(tbodyEl, rows, comp) {
    if (!rows || rows.length === 0) {
        tbodyEl.innerHTML = `<tr class="empty-row"><td colspan="8">${icon("info")}Puan durumu henüz yayımlanmadı.</td></tr>`;
        return;
    }
    tbodyEl.innerHTML = rows.map(r => {
        const gd = r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference;
        const zone = zoneOf(comp, r.position, rows.length);
        const fb = r.is_fenerbahce;
        // Sarı Fenerbahçe satırında sarı/beyaz şerit görünmez: küme düşme dışında lacivert çizilir
        const stripe = zone && (fb && !zone.last ? "var(--c-accent-ink)" : zone.color);
        return `<tr class="${fb ? "fb-row" : ""}"${zone ? ` style="--zone:${stripe}"` : ""}>
            <td class="pos"${zone ? ` title="${esc(zone.label)}"` : ""}>${r.position}</td>
            <td class="team"><span class="team-cell">${fb ? crest("Fenerbahçe", "crest-xs") : ""}<span>${esc(r.team)}</span></span></td>
            <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
            <td class="gd">${gd}</td><td class="pts">${r.points}</td>
        </tr>`;
    }).join("");
    renderZoneLegend(comp);
    scrollToFbRow(tbodyEl);
}

async function loadStandings() {
    const tables = document.querySelectorAll("#puanlar .standings-table");
    const body = comp => document.querySelector(`#puanlar .standings-table[data-comp="${comp}"] tbody`);

    try {
        const [sl, eu] = await Promise.all([
            apiGet("/api/standings/super_lig"),
            apiGet("/api/standings/uefa"),
        ]);

        if (body("super_lig")) renderStandings(body("super_lig"), sl, "super_lig");
        if (body("uefa")) renderStandings(body("uefa"), eu, "uefa");

        console.log("Puan durumu API'den yüklendi");
    } catch (err) {
        console.error("Puan durumu yüklenemedi:", err);
        tables.forEach(t => showLoadError(t.tBodies[0], 8));
    }
}

// ---------- Kadro ----------
const STATUS_VIEW = {
    available: { text: "Hazır",  ic: "check",  cls: "st-ok" },
    injured:   { text: "Sakat",  ic: "injury", cls: "st-injured" },
    suspended: { text: "Cezalı", ic: "card",   cls: "st-suspended" },
};
const POSITION_TR = { G: "Kaleci", D: "Defans", M: "Orta Saha", F: "Forvet" };
const POSITION_ORDER = { G: 0, D: 1, M: 2, F: 3 };

// Filtre ve sıralama durumu; veri her yenilemede korunur
const squadState = { players: null, pos: "all", sort: null, dir: "desc" };

function initials(name) {
    const w = name.split(/\s+/).filter(Boolean);
    return ((w[0]?.[0] || "") + (w.length > 1 ? w[w.length - 1][0] : "")).toLocaleUpperCase("tr");
}

function playerAvatar(p) {
    const num = p.shirt_number ?? null;
    return `<span class="avatar" aria-hidden="true">${esc(initials(p.name))}` +
        (num !== null ? `<b class="avatar-num">${esc(num)}</b>` : "") + `</span>`;
}

// Sakat/cezalı rozeti: üzerine gelince ya da odaklanınca sebep ve dönüş tarihi görünür
function statusCell(p) {
    const s = STATUS_VIEW[p.status];
    if (!s || p.status === "available") {
        return `<span class="status st-ok">${icon("check")}<span class="status-text">Hazır</span></span>`;
    }
    const detail = [p.status_reason, p.return_note ? `Dönüş: ${p.return_note}` : null]
        .filter(Boolean).join(" · ") || "Ayrıntı bilinmiyor";
    const tid = `sq-tip-${p.id}`;
    return `<span class="tip-wrap">
        <button type="button" class="status status-tip ${s.cls}" aria-describedby="${tid}">${icon(s.ic)}<span class="status-text">${s.text}</span></button>
        <span class="tip" role="tooltip" id="${tid}">${esc(detail)}</span>
    </span>`;
}

function sortedSquad() {
    const { players, pos, sort, dir } = squadState;
    const list = players.filter(p => pos === "all" || p.position === pos);
    const byName = (a, b) => a.name.localeCompare(b.name, "tr");
    // Varsayılan: mevki sırası (kaleci → forvet), sonra forma numarası
    const byDefault = (a, b) =>
        (POSITION_ORDER[a.position] ?? 9) - (POSITION_ORDER[b.position] ?? 9) ||
        (a.shirt_number ?? 999) - (b.shirt_number ?? 999) || byName(a, b);
    return list.sort(sort
        ? (a, b) => (dir === "desc" ? b[sort] - a[sort] : a[sort] - b[sort]) || byName(a, b)
        : byDefault);
}

function renderSquad() {
    const tbody = document.querySelector(".player-stats-table tbody");
    if (!tbody || !squadState.players) return;
    const rows = sortedSquad();
    // Rozetler: maç beyaz-lacivert, gol dolu sarı, asist sarı çerçeve; sıfırlar soluk
    const badge = (v, kind) => `<span class="stat-badge stat-${kind}${v ? "" : " is-zero"}">${v}</span>`;

    tbody.innerHTML = rows.map(p => {
        const out = p.status === "injured" || p.status === "suspended";
        const pos = POSITION_TR[p.position] ?? p.position ?? "-";
        return `<tr class="${out ? "is-out" : ""}">
            <td><div class="player-cell">${playerAvatar(p)}
                <div class="player-id"><strong>${esc(p.name)}</strong><span class="player-pos-sm">${esc(pos)}</span></div>
            </div></td>
            <td class="col-pos">${esc(pos)}</td>
            <td class="num">${badge(p.appearances, "match")}</td>
            <td class="num">${badge(p.goals, "goal")}</td>
            <td class="num">${badge(p.assists, "assist")}</td>
            <td class="col-status">${statusCell(p)}</td>
        </tr>`;
    }).join("") || `<tr class="empty-row"><td colspan="6">Bu mevkide oyuncu yok.</td></tr>`;

    document.querySelectorAll(".player-stats-table th[data-sort]").forEach(th => {
        const on = th.dataset.sort === squadState.sort;
        th.setAttribute("aria-sort", on ? (squadState.dir === "desc" ? "descending" : "ascending") : "none");
        th.querySelector(".sort-ico use").setAttribute("href",
            on ? (squadState.dir === "desc" ? "#i-sort-down" : "#i-sort-up") : "#i-sort");
    });
    const count = document.getElementById("squadCount");
    if (count) count.textContent = `${rows.length} oyuncu`;
}

function initSquadControls() {
    document.querySelectorAll(".squad-filter [data-pos]").forEach(btn => {
        btn.addEventListener("click", () => {
            squadState.pos = btn.dataset.pos;
            document.querySelectorAll(".squad-filter [data-pos]")
                .forEach(b => b.setAttribute("aria-pressed", String(b === btn)));
            renderSquad();
        });
    });
    // Başlığa basınca: çoktan aza → azdan çoka → varsayılan sıra
    document.querySelectorAll(".player-stats-table th[data-sort] .sort-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const key = btn.closest("th").dataset.sort;
            if (squadState.sort !== key) Object.assign(squadState, { sort: key, dir: "desc" });
            else if (squadState.dir === "desc") squadState.dir = "asc";
            else squadState.sort = null;
            renderSquad();
        });
    });
}

async function loadSquad() {
    const tbody = document.querySelector(".player-stats-table tbody");
    if (!tbody) return;
    try {
        squadState.players = await apiGet("/api/squad");
        renderSquad();
        console.log("Kadro API'den yüklendi");
    } catch (err) {
        console.warn("Kadro API'sine ulaşılamadı:", err);
        showLoadError(tbody, 6);
    }
}

// ---------- Sakatlık & Ceza Raporu ----------
function renderAbsences(container, rows) {
    container.innerHTML = rows.map(a => {
        const suspended = a.type === "suspension";
        const detail = [a.reason, a.return_note ? `Dönüş: ${a.return_note}` : null]
            .filter(Boolean).join(" • ");
        const pos = a.position ? ` (${a.position})` : "";
        return `<div class="injury-report-card ${suspended ? "suspended-card" : ""}">
            <div>
                <div class="ir-name">${esc(a.player + pos)}</div>
                <div class="ir-stats">${a.appearances} Maç • ${a.goals} Gol • ${a.assists} Asist</div>
                <div class="ir-detail">${esc(detail)}</div>
            </div>
            <span class="status-tag ${suspended ? "tag-suspended" : "tag-injured"}">${suspended ? icon("card") + "Cezalı" : icon("injury") + "Sakat"}</span>
        </div>`;
    }).join("") || `<p class="empty-note">${icon("check-circle")}Sakat ya da cezalı oyuncu yok.</p>`;
}

async function loadAbsences() {
    const container = document.querySelector(".injury-report-list");
    if (!container) return;
    try {
        renderAbsences(container, await apiGet("/api/absences"));
        console.log("Sakatlık raporu API'den yüklendi");
    } catch (err) {
        console.warn("Sakatlık API'sine ulaşılamadı:", err);
        showLoadError(container);
    }
}

// ---------- Yakın Maç Kartları ----------
const ABSENCE_TAG = {
    injury:     { cls: "tag-injured",   ic: "injury", text: "Sakat" },
    suspension: { cls: "tag-suspended", ic: "card",   text: "Cezalı" },
};
const DAYS_TR = ["Paz", "Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"];
const DAYS_LONG_TR = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"];
const MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const MATCH_KEYS = ["alanya", "slavia", "gs"];
const COMPETITION_LABEL = {
    super_lig: "Trendyol Süper Lig",
    uefa: "UEFA Şampiyonlar Ligi",
};
const COMPETITION_SHORT = { super_lig: "Süper Lig", uefa: "Şampiyonlar Ligi" };
const DERBY_RIVALS = ["Galatasaray", "Beşiktaş JK", "Trabzonspor"];
const HOME_STADIUM = "Chobani Stadyumu";   // API stat bilgisi vermiyor; deplasmanda "Deplasman" yazılır

// API logo vermiyor: rakipler kısaltma + kulüp renkleriyle rozet olarak çizilir
const TEAM_BADGE = {
    "Galatasaray":   ["GS",  "#a90432", "#fdb912"],
    "Beşiktaş JK":   ["BJK", "#161616", "#ffffff"],
    "Trabzonspor":   ["TS",  "#6c1d45", "#7cc3ed"],
    "Başakşehir FK": ["İBFK", "#16285b", "#f47920"],
    "Göztepe":       ["GÖZ", "#c8102e", "#ffd100"],
    "Slavia Prag":   ["SLA", "#c8102e", "#ffffff"],
};
const NAME_SUFFIXES = new Set(["FK", "SK", "JK", "FC", "AŞ", "A.Ş.", "SC", "CF", "AFC", "KF"]);

const pad2 = n => String(n).padStart(2, "0");

function localISODate(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function rivalOf(m) {
    return m.home === "Fenerbahçe" ? m.away : m.home;
}

function monogram(name) {
    const up = t => t.toLocaleUpperCase("tr");
    const words = name.split(/\s+/).filter(w => w && !NAME_SUFFIXES.has(up(w)));
    if (words.length >= 2) return up(words[0][0] + words[1][0]);
    return up((words[0] || name).slice(0, 3));
}

function crest(name, size = "") {
    if (name === "Fenerbahçe") {
        return `<img class="crest ${size}" src="img/fenerbahce-logo.png" alt="" loading="lazy">`;
    }
    // Kulüp renkleri veri olduğu için sabit; bilinmeyen rakip tema token'larıyla çizilir
    const [code, bg, fg] = TEAM_BADGE[name] || [monogram(name), "var(--c-navy-600)", "var(--c-text-2)"];
    return `<span class="crest crest-mono ${size}${code.length > 2 ? " is-long" : ""}" style="--crest-bg:${bg};--crest-fg:${fg}" aria-hidden="true">${esc(code)}</span>`;
}

function liveMinute(m) {
    if (m.status_code === 31) return "Devre Arası";
    if (!m.period_start || (m.status_code !== 6 && m.status_code !== 7)) return null;
    const secs = Math.floor(Date.now() / 1000) - m.period_start + (m.period_initial || 0);
    const min = Math.floor(secs / 60) + 1;
    const cap = m.status_code === 6 ? 45 : 90;
    return min > cap ? `${cap}+${min - cap}'` : `${min}'`;
}

function kickoffDate(m) {
    if (!m.match_date) return null;
    return new Date(`${m.match_date}T${(m.kickoff_time || "00:00").slice(0, 5)}:00+03:00`);
}

function longDate(m) {
    if (!m.match_date) return "Tarih belli değil";
    const d = new Date(m.match_date + "T00:00:00");
    return `${DAYS_LONG_TR[d.getDay()]}, ${d.getDate()} ${MONTHS_TR[d.getMonth()]}` + (m.kickoff_time ? ` · ${m.kickoff_time}` : "");
}

function shortDate(m) {
    if (!m.match_date) return "Tarih belli değil";
    const d = new Date(m.match_date + "T00:00:00");
    return `${DAYS_TR[d.getDay()]} ${d.getDate()} ${MONTHS_TR[d.getMonth()]}` + (m.kickoff_time ? ` · ${m.kickoff_time}` : "");
}

function badgeInfo(m) {
    if (m.status === "live") {
        const mn = liveMinute(m);
        return { cls: "badge-live", ic: "radio", text: `Canlı${mn ? " · " + mn : ""}`, special: true };
    }
    if (m.match_date === localISODate(new Date())) {
        return { cls: "badge-today", ic: "clock", text: "Bugün", special: true };
    }
    if (DERBY_RIVALS.includes(rivalOf(m))) {
        return { cls: "badge-derby", ic: "flame", text: "Derbi", special: true };
    }
    return { cls: "badge-upcoming", ic: "calendar", text: "Sıradaki maç", special: false };
}

// Gün / saat / dakika geri sayımı (sadece hero kartta)
function countdownHTML(m) {
    const k = kickoffDate(m);
    const diff = k ? k - Date.now() : 0;
    if (diff <= 0) return `<div class="mc-count is-soon">Maç başlıyor</div>`;
    const s = Math.floor(diff / 1000);
    const parts = [[Math.floor(s / 86400), "gün"], [Math.floor((s % 86400) / 3600), "saat"], [Math.floor((s % 3600) / 60), "dk"]];
    return `<div class="mc-count" role="timer" aria-label="Maça kalan süre">` +
        parts.map(([v, u]) => `<span class="mc-unit"><b>${pad2(v)}</b><i>${u}</i></span>`).join('<span class="mc-sep" aria-hidden="true">:</span>') +
        `</div>`;
}

function renderAbsenceItem(a) {
    if (a.type === "returned") {
        return `<div class="matchday-missing-item">
            <div class="missing-player-info">
                <span class="missing-player-name">${esc(a.player)}</span>
                <span class="missing-player-stats">${esc(a.reason ?? "")}</span>
            </div>
            <span class="status-tag tag-ok">${icon("check")}Kadroda</span>
        </div>`;
    }
    const tag = ABSENCE_TAG[a.type] || ABSENCE_TAG.injury;
    return `<div class="matchday-missing-item">
        <div class="missing-player-info">
            <span class="missing-player-name">${esc(a.player)}</span>
            <span class="missing-player-stats">${esc(a.reason ?? "")}</span>
        </div>
        <span class="status-tag ${tag.cls}">${icon(tag.ic)}${tag.text}</span>
    </div>`;
}

// Maç günü eksikleri; yoksa sade bir "Tam kadro" notu.
// compact: küçük kartlarda tek satırlık özet (tam liste title'da)
function absencesHTML(m, compact) {
    const items = m.absences || [];
    const missing = items.filter(a => a.type !== "returned");
    if (!missing.length && (compact || !items.length)) {
        return `<p class="mc-full">${icon("check-circle")}Tam kadro</p>`;
    }
    if (compact) {
        const names = missing.map(a => a.player);
        const shown = names.slice(0, 2).join(", ") + (names.length > 2 ? ` +${names.length - 2}` : "");
        const all = missing.map(a => `${a.player}${a.reason ? " (" + a.reason + ")" : ""}`).join(", ");
        return `<p class="mc-absent" title="${esc(all)}">${icon("injury")}<b>${missing.length} eksik</b><span>${esc(shown)}</span></p>`;
    }
    return `<div class="matchday-missing-box">
        <div class="matchday-missing-title"><span>Maç günü eksikleri</span><span>${m.absence_count ?? missing.length}</span></div>
        ${items.map(renderAbsenceItem).join("")}
    </div>`;
}

function renderMatchCard(card, m, key) {
    const hero = card.classList.contains("is-hero");
    const live = m.status === "live";
    const hasScore = m.home_score !== null && m.home_score !== undefined;
    const fbHome = m.home === "Fenerbahçe";
    const st = badgeInfo(m);
    const label = live ? "Canlı simülasyonu izle" : "2D simülasyonu aç";

    card.classList.remove("is-loading");
    card.removeAttribute("aria-busy");
    card.classList.toggle("is-live", live);
    card.setAttribute("aria-label", `${m.home} - ${m.away}, ${COMPETITION_LABEL[m.competition] ?? ""}`);

    const top = `<div class="mc-top">
        <span class="comp-badge">${icon(m.competition === "uefa" ? "star" : "trophy")}${esc(COMPETITION_SHORT[m.competition] ?? "")}</span>
        ${hero || st.special ? `<span class="match-badge ${st.cls}">${icon(st.ic)}${esc(st.text)}</span>` : ""}
    </div>`;

    if (hero) {
        let mid;
        if (live || (m.status === "finished" && hasScore)) {
            mid = `<div class="mc-score${live ? " is-live" : ""}"><b>${m.home_score ?? 0}</b><span>-</span><b>${m.away_score ?? 0}</b></div>
                <div class="mc-state">${live ? `<span class="live-pulse"></span><span class="mc-live-min">${esc(liveMinute(m) ?? "Canlı")}</span>` : "Maç sonu"}</div>`;
        } else {
            mid = countdownHTML(m) + `<div class="mc-state">${esc(longDate(m))}</div>`;
        }
        card.innerHTML = top + `
            <div class="mc-board">
                <div class="mc-team">${crest(m.home, "crest-lg")}<span class="mc-name">${esc(m.home)}</span></div>
                <div class="mc-mid">${mid}</div>
                <div class="mc-team">${crest(m.away, "crest-lg")}<span class="mc-name">${esc(m.away)}</span></div>
            </div>
            <p class="mc-meta">${icon(fbHome ? "home" : "plane")}${fbHome ? HOME_STADIUM : "Deplasman"}</p>
            ${absencesHTML(m)}
            <button type="button" class="btn btn-primary open-sim-btn" onclick="openSimulation('${key}')">${icon("zap")}${label}</button>`;
        return;
    }

    const row = (team, score) => `<div class="mc-row${team === "Fenerbahçe" ? " is-fb" : ""}">
        ${crest(team, "crest-sm")}<span class="mc-name">${esc(team)}</span>
        ${hasScore ? `<b class="mc-row-score${live ? " is-live" : ""}">${score}</b>` : ""}
    </div>`;
    card.innerHTML = top + `
        <div class="mc-rows">${row(m.home, m.home_score)}${row(m.away, m.away_score)}</div>
        <p class="mc-meta">${icon("calendar")}${esc(shortDate(m))}<span aria-hidden="true">·</span>${fbHome ? "İç saha" : "Deplasman"}</p>
        ${absencesHTML(m, true)}
        <button type="button" class="btn open-sim-btn" onclick="openSimulation('${key}')">${icon("zap")}${label}</button>`;
}

// Hero karttaki sayaç ve canlı dakika her saniye güncellenir (tüm kart yeniden çizilmez)
function tickHeroCard() {
    const card = document.querySelector(".recent-match-card.is-hero");
    const m = navMatch;
    if (!card || !m) return;
    if (m.status === "live") {
        const el = card.querySelector(".mc-live-min");
        if (el) el.textContent = liveMinute(m) ?? "Canlı";
        return;
    }
    const count = card.querySelector(".mc-count");
    if (!count) return;
    const html = countdownHTML(m);
    if (count.outerHTML !== html) count.outerHTML = html;
}

function syncMatchMeta(m, key) {
    // main.js içindeki matchMeta'nın üzerine API verisini yazar (simülasyon için)
    if (typeof matchMeta === "undefined") return;
    const live = m.status === "live";
    matchMeta[key] = {
        id: m.id,
        home: m.home.toUpperCase(),
        away: m.away.toUpperCase(),
        score: m.home_score === null ? "v" : `${m.home_score} - ${m.away_score}`,
        minute: live ? (liveMinute(m) ?? "Canlı") : "Ön İzleme",
        league: COMPETITION_LABEL[m.competition] ?? matchMeta[key]?.league,
    };
}

// ---------- Menüdeki "Sıradaki maç" kutusu ----------
let navMatch = null;
let finishedMatch = null;   // biten maçın final skoru geçici olarak gösterilir

function renderNavNext() {
    const el = document.getElementById("navNext");
    if (!el) return;
    const m = navMatch;

    // Maç yeni bittiyse 10 dakika final skorunu göster
    if (finishedMatch && Date.now() < finishedMatch.until && !(m && m.status === "live")) {
        const f = finishedMatch.m;
        el.style.display = "";
        el.classList.add("is-live");
        el.innerHTML = `<span class="nn-label">${icon("flag")}MS</span>
            <span class="nn-live">${esc(f.home)} ${f.home_score ?? 0} - ${f.away_score ?? 0} ${esc(f.away)}</span>`;
        return;
    }

    if (!m) { el.style.display = "none"; return; }
    el.style.display = "";

    if (m.status === "live") {
        const mn = liveMinute(m);
        el.classList.add("is-live");
        el.innerHTML = `<span class="nn-label">${icon("radio")}CANLI${mn ? " " + mn : ""}</span>
            <span class="nn-live">${esc(m.home)} ${m.home_score ?? 0} - ${m.away_score ?? 0} ${esc(m.away)}</span>`;
        return;
    }
    el.classList.remove("is-live");

    const time = (m.kickoff_time || "00:00").slice(0, 5);
    const diff = new Date(`${m.match_date}T${time}:00+03:00`) - new Date();
    if (diff <= 0) {
        el.innerHTML = `<span class="nn-label">${esc(rivalOf(m))}</span><span class="nn-live">Maç başlıyor</span>`;
        return;
    }

    const s = Math.floor(diff / 1000);
    const parts = [
        [Math.floor(s / 86400), "gün"],
        [Math.floor((s % 86400) / 3600), "saat"],
        [Math.floor((s % 3600) / 60), "dk"],
        [s % 60, "sn"],
    ];
    el.innerHTML = `<span class="nn-label">${esc(rivalOf(m))}</span>` +
        parts.map(([v, u]) =>
            `<span class="nn-box"><b>${String(v).padStart(2, "0")}</b><i>${u}</i></span>`
        ).join("");
}

async function loadUpcomingMatches() {
    const cards = document.querySelectorAll(".recent-match-card");
    if (!cards.length) return;
    try {
        const matches = await apiGet("/api/matches/upcoming");

        const prev = navMatch;
        const next = matches[0] || null;
        // Canlı maç bitti: final skoru çekip 10 dk göster
        if (prev && prev.status === "live" && (!next || next.id !== prev.id)) {
            try {
                const fin = await apiGet(`/api/matches/${prev.id}`);
                finishedMatch = { m: fin, until: Date.now() + 10 * 60 * 1000 };
            } catch (e) { /* final skoru alınamazsa geçilir */ }
        }
        navMatch = next;
        renderNavNext();

        cards.forEach((card, i) => {
            const m = matches[i];
            card.hidden = !m;
            if (!m) return;
            renderMatchCard(card, m, MATCH_KEYS[i]);
            if (MATCH_KEYS[i]) syncMatchMeta(m, MATCH_KEYS[i]);
        });
        console.log("Yakın maçlar API'den yüklendi");
    } catch (err) {
        console.warn("Maç API'sine ulaşılamadı:", err);
        const hero = document.querySelector(".recent-match-card.is-hero.is-loading");
        if (hero) hero.innerHTML = `<p class="empty-note">${icon("info")}Maç bilgisi şu an alınamadı, birazdan tekrar denenecek.</p>`;
    }
}

// ---------- Fikstür ----------
const RESULT = {
    win:  { letter: "G", label: "Galibiyet" },
    draw: { letter: "B", label: "Beraberlik" },
    loss: { letter: "M", label: "Mağlubiyet" },
};

function resultOf(m) {
    const fbHome = m.home === "Fenerbahçe";
    const fb = fbHome ? m.home_score : m.away_score;
    const opp = fbHome ? m.away_score : m.home_score;
    return fb > opp ? "win" : fb < opp ? "loss" : "draw";
}

function fixtureCard(m, isNext) {
    const hasScore = m.home_score !== null && m.home_score !== undefined;
    const live = m.status === "live";
    const done = m.status === "finished" && hasScore;
    const fbHome = m.home === "Fenerbahçe";
    const rival = rivalOf(m);
    const d = m.match_date ? new Date(m.match_date + "T00:00:00") : null;

    let cls = "fx-card", right;
    if (live) {
        cls += " is-live";
        right = `<span class="fx-live"><span class="live-pulse"></span>${esc(liveMinute(m) ?? "Canlı")}</span>
            <b class="fx-score">${m.home_score ?? 0} - ${m.away_score ?? 0}</b>`;
    } else if (done) {
        const res = resultOf(m);
        cls += ` is-played ${res}`;
        right = `<span class="res-badge ${res}" title="${RESULT[res].label}">${RESULT[res].letter}</span>
            <b class="fx-score">${m.home_score} - ${m.away_score}</b>`;
    } else {
        cls += " is-upcoming" + (isNext ? " is-next" : "");
        right = `<b class="fx-time">${esc(m.kickoff_time ?? "--:--")}</b>${isNext ? `<span class="fx-next">Sıradaki</span>` : ""}`;
    }

    const label = `${m.home} - ${m.away}, ${d ? longDate(m) : "tarih belli değil"}`;
    return `<article class="${cls}" aria-label="${esc(label)}"${isNext ? ' aria-current="true"' : ""}>
        <div class="fx-date">${d ? `<b>${d.getDate()}</b><span>${DAYS_TR[d.getDay()]}</span>` : "<b>–</b>"}</div>
        <div class="fx-body">
            <div class="fx-opp">${crest(rival, "crest-sm")}<span>${esc(rival)}</span></div>
            <div class="fx-tags">
                <span class="fx-comp">${icon(m.competition === "uefa" ? "star" : "trophy")}${esc(COMPETITION_SHORT[m.competition] ?? "")}</span>
                <span class="fx-venue">${icon(fbHome ? "home" : "plane")}${fbHome ? "İç saha" : "Deplasman"}</span>
            </div>
        </div>
        <div class="fx-right">${right}</div>
    </article>`;
}

function renderFixtures(container, matches) {
    // Tarihe göre sırala; tarihi belli olmayanlar sona
    const list = [...matches].sort((a, b) =>
        (a.match_date || "9999").localeCompare(b.match_date || "9999") ||
        (a.kickoff_time || "").localeCompare(b.kickoff_time || ""));
    const next = list.find(m => m.status !== "finished");

    // Aylara göre grupla
    const groups = new Map();
    list.forEach(m => {
        const key = m.match_date ? m.match_date.slice(0, 7) : "tbd";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(m);
    });
    const monthTitle = key => {
        if (key === "tbd") return "Tarihi belli olmayanlar";
        const [y, mo] = key.split("-").map(Number);
        return `${MONTHS_TR[mo - 1]} ${y}`;
    };

    container.innerHTML = [...groups].map(([key, ms]) => `<section class="fx-month" aria-label="${monthTitle(key)}">
        <h3 class="fx-month-title">${monthTitle(key)}<span>${ms.length} maç</span></h3>
        <div class="fx-list">${ms.map(m => fixtureCard(m, m === next)).join("")}</div>
    </section>`).join("");

    // Sezon özeti: oynanan maçların G/B/M dağılımı
    const played = list.filter(m => m.status === "finished" && m.home_score !== null);
    const count = r => played.filter(m => resultOf(m) === r).length;
    const summary = document.getElementById("fxSummary");
    if (summary && played.length) {
        summary.innerHTML = `${played.length} maç oynandı
            <span class="res-badge win">${count("win")}G</span>
            <span class="res-badge draw">${count("draw")}B</span>
            <span class="res-badge loss">${count("loss")}M</span>`;
    }

    // İlk yüklemede liste sıradaki maça kayar (sayfa kaydırılmaz)
    const nextCard = container.querySelector(".fx-card.is-next, .fx-card.is-live");
    if (nextCard && !container.dataset.autoScrolled) {
        container.dataset.autoScrolled = "1";
        const header = nextCard.closest(".fx-month").querySelector(".fx-month-title");
        container.scrollTop += nextCard.getBoundingClientRect().top - container.getBoundingClientRect().top
            - header.offsetHeight - 12;
    }
}

async function loadFixtures() {
    const container = document.querySelector(".fixtures-grid");
    if (!container) return;
    try {
        renderFixtures(container, await apiGet("/api/matches"));
        console.log("Fikstür API'den yüklendi");
    } catch (err) {
        console.warn("Fikstür API'sine ulaşılamadı:", err);
        showLoadError(container);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    setInterval(() => { renderNavNext(); tickHeroCard(); }, 1000);
    loadStandings();
    initSquadControls();
    loadSquad();
    loadAbsences();
    loadUpcomingMatches();
    loadFixtures();
    setInterval(loadUpcomingMatches, 60 * 1000);   // kartlar dakikada bir
    setInterval(loadFixtures, 5 * 60 * 1000);      // fikstür 5 dakikada bir
    setInterval(loadStandings, 5 * 60 * 1000);
    setInterval(loadSquad, 10 * 60 * 1000);
    setInterval(loadAbsences, 10 * 60 * 1000);
});