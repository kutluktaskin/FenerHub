const API_BASE = "http://127.0.0.1:8000/api";

async function apiGet(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`API hatası: ${res.status}`);
    return res.json();
}

function renderStandings(tbodyEl, rows) {
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

function badgeText(m) {
    const d = new Date(m.match_date + "T00:00:00");
    const date = `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")} ${DAYS_TR[d.getDay()]}`;
    const time = m.kickoff_time ? ` ${m.kickoff_time}` : "";
    return `${date}${time}`;
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
    const badge = card.querySelector(".match-badge");
    if (badge && m.match_date) {
        const live = m.status === "live";
        badge.textContent = `${live ? "🔴 CANLI" : "⏳ YAKLAŞAN"} • ${badgeText(m)}`;
        badge.className = `match-badge ${live ? "badge-live" : "badge-upcoming"}`;
    }

    const score = card.querySelector(".recent-score");
    if (score) {
        score.textContent = m.home_score === null ? "v" : `${m.home_score} - ${m.away_score}`;
    }

    const box = card.querySelector(".matchday-missing-box");
    if (box) {
        const countEl = box.querySelector(".matchday-missing-title span:last-child");
        if (countEl) countEl.textContent = `${m.absence_count} Eksik`;
        box.querySelectorAll(".matchday-missing-item").forEach(el => el.remove());
        box.insertAdjacentHTML("beforeend", m.absences.map(renderAbsenceItem).join(""));
    }
}

async function loadUpcomingMatches() {
   const MATCH_KEYS = ["alanya", "slavia", "gs"];
const COMPETITION_LABEL = {
    super_lig: "Trendyol Süper Lig",
    uefa: "UEFA Avrupa Kupası",
};

function syncMatchMeta(m, key) {
    // main.js içindeki matchMeta'nın üzerine API verisini yazar
    if (typeof matchMeta === "undefined") return;
    const live = m.status === "live";
    matchMeta[key] = {
        home: m.home.toUpperCase(),
        away: m.away.toUpperCase(),
        score: m.home_score === null ? "v" : `${m.home_score} - ${m.away_score}`,
        minute: live ? m.minute : (matchMeta[key]?.minute ?? "Ön İzleme"),
        league: COMPETITION_LABEL[m.competition] ?? matchMeta[key]?.league,
    };
}

async function loadUpcomingMatches() {
    const cards = document.querySelectorAll(".recent-match-card");
    if (!cards.length) return;
    try {
        const matches = await apiGet("/matches/upcoming");
        matches.forEach((m, i) => {
            if (cards[i]) updateMatchCard(cards[i], m);
            if (MATCH_KEYS[i]) syncMatchMeta(m, MATCH_KEYS[i]);
        });
        console.log("Yakın maçlar API'den yüklendi");
    } catch (err) {
        console.warn("Maç API'sine ulaşılamadı, statik kartlar gösteriliyor:", err);
    }
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
    container.innerHTML = matches.map(m => `
        <div class="fixture-item">
            <div class="fixture-date">${fixtureDate(m)}</div>
            <div class="fixture-teams">${m.home} - ${m.away}</div>
            <div class="fixture-time">${m.kickoff_time ?? "Henüz belirlenmedi"}</div>
        </div>`).join("");
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
    loadStandings();
    loadSquad();
    loadAbsences();
    loadUpcomingMatches();
    loadFixtures();
});