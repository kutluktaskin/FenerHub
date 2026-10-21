/* 2D maç simülasyonu.
   Gerçek veri: skor, dakika, kadro (forma numarası ve isim), olaylar (gol, kart, değişiklik,
   VAR, penaltı) ve istatistikler. Veri /ws/live kanalından anında gelir; bağlantı yoksa
   /api/matches/{id}/detail 20 sn'de bir sorgulanır.
   Temsili: oyuncuların sahadaki konumları ve top akışı (API anlık konum vermez). Topla
   oynama oranı hangi takımın daha çok atakta görüneceğini belirler. */
const pitchCanvas = document.getElementById("matchPitch");
const pCtx = pitchCanvas.getContext("2d");
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)");

function resizePitch() {
    if (!pitchCanvas || !pitchCanvas.clientWidth) return;
    pitchCanvas.width = pitchCanvas.clientWidth;
    pitchCanvas.height = pitchCanvas.clientHeight;
}
window.addEventListener('resize', resizePitch);

let matchState = 'idle';      // idle | attack_fb | midfield | attack_rival
let simMode = 'scheduled';    // scheduled | live | finished
let holdUntil = 0;            // gerçek bir olay gösterilirken akış yazısı ve hareket değişmesin
let carrierIndex = -1;
let hoverIndex = -1;          // fareyle üzerine gelinen oyuncu (adı gösterilir)

// ---------- Diziliş ve kadro ----------
// Fenerbahçe soldan sağa, rakip sağdan sola hücum eder. API ilk 11'i kaleci, sonra her hat
// sağdan sola sıralı verir: sağa hücum edenin sağı sahanın altı, sola hücum edeninki üstü.
function buildFormation(str, team) {
    let lines = String(str || '4-3-3').split('-').map(Number);
    if (lines.some(n => !(n > 0)) || lines.reduce((a, b) => a + b, 0) !== 10) lines = [4, 3, 3];
    const pts = [{ rx: 0.06, ry: 0.5, role: 'gk' }];
    lines.forEach((count, li) => {
        const rx = 0.17 + (lines.length > 1 ? li / (lines.length - 1) : 0) * 0.38;
        const role = li === 0 ? 'def' : (li === lines.length - 1 ? 'fwd' : 'mid');
        for (let k = 0; k < count; k++) {
            const t = (k + 1) / (count + 1);
            pts.push({ rx, ry: team === 'fb' ? 1 - t : t, role });
        }
    });
    return pts.map(p => ({ ...p, team, rx: team === 'fb' ? p.rx : 1 - p.rx }));
}

function makePlayers(fbForm, rivForm, fbXI = [], rivXI = []) {
    const w = pitchCanvas.width || 800;
    const h = pitchCanvas.height || 430;
    const named = (pts, xi) => pts.map((p, i) => ({
        ...p,
        num: xi.length === 11 ? xi[i].number : null,
        name: xi.length === 11 ? xi[i].name : null,
    }));
    return [...named(buildFormation(fbForm, 'fb'), fbXI), ...named(buildFormation(rivForm, 'rival'), rivXI)]
        .map(f => ({ ...f, x: f.rx * w, y: f.ry * h, offsetX: 0, offsetY: 0,
                     card: null, out: false, alpha: 1, flashUntil: 0, tag: null, tagUntil: 0 }));
}

let players = makePlayers('4-3-3', '4-3-3');
let ball = { x: 400, y: 215, targetX: 400, targetY: 215, trail: [] };

const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
function findPlayer(name, team) {
    if (!name) return -1;
    const n = norm(name);
    return players.findIndex(p => !p.out && p.name && (!team || p.team === team) && norm(p.name) === n);
}

// ---------- Yardımcılar ----------
function setText(id, t) {
    const el = document.getElementById(id);
    if (el) el.innerText = t;
}
// t: düz metin ya da { ic: ikon adı, text }
function setStatus(t) {
    const el = document.getElementById('matchStatusText');
    if (!el) return;
    const { ic, text } = typeof t === 'string' ? { text: t } : t;
    el.innerHTML = (ic ? icon(ic) : '') + esc(text);
}
function setMinute(ic, text, live) {
    const el = document.getElementById('matchMinute');
    if (!el) return;
    el.innerHTML = icon(ic) + esc(text);
    el.classList.toggle('is-live', !!live);
}

function teamIndices(team, roles) {
    return players.map((p, i) => i)
        .filter(i => players[i].team === team && !players[i].out && (!roles || roles.includes(players[i].role)));
}

function pickCarrier(state) {
    let pool;
    if (state === 'attack_fb') pool = teamIndices('fb', ['mid', 'fwd']);
    else if (state === 'attack_rival') pool = teamIndices('rival', ['mid', 'fwd']);
    else pool = teamIndices('fb', ['mid']).concat(teamIndices('rival', ['mid']));
    return pool.length ? pool[Math.floor(Math.random() * pool.length)] : -1;
}

// Pas: top aynı takımda, çoğunlukla hücum yönündeki bir arkadaşa gider
function nextPass() {
    const cur = players[carrierIndex];
    if (!cur || cur.out) return pickCarrier(matchState);
    const dir = cur.team === 'fb' ? 1 : -1;
    const mates = teamIndices(cur.team).filter(i => i !== carrierIndex && players[i].role !== 'gk');
    if (!mates.length) return carrierIndex;
    const forward = mates.filter(i => (players[i].x - cur.x) * dir > -20);
    const pool = forward.length && Math.random() < 0.75 ? forward : mates;
    return pool[Math.floor(Math.random() * pool.length)];
}

const isHalftime = () => !!(feed.m && feed.m.status_code === 31);

function pickState() {
    if (simMode !== 'live' || isHalftime()) return 'idle';     // devre arasında oyun durur
    const p = feed.fbPoss;            // gerçek topla oynama oranı
    const r = Math.random();
    if (r < p * 0.55) return 'attack_fb';
    if (r < p * 0.55 + (1 - p) * 0.55) return 'attack_rival';
    return 'midfield';
}

function idleCaption() {
    if (simMode === 'finished') return { ic: 'flag', text: 'Maç bitti.' };
    if (isHalftime()) return { ic: 'pause', text: `Devre arası • ${feed.m.home} ${feed.m.home_score ?? 0} - ${feed.m.away_score ?? 0} ${feed.m.away}` };
    if (feed.fbForm && feed.rivForm) {
        return { ic: 'clock', text: `Maç başlamadı • Diziliş: Fenerbahçe ${feed.fbForm} • ${feed.rivName} ${feed.rivForm}` };
    }
    return { ic: 'clock', text: 'Maç başlamadı • İlk 11 genelde maçtan 30-60 dk önce açıklanır.' };
}

function captionFor(state) {
    if (state === 'idle') return idleCaption();
    const poss = feed.hasStats ? ` • Topla oynama: FB %${Math.round(feed.fbPoss * 100)}` : '';
    const [ic, base] = state === 'attack_fb' ? ['zap', 'Fenerbahçe rakip yarı sahada baskı kuruyor']
        : state === 'attack_rival' ? ['alert', 'Rakip takım atakta, savunmamız yerleşiyor']
        : ['swords', 'Oyun orta sahada'];
    return { ic, text: base + poss };
}

function jitter() {
    const amp = simMode === 'live' ? 40 : 14;
    players.forEach(p => {
        p.offsetX = (Math.random() - 0.5) * amp;
        p.offsetY = (Math.random() - 0.5) * amp;
    });
}

setInterval(() => {
    jitter();
    if (Date.now() < holdUntil) return;
    matchState = pickState();
    carrierIndex = matchState === 'idle' ? -1 : pickCarrier(matchState);
    setStatus(captionFor(matchState));
}, 2200);

setInterval(() => {
    if (simMode === 'live' && matchState !== 'idle' && Date.now() >= holdUntil) carrierIndex = nextPass();
}, 1100);

// Dakika her saniye ilerler (WS'ten mesaj gelmeyen dakikalarda da saat durmasın)
setInterval(() => {
    if (feed.m && feed.m.status === 'live') applyScoreboard(feed.m, feed.incidents);
}, 1000);

// ---------- Gerçek veri akışı ----------
function newFeed(id) {
    return {
        id, timer: null, seen: null, fbIsHome: true, fbPoss: 0.5, hasStats: false,
        fbForm: null, rivForm: null, formKey: '', rivName: 'Rakip', m: null, incidents: null,
        subNumbers: {}, ws: false,
    };
}
let feed = newFeed(null);

function simStartFeed(matchKey, meta) {
    if (feed.timer) clearInterval(feed.timer);
    feed = newFeed(meta && meta.id);
    simMode = 'scheduled';
    matchState = 'idle';
    carrierIndex = -1;
    holdUntil = 0;
    simFx = null;
    confetti = [];
    players = makePlayers('4-3-3', '4-3-3');
    hideBanner();
    pushFeed([], false);
    if (!feed.id) {
        setStatus('Canlı veri bağlantısı yok (maç verisi API’den gelmedi).');
        return;
    }
    simPoll();
    feed.timer = setInterval(() => { if (!feed.ws) simPoll(); }, 20000);
    connectLive();
}

async function simPoll() {
    const f = feed;
    let d;
    try {
        d = await apiGet(`/api/matches/${f.id}/detail`);
    } catch (e) {
        return;
    }
    if (f !== feed) return;           // bu arada başka maç açıldı
    applyDetail(d.match, d.incidents, d.statistics, d.lineups);
}

function applyDetail(m, incidents, statistics, lineups) {
    const f = feed;
    f.m = m;
    f.fbIsHome = m.home === 'Fenerbahçe';
    f.rivName = f.fbIsHome ? m.away : m.home;
    simMode = m.status === 'live' ? 'live' : (m.status === 'finished' ? 'finished' : 'scheduled');
    // Sadece skor/durum güncellemesi gelince (undefined) sekmelerdeki mevcut veri silinmesin
    if (statistics !== undefined) { applyStats(statistics); renderStatsTab(statistics, m); }
    if (lineups !== undefined) { applyLineups(lineups); renderLineupTab(lineups, m); }
    applyIncidents(incidents, m);
    applyScoreboard(m, incidents || f.incidents);
}

// /ws/live: backend'in izlediği maçın durumu ve değişiklikleri anında gelir (app/live.py)
let liveSock = null;
function connectLive() {
    if (liveSock || typeof API_BASE === 'undefined' || !('WebSocket' in window)) return;
    try {
        liveSock = new WebSocket(API_BASE.replace(/^http/, 'ws') + '/ws/live');
    } catch (e) {
        liveSock = null;
        return;
    }
    liveSock.onmessage = e => {
        try { onLiveMessage(JSON.parse(e.data)); } catch (err) { /* bozuk mesaj yok sayılır */ }
    };
    liveSock.onclose = () => {
        liveSock = null;
        feed.ws = false;
        // Simülasyon açıksa 10 sn sonra yeniden bağlan
        setTimeout(() => {
            if (feed.id && document.getElementById('simulasyonWrapper')?.classList.contains('open')) connectLive();
        }, 10000);
    };
}

let liveMatchId = null;
function onLiveMessage(d) {
    if (d.type === 'state') {
        liveMatchId = d.match_id;
        if (d.match_id !== feed.id || !d.match) return;
        feed.ws = d.source === 'ws' || d.source === 'rest';
        applyDetail(d.match, d.incidents, d.statistics, d.lineups);
        return;
    }
    if (liveMatchId !== feed.id) return;
    if (d.type === 'source') {
        feed.ws = d.source === 'ws' || d.source === 'rest';
    } else if (d.type === 'update' && feed.m) {
        if (d.kind === 'match') applyDetail(d.data);
        else if (d.kind === 'incidents') { applyIncidents(d.data, feed.m); applyScoreboard(feed.m, d.data); }
        else if (d.kind === 'statistics') { applyStats(d.data); renderStatsTab(d.data, feed.m); }
        else if (d.kind === 'lineups') { applyLineups(d.data); renderLineupTab(d.data, feed.m); }
    }
}

function applyScoreboard(m, incidents) {
    setText('simHomeTeam', m.home.toUpperCase());
    setText('simAwayTeam', m.away.toUpperCase());
    setText('simScore', m.home_score === null ? 'v' : `${m.home_score} - ${m.away_score}`);
    if (m.status === 'live') {
        const latest = incidents && incidents[0];
        if (latest && latest.incidentType === 'period' && latest.text === 'HT') {
            setMinute('pause', 'Devre arası', true);
        } else {
            const mn = (typeof liveMinute === 'function') ? liveMinute(m) : null;
            setMinute('radio', mn || 'Canlı', true);
        }
    } else if (m.status === 'finished') {
        setMinute('flag', 'Maç bitti');
    } else {
        setMinute('clock', 'Başlamadı');
    }
}

function applyStats(groups) {
    if (!groups) return;
    for (const g of groups) {
        for (const it of g.items) {
            if (it.key === 'ballPossession') {
                const h = parseInt(it.home, 10);
                const a = parseInt(it.away, 10);
                if (!isNaN(h) && !isNaN(a)) {
                    feed.fbPoss = (feed.fbIsHome ? h : a) / 100;
                    feed.hasStats = true;
                }
                return;
            }
        }
    }
}

function applyLineups(l) {
    if (!l) return;
    const fb = feed.fbIsHome ? l.home : l.away;
    const rv = feed.fbIsHome ? l.away : l.home;
    feed.fbForm = fb && fb.formation;
    feed.rivForm = rv && rv.formation;
    // Yedeklerin forma numarası: değişiklikte giren oyuncu bununla görünür
    [fb, rv].forEach(side => (side?.players || []).forEach(p => { feed.subNumbers[norm(p.name)] = p.number; }));
    const xi = side => (side?.players || []).filter(p => !p.substitute);
    const key = `${feed.fbForm}|${feed.rivForm}|${xi(fb).length}|${xi(rv).length}`;
    if (feed.fbForm && feed.rivForm && key !== feed.formKey) {
        feed.formKey = key;
        players = makePlayers(feed.fbForm, feed.rivForm, xi(fb), xi(rv));
        carrierIndex = -1;
        // Kadro yeniden kurulunca o ana kadarki kart ve değişiklikler tekrar işlenir
        if (feed.incidents) [...feed.incidents].reverse().forEach(i => applyIncidentState(i, false));
    }
}

function incTime(i) {
    return (i.addedTime && i.addedTime < 100) ? `${i.time}+${i.addedTime}'` : `${i.time}'`;
}

