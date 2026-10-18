const API_BASE = "http://127.0.0.1:8000/api";

async function apiGet(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`API hatası: ${res.status}`);
    return res.json();
}

function renderStandings(tbodyEl, rows) {
    if (!rows || rows.length === 0) {
        tbodyEl.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:18px; opacity:0.7;">
            Puan durumu yakında eklenecek
        </td></tr>`;
        return;
    }
    tbodyEl.innerHTML = rows.map(r => {
        const gd = r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference;
        return `<tr class="${r.is_fenerbahce ? "fb-row" : ""}">
            <td>${r.position}</td><td>${r.team}</td><td>${r.played}</td>
            <td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
            <td>${gd}</td><td>${r.points}</td>
        </tr>`;
    }).join("");
}

async function loadStandings() {
    const tables = document.querySelectorAll("#puanlar .standings-table tbody");
    const [superLig, uefa] = tables;
    try {
        const [sl, eu] = await Promise.all([
            apiGet("/standings/super_lig"),
            apiGet("/standings/uefa"),
        ]);
        renderStandings(superLig, sl);
        renderStandings(uefa, eu);
        console.log("Puan durumu API'den yüklendi");
    } catch (err) {
        console.warn("API'ye ulaşılamadı, statik tablo gösteriliyor:", err);
    }
}

const STATUS_VIEW = {
    available: { text: "✔ Hazır",   color: "#2ecc71" },
    injured:   { text: "🚑 Sakat",  color: "#ff6b6b" },
    suspended: { text: "🟨 Cezalı", color: "#f1c40f" },
};

function renderSquad(tbodyEl, players) {
    tbodyEl.innerHTML = players.map(p => {
        const s = STATUS_VIEW[p.status] || STATUS_VIEW.available;
        return `<tr>
            <td><strong>${p.name}</strong></td>
            <td style="color:#bbb;">${p.position ?? "-"}</td>
            <td><span class="stat-badge stat-match">${p.appearances}</span></td>
            <td><span class="stat-badge stat-goal">${p.goals}</span></td>
            <td><span class="stat-badge stat-assist">${p.assists}</span></td>
            <td style="color:${s.color}; font-weight:bold;">${s.text}</td>
        </tr>`;
    }).join("");
}

async function loadSquad() {
    const tbody = document.querySelector(".player-stats-table tbody");
    if (!tbody) return;
    try {
        const players = await apiGet("/squad");
        renderSquad(tbody, players);
        console.log("Kadro API'den yüklendi");
    } catch (err) {
        console.warn("Kadro API'sine ulaşılamadı, statik tablo gösteriliyor:", err);
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
                <div style="font-weight:bold; font-size:1em;">${a.player}${pos}</div>
                <div style="font-size:0.84em; color:#ccc; margin-top:4px;">${a.appearances} Maç • ${a.goals} Gol • ${a.assists} Asist</div>
                <div style="font-size:0.8em; color:${suspended ? "#f1c40f" : "#ff9999"}; margin-top:3px;">${detail}</div>
            </div>
            <span class="status-tag ${suspended ? "tag-suspended" : "tag-injured"}">${suspended ? "🟨 Cezalı" : "🚑 Sakat"}</span>
        </div>`;
    }).join("");
}

async function loadAbsences() {
    const container = document.querySelector(".injury-report-list");
    if (!container) return;
    try {
        renderAbsences(container, await apiGet("/absences"));
        console.log("Sakatlık raporu API'den yüklendi");
    } catch (err) {
        console.warn("Sakatlık API'sine ulaşılamadı, statik içerik gösteriliyor:", err);
    }
}

// ---------- Yakın Maç Kartları ----------
const ABSENCE_TAG = {
    injury:     { cls: "tag-injured",   text: "🚑 Sakat" },
    suspension: { cls: "tag-suspended", text: "🟨 Cezalı" },
};
const DAYS_TR = ["Paz", "Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"];
const MATCH_KEYS = ["alanya", "slavia", "gs"];
const COMPETITION_LABEL = {
    super_lig: "Trendyol Süper Lig",
    uefa: "UEFA Şampiyonlar Ligi",
};
const DERBY_RIVALS = ["Galatasaray", "Beşiktaş JK", "Trabzonspor"];

const pad2 = n => String(n).padStart(2, "0");

