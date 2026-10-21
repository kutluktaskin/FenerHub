// Maç sonu özeti testleri: şut konumu, xG toplamı, baskı grafiği yönü.
const test = require("node:test");
const assert = require("node:assert/strict");
const { shotPoint, xgTotals, momentumBars } = require("../js/summary.js");

test("shotPoint: Fenerbahçe sağdaki kaleye, rakip soldakine şut atar", () => {
    // Fenerbahçe ev sahibi; kaleye %10 uzaklık, tam ortadan
    const fb = shotPoint({ isHome: true, x: 10, y: 50, xg: 0.25 }, true);
    assert.equal(fb.fb, true);
    assert.equal(fb.x, 94.5);              // 105 - 10.5
    assert.equal(fb.y, 34);
    const rv = shotPoint({ isHome: false, x: 10, y: 25, xg: 0 }, true);
    assert.equal(rv.fb, false);
    assert.equal(rv.x, 10.5);
    assert.equal(rv.y, 51);                // ayna: 68 - 17
    // Fenerbahçe deplasmandaysa taraflar isHome'a göre değil Fenerbahçe'ye göre seçilir
    assert.equal(shotPoint({ isHome: false, x: 10, y: 50 }, false).fb, true);
    assert.ok(fb.r > rv.r, "yüksek xG büyük daire");
});

test("xgTotals: taraflara göre xG, şut, isabet ve gol", () => {
    const shots = [
        { isHome: true, xg: 0.5, type: "goal" }, { isHome: true, xg: 0.1, type: "save" },
        { isHome: true, xg: 0.05, type: "miss" }, { isHome: false, xg: 0.3, type: "block" },
    ];
    const t = xgTotals(shots, true);
    assert.deepEqual(t.fb, { xg: 0.65, shots: 3, onTarget: 2, goals: 1 });
    assert.deepEqual(t.rival, { xg: 0.3, shots: 1, onTarget: 0, goals: 0 });
    assert.deepEqual(xgTotals(shots, false).fb, { xg: 0.3, shots: 1, onTarget: 0, goals: 0 });
});

test("momentumBars: yukarı her zaman Fenerbahçe baskısı", () => {
    const graph = { periodTime: 45, points: [[45, 30], [90, -20]] };
    assert.deepEqual(momentumBars(graph, true), [{ x: 50, v: 30 }, { x: 100, v: -20 }]);
    assert.deepEqual(momentumBars(graph, false), [{ x: 50, v: -30 }, { x: 100, v: 20 }]);
    assert.deepEqual(momentumBars(null, true), []);
});
