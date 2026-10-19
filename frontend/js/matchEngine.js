const pitchCanvas = document.getElementById("matchPitch");
const pCtx = pitchCanvas.getContext("2d");

function resizePitch() {
    if (!pitchCanvas || !pitchCanvas.clientWidth) return;
    pitchCanvas.width = pitchCanvas.clientWidth;
    pitchCanvas.height = pitchCanvas.clientHeight;
}
window.addEventListener('resize', resizePitch);

let matchState = 'idle';      // idle | attack_fb | midfield | attack_rival
let simMode = 'scheduled';    // scheduled | live | finished
let holdUntil = 0;            // gerçek bir olay gösterilirken akış yazısı değişmesin
let carrierIndex = -1;

// ---------- Diziliş ----------
function buildFormation(str, team) {
    let lines = String(str || '4-3-3').split('-').map(Number);
    if (lines.some(n => !(n > 0)) || lines.reduce((a, b) => a + b, 0) !== 10) lines = [4, 3, 3];
    const pts = [{ rx: 0.06, ry: 0.5, role: 'gk' }];
    lines.forEach((count, li) => {
        const rx = 0.17 + (lines.length > 1 ? li / (lines.length - 1) : 0) * 0.38;
        const role = li === 0 ? 'def' : (li === lines.length - 1 ? 'fwd' : 'mid');
        for (let k = 0; k < count; k++) pts.push({ rx, ry: (k + 1) / (count + 1), role });
    });
    return pts.map(p => ({ ...p, team, rx: team === 'fb' ? p.rx : 1 - p.rx }));
}

function makePlayers(fbForm, rivForm) {
    const w = pitchCanvas.width || 800;
    const h = pitchCanvas.height || 430;
    return [...buildFormation(fbForm, 'fb'), ...buildFormation(rivForm, 'rival')]
        .map(f => ({ ...f, x: f.rx * w, y: f.ry * h, offsetX: 0, offsetY: 0 }));
}

let players = makePlayers('4-3-3', '4-3-3');
let ball = { x: 400, y: 215, targetX: 400, targetY: 215 };

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

function pickCarrier(state) {
    const idx = (team, roles) => players
        .map((p, i) => i)
        .filter(i => players[i].team === team && roles.includes(players[i].role));
    let pool;
    if (state === 'attack_fb') pool = idx('fb', ['mid', 'fwd']);
    else if (state === 'attack_rival') pool = idx('rival', ['mid', 'fwd']);
    else pool = idx('fb', ['mid']).concat(idx('rival', ['mid']));
    return pool.length ? pool[Math.floor(Math.random() * pool.length)] : -1;
}

function pickState() {
    if (simMode !== 'live') return 'idle';
    const p = feed.fbPoss;            // gerçek topla oynama oranı
    const r = Math.random();
    if (r < p * 0.55) return 'attack_fb';
    if (r < p * 0.55 + (1 - p) * 0.55) return 'attack_rival';
    return 'midfield';
}

