// Demo modu testleri: zaman çizelgesi ve dakika sayacı kaydırması. Çalıştırma: node --test "frontend/tests/*.test.cjs"
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { dueEvents, shiftedPeriodStart } = require("../js/demo.js");

test("dueEvents: (from, to] aralığındaki olaylar, sırası korunur", () => {
    const ev = [[0, "a"], [10, "b"], [10, "c"], [25, "d"]];
    assert.deepEqual(dueEvents(ev, -1, 0).map(e => e[1]), ["a"]);
    assert.deepEqual(dueEvents(ev, 0, 10).map(e => e[1]), ["b", "c"]);
    assert.deepEqual(dueEvents(ev, 10, 24).map(e => e[1]), []);
    assert.deepEqual(dueEvents(ev, 10, 100).map(e => e[1]), ["d"]);
});

test("shiftedPeriodStart: sanal saatte geçen süre gerçek saate taşınır", () => {
    // Kayıtta periyot 1000'de başladı, sanal saat 1600 (10 dk geçti), gerçek saat 50000
    assert.equal(shiftedPeriodStart(1000, 1600, 50000), 49400);   // 50000 - 49400 = 600 sn = 10 dk
    assert.equal(shiftedPeriodStart(null, 1600, 50000), null);
});

test("demo kaydı: geçerli biçim, sıralı, maç başlıyor ve bitiyor", () => {
    const file = path.join(__dirname, "..", "demo", "slavia-2026-10-20.json");
    const demo = JSON.parse(fs.readFileSync(file, "utf8"));
    assert.ok(demo.meta.duration > 90 * 60 && demo.meta.start > 0);
    assert.equal(demo.events[0][0], 0);
    assert.equal(demo.events[0][1].type, "state");
    const times = demo.events.map(e => e[0]);
    assert.deepEqual(times, [...times].sort((a, b) => a - b));
    const statuses = demo.events.filter(e => e[1].kind === "match").map(e => e[1].data.status_code);
    assert.ok(statuses.includes(6) && statuses.includes(31) && statuses.includes(7), "ilk yarı, devre arası, ikinci yarı");
    assert.equal(demo.events.filter(e => e[1].kind === "match").at(-1)[1].data.status, "finished");
    assert.ok(fs.statSync(file).size < 400 * 1024, "dosya küçük kalmalı");
});
