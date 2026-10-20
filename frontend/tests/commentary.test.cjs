// Canlı maç anlatıcısı testleri. Çalıştırma: node --test frontend/tests
const test = require("node:test");
const assert = require("node:assert/strict");
const { line, templates } = require("../js/commentary.js");

const HOME = { home: "Fenerbahçe", away: "Slavia Prag", fbIsHome: true };
const AWAY = { home: "Galatasaray", away: "Fenerbahçe", fbIsHome: false };
const KNOWN = new Set(["oyuncu", "asist", "dk", "skor", "fb", "rakip", "giren", "cikan", "takim"]);

test("kalıplar: yeterli çeşit, bilinen yer tutucular, isimden sonra ek yok", () => {
    for (const g of ["goal_fb", "goal_rival", "yellow", "sub"]) {
        assert.ok(templates[g].length >= 10, `${g} en az 10 kalıp`);
    }
    for (const [g, list] of Object.entries(templates)) {
        assert.ok(list.length > 0, g);
        for (const t of list) {
            for (const [, k] of t.matchAll(/\{(\w+)\}/g)) assert.ok(KNOWN.has(k), `${g}: {${k}}`);
            assert.ok(!/\}'/.test(t), `${g}: yer tutucudan sonra kesme işaretli ek var: ${t}`);
            assert.ok(!/Kadıköy/.test(t), `${g}: deplasmanda da kullanılır, yer adı geçmemeli: ${t}`);
        }
    }
});

test("Fenerbahçe golü: oyuncu, dakika ve skor gerçek veriden; aynı olay hep aynı cümle", () => {
    const goal = { incidentType: "goal", incidentClass: "regular", time: 41, isHome: true,
        homeScore: 1, awayScore: 0, player: "Vedat Muriqi" };
    const a = line(goal, HOME);
    assert.match(a, /Vedat Muriqi/);
    assert.match(a, /Fenerbahçe 1-0 Slavia Prag/);
    assert.ok(templates.goal_fb.some(t => a.startsWith(t.split("{")[0])));
    assert.equal(line(goal, HOME), a);
    assert.ok(!/[{}]/.test(a) && !/\(\s*\)/.test(a));
});

test("rakip golü, asist ve uzatma dakikası", () => {
    const goal = { incidentType: "goal", incidentClass: "regular", time: 90, addedTime: 3, isHome: true,
        homeScore: 2, awayScore: 1, player: "Mauro Icardi", assist: "Barış Alper Yılmaz" };
    const a = line(goal, AWAY);           // Fenerbahçe deplasmanda, ev sahibi golü
    assert.match(a, /Mauro Icardi/);
    assert.match(a, /Galatasaray 2-1 Fenerbahçe/);
    assert.match(a, /Barış Alper Yılmaz/);
    assert.match(a, /Fenerbahçe\. /);                // skordan sonra asist cümlesi noktayla ayrılır
    assert.ok(templates.goal_rival.some(t => a.startsWith(fillStart(t, "Galatasaray"))));
});

function fillStart(t, rakip) {
    return t.split("{oyuncu}")[0].replace("{rakip}", rakip).replace(/\{dk\}.*$/, "").split("{")[0];
}

test("kartlar: sarı, ikinci sarı ve direkt kırmızı ayrı anlatılır", () => {
    const card = { incidentType: "card", incidentClass: "yellow", time: 55, isHome: false, player: "Tomáš Holeš" };
    const y = line(card, HOME);
    assert.match(y, /Tomáš Holeš/);
    assert.match(y, /[Ss]arı kart/);
    assert.match(line(card, { ...HOME, secondYellow: true }), /ikinci sarı|İkinci sarı/i);
    assert.match(line({ ...card, incidentClass: "yellowRed" }, HOME), /ikinci sarı|İkinci sarı/i);
    assert.match(line({ ...card, incidentClass: "red" }, HOME), /[Kk]ırmızı/);
});

test("değişiklik giren ve çıkanı söyler; isimsiz değişiklik de boş kalmaz", () => {
    const sub = { incidentType: "substitution", time: 70, isHome: true, playerIn: "Kerem Aktürkoğlu", playerOut: "Oğuz Aydın" };
    const s = line(sub, HOME);
    assert.match(s, /Kerem Aktürkoğlu/);
    assert.match(s, /Oğuz Aydın/);
    assert.match(line({ incidentType: "substitution", time: 70, isHome: true }, HOME), /değişikliği, 70\. dakika/);
});

test("maç sonu Fenerbahçe açısından: deplasmanda galibiyet, beraberlik, mağlubiyet", () => {
    const ft = (h, a) => line({ incidentType: "period", text: "FT", homeScore: h, awayScore: a }, AWAY);
    assert.ok(templates.ft_win.some(t => ft(0, 2).startsWith(t.split("{")[0])));
    assert.ok(templates.ft_draw.some(t => ft(1, 1).startsWith(t.split("{")[0])));
    assert.ok(templates.ft_loss.some(t => ft(3, 1).startsWith(t.split("{")[0])));
    assert.match(ft(0, 2), /Galatasaray 0-2 Fenerbahçe/);
});

test("VAR, penaltı, kendi kalesine gol ve bilinmeyen olay", () => {
    assert.match(line({ incidentType: "varDecision", incidentClass: "goalNotAwarded", time: 30, isHome: true }, HOME), /iptal|geçersiz/);
    assert.match(line({ incidentType: "inGamePenalty", incidentClass: "missed", time: 17, isHome: true, player: "Mason Greenwood" }, HOME), /Mason Greenwood/);
    const og = line({ incidentType: "goal", incidentClass: "ownGoal", time: 12, isHome: true, homeScore: 1, awayScore: 0, player: "David Zima" }, HOME);
    assert.ok(templates.own_goal_for_fb.some(t => og.startsWith(t.split("{")[0])));
    assert.equal(line({ incidentType: "injuryTime", time: 45, length: 3 }, HOME), null);
    assert.equal(line(null, HOME), null);
});