function idleCaption() {
    if (simMode === 'finished') return { ic: 'flag', text: 'Maç bitti.' };
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

// ---------- Gerçek veri akışı ----------
function newFeed(id) {
    return {
        id, timer: null, seen: null, fbIsHome: true, fbPoss: 0.5, hasStats: false,
        fbForm: null, rivForm: null, formKey: '', rivName: 'Rakip',
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
    players = makePlayers('4-3-3', '4-3-3');
    if (!feed.id) {
        setStatus('Canlı veri bağlantısı yok (maç verisi API’den gelmedi).');
        return;
    }
    simPoll();
    feed.timer = setInterval(simPoll, 20000);
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
    const m = d.match;
    f.fbIsHome = m.home === 'Fenerbahçe';
    f.rivName = f.fbIsHome ? m.away : m.home;
    simMode = m.status === 'live' ? 'live' : (m.status === 'finished' ? 'finished' : 'scheduled');
    applyStats(d.statistics);
    applyLineups(d.lineups);
    renderLineupTab(d.lineups, m);
    renderStatsTab(d.statistics, m);
    applyIncidents(d.incidents, m);
    applyScoreboard(m, d.incidents);
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
    const key = `${feed.fbForm}|${feed.rivForm}`;
    if (feed.fbForm && feed.rivForm && key !== feed.formKey) {
        feed.formKey = key;
        players = makePlayers(feed.fbForm, feed.rivForm);
        carrierIndex = -1;
    }
}

function incTime(i) {
    return (i.addedTime && i.addedTime < 100) ? `${i.time}+${i.addedTime}'` : `${i.time}'`;
}

function describeIncident(i, m) {
    const team = (i.isHome === null || i.isHome === undefined) ? '' : (i.isHome ? m.home : m.away);
    const who = i.player ? ` ${i.player}` : '';
    const t = incTime(i);
    switch (i.incidentType) {
        case 'goal':
            return { ic: 'ball', text: `GOL! ${t}${who} (${team}) • ${i.homeScore}-${i.awayScore}` };
        case 'card':
            return { ic: 'card', text: `${i.incidentClass === 'yellow' ? 'Sarı kart' : 'Kırmızı kart'} ${t}${who} (${team})` };
        case 'substitution':
            return { ic: 'swap', text: `${t} ${team} oyuncu değişikliği` };
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
    const base = [i.incidentType, i.incidentClass, i.time, i.addedTime, i.isHome, i.player].join('|');
    counts[base] = (counts[base] || 0) + 1;      // aynı dakikada iki değişiklik olabilir
    return base + '#' + counts[base];
}

function onNewEvent(i, m) {
    const ev = describeIncident(i, m);
    if (!ev) return;
    setStatus(ev);
    holdUntil = Date.now() + 9000;
    if (i.incidentType === 'goal') {
        matchState = (i.isHome === feed.fbIsHome) ? 'attack_fb' : 'attack_rival';
        carrierIndex = pickCarrier(matchState);
    }
}

function applyIncidents(list, m) {
    if (!list) return;
    const counts = {};
    const keyed = list.map(i => [incKey(i, counts), i]);   // liste yeniden eskiye sıralı geliyor
    if (feed.seen === null) {
        feed.seen = new Set(keyed.map(k => k[0]));
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

// ---------- Hareket ve çizim ----------
function updateSimulation() {
    const w = pitchCanvas.width || 800;
    const h = pitchCanvas.height || 430;

    let teamShiftX = 0;
    if (matchState === 'attack_fb') teamShiftX = w * 0.14;
    else if (matchState === 'attack_rival') teamShiftX = -w * 0.14;

    players.forEach((p, idx) => {
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

    if (matchState === 'idle' || carrierIndex < 0) {
        ball.targetX = w / 2;
        ball.targetY = h / 2;
    }

    ball.x += (ball.targetX - ball.x) * 0.12;
    ball.y += (ball.targetY - ball.y) * 0.12;
}

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
        fb: read('--c-accent'), rival: read('--c-pitch-rival'),
        outline: read('--c-navy-950'), ball: read('--c-text'),
    };
    probe.remove();
    return c;
}

function drawPitch() {
    const w = pitchCanvas.width;
    const h = pitchCanvas.height;
    if (!w || !h) return;
    if (!pitchColors) pitchColors = readPitchColors();
    const col = pitchColors;

    pCtx.clearRect(0, 0, w, h);

    pCtx.strokeStyle = col.line;
    pCtx.lineWidth = 2;

    pCtx.beginPath();
    pCtx.moveTo(w / 2, 0);
    pCtx.lineTo(w / 2, h);
    pCtx.stroke();

    pCtx.beginPath();
    pCtx.arc(w / 2, h / 2, 52, 0, Math.PI * 2);
    pCtx.stroke();

    pCtx.strokeRect(0, h / 2 - 90, 105, 180);
    pCtx.strokeRect(w - 105, h / 2 - 90, 105, 180);

    pCtx.fillStyle = col.area;
    pCtx.strokeRect(0, h / 2 - 42, 26, 84);
    pCtx.fillRect(0, h / 2 - 42, 26, 84);

    pCtx.strokeRect(w - 26, h / 2 - 42, 26, 84);
    pCtx.fillRect(w - 26, h / 2 - 42, 26, 84);

    players.forEach(p => {
        pCtx.beginPath();
        pCtx.arc(p.x, p.y, 9, 0, Math.PI * 2);
        pCtx.fillStyle = p.team === 'fb' ? col.fb : col.rival;
        pCtx.fill();
        pCtx.lineWidth = 2;
        pCtx.strokeStyle = col.outline;
        pCtx.stroke();
    });

    pCtx.beginPath();
    pCtx.arc(ball.x, ball.y, 5.5, 0, Math.PI * 2);
    pCtx.fillStyle = col.ball;
    pCtx.fill();
    pCtx.strokeStyle = col.outline;
    pCtx.stroke();
}

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