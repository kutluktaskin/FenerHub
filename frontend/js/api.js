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

    // Başlıktaki "i" butonunun popover'ı: bölgeler + kısaltmalar
    const pop = document.querySelector(`.zone-pop[data-comp="${comp}"]`);
    if (pop) {
        pop.innerHTML = `<b>Sıra renkleri</b>
            <ul class="zone-legend">${ul.innerHTML}</ul>
            <b>Kısaltmalar</b>
            <p>O oynanan · G galibiyet · B beraberlik · M mağlubiyet · AV averaj · P puan</p>`;
    }
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
            <td class="gd">${gd}</td><td class="pts"${fb && !tbodyEl.dataset.counted ? ` data-count="${r.points}"` : ""}>${r.points}</td>
        </tr>`;
    }).join("");
    renderZoneLegend(comp);
    scrollToFbRow(tbodyEl);
    // Fenerbahçe'nin puanı ilk görünüşte sayarak gelir (yenilemelerde doğrudan yazılır)
    if (window.fx && !tbodyEl.dataset.counted) { fx.observeCounts(tbodyEl); tbodyEl.dataset.counted = "1"; }
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
        <button type="button" class="status status-tip ${s.cls}" popovertarget="${tid}" data-hover aria-describedby="${tid}">${icon(s.ic)}<span class="status-text">${s.text}</span></button>
        <span class="tip fx-pop" popover id="${tid}" role="tooltip"><b>${esc(p.name)}</b>${esc(detail)}</span>
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
        return `<tr class="${out ? "is-out" : ""}" data-pos="${esc(p.position ?? "")}">
            <td><div class="player-cell">${playerAvatar(p)}
                <div class="player-id"><strong>${esc(p.name)}</strong><span class="player-pos-sm">${esc(pos)}</span></div>
            </div></td>
            <td class="col-pos"><span class="pos-tag">${esc(pos)}</span></td>
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
            fx.transition(() => {
                document.querySelectorAll(".squad-filter [data-pos]")
                    .forEach(b => b.setAttribute("aria-pressed", String(b === btn)));
                renderSquad();
            });
        });
    });
    // Başlığa basınca: çoktan aza → azdan çoka → varsayılan sıra
    document.querySelectorAll(".player-stats-table th[data-sort] .sort-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const key = btn.closest("th").dataset.sort;
            if (squadState.sort !== key) Object.assign(squadState, { sort: key, dir: "desc" });
            else if (squadState.dir === "desc") squadState.dir = "asc";
            else squadState.sort = null;
            fx.transition(renderSquad);
        });
    });
}

// Kadro hazırlık özeti: yüzde halkası + mevki başına hazır/eksik çubuğu
function renderReadiness(players) {
    const el = document.getElementById("readiness");
    if (!el || !players.length) return;
    const isReady = p => p.status !== "injured" && p.status !== "suspended";
    const ready = players.filter(isReady).length;
    const pct = Math.round(ready / players.length * 100);
    const rows = ["G", "D", "M", "F"].map(pos => {
        const group = players.filter(p => p.position === pos);
        const ok = group.filter(isReady).length;
        const miss = group.length - ok;
        return `<li>
            <span class="rb-label">${POSITION_TR[pos]}</span>
            <span class="rb-track" aria-hidden="true">
                <i class="rb-ok" style="flex-grow:${ok}"></i>${miss ? `<i class="rb-miss" style="flex-grow:${miss}"></i>` : ""}
            </span>
            <span class="rb-count">${ok}/${group.length}</span>
        </li>`;
    }).join("");
    el.innerHTML = `
        <div class="ready-ring" style="--p:${pct}" role="img" aria-label="Kadronun yüzde ${pct}'i hazır"><b>%${pct}</b></div>
        <div class="ready-text">
            <p class="ready-title">Kadronun %${pct}'i hazır</p>
            <p class="ready-sub">${players.length} oyuncudan ${ready} hazır, ${players.length - ready} eksik</p>
        </div>
        <ul class="ready-bars" aria-label="Mevkilere göre hazır oyuncu">${rows}</ul>`;
    el.hidden = false;
}

async function loadSquad() {
    const tbody = document.querySelector(".player-stats-table tbody");
    if (!tbody) return;
    try {
        squadState.players = await apiGet("/api/squad");
        renderSquad();
        renderReadiness(squadState.players);
        renderSquadSummary(squadState.players);
    } catch (err) {
        console.warn("Kadro API'sine ulaşılamadı:", err);
        showLoadError(tbody, 6);
    }
}