function describeIncident(i, m) {
    if (typeof i.time === 'number' && i.time < 0) return null;   // maç öncesi (ör. teknik ekibe kart)
    const team = (i.isHome === null || i.isHome === undefined) ? '' : (i.isHome ? m.home : m.away);
    const who = i.player ? ` ${i.player}` : '';
    const t = incTime(i);
    switch (i.incidentType) {
        case 'goal':
            return { ic: 'ball', text: `GOL! ${t}${who} (${team}) • ${i.homeScore}-${i.awayScore}` };
        case 'card':
            return { ic: 'card', text: `${i.incidentClass === 'yellow' ? 'Sarı kart' : 'Kırmızı kart'} ${t}${who} (${team})` };
        case 'substitution':
            return { ic: 'swap', text: `${t} ${team} değişiklik${i.playerIn ? ` • Giren: ${i.playerIn}` : ''}${i.playerOut ? ` • Çıkan: ${i.playerOut}` : ''}` };
        case 'varDecision':
            return { ic: 'tv', text: `${t} VAR incelemesi${who ? ' •' + who : ''}` };
        case 'inGamePenalty':
            return i.incidentClass === 'missed'
                ? { ic: 'x-circle', text: `${t} Penaltı kaçtı •${who}` }
                : { ic: 'target', text: `${t} Penaltı •${who}` };
        case 'period':
            if (i.text === 'HT') return { ic: 'pause', text: `Devre arası (${i.homeScore}-${i.awayScore})` };
            if (i.text === 'FT') return { ic: 'flag', text: `Maç sona erdi (${i.homeScore}-${i.awayScore})` };
            return null;
        default:
            return null;
    }
}

function incKey(i, counts) {
    const base = [i.incidentType, i.incidentClass, i.time, i.addedTime, i.isHome, i.player, i.playerIn].join('|');
    counts[base] = (counts[base] || 0) + 1;      // aynı dakikada iki değişiklik olabilir
    return base + '#' + counts[base];
}

const sideOf = i => (i.isHome === feed.fbIsHome ? 'fb' : 'rival');

// Olayın sahadaki kalıcı etkisi: kart, kırmızıda oyuncu çıkar, değişiklikte numara/isim değişir.
// animate=false: sayfa açılınca geçmiş olaylar sessizce uygulanır.
function applyIncidentState(i, animate) {
    if (i.isHome === null || i.isHome === undefined) return -1;
    const team = sideOf(i);
    if (i.incidentType === 'card') {
        const idx = findPlayer(i.player, team);
        if (idx < 0) return -1;
        const p = players[idx];
        const red = i.incidentClass !== 'yellow';
        p.card = red ? 'red' : (p.card === 'yellow' ? 'red' : 'yellow');
        if (p.card === 'red') {
            p.out = true;
            if (!animate) p.alpha = 0;
        }
        return idx;
    }
    if (i.incidentType === 'substitution') {
        const idx = findPlayer(i.playerOut, team);
        if (idx < 0 || !i.playerIn) return -1;
        const p = players[idx];
        p.name = i.playerIn;
        p.num = feed.subNumbers[norm(i.playerIn)] ?? p.num;
        p.card = null;
        return idx;
    }
    return -1;
}

function onNewEvent(i, m) {
    const ev = describeIncident(i, m);
    const idx = applyIncidentState(i, true);
    if (!ev) return;
    setStatus(ev);
    holdUntil = Date.now() + 9000;
    const team = (i.isHome === null || i.isHome === undefined) ? null : sideOf(i);
    const t = incTime(i);
    switch (i.incidentType) {
        case 'goal': {
            const fbGoal = team === 'fb';
            const scorer = findPlayer(i.player, team);
            startGoal(team, scorer);
            showBanner(fbGoal ? 'goal' : 'goal-rival', 'ball', 'GOL!',
                `${i.player ?? ''} ${t}${i.assist ? ` • Asist: ${i.assist}` : ''}`);
            pulseScore();
            break;
        }
        case 'card': {
            const red = idx >= 0 ? players[idx].card === 'red' : i.incidentClass !== 'yellow';
            const title = !red ? 'Sarı kart' : (i.incidentClass === 'yellow' ? 'İkinci sarıdan kırmızı' : 'Kırmızı kart');
            if (idx >= 0) {
                players[idx].flashUntil = Date.now() + 2500;
                tagPlayer(idx, red ? 'Kırmızı kart' : 'Sarı kart');
            }
            showBanner(red ? 'red' : 'yellow', 'card', title, `${i.player ?? ''} ${t}`);
            setStatus({ ic: 'card', text: `${title} ${t} ${i.player ?? ''} (${team === 'fb' ? 'Fenerbahçe' : feed.rivName})` });
            break;
        }
        case 'substitution':
            if (idx >= 0) tagPlayer(idx, `↑ ${i.playerIn}`);
            showBanner('sub', 'swap', 'Oyuncu değişikliği',
                `${i.playerIn ? '↑ ' + i.playerIn : ''}${i.playerOut ? '  ↓ ' + i.playerOut : ''}`);
            break;
        case 'varDecision':
            showBanner('var', 'tv', 'VAR incelemesi', `${i.player ?? ''} ${t}`);
            simFx = { type: 'var', start: performance.now(), dur: 3500 };
            break;
        case 'inGamePenalty':
            simFx = { type: 'penalty', start: performance.now(), dur: 2500, team };
            showBanner('var', 'target', i.incidentClass === 'missed' ? 'Penaltı kaçtı' : 'Penaltı', `${i.player ?? ''} ${t}`);
            break;
        case 'period':
            showBanner('period', i.text === 'HT' ? 'pause' : 'flag', i.text === 'HT' ? 'Devre arası' : 'Maç sona erdi',
                `${m.home} ${i.homeScore} - ${i.awayScore} ${m.away}`);
            break;
    }
    const secondYellow = i.incidentType === 'card' && i.incidentClass === 'yellow' && idx >= 0 && players[idx].card === 'red';
    const line = commentaryFor(i, m, secondYellow);
    if (line) {
        setStatus({ ic: ev.ic, text: line });
        pushFeed([{ i, ic: ev.ic, text: line }], true);
    }
}

// ---------- Anlatım (js/commentary.js) ----------
function commentaryFor(i, m, secondYellow) {
    if (!window.Commentary) return null;
    return Commentary.line(i, { home: m.home, away: m.away, fbIsHome: feed.fbIsHome, secondYellow });
}

const FEED_MAX = 8;
// Akışa satır ekler (yeni olay en üste); prepend=false: listeyi baştan kurar
function pushFeed(items, prepend) {
    const el = document.getElementById('simFeed');
    if (!el) return;
    const html = items.map(({ i, ic, text }) => `<li class="sim-feed-${esc(i.incidentType)}">
        <span class="sim-feed-min">${esc(incTime(i))}</span>${icon(ic)}<span>${esc(text)}</span></li>`).join('');
    if (prepend) el.insertAdjacentHTML('afterbegin', html);
    else el.innerHTML = html;
    while (el.children.length > FEED_MAX) el.lastElementChild.remove();
    el.hidden = !el.children.length;
}

// Sayfa açılınca o ana kadarki olayların anlatımı (ikinci sarılar sırayla sayılarak)
function feedFromHistory(list, m) {
    const yellows = {};
    const items = [];
    [...list].reverse().forEach(i => {
        let second = false;
        if (i.incidentType === 'card' && i.incidentClass === 'yellow' && i.player) {
            const k = `${i.isHome}|${norm(i.player)}`;
            yellows[k] = (yellows[k] || 0) + 1;
            second = yellows[k] === 2;
        }
        const ev = describeIncident(i, m);
        const text = ev && commentaryFor(i, m, second);
        if (text) items.push({ i, ic: ev.ic, text });
    });
    pushFeed(items.reverse().slice(0, FEED_MAX), false);
}

function applyIncidents(list, m) {
    if (!list) return;
    feed.incidents = list;
    const counts = {};
    const keyed = list.map(i => [incKey(i, counts), i]);   // liste yeniden eskiye sıralı geliyor
    if (feed.seen === null) {
        feed.seen = new Set(keyed.map(k => k[0]));
        [...list].reverse().forEach(i => applyIncidentState(i, false));
        feedFromHistory(list, m);
        const last = keyed.map(k => describeIncident(k[1], m)).find(Boolean);
        if (last) {
            setStatus({ ic: last.ic, text: 'Son olay: ' + last.text });
            holdUntil = Date.now() + 6000;
        }
        return;
    }
    keyed.filter(k => !feed.seen.has(k[0])).reverse().forEach(([k, i]) => {
        feed.seen.add(k);
        onNewEvent(i, m);
    });
}

// ---------- Olay efektleri ----------
let simFx = null;            // { type: goal | var | penalty, start, dur, ... }
let confetti = [];

function tagPlayer(idx, text) {
    players[idx].tag = text;
    players[idx].tagUntil = Date.now() + 4500;
}

function startGoal(team, scorerIdx) {
    const w = pitchCanvas.width || 800, h = pitchCanvas.height || 430;
    const from = scorerIdx >= 0 ? players[scorerIdx] : { x: team === 'fb' ? w * 0.78 : w * 0.22, y: h / 2 };
    if (scorerIdx >= 0) tagPlayer(scorerIdx, 'GOL!');
    simFx = {
        type: 'goal', team, start: performance.now(), dur: 4200,
        fromX: from.x, fromY: from.y, toX: team === 'fb' ? w - 4 : 4, toY: h / 2 + (Math.random() - 0.5) * 50,
    };
    matchState = team === 'fb' ? 'attack_fb' : 'attack_rival';
    carrierIndex = -1;
    if (REDUCED.matches) return;
    const colors = team === 'fb' ? ['#ffd200', '#ffe866', '#1e3f9a', '#ffffff'] : [rivalColor(), '#ffffff'];
    for (let k = 0; k < 90; k++) {
        confetti.push({
            x: simFx.toX, y: simFx.toY, vx: (team === 'fb' ? -1 : 1) * (1 + Math.random() * 6),
            vy: -3 - Math.random() * 6, rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4,
            c: colors[k % colors.length], life: 1, delay: 700 + Math.random() * 300,
        });
    }
}

function pulseScore() {
    const el = document.getElementById('simScore');
    if (!el) return;
    el.classList.remove('is-goal');
    void el.offsetWidth;                 // animasyonu yeniden başlat
    el.classList.add('is-goal');
}

let bannerTimer = null;
function showBanner(kind, ic, title, sub) {
    const el = document.getElementById('simBanner');
    if (!el) return;
    el.className = `sim-banner is-${kind}`;
    el.innerHTML = `${icon(ic)}<b>${esc(title)}</b>${sub ? `<span>${esc(sub)}</span>` : ''}`;
    el.hidden = false;
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(hideBanner, kind.startsWith('goal') ? 5000 : 3800);
}
function hideBanner() {
    const el = document.getElementById('simBanner');
    if (el) el.hidden = true;
}

// ---------- Hareket ----------
function updateSimulation() {
    const w = pitchCanvas.width || 800;
    const h = pitchCanvas.height || 430;

    let teamShiftX = 0;
    if (matchState === 'attack_fb') teamShiftX = w * 0.14;
    else if (matchState === 'attack_rival') teamShiftX = -w * 0.14;

    players.forEach((p, idx) => {
        // Kırmızı kart: oyuncu sönerek sahadan çıkar
        if (p.out) { p.alpha = Math.max(0, p.alpha - 0.012); return; }
        const shift = p.role === 'gk' ? teamShiftX * 0.12 : teamShiftX;
        let targetX = (p.rx * w) + shift + p.offsetX;
        let targetY = (p.ry * h) + p.offsetY;

        targetX = Math.max(35, Math.min(w - 35, targetX));
        targetY = Math.max(25, Math.min(h - 25, targetY));

        p.x += (targetX - p.x) * 0.04;
        p.y += (targetY - p.y) * 0.04;

        if (idx === carrierIndex) {
            ball.targetX = p.x + (p.team === 'fb' ? 12 : -12);
            ball.targetY = p.y;
        }
    });

    if (simFx && simFx.type === 'goal') {
        // Top atan oyuncudan kaleye uçar, sonra ağda kalır
        const t = Math.min(1, (performance.now() - simFx.start) / 700);
        const e = 1 - (1 - t) ** 3;
        ball.x = simFx.fromX + (simFx.toX - simFx.fromX) * e;
        ball.y = simFx.fromY + (simFx.toY - simFx.fromY) * e - Math.sin(Math.PI * t) * 28;
    } else if (simFx && simFx.type === 'penalty') {
        ball.x += ((simFx.team === 'fb' ? w - 70 : 70) - ball.x) * 0.15;
        ball.y += (h / 2 - ball.y) * 0.15;
    } else {
        if (matchState === 'idle' || carrierIndex < 0) {
            ball.targetX = w / 2;
            ball.targetY = h / 2;
        }
        ball.x += (ball.targetX - ball.x) * 0.12;
        ball.y += (ball.targetY - ball.y) * 0.12;
    }
    ball.trail.push([ball.x, ball.y]);
    if (ball.trail.length > 8) ball.trail.shift();

    if (simFx && performance.now() - simFx.start > simFx.dur) {
        simFx = null;
        ball.x = w / 2; ball.y = h / 2;
    }
    const now = performance.now();
    confetti.forEach(c => {
        if (now - (c.start ??= now) < c.delay) return;
        c.x += c.vx; c.y += c.vy; c.vy += 0.18; c.vx *= 0.99; c.rot += c.vr; c.life -= 0.009;
    });
    confetti = confetti.filter(c => c.life > 0 && c.y < h + 20);
}

// ---------- Çizim ----------
// Saha renkleri style.css token'larından okunur (kanvas var() anlamaz).
// Gizli bir öğeye uygulanıp çözümlenmiş rgb değeri alınır; ilk çizimde bir kez yapılır.
let pitchColors = null;
function readPitchColors() {
    const probe = document.createElement('span');
    probe.style.display = 'none';
    document.body.append(probe);
    const read = name => {
        probe.style.color = `var(${name})`;
        return getComputedStyle(probe).color;
    };
    const c = {
        line: read('--c-pitch-line'), area: read('--c-pitch-area'),
        fb: read('--c-accent'), fbInk: read('--c-accent-ink'), rival: read('--c-pitch-rival'),
        outline: read('--c-navy-950'), ball: read('--c-text'),
    };
    probe.remove();
    return c;
}

// Rakip forma rengi: kulübün API rengi (beyaz/siyah/gri ise varsayılan kırmızı)
function rivalColor() {
    const c = typeof teamAccent === 'function' ? teamAccent(feed.rivName) : null;
    return c || (pitchColors && pitchColors.rival) || '#e5484d';
}
function inkFor(color) {
    const rgb = typeof hexRGB === 'function' ? hexRGB(color) : null;
    return rgb && typeof relLum === 'function' && relLum(rgb) > 0.35 ? '#061233' : '#ffffff';
}

function roundRect(x, y, w, h, r) {
    pCtx.beginPath();
    pCtx.moveTo(x + r, y);
    pCtx.arcTo(x + w, y, x + w, y + h, r);
    pCtx.arcTo(x + w, y + h, x, y + h, r);
    pCtx.arcTo(x, y + h, x, y, r);
    pCtx.arcTo(x, y, x + w, y, r);
    pCtx.closePath();
}

function drawTag(x, y, text, bg, fg) {
    pCtx.font = '600 11px Inter, system-ui, sans-serif';
    const tw = pCtx.measureText(text).width + 12;
    roundRect(x - tw / 2, y - 30, tw, 18, 6);
    pCtx.fillStyle = bg;
    pCtx.fill();
    pCtx.fillStyle = fg;
    pCtx.textAlign = 'center';
    pCtx.textBaseline = 'middle';
    pCtx.fillText(text, x, y - 21);
}

// Saha çizgilerinin ölçüleri (800x430 sahada eski sabit değerlerle aynı)
function pitchBoxes(w, h) {
    return {
        circle: Math.min(w, h) * 0.12,
        bigW: w * 0.13, bigH: Math.min(h * 0.42, w * 0.3),
        goalW: w * 0.033, goalH: Math.min(h * 0.2, w * 0.14),
    };
}

function drawPitch() {
    const w = pitchCanvas.width;
    const h = pitchCanvas.height;
    if (!w || !h) return;
    if (!pitchColors) pitchColors = readPitchColors();
    const col = pitchColors;
    const now = Date.now();

    pCtx.clearRect(0, 0, w, h);

    // Çim şeritleri
    pCtx.fillStyle = 'rgba(255,255,255,0.025)';
    for (let k = 0; k < 12; k += 2) pCtx.fillRect((w / 12) * k, 0, w / 12, h);

    pCtx.strokeStyle = col.line;
    pCtx.lineWidth = 2;
    pCtx.beginPath();
    pCtx.moveTo(w / 2, 0);
    pCtx.lineTo(w / 2, h);
    pCtx.stroke();
    const box = pitchBoxes(w, h);
    pCtx.beginPath();
    pCtx.arc(w / 2, h / 2, box.circle, 0, Math.PI * 2);
    pCtx.stroke();
    pCtx.strokeRect(0, h / 2 - box.bigH / 2, box.bigW, box.bigH);
    pCtx.strokeRect(w - box.bigW, h / 2 - box.bigH / 2, box.bigW, box.bigH);
    pCtx.fillStyle = col.area;
    pCtx.strokeRect(0, h / 2 - box.goalH / 2, box.goalW, box.goalH);
    pCtx.fillRect(0, h / 2 - box.goalH / 2, box.goalW, box.goalH);
    pCtx.strokeRect(w - box.goalW, h / 2 - box.goalH / 2, box.goalW, box.goalH);
    pCtx.fillRect(w - box.goalW, h / 2 - box.goalH / 2, box.goalW, box.goalH);

    // Gol: ağ parlar
    if (simFx && simFx.type === 'goal') {
        const t = (performance.now() - simFx.start) / simFx.dur;
        const gx = simFx.team === 'fb' ? w - box.goalW : 0;
        pCtx.fillStyle = `rgba(255,210,0,${0.55 * Math.max(0, 1 - t) * (0.6 + 0.4 * Math.sin(t * 40))})`;
        pCtx.fillRect(gx, h / 2 - box.goalH / 2, box.goalW, box.goalH);
    }

    const rivFill = rivalColor();
    const rivInk = inkFor(rivFill);
    players.forEach((p, idx) => {
        if (p.alpha <= 0) return;
        pCtx.globalAlpha = p.alpha;
        const r = 11;
        if (p.flashUntil > now) {
            pCtx.beginPath();
            pCtx.arc(p.x, p.y, r + 6 + Math.sin(now / 90) * 2, 0, Math.PI * 2);
            pCtx.fillStyle = p.card === 'yellow' ? 'rgba(255,210,0,0.35)' : 'rgba(229,72,77,0.4)';
            pCtx.fill();
        }
        pCtx.beginPath();
        pCtx.arc(p.x, p.y, r, 0, Math.PI * 2);
        pCtx.fillStyle = p.team === 'fb' ? col.fb : rivFill;
        pCtx.fill();
        pCtx.lineWidth = 2;
        pCtx.strokeStyle = idx === hoverIndex ? '#ffffff' : col.outline;
        pCtx.stroke();
        if (p.num !== null && p.num !== undefined) {
            pCtx.fillStyle = p.team === 'fb' ? col.fbInk : rivInk;
            pCtx.font = '700 10px Inter, system-ui, sans-serif';
            pCtx.textAlign = 'center';
            pCtx.textBaseline = 'middle';
            pCtx.fillText(String(p.num), p.x, p.y + 0.5);
        }
        if (p.card) {
            pCtx.fillStyle = p.card === 'yellow' ? '#ffd200' : '#e5484d';
            pCtx.fillRect(p.x + 6, p.y - 15, 6, 8);
        }
        if (p.tag && p.tagUntil > now) drawTag(p.x, p.y, p.tag, 'rgba(4,11,34,0.88)', '#ffd200');
        else if (idx === hoverIndex && p.name) drawTag(p.x, p.y, `${p.num ?? ''} ${p.name}`.trim(), 'rgba(4,11,34,0.88)', '#ffffff');
        pCtx.globalAlpha = 1;
    });

    // Top ve izi
    ball.trail.forEach(([x, y], k) => {
        pCtx.beginPath();
        pCtx.arc(x, y, 1.5 + k * 0.4, 0, Math.PI * 2);
        pCtx.fillStyle = `rgba(255,255,255,${0.04 * k})`;
        pCtx.fill();
    });
    pCtx.beginPath();
    pCtx.arc(ball.x, ball.y, 5.5, 0, Math.PI * 2);
    pCtx.fillStyle = col.ball;
    pCtx.fill();
    pCtx.lineWidth = 2;
    pCtx.strokeStyle = col.outline;
    pCtx.stroke();

    confetti.forEach(c => {
        if (c.start === undefined || performance.now() - c.start < c.delay) return;
        pCtx.save();
        pCtx.globalAlpha = Math.max(0, c.life);
        pCtx.translate(c.x, c.y);
        pCtx.rotate(c.rot);
        pCtx.fillStyle = c.c;
        pCtx.fillRect(-3, -2, 6, 4);
        pCtx.restore();
    });

    // VAR: saha kararır, üstte tarama çizgisi
    if (simFx && simFx.type === 'var') {
        const t = (performance.now() - simFx.start) / simFx.dur;
        pCtx.fillStyle = 'rgba(4,11,34,0.45)';
        pCtx.fillRect(0, 0, w, h);
        pCtx.fillStyle = 'rgba(120,180,255,0.35)';
        pCtx.fillRect(0, (t * 3 % 1) * h, w, 3);
    }
}

// Fareyle üzerine gelinen oyuncunun adı görünür (dokunmatikte dokununca)
function pointerAt(e) {
    const r = pitchCanvas.getBoundingClientRect();
    const x = (e.clientX - r.left) * (pitchCanvas.width / r.width);
    const y = (e.clientY - r.top) * (pitchCanvas.height / r.height);
    let best = -1, bestD = 18 * 18;
    players.forEach((p, i) => {
        if (p.out || !p.name) return;
        const d = (p.x - x) ** 2 + (p.y - y) ** 2;
        if (d < bestD) { bestD = d; best = i; }
    });
    hoverIndex = best;
    pitchCanvas.style.cursor = best >= 0 ? 'pointer' : '';
}
pitchCanvas.addEventListener('pointermove', pointerAt);
pitchCanvas.addEventListener('pointerdown', pointerAt);
pitchCanvas.addEventListener('pointerleave', () => { hoverIndex = -1; });

function loop() {
    updateSimulation();
    drawPitch();
    requestAnimationFrame(loop);
}
loop();

// ---------- İlk 11 ve istatistik sekmeleri ----------
function renderLineupTab(l, m) {
    const el = document.getElementById('lineupBody');
    if (!el) return;
    if (!l) {
        el.innerHTML = '<p class="muted">İlk 11 henüz açıklanmadı. Genelde maçtan 30-60 dk önce gelir.</p>';
        return;
    }
    const row = p => `<div class="lu-row">
        <span class="lu-num">${esc(p.number ?? '-')}</span>
        <span class="lu-name">${esc(p.name)}</span>
        <span class="lu-pos">${esc(p.position ?? '')}</span>
    </div>`;
    const col = (name, side, fb) => {
        const players = (side && side.players) || [];
        const starters = players.filter(p => !p.substitute);
        const subs = players.filter(p => p.substitute);
        return `<div class="lu-col${fb ? ' is-fb' : ''}">
            <div class="lu-head">${esc(name)} <span>${esc((side && side.formation) || '-')}</span></div>
            ${starters.map(row).join('')}
            <div class="lu-subs">Yedekler</div>
            ${subs.map(row).join('')}
        </div>`;
    };
    el.innerHTML = `<div class="lu-grid">
        ${col(m.home, l.home, m.home === 'Fenerbahçe')}
        ${col(m.away, l.away, m.away === 'Fenerbahçe')}
    </div>`;
}

function renderStatsTab(groups, m) {
    const el = document.getElementById('statsBody');
    if (!el) return;
    if (!groups) {
        el.innerHTML = '<p class="muted">Maç başladığında istatistikler burada görünür.</p>';
        return;
    }
    const items = {};
    groups.forEach(g => g.items.forEach(it => {
        const k = it.key || it.name;
        if (!(k in items)) items[k] = it;
    }));
    const byName = re => Object.values(items).find(it => re.test(it.name || ''));

    const wanted = [
        [items.ballPossession, 'Topla Oynama'],
        [items.expectedGoals, 'Beklenen Gol (xG)'],
        [items.totalShotsOnGoal, 'Toplam Şut'],
        [items.shotsOnGoal, 'İsabetli Şut'],
        [items.bigChanceCreated, 'Büyük Pozisyon'],
        [byName(/^corner/i), 'Korner'],
        [byName(/^fouls?$/i), 'Faul'],
        [byName(/^offsides?$/i), 'Ofsayt'],
        [items.goalkeeperSaves, 'Kurtarış'],
    ].filter(w => w[0]);

    const num = v => parseFloat(String(v).replace(',', '.')) || 0;
    const fbHome = m.home === 'Fenerbahçe';

    el.innerHTML = wanted.map(([it, label]) => {
        const fbTxt = fbHome ? it.home : it.away;
        const rvTxt = fbHome ? it.away : it.home;
        const a = num(fbTxt), b = num(rvTxt);
        const pct = (a + b) > 0 ? Math.round(a / (a + b) * 100) : 50;
        return `<div class="stats-row">
            <div class="stats-label"><span>${esc(fbTxt)}</span><span>${label}</span><span>${esc(rvTxt)}</span></div>
            <div class="stats-bar-bg"><div class="stats-bar-fb" style="width:${pct}%;"></div></div>
        </div>`;
    }).join('') + `<p class="muted small">Sol: Fenerbahçe • Sağ: ${esc(fbHome ? m.away : m.home)}</p>`;
}