function localISODate(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function rivalOf(m) {
    return m.home === "Fenerbahçe" ? m.away : m.home;
}

function liveMinute(m) {
    if (m.status_code === 31) return "Devre Arası";
    if (!m.period_start || (m.status_code !== 6 && m.status_code !== 7)) return null;
    const secs = Math.floor(Date.now() / 1000) - m.period_start + (m.period_initial || 0);
    const min = Math.floor(secs / 60) + 1;
    const cap = m.status_code === 6 ? 45 : 90;
    return min > cap ? `${cap}+${min - cap}'` : `${min}'`;
}

function badgeInfo(m) {
    const d = new Date(m.match_date + "T00:00:00");
    const when = `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)} ${DAYS_TR[d.getDay()]}` +
        (m.kickoff_time ? ` ${m.kickoff_time}` : "");
    if (m.status === "live") {
        const mn = liveMinute(m);
        return { cls: "badge-live", text: `🔴 CANLI${mn ? " • " + mn : ""} • ${when}` };
    }
    if (m.match_date === localISODate(new Date())) {
        return { cls: "badge-upcoming", text: `⏳ BUGÜN • ${when}` };
    }
    if (DERBY_RIVALS.includes(rivalOf(m))) {
        return { cls: "badge-upcoming", text: `🔥 DERBİ • ${when}` };
    }
    return { cls: "badge-upcoming", text: `⏳ YAKLAŞAN • ${when}` };
}

function renderAbsenceItem(a) {
    if (a.type === "returned") {
        return `<div class="matchday-missing-item">
            <div class="missing-player-info">
                <span class="missing-player-name">${a.player}</span>
                <span class="missing-player-stats">${a.reason ?? ""}</span>
            </div>
            <span class="status-tag" style="background:rgba(46,204,113,0.2); color:#2ecc71; border:1px solid #2ecc71;">✔ Kadroda</span>
        </div>`;
    }
    const tag = ABSENCE_TAG[a.type] || ABSENCE_TAG.injury;
    return `<div class="matchday-missing-item">
        <div class="missing-player-info">
            <span class="missing-player-name">${a.player}</span>
            <span class="missing-player-stats">${a.reason ?? ""}</span>
        </div>
        <span class="status-tag ${tag.cls}">${tag.text}</span>
    </div>`;
}

function updateMatchCard(card, m) {
    const b = badgeInfo(m);
    const badge = card.querySelector(".match-badge");
    if (badge) {
        badge.textContent = b.text;
        badge.className = `match-badge ${b.cls}`;
    }

    const teams = card.querySelectorAll(".recent-teams span");
    if (teams.length >= 3) {
        teams[0].textContent = m.home;
        teams[2].textContent = m.away;
        teams[1].textContent = m.home_score === null ? "v" : `${m.home_score} - ${m.away_score}`;
    }

    const meta = card.querySelector(".card-top-center > div:last-child");
    if (meta) {
        const place = m.home === "Fenerbahçe" ? "Chobani Stadium" : "Deplasman";
        meta.textContent = `${COMPETITION_LABEL[m.competition] ?? ""} • ${place}`;
    }

    const box = card.querySelector(".matchday-missing-box");
    if (box) {
        const items = m.absences || [];
        box.style.display = items.length ? "" : "none";
        const titleSpans = box.querySelectorAll(".matchday-missing-title span");
        if (titleSpans[0]) titleSpans[0].textContent = `🚨 Maç Günü Eksikleri (${rivalOf(m)})`;
        if (titleSpans[1]) titleSpans[1].textContent = `${m.absence_count} Eksik`;
        box.querySelectorAll(".matchday-missing-item").forEach(el => el.remove());
        box.insertAdjacentHTML("beforeend", items.map(renderAbsenceItem).join(""));
    }
}

function syncMatchMeta(m, key) {
    // main.js içindeki matchMeta'nın üzerine API verisini yazar (simülasyon için)
    if (typeof matchMeta === "undefined") return;
    const live = m.status === "live";
    matchMeta[key] = {
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
        el.innerHTML = `<span class="nn-label">✅ MS</span>
            <span class="nn-live">${f.home} ${f.home_score ?? 0} - ${f.away_score ?? 0} ${f.away}</span>`;
        return;
    }

    if (!m) { el.style.display = "none"; return; }
    el.style.display = "";

    if (m.status === "live") {
        const mn = liveMinute(m);
        el.classList.add("is-live");
        el.innerHTML = `<span class="nn-label">🔴 CANLI${mn ? " " + mn : ""}</span>
            <span class="nn-live">${m.home} ${m.home_score ?? 0} - ${m.away_score ?? 0} ${m.away}</span>`;
        return;
    }
    el.classList.remove("is-live");

    const time = (m.kickoff_time || "00:00").slice(0, 5);
    const diff = new Date(`${m.match_date}T${time}:00+03:00`) - new Date();
    if (diff <= 0) {
        el.innerHTML = `<span class="nn-label">${rivalOf(m)}</span><span class="nn-live">Maç başlıyor</span>`;
        return;
    }

    const s = Math.floor(diff / 1000);
    const parts = [
        [Math.floor(s / 86400), "gün"],
        [Math.floor((s % 86400) / 3600), "saat"],
        [Math.floor((s % 3600) / 60), "dk"],
        [s % 60, "sn"],
    ];
    el.innerHTML = `<span class="nn-label">${rivalOf(m)}</span>` +
        parts.map(([v, u]) =>
            `<span class="nn-box"><b>${String(v).padStart(2, "0")}</b><i>${u}</i></span>`
        ).join("");
}

async function loadUpcomingMatches() {
    const cards = document.querySelectorAll(".recent-match-card");
    if (!cards.length) return;
    try {
        const matches = await apiGet("/matches/upcoming");

        const prev = navMatch;
        const next = matches[0] || null;
        // Canlı maç bitti: final skoru çekip 10 dk göster
        if (prev && prev.status === "live" && (!next || next.id !== prev.id)) {
            try {
                const fin = await apiGet(`/matches/${prev.id}`);
                finishedMatch = { m: fin, until: Date.now() + 10 * 60 * 1000 };
            } catch (e) { /* final skoru alınamazsa geçilir */ }
        }
        navMatch = next;
        renderNavNext();

        cards.forEach((card, i) => {
            const m = matches[i];
            card.style.display = m ? "" : "none";
            if (!m) return;
            updateMatchCard(card, m);
            if (MATCH_KEYS[i]) syncMatchMeta(m, MATCH_KEYS[i]);
        });
        console.log("Yakın maçlar API'den yüklendi");
    } catch (err) {
        console.warn("Maç API'sine ulaşılamadı, statik kartlar gösteriliyor:", err);
    }
}

// ---------- Fikstür ----------
function fixtureDate(m) {
    if (!m.match_date) return "Sezon Sonu";
    const d = new Date(m.match_date + "T00:00:00");
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    return `${dd}/${mm} ${DAYS_TR[d.getDay()]}`;
}

function renderFixtures(container, matches) {
    container.innerHTML = matches.map(m => {
        const hasScore = m.home_score !== null && m.home_score !== undefined;
        const live = m.status === "live" && hasScore;
        const done = m.status === "finished" && hasScore;

        let cls = "fixture-item";
        let bottom = `<div class="fixture-time">${m.kickoff_time ?? "Henüz belirlenmedi"}</div>`;

        if (live) {
            cls += " is-live";
            bottom = `<div class="fixture-score live">🔴 CANLI ${m.home_score} - ${m.away_score}</div>`;
        } else if (done) {
            const fbHome = m.home === "Fenerbahçe";
            const fb = fbHome ? m.home_score : m.away_score;
            const opp = fbHome ? m.away_score : m.home_score;
            const res = fb > opp ? "win" : fb < opp ? "loss" : "draw";
            const label = { win: "Galibiyet", draw: "Beraberlik", loss: "Mağlubiyet" }[res];
            cls += ` finished ${res}`;
            bottom = `<div class="fixture-score ${res}">${m.home_score} - ${m.away_score} • ${label}</div>`;
        }

        return `<div class="${cls}">
            <div class="fixture-date">${fixtureDate(m)}</div>
            <div class="fixture-teams">${m.home} - ${m.away}</div>
            ${bottom}
        </div>`;
    }).join("");
}

async function loadFixtures() {
    const container = document.querySelector(".fixtures-grid");
    if (!container) return;
    try {
        renderFixtures(container, await apiGet("/matches"));
        console.log("Fikstür API'den yüklendi");
    } catch (err) {
        console.warn("Fikstür API'sine ulaşılamadı, statik içerik gösteriliyor:", err);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    setInterval(renderNavNext, 1000);
    loadStandings();
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