// ---------- Sakatlık & Ceza Raporu ----------
// API sakatlığın başlangıç tarihini vermiyor, sadece "2 Hafta", "10 Gün", "Mart 2027" gibi bir dönüş notu var.
// Bu nottan kalan gün sayısı tahmin edilir; çözülemezse null (çubuk gösterilmez, sadece metin).
const RETURN_SCALE_DAYS = 84;   // çubuk ölçeği: 12 hafta ve üstü = boş
function daysUntilReturn(note) {
    if (!note) return null;
    const t = note.toLocaleLowerCase("tr").trim();
    const n = t.match(/(\d+)\s*(gün|hafta|ay)/);
    if (n) return Number(n[1]) * { "gün": 1, "hafta": 7, "ay": 30 }[n[2]];
    const month = MONTHS_TR.findIndex(mo => t.startsWith(mo.toLocaleLowerCase("tr")));
    if (month >= 0) {
        const year = Number((t.match(/\d{4}/) || [])[0]) || new Date().getFullYear();
        return Math.max(0, Math.round((new Date(year, month, 1) - Date.now()) / 86400000));
    }
    return null;
}

function returnBar(note) {
    const days = daysUntilReturn(note);
    if (days === null) return "";
    // Doluluk dönüşe yakınlığı gösterir: dolu = dönüşe az kaldı
    const near = 1 - Math.min(days, RETURN_SCALE_DAYS) / RETURN_SCALE_DAYS;
    const label = days < 14 ? `~${days} gün` : `~${Math.round(days / 7)} hafta`;
    return `<div class="ir-return" role="img" aria-label="Dönüşe yaklaşık ${label} kaldı">
        <span class="ir-track"><i style="transform:scaleX(${near.toFixed(3)})"></i></span>
        <span class="ir-left">Dönüşe ${label}</span>
    </div>`;
}

function renderAbsences(container, rows) {
    container.innerHTML = rows.map(a => {
        const suspended = a.type === "suspension";
        const pos = POSITION_TR[a.position] ?? a.position ?? "";
        return `<div class="injury-report-card ${suspended ? "suspended-card" : ""}" data-pos="${esc(a.position ?? "")}">
            <div class="ir-main">
                <div class="ir-head">
                    <span class="ir-name">${esc(a.player)}</span>
                    ${pos ? `<span class="pos-tag">${esc(pos)}</span>` : ""}
                </div>
                <div class="ir-detail">${icon(suspended ? "card" : "injury")}${esc(a.reason || (suspended ? "Ceza" : "Sakatlık"))}${a.return_note ? ` · Dönüş: ${esc(a.return_note)}` : ""}</div>
                ${returnBar(a.return_note)}
                <div class="ir-stats">${a.appearances} maç · ${a.goals} gol · ${a.assists} asist</div>
            </div>
            <span class="status-tag ${suspended ? "tag-suspended" : "tag-injured"}">${suspended ? icon("card") + "Cezalı" : icon("injury") + "Sakat"}</span>
        </div>`;
    }).join("") || `<p class="empty-note">${icon("check-circle")}Sakat ya da cezalı oyuncu yok.</p>`;

    const badge = document.getElementById("injuryCount");
    if (badge) {
        badge.textContent = rows.length ? `${rows.length} eksik` : "Tam kadro";
        badge.classList.toggle("is-clear", !rows.length);
    }
}

async function loadAbsences() {
    const container = document.querySelector(".injury-report-list");
    if (!container) return;
    try {
        renderAbsences(container, await apiGet("/api/absences"));
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

// ---------- Takım bilgisi: API id, kulüp renkleri, logo ----------
// /api/matches cevabındaki home_api_id / home_color alanlarından doldurulur.
const teamInfo = {};
// download_logos.py'nin indirdiği logolar (img/teams/index.json); yoksa boş küme
let teamLogos = new Set();
const logosReady = fetch("img/teams/index.json")
    .then(r => (r.ok ? r.json() : []))
    .then(ids => { teamLogos = new Set(ids); })
    .catch(() => {});

function rememberTeams(matches) {
    matches.forEach(m => {
        if (m.home_api_id) teamInfo[m.home] = { id: m.home_api_id, c1: m.home_color, c2: m.home_color2 };
        if (m.away_api_id) teamInfo[m.away] = { id: m.away_api_id, c1: m.away_color, c2: m.away_color2 };
    });
}

const hexRGB = h => /^#[0-9a-f]{6}$/i.test(h || "") ? [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)) : null;
const chroma = rgb => Math.max(...rgb) - Math.min(...rgb);
function relLum(rgb) {
    const [r, g, b] = rgb.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Kartı boyamak için takımın en canlı rengi (beyaz/siyah/gri ise null)
function teamAccent(name) {
    const t = teamInfo[name];
    const cands = [t && t.c1, t && t.c2, TEAM_BADGE[name] && TEAM_BADGE[name][1]].filter(hexRGB);
    const best = cands.sort((a, b) => chroma(hexRGB(b)) - chroma(hexRGB(a)))[0];
    return best && chroma(hexRGB(best)) > 60 ? best : null;
}
window.teamAccent = teamAccent;   // forum.js maç odası sekmesi kullanır

function crest(name, size = "") {
    if (name === "Fenerbahçe") {
        return `<img class="crest ${size}" src="img/fenerbahce-logo.png" alt="" loading="lazy">`;
    }
    const t = teamInfo[name];
    if (t && teamLogos.has(t.id)) {
        return `<img class="crest ${size}" src="img/teams/${t.id}.png" alt="" loading="lazy">`;
    }
    // Logo yoksa: kulübün ana rengiyle daire, ikincil renkte halka, okunur kısaltma
    const code = (TEAM_BADGE[name] || [monogram(name)])[0];
    const bg = (t && hexRGB(t.c1) && t.c1) || (TEAM_BADGE[name] && TEAM_BADGE[name][1]);
    const ring = (t && hexRGB(t.c2) && t.c2) || (TEAM_BADGE[name] && TEAM_BADGE[name][2]) || "var(--c-ring)";
    const style = bg
        ? `--crest-bg:${bg};--crest-fg:${relLum(hexRGB(bg)) > 0.35 ? "var(--c-accent-ink)" : "#ffffff"};--crest-ring:${ring}`
        : "--crest-bg:var(--c-navy-600);--crest-fg:var(--c-text);--crest-ring:var(--c-ring)";
    return `<span class="crest crest-mono ${size}${code.length > 2 ? " is-long" : ""}" style="${style}" aria-hidden="true">${esc(code)}</span>`;
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
    const k = kickoffDate(m);
    const left = k ? k - Date.now() : Infinity;
    if (left > 0 && left < 24 * 3600 * 1000) {
        return { cls: "badge-matchday", ic: "clock", text: "Maç günü", special: true };
    }
    return { cls: "badge-upcoming", ic: "calendar", text: "Sıradaki maç", special: false };
}

// Gün / saat / dakika geri sayımı (sadece hero kartta)
function countdownParts(m) {
    const k = kickoffDate(m);
    const diff = k ? k - Date.now() : 0;
    if (diff <= 0) return null;
    const s = Math.floor(diff / 1000);
    return [[Math.floor(s / 86400), "gün"], [Math.floor((s % 86400) / 3600), "saat"],
            [Math.floor((s % 3600) / 60), "dk"], [s % 60, "sn"]];
}
const digitSpans = str => [...str].map(d => `<span class="dg">${d}</span>`).join("");

function countdownHTML(m) {
    const parts = countdownParts(m);
    if (!parts) return `<div class="mc-count is-soon">Maç başlıyor</div>`;
    return `<div class="mc-count" role="timer" aria-label="Maça kalan süre">` +
        parts.map(([v, u]) => `<span class="mc-unit"><b data-v="${pad2(v)}">${digitSpans(pad2(v))}</b><i>${u}</i></span>`)
            .join('<span class="mc-sep" aria-hidden="true">:</span>') +
        `</div>`;
}

// Sadece değişen haneyi yeniler; yeni hane CSS ile yukarıdan kayarak gelir (transform + opacity)
function tickCountdown(count, m) {
    const parts = countdownParts(m);
    const units = count.querySelectorAll(".mc-unit b");
    if (!parts || units.length !== parts.length) { count.outerHTML = countdownHTML(m); return; }
    units.forEach((b, i) => {
        const next = pad2(parts[i][0]);
        const old = b.dataset.v || "";
        if (old === next) return;
        b.dataset.v = next;
        if (old.length !== next.length) { b.innerHTML = digitSpans(next); return; }
        [...next].forEach((d, j) => {
            if (old[j] === d) return;
            const span = document.createElement("span");
            span.className = "dg is-new";
            span.textContent = d;
            b.children[j].replaceWith(span);
        });
    });
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

    // Kart zemini: Fenerbahçe tarafı lacivert, rakip tarafı rakibin koyulaştırılmış rengi
    const accent = teamAccent(rivalOf(m));
    if (accent) {
        // Açık renkli rakipte (sarı, turuncu) karışım azalır ki yazılar okunur kalsın
        const light = relLum(hexRGB(accent)) > 0.3;
        card.style.setProperty("--rival", accent);
        card.style.setProperty("--rival-mix", light ? "20%" : "30%");
        card.style.setProperty("--rival-glow-mix", light ? "8%" : "16%");
    } else {
        ["--rival", "--rival-mix", "--rival-glow-mix"].forEach(v => card.style.removeProperty(v));
    }
    card.classList.toggle("has-rival", !!accent);
    card.classList.toggle("fb-away", !fbHome);

    const derby = DERBY_RIVALS.includes(rivalOf(m));
    const top = `<div class="mc-top">
        <span class="comp-badge comp-${esc(m.competition)}">${icon(m.competition === "uefa" ? "star" : "trophy")}${esc(COMPETITION_SHORT[m.competition] ?? "")}</span>
        ${derby ? `<span class="match-badge badge-derby">${icon("flame")}Derbi</span>` : ""}
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
            <div class="mc-strip" id="heroStrip" hidden></div>
            <p class="mc-meta">${icon(fbHome ? "home" : "plane")}${fbHome ? HOME_STADIUM : "Deplasman"}</p>
            ${absencesHTML(m)}
            <button type="button" class="btn btn-primary open-sim-btn" onclick="openSimulation('${key}')">${icon("zap")}${label}</button>`;
        renderHeroStrip();
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

// Hero şeridi: geri sayım ile stat arasında Fenerbahçe'nin son 5 maçı ve "maça kalan" çubuğu.
// Rakibin formu için ek API isteği gerekeceğinden sadece Fenerbahçe'nin formu gösterilir.
let fixtureList = null;    // renderFixtures saklar

function heroProgress(m) {
    if (!fixtureList) return null;
    const played = fixtureList.filter(x => x.status === "finished" && x.match_date);
    const prev = played[played.length - 1];
    const k = kickoffDate(m), p = prev && kickoffDate(prev);
    if (!k || !p || k <= p) return null;
    return Math.min(1, Math.max(0, (Date.now() - p) / (k - p)));
}

function renderHeroStrip() {
    const el = document.getElementById("heroStrip");
    const m = navMatch;
    if (!el) return;
    if (!m || !fixtureList) { el.hidden = true; return; }
    const last = fixtureList.filter(x => x.status === "finished" && x.home_score !== null && x.home_score !== undefined).slice(-5);
    const pct = m.status === "live" ? null : heroProgress(m);   // canlıda sadece form
    el.innerHTML = `
        <div class="strip-block">
            <span class="strip-label">Fenerbahçe formu</span>
            <ol class="form-dots" aria-label="Son ${last.length} maç, eskiden yeniye">
                ${last.map(x => {
                    const r = resultOf(x);
                    return `<li class="${r}" title="${esc(`${x.home} ${x.home_score}-${x.away_score} ${x.away}`)}">${RESULT[r].letter}</li>`;
                }).join("")}
            </ol>
        </div>
        ${pct === null ? "" : `<div class="strip-block strip-progress">
            <span class="strip-label">Maça kalan</span>
            <span class="prog-track" role="progressbar" aria-label="Önceki maçtan bu maça geçen süre" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(pct * 100)}">
                <i style="transform:scaleX(${pct.toFixed(4)})"></i>
            </span>
            <span class="prog-val">%${Math.round(pct * 100)}</span>
        </div>`}`;
    el.hidden = false;
}

function tickHeroProgress(card, m) {
    const pct = heroProgress(m);
    const bar = card.querySelector(".prog-track");
    if (pct === null || !bar) return;
    bar.firstElementChild.style.transform = `scaleX(${pct.toFixed(4)})`;
    const v = Math.round(pct * 100);
    if (bar.getAttribute("aria-valuenow") !== String(v)) {
        bar.setAttribute("aria-valuenow", v);
        card.querySelector(".prog-val").textContent = `%${v}`;
    }
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
    if (count) tickCountdown(count, m);
    tickHeroProgress(card, m);
}

// ---------- Bento: son form ve kadro özeti ----------
const POINTS = { win: 3, draw: 1, loss: 0 };

function renderForm(list) {
    const body = document.getElementById("formBody");
    if (!body) return;
    const played = list.filter(m => m.status === "finished" && m.home_score !== null && m.home_score !== undefined);
    const last = played.slice(-5);
    if (!last.length) { body.innerHTML = `<p class="empty-note">Henüz oynanmış maç yok.</p>`; return; }
    const pts = last.reduce((sum, m) => sum + POINTS[resultOf(m)], 0);
    body.innerHTML = `
        <ol class="form-row" aria-label="Son ${last.length} maç, eskiden yeniye">
            ${last.map(m => {
                const res = resultOf(m), rival = rivalOf(m);
                const code = (TEAM_BADGE[rival] || [monogram(rival)])[0];
                const where = m.home === "Fenerbahçe" ? "İç saha" : "Deplasman";
                return `<li class="form-pip ${res}" title="${esc(`${m.home} ${m.home_score}-${m.away_score} ${m.away} · ${where}`)}">
                    <b>${RESULT[res].letter}</b><span>${esc(code)}</span>
                </li>`;
            }).join("")}
        </ol>
        <p class="bento-stat"><b data-count="${pts}">${pts}</b><span>puan · son ${last.length} maç</span></p>`;
    if (window.fx) fx.observeCounts(body);
}

function renderSquadSummary(players) {
    const body = document.getElementById("squadSummaryBody");
    if (!body || !players.length) return;
    const ready = players.filter(p => p.status !== "injured" && p.status !== "suspended").length;
    const pct = Math.round(ready / players.length * 100);
    const top = key => [...players].sort((a, b) => b[key] - a[key] || a.name.localeCompare(b.name, "tr"))[0];
    const scorer = top("goals"), assister = top("assists");
    body.innerHTML = `
        <div class="bento-stat"><b data-count="${pct}" data-prefix="%">%${pct}</b><span>hazır</span></div>
        <div class="bento-stat"><b data-count="${scorer.goals}">${scorer.goals}</b><span>gol · ${esc(scorer.name)}</span></div>
        <div class="bento-stat"><b data-count="${assister.assists}">${assister.assists}</b><span>asist · ${esc(assister.name)}</span></div>`;
    if (window.fx) fx.observeCounts(body);
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
        rememberTeams(matches);
        await logosReady;

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

// Kartın kenar şeridi (--home/--away) ve zemin geçişi (--home-wash/--away-wash) için takım
// renkleri: Fenerbahçe şeritte sarı, zeminde mavi (sarı lacivertle karışınca zeytine döner);
// rakip API rengi, beyaz/siyah/gri ise nötr gri (lacivert zeminde kaybolmasın).
function fxTeamVars(name, side) {
    if (name === "Fenerbahçe") return `--${side}:var(--c-accent);--${side}-wash:var(--c-fb-blue)`;
    const c = teamAccent(name) || "var(--c-text-3)";
    return `--${side}:${c};--${side}-wash:${c}`;
}

function fxTeam(name, side, cls) {
    return `<div class="fx-team ${side}${cls}">${side === "home"
        ? `<span class="fx-name">${esc(name)}</span>${crest(name, "crest-sm")}`
        : `${crest(name, "crest-sm")}<span class="fx-name">${esc(name)}</span>`}</div>`;
}

function fixtureCard(m, isNext) {
    const hasScore = m.home_score !== null && m.home_score !== undefined;
    const live = m.status === "live";
    const done = m.status === "finished" && hasScore;
    const d = m.match_date ? new Date(m.match_date + "T00:00:00") : null;

    let cls = "fx-card", center, state = "";
    let homeCls = "", awayCls = "";
    if (live) {
        cls += " is-live";
        center = `<b class="fx-score">${m.home_score ?? 0}<i>-</i>${m.away_score ?? 0}</b>
            <span class="fx-live"><span class="live-pulse"></span>${esc(liveMinute(m) ?? "Canlı")}</span>`;
    } else if (done) {
        const res = resultOf(m);
        cls += ` is-played ${res}`;
        center = `<b class="fx-score">${m.home_score}<i>-</i>${m.away_score}</b>`;
        state = `<span class="res-badge ${res}" title="${RESULT[res].label}">${RESULT[res].letter}</span>`;
        // Kazanan tarafın adı kalın, kaybedenin soluk
        if (m.home_score > m.away_score) awayCls = " is-loser";
        if (m.home_score < m.away_score) homeCls = " is-loser";
    } else {
        cls += " is-upcoming" + (isNext ? " is-next" : "");
        center = `<b class="fx-time">${esc(m.kickoff_time ?? "--:--")}</b>`;
        if (isNext) state = `<span class="fx-next">Sıradaki</span>`;
    }

    const comp = COMPETITION_SHORT[m.competition] ?? "";
    const week = m.matchday ? ` · ${m.matchday}. Hafta` : "";
    const date = d ? `${d.getDate()} ${MONTHS_TR[d.getMonth()].slice(0, 3)} ${DAYS_TR[d.getDay()]}` : "Tarih belli değil";
    const label = `${m.home} - ${m.away}, ${d ? longDate(m) : "tarih belli değil"}`;
    const colors = `${fxTeamVars(m.home, "home")};${fxTeamVars(m.away, "away")}`;
    return `<article class="${cls}" style="${colors}" aria-label="${esc(label)}"${isNext ? ' aria-current="true"' : ""}>
        <div class="fx-meta">
            <time${m.match_date ? ` datetime="${m.match_date}"` : ""}>${date}</time>
            <span class="fx-comp comp-${esc(m.competition)}">${icon(m.competition === "uefa" ? "star" : "trophy")}${esc(comp)}${week}</span>
            <span class="fx-state">${state}</span>
        </div>
        <div class="fx-match">
            ${fxTeam(m.home, "home", homeCls)}
            <div class="fx-center">${center}</div>
            ${fxTeam(m.away, "away", awayCls)}
        </div>
    </article>`;
}

// ---------- Fikstür filtreleri ----------
const FX_FILTERS = {
    comp:  { all: () => true, super_lig: m => m.competition === "super_lig", uefa: m => m.competition === "uefa" },
    venue: { all: () => true, home: m => m.home === "Fenerbahçe", away: m => m.away === "Fenerbahçe" },
    state: { all: () => true, played: m => m.status === "finished", upcoming: m => m.status !== "finished" },
};
const fxFilter = { comp: "all", venue: "all", state: "all" };
let fxAll = null;           // son yüklenen maç listesi (filtre değişince yeniden çizilir)

function initFixtureFilters() {
    const bar = document.querySelector(".fx-filters");
    if (!bar) return;
    bar.addEventListener("click", e => {
        const btn = e.target.closest("button[data-value]");
        if (!btn) return;
        const group = btn.closest("[data-group]").dataset.group;
        fxFilter[group] = btn.dataset.value;
        btn.closest("[data-group]").querySelectorAll("button").forEach(b =>
            b.setAttribute("aria-pressed", String(b === btn)));
        const container = document.querySelector(".fixtures-grid");
        if (container && fxAll) {
            delete container.dataset.autoScrolled;   // filtre değişince sıradaki maça yeniden kay
            calScroll = true;
            renderFixtures(container, fxAll);
        }
    });

    // Görünüm: Takvim / Liste (seçim bu tarayıcıda hatırlanır)
    let saved = null;
    try { saved = localStorage.getItem("fxView"); } catch (e) { /* depolama kapalı olabilir */ }
    setFixtureView(saved === "list" ? "list" : "cal");
    document.querySelector(".fx-view")?.addEventListener("click", e => {
        const btn = e.target.closest("button[data-view]");
        if (!btn) return;
        setFixtureView(btn.dataset.view);
        try { localStorage.setItem("fxView", btn.dataset.view); } catch (e) { /* önemsiz */ }
    });

    // Takvim şeridi: oklar bir ekran kaydırır, yaprağa tıklayınca maç kartı altta açılır
    const strip = document.getElementById("calGrid");
    document.querySelectorAll(".cal-nav").forEach(btn => btn.addEventListener("click", () => {
        const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
        strip.scrollBy({ left: Number(btn.dataset.step) * strip.clientWidth * 0.8, behavior: reduce ? "auto" : "smooth" });
    }));
    strip?.addEventListener("scroll", updateCalNav, { passive: true });
    strip?.addEventListener("click", e => {
        const cell = e.target.closest(".cal-day[data-id]");
        if (!cell) return;
        calSelected = Number(cell.dataset.id);
        renderCalendar();
    });
}

function setFixtureView(view) {
    document.querySelectorAll(".fx-view button").forEach(b =>
        b.setAttribute("aria-pressed", String(b.dataset.view === view)));
    const cal = document.getElementById("fxCal");
    const list = document.querySelector(".fixtures-grid");
    if (cal) {
        cal.hidden = view !== "cal";
        if (view === "cal" && fxAll) { calScroll = true; renderCalendar(); }
    }
    if (list) {
        list.hidden = view !== "list";
        // Gizliyken kaydırma ölçülemez: listeye geçince sıradaki maça yeniden kay
        if (view === "list" && fxAll) {
            delete list.dataset.autoScrolled;
            renderFixtures(list, fxAll);
        }
    }
}

// ---------- Takvim görünümü ----------
// Sezonun bütün maçları tek şeritte yan yana (takvim yaprakları); ay başlarında ay etiketi.
let calSelected = null;     // altta kartı açık maçın id'si
let calScroll = true;       // bir sonraki çizimde şerit seçili maça kaysın mı

function fxFiltered(list) {
    return list.filter(m => Object.entries(fxFilter).every(([g, v]) => FX_FILTERS[g][v](m)));
}

function updateCalNav() {
    const strip = document.getElementById("calGrid");
    if (!strip) return;
    const max = strip.scrollWidth - strip.clientWidth;
    document.querySelector('.cal-nav[data-step="-1"]').disabled = strip.scrollLeft <= 2;
    document.querySelector('.cal-nav[data-step="1"]').disabled = strip.scrollLeft >= max - 2;
}

function renderCalendar() {
    const strip = document.getElementById("calGrid");
    if (!strip || !fxAll) return;
    const all = [...fxAll].filter(m => m.match_date).sort((a, b) =>
        a.match_date.localeCompare(b.match_date) || (a.kickoff_time || "").localeCompare(b.kickoff_time || ""));
    const next = all.find(m => m.status !== "finished");
    const visible = fxFiltered(all);

    // Başlık: sezon ve filtredeki maçların sonuçları
    const played = visible.filter(m => m.status === "finished" && m.home_score !== null);
    const cnt = r => played.filter(m => resultOf(m) === r).length;
    document.getElementById("calTitle").innerHTML = `Sezon 2026/27
        <small>${visible.length} maç${played.length ? ` <span class="res-badge win">${cnt("win")}G</span><span class="res-badge draw">${cnt("draw")}B</span><span class="res-badge loss">${cnt("loss")}M</span>` : ""}</small>`;

    // Seçili maç: tıklanan; yoksa canlı/sıradaki; yoksa son oynanan
    const pick = visible.find(m => m.id === calSelected)
        || visible.find(m => m.status === "live" || m === next)
        || [...visible].reverse().find(m => m.status === "finished")
        || visible[0];

    const today = localISODate(new Date());
    let html = "", month = "";
    visible.forEach(m => {
        const key = m.match_date.slice(0, 7);
        if (key !== month) {
            month = key;
            html += `<span class="cal-month"><b>${MONTHS_TR[Number(key.slice(5, 7)) - 1]}</b>${key.slice(0, 4)}</span>`;
        }
        html += calCell(m, m === next, m === pick, m.match_date === today);
    });
    const keep = strip.scrollLeft;
    strip.innerHTML = html || `<p class="empty-note">${icon("info")}Bu filtreye uyan maç yok.</p>`;

    // İlk açılışta / filtre değişince seçili maç ortaya gelir; yaprak seçince kaydırma korunur
    const sel = strip.querySelector(".cal-day.is-selected");
    if (calScroll && sel && strip.clientWidth) {
        const r = sel.getBoundingClientRect(), g = strip.getBoundingClientRect();
        strip.scrollLeft = keep + r.left - g.left - (strip.clientWidth - r.width) / 2;
        calScroll = false;
    } else {
        strip.scrollLeft = keep;
    }
    updateCalNav();

    const detail = document.getElementById("calDetail");
    detail.innerHTML = pick ? fixtureCard(pick, pick === next) : "";
}

function calCell(m, isNext, isSelected, isToday) {
    const fbHome = m.home === "Fenerbahçe";
    const rival = rivalOf(m);
    const live = m.status === "live";
    const done = m.status === "finished" && m.home_score !== null && m.home_score !== undefined;
    let cls = "cal-day" + (isToday ? " is-today" : ""), body;
    if (live) {
        cls += " is-live";
        body = `<b class="cal-score">${m.home_score ?? 0}-${m.away_score ?? 0}</b><span class="cal-sub is-live">${esc(liveMinute(m) ?? "Canlı")}</span>`;
    } else if (done) {
        const res = resultOf(m);
        cls += ` is-played ${res}`;
        body = `<b class="cal-score">${m.home_score}-${m.away_score}</b>`;
    } else {
        cls += isNext ? " is-next" : " is-upcoming";
        body = `<b class="cal-time">${esc((m.kickoff_time || "--:--").slice(0, 5))}</b>`;
    }
    if (isSelected) cls += " is-selected";
    const accent = teamAccent(rival) || "var(--c-text-3)";
    const d = new Date(m.match_date + "T00:00:00");
    const venue = fbHome ? "İç saha" : "Deplasman";
    const comp = COMPETITION_SHORT[m.competition] ?? "";
    const label = `${longDate(m)}, ${venue}, ${comp}: ${m.home} - ${m.away}` +
        (done ? `, ${m.home_score}-${m.away_score}` : "");
    return `<button type="button" class="${cls}" data-id="${m.id}" style="--rival:${accent}"
            aria-label="${esc(label)}" aria-pressed="${isSelected}">
        <span class="cal-date"><b>${d.getDate()}</b><span>${MONTHS_TR[d.getMonth()].slice(0, 3)}<i>${DAYS_TR[d.getDay()]}</i></span></span>
        <span class="cal-venue ${fbHome ? "is-home" : "is-away"}">${icon(fbHome ? "home" : "plane")}${venue}</span>
        <span class="cal-crest">${crest(rival, "crest-sm")}</span>
        <span class="cal-rival">${esc(rival)}</span>
        ${body}
        <span class="cal-comp">${icon(m.competition === "uefa" ? "star" : "trophy")}${esc(comp)}</span>
    </button>`;
}

function renderFixtures(container, matches) {
    // Tarihe göre sırala; tarihi belli olmayanlar sona
    const list = [...matches].sort((a, b) =>
        (a.match_date || "9999").localeCompare(b.match_date || "9999") ||
        (a.kickoff_time || "").localeCompare(b.kickoff_time || ""));
    const next = list.find(m => m.status !== "finished");
    fxAll = matches;
    renderCalendar();

    const shown = list.filter(m => Object.entries(fxFilter).every(([g, v]) => FX_FILTERS[g][v](m)));

    // Aylara göre grupla
    const groups = new Map();
    shown.forEach(m => {
        const key = m.match_date ? m.match_date.slice(0, 7) : "tbd";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(m);
    });
    const monthTitle = key => {
        if (key === "tbd") return "Tarihi belli olmayanlar";
        const [y, mo] = key.split("-").map(Number);
        return `${MONTHS_TR[mo - 1]} ${y}`;
    };

    container.innerHTML = groups.size
        ? [...groups].map(([key, ms]) => `<section class="fx-month" aria-label="${monthTitle(key)}">
            <h3 class="fx-month-title">${monthTitle(key)}<span>${ms.length} maç</span></h3>
            <div class="fx-list">${ms.map(m => fixtureCard(m, m === next)).join("")}</div>
        </section>`).join("")
        : `<p class="empty-note">${icon("info")}Bu filtreye uyan maç yok.</p>`;

    renderForm(list);
    fixtureList = list;
    renderHeroStrip();

    // Özet: filtredeki oynanmış maçların G/B/M dağılımı
    const played = shown.filter(m => m.status === "finished" && m.home_score !== null);
    const count = r => played.filter(m => resultOf(m) === r).length;
    const summary = document.getElementById("fxSummary");
    if (summary) {
        summary.innerHTML = played.length ? `${played.length} maç oynandı
            <span class="res-badge win">${count("win")}G</span>
            <span class="res-badge draw">${count("draw")}B</span>
            <span class="res-badge loss">${count("loss")}M</span>` : "";
    }

    // İlk yüklemede (ve filtre değişince) liste sıradaki maça kayar; sayfa kaydırılmaz
    if (!container.dataset.autoScrolled) {
        container.dataset.autoScrolled = "1";
        const nextCard = container.querySelector(".fx-card.is-next, .fx-card.is-live");
        if (nextCard) {
            const header = nextCard.closest(".fx-month").querySelector(".fx-month-title");
            container.scrollTop += nextCard.getBoundingClientRect().top - container.getBoundingClientRect().top
                - header.offsetHeight - 12;
        } else {
            container.scrollTop = 0;
        }
    }
}

async function loadFixtures() {
    const container = document.querySelector(".fixtures-grid");
    if (!container) return;
    try {
        const all = await apiGet("/api/matches");
        rememberTeams(all);
        await logosReady;
        renderFixtures(container, all);
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
    initFixtureFilters();
    loadUpcomingMatches();
    loadFixtures();
    setInterval(loadUpcomingMatches, 60 * 1000);   // kartlar dakikada bir
    setInterval(loadFixtures, 5 * 60 * 1000);      // fikstür 5 dakikada bir
    setInterval(loadStandings, 5 * 60 * 1000);
    setInterval(loadSquad, 10 * 60 * 1000);
    setInterval(loadAbsences, 10 * 60 * 1000);
});