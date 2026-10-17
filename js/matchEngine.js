const pitchCanvas = document.getElementById("matchPitch");
const pCtx = pitchCanvas.getContext("2d");

function resizePitch() {
    if (!pitchCanvas || !pitchCanvas.clientWidth) return;
    pitchCanvas.width = pitchCanvas.clientWidth;
    pitchCanvas.height = pitchCanvas.clientHeight;
}
window.addEventListener('resize', resizePitch);

let matchState = 'attack_fb';

const formations = [
    { rx: 0.06, ry: 0.50, role: 'gk', team: 'fb' },
    { rx: 0.18, ry: 0.18, role: 'def', team: 'fb' },
    { rx: 0.16, ry: 0.38, role: 'def', team: 'fb' },
    { rx: 0.16, ry: 0.62, role: 'def', team: 'fb' },
    { rx: 0.18, ry: 0.82, role: 'def', team: 'fb' },
    { rx: 0.34, ry: 0.30, role: 'mid', team: 'fb' },
    { rx: 0.30, ry: 0.50, role: 'mid', team: 'fb' },
    { rx: 0.34, ry: 0.70, role: 'mid', team: 'fb' },
    { rx: 0.52, ry: 0.20, role: 'fwd', team: 'fb' },
    { rx: 0.56, ry: 0.50, role: 'fwd', team: 'fb' },
    { rx: 0.52, ry: 0.80, role: 'fwd', team: 'fb' },

    { rx: 0.94, ry: 0.50, role: 'gk', team: 'rival' },
    { rx: 0.82, ry: 0.18, role: 'def', team: 'rival' },
    { rx: 0.84, ry: 0.38, role: 'def', team: 'rival' },
    { rx: 0.84, ry: 0.62, role: 'def', team: 'rival' },
    { rx: 0.82, ry: 0.82, role: 'def', team: 'rival' },
    { rx: 0.66, ry: 0.30, role: 'mid', team: 'rival' },
    { rx: 0.70, ry: 0.50, role: 'mid', team: 'rival' },
    { rx: 0.66, ry: 0.70, role: 'mid', team: 'rival' },
    { rx: 0.48, ry: 0.20, role: 'fwd', team: 'rival' },
    { rx: 0.44, ry: 0.50, role: 'fwd', team: 'rival' },
    { rx: 0.48, ry: 0.80, role: 'fwd', team: 'rival' }
];

let players = formations.map(f => ({
    ...f,
    x: f.rx * 800,
    y: f.ry * 430,
    offsetX: 0,
    offsetY: 0
}));

let ball = { x: 400, y: 215, targetX: 400, targetY: 215 };
let carrierIndex = 6;

setInterval(() => {
    const states = ['attack_fb', 'midfield', 'attack_rival', 'attack_fb'];
    matchState = states[Math.floor(Math.random() * states.length)];

    const statusText = document.getElementById('matchStatusText');
    if (statusText) {
        if (matchState === 'attack_fb') {
            statusText.innerText = "⚡ Fenerbahçe rakip kaleye doğru organize paslarla yükleniyor!";
            const fbIndices = [5, 6, 7, 8, 9, 10];
            carrierIndex = fbIndices[Math.floor(Math.random() * fbIndices.length)];
        } else if (matchState === 'attack_rival') {
            statusText.innerText = "⚠️ Rakip takım kontratağa kalktı, savunmamız yerleşiyor.";
            const rivalIndices = [16, 17, 18, 19, 20, 21];
            carrierIndex = rivalIndices[Math.floor(Math.random() * rivalIndices.length)];
        } else {
            statusText.innerText = "⚔️ Top orta alanda iki takım arasında karşılıklı paslarla el değiştiriyor.";
            const midIndices = [5, 6, 7, 16, 17, 18];
            carrierIndex = midIndices[Math.floor(Math.random() * midIndices.length)];
        }
    }

    players.forEach(p => {
        p.offsetX = (Math.random() - 0.5) * 40;
        p.offsetY = (Math.random() - 0.5) * 40;
    });
}, 2200);

function updateSimulation() {
    const w = pitchCanvas.width || 800;
    const h = pitchCanvas.height || 430;

    let teamShiftX = 0;
    if (matchState === 'attack_fb') teamShiftX = w * 0.14;
    else if (matchState === 'attack_rival') teamShiftX = -w * 0.14;

    players.forEach((p, idx) => {
        let shift = p.role === 'gk' ? teamShiftX * 0.12 : teamShiftX;
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

    ball.x += (ball.targetX - ball.x) * 0.12;
    ball.y += (ball.targetY - ball.y) * 0.12;
}

function drawPitch() {
    const w = pitchCanvas.width;
    const h = pitchCanvas.height;
    if (!w || !h) return;

    pCtx.clearRect(0, 0, w, h);

    pCtx.strokeStyle = "rgba(255, 255, 255, 0.45)";
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

    pCtx.fillStyle = "rgba(255, 255, 255, 0.15)";
    pCtx.strokeRect(0, h / 2 - 42, 26, 84);
    pCtx.fillRect(0, h / 2 - 42, 26, 84);

    pCtx.strokeRect(w - 26, h / 2 - 42, 26, 84);
    pCtx.fillRect(w - 26, h / 2 - 42, 26, 84);

    players.forEach(p => {
        pCtx.beginPath();
        pCtx.arc(p.x, p.y, 9, 0, Math.PI * 2);
        pCtx.fillStyle = p.team === 'fb' ? '#fcd116' : '#ff3333';
        pCtx.fill();
        pCtx.lineWidth = 2;
        pCtx.strokeStyle = '#001538';
        pCtx.stroke();
    });

    pCtx.beginPath();
    pCtx.arc(ball.x, ball.y, 5.5, 0, Math.PI * 2);
    pCtx.fillStyle = '#ffffff';
    pCtx.fill();
    pCtx.strokeStyle = '#000';
    pCtx.stroke();
}

function loop() {
    updateSimulation();
    drawPitch();
    requestAnimationFrame(loop);
}
loop();