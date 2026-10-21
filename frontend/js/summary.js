/* Maç sonu özeti (simülasyonda "Maç özeti" sekmesi): şut haritası, baskı grafiği, en iyi oyuncular.
   Veri /api/matches/{id}/detail -> summary (backend maç bitince bir kez çeker).
   Saf yardımcılar (shotPoint, xgTotals, momentumBars) Node testleri için de dışa açılır. */
(function (root) {
    const L = 105, W = 68;                    // saha ölçüleri (m): SVG koordinatları

    /* Şutun sahadaki yeri. Fenerbahçe sağa, rakip sola hücum eder (simülasyonla aynı).
       x: kaleye uzaklık (saha boyunun %'si), y: yan konum (0-100). */
    function shotPoint(s, fbIsHome) {
        const fb = s.isHome === fbIsHome;
        const px = fb ? L - s.x * L / 100 : s.x * L / 100;
        const py = fb ? s.y * W / 100 : W - s.y * W / 100;
        return { fb, x: +px.toFixed(2), y: +py.toFixed(2), r: +(0.9 + Math.sqrt(Math.max(0, s.xg || 0)) * 3.2).toFixed(2) };
    }

    function xgTotals(shots, fbIsHome) {
        const t = { fb: { xg: 0, shots: 0, onTarget: 0, goals: 0 }, rival: { xg: 0, shots: 0, onTarget: 0, goals: 0 } };
        (shots || []).forEach(s => {
            const side = s.isHome === fbIsHome ? t.fb : t.rival;
            side.xg += s.xg || 0;
            side.shots += 1;
            if (s.type === "goal" || s.type === "save") side.onTarget += 1;
            if (s.type === "goal") side.goals += 1;
        });
        t.fb.xg = +t.fb.xg.toFixed(2);
        t.rival.xg = +t.rival.xg.toFixed(2);
        return t;
    }

    /* Baskı grafiği: Fenerbahçe açısından (yukarı = Fenerbahçe baskısı). x 0-100, değer -100..100. */
    function momentumBars(graph, fbIsHome) {
        if (!graph || !graph.points) return [];
        const total = (graph.periodTime || 45) * 2;
        return graph.points.map(([minute, value]) => ({
            x: +(Math.min(minute, total) / total * 100).toFixed(2),
            v: fbIsHome ? value : -value,
        }));
    }

    const api = { shotPoint, xgTotals, momentumBars };
    root.MatchSummary = api;
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    if (typeof document === "undefined") return;

    const RESULT_TR = { goal: "Gol", save: "Kurtarış", miss: "Auta", block: "Blok", post: "Direk" };

    function pitchLines() {
        return `<rect x="0" y="0" width="${L}" height="${W}" class="sm-grass"/>
            <g class="sm-line"><rect x="0.3" y="0.3" width="${L - 0.6}" height="${W - 0.6}"/>
            <line x1="${L / 2}" y1="0" x2="${L / 2}" y2="${W}"/><circle cx="${L / 2}" cy="${W / 2}" r="9.15"/>
            <rect x="0" y="${W / 2 - 20.16}" width="16.5" height="40.32"/><rect x="${L - 16.5}" y="${W / 2 - 20.16}" width="16.5" height="40.32"/>
            <rect x="0" y="${W / 2 - 9.16}" width="5.5" height="18.32"/><rect x="${L - 5.5}" y="${W / 2 - 9.16}" width="5.5" height="18.32"/></g>`;
    }

    function shotmapSvg(shots, m, fbIsHome, rivalCol) {
        const dots = shots.map(s => {
            const p = shotPoint(s, fbIsHome);
            const col = p.fb ? "var(--c-accent)" : rivalCol;
            const goal = s.type === "goal";
            const onT = s.type === "save";
            const fill = goal ? col : onT ? `color-mix(in oklab, ${col} 45%, transparent)` : "transparent";
            const min = s.addedTime ? `${s.time}+${s.addedTime}` : s.time;
            return `<circle cx="${p.x}" cy="${p.y}" r="${p.r}" fill="${fill}" stroke="${goal ? "#fff" : col}"
                stroke-width="${goal ? 0.6 : 0.45}" class="${goal ? "sm-goal" : ""}"><title>${esc(s.player || "")} · ${esc(min)}' · ${RESULT_TR[s.type] || esc(s.type)} · xG ${s.xg}</title></circle>`;
        }).join("");
        const fbName = "Fenerbahçe", rvName = fbIsHome ? m.away : m.home;
        return `<svg class="sm-pitch" viewBox="0 0 ${L} ${W}" role="img" aria-label="Şut haritası: ${esc(fbName)} sağa, ${esc(rvName)} sola hücum ediyor">
            ${pitchLines()}${dots}</svg>
            <p class="sm-legend"><span><i class="sm-key is-goal"></i>Gol</span><span><i class="sm-key is-on"></i>İsabetli</span>
            <span><i class="sm-key"></i>İsabetsiz / blok</span><span>Büyüklük: gol beklentisi (xG)</span>
            <span>→ ${esc(fbName)} · ← ${esc(rvName)}</span></p>`;
    }

    function momentumSvg(summary, incidents, fbIsHome, rivalCol) {
        const bars = momentumBars(summary.graph, fbIsHome);
        if (!bars.length) return "";
        const bw = Math.max(0.4, 100 / bars.length * 0.8);
        const rects = bars.map(b => {
            const h = Math.abs(b.v) / 100 * 18;
            return b.v >= 0
                ? `<rect x="${b.x - bw / 2}" y="${20 - h}" width="${bw}" height="${h}" class="mo-fb"/>`
                : `<rect x="${b.x - bw / 2}" y="20" width="${bw}" height="${h}" fill="${rivalCol}"/>`;
        }).join("");
        const total = ((summary.graph.periodTime) || 45) * 2;
        // Gol işaretleri SVG dışında: grafik yatayda esnediği için daire basık çıkmasın
        const goals = (incidents || []).filter(i => i.incidentType === "goal" && i.time >= 0).map(i => {
            const fb = i.isHome === fbIsHome;
            const x = Math.min(i.time, total) / total * 100;
            return `<span class="mo-goal ${fb ? "is-fb" : "is-rv"}" style="left:${x.toFixed(2)}%" title="Gol: ${esc(i.player || "")} ${i.time}'"></span>`;
        }).join("");
        return `<div class="mo-wrap">${goals}<svg class="mo-chart" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="Baskı grafiği: yukarı Fenerbahçe, aşağı rakip baskısı">
            <line x1="0" y1="20" x2="100" y2="20" class="mo-axis" vector-effect="non-scaling-stroke"/>
            <line x1="50" y1="0" x2="50" y2="40" class="mo-ht" vector-effect="non-scaling-stroke"/>
            ${rects}</svg></div>
            <p class="sm-legend"><span>Yukarı: Fenerbahçe baskısı</span><span>Aşağı: rakip baskısı</span><span>Kesikli çizgi: devre arası</span><span><i class="mo-goal-key"></i>Gol</span></p>`;
    }

    function bestHtml(best) {
        if (!best || !best.top || !best.top.length) return "";
        return `<ol class="sm-best">${best.top.map((p, k) => `<li class="${p.team === "Fenerbahçe" ? "is-fb" : ""}">
            <span class="sm-rank">${k + 1}</span><span class="sm-name">${esc(p.name)}<small>${esc(p.team || "")}</small></span>
            <b class="sm-rating">${esc(p.rating)}</b></li>`).join("")}</ol>`;
    }

    function statBox(label, a, b) {
        return `<div class="sm-stat"><b>${a}</b><span>${label}</span><b>${b}</b></div>`;
    }

    // matchEngine.js simPoll çağırır; özet yoksa sekme gizli kalır
    root.renderSummaryTab = function (summary, m, incidents) {
        const btn = document.getElementById("btn-summaryTab");
        const body = document.getElementById("summaryBody");
        if (!btn || !body) return false;
        btn.hidden = !summary;
        if (!summary || !m) { body.innerHTML = ""; return false; }
        const fbIsHome = m.home === "Fenerbahçe";
        const rival = fbIsHome ? m.away : m.home;
        const rivalCol = (typeof teamAccent === "function" && teamAccent(rival)) || "#e5484d";
        const t = xgTotals(summary.shotmap, fbIsHome);
        body.innerHTML = `
            <div class="sm-head"><span>Fenerbahçe</span><span></span><span>${esc(rival)}</span></div>
            ${summary.shotmap ? statBox("Gol beklentisi (xG)", t.fb.xg, t.rival.xg) + statBox("Şut", t.fb.shots, t.rival.shots) + statBox("İsabetli şut", t.fb.onTarget, t.rival.onTarget) : ""}
            ${summary.shotmap ? `<h4 class="sm-title">${icon("target")}Şut haritası</h4>${shotmapSvg(summary.shotmap, m, fbIsHome, rivalCol)}` : ""}
            ${summary.graph ? `<h4 class="sm-title">${icon("chart")}Baskı grafiği</h4>${momentumSvg(summary, incidents, fbIsHome, rivalCol)}` : ""}
            ${summary.best ? `<h4 class="sm-title">${icon("star")}Maçın en iyileri <small>SportsAPI puanı</small></h4>${bestHtml(summary.best)}` : ""}`;
        return true;
    };

    // Fikstürdeki "Maç özeti" düğmesi: o maçın simülasyonunu açıp özet sekmesine geçer
    root.openMatchSummary = function (id) {
        const m = (typeof fixtureList !== "undefined" && fixtureList || []).find(x => x.id === id);
        if (!m || typeof matchMeta === "undefined") return;
        matchMeta.ozet = {
            id: m.id, home: m.home.toUpperCase(), away: m.away.toUpperCase(),
            score: `${m.home_score} - ${m.away_score}`, minute: "Maç bitti",
            league: (typeof COMPETITION_LABEL !== "undefined" && COMPETITION_LABEL[m.competition]) || "",
        };
        root.summaryWanted = true;
        openSimulation("ozet");
    };
})(typeof window !== "undefined" ? window : globalThis);
