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

document.addEventListener("DOMContentLoaded", loadStandings);