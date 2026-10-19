/* Arka plan: kaydırmaya bağlı boğa/stadyum animasyonu (frames/ klasöründeki kareler).
   - Yükleme ekranı yok: sayfa kareleri beklemeden açılır, arka plan ilk kare çizilince belirir.
   - Kalan kareler arka planda kademeli yüklenir: önce seyrek (her 16. kare), sonra aradakiler.
     Böylece kaydırırken her yerde yakın bir kare hazır olur.
   - Mobilde / veri tasarrufunda 4 karede bir kare kullanılır (400 yerine 100).
   - prefers-reduced-motion açıkken tek sabit kare gösterilir, animasyon yok. */
const canvas = document.getElementById("bogaCanvas");
const context = canvas.getContext("2d");

const TOTAL_FRAMES = 400;   // frames klasöründeki kare sayısıyla aynı olmalı
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const saveData = !!(navigator.connection && navigator.connection.saveData);
const smallScreen = window.matchMedia("(max-width: 768px), (pointer: coarse)").matches;

// Kullanılan kareler: masaüstünde hepsi, mobilde 4'te 1, hareket azaltmada tek kare
const STEP = reduceMotion ? TOTAL_FRAMES : (smallScreen || saveData ? 4 : 1);
const frameCount = Math.ceil(TOTAL_FRAMES / STEP);
const STATIC_FRAME = 0;     // hareket azaltmada gösterilecek kare
const frameSrc = i => `./frames/frame_${(i * STEP + 1).toString().padStart(4, "0")}.jpg`;

const images = new Array(frameCount);
const boga = { frame: 0 };

function resizeCanvas() {
    // Görüntü zaten bulanık; yüksek DPI'da çizmek gereksiz iş
    const dpr = Math.min(window.devicePixelRatio || 1, 1.25);
    canvas.width = Math.round(window.innerWidth * dpr);
    canvas.height = Math.round(window.innerHeight * dpr);
}

// İstenen kare yoksa en yakın yüklenmiş kareyi bulur
function nearestLoaded(index) {
    for (let d = 0; d < frameCount; d++) {
        for (const i of [index - d, index + d]) {
            const img = images[i];
            if (img && img.complete && img.naturalWidth > 0) return img;
        }
    }
    return null;
}

let drawn = null;
function renderBg() {
    const img = nearestLoaded(Math.round(boga.frame));
    if (!img) return;   // hiç kare yoksa arka plan düz renk kalır
    drawn = img;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const scale = Math.max(canvas.width / img.width, canvas.height / img.height);
    const x = canvas.width / 2 - (img.width / 2) * scale;
    const y = canvas.height / 2 - (img.height / 2) * scale;
    context.drawImage(img, x, y, img.width * scale, img.height * scale);
}

// Yeni yüklenen kare ekrandakinden daha yakınsa yeniden çiz (karede bir kez)
let redrawQueued = false;
function maybeRedraw() {
    if (redrawQueued) return;
    redrawQueued = true;
    requestAnimationFrame(() => {
        redrawQueued = false;
        if (nearestLoaded(Math.round(boga.frame)) !== drawn) renderBg();
    });
}

function loadFrame(i, priority = "low") {
    return new Promise(resolve => {
        if (images[i]) return resolve();
        const img = new Image();
        img.decoding = "async";
        if ("fetchPriority" in img) img.fetchPriority = priority;
        img.onload = () => { maybeRedraw(); resolve(); };
        img.onerror = resolve;      // kare bulunamasa bile sıra takılmaz
        img.src = frameSrc(i);
        images[i] = img;
    });
}

// Kademeli yükleme sırası: 0, 16, 32, ... sonra 8, 24, ... sonra 4, 12, ... en sonda hepsi
function loadOrder() {
    const order = [];
    const seen = new Set();
    for (let gap = 16; gap >= 1; gap /= 2) {
        for (let i = 0; i < frameCount; i += gap) {
            if (!seen.has(i)) { seen.add(i); order.push(i); }
        }
    }
    return order;
}

// Aynı anda en fazla birkaç istek: sayfanın asıl verisi (API, fontlar) beklemesin
async function loadRest(order, parallel = 4) {
    let next = 0;
    const worker = async () => {
        while (next < order.length) await loadFrame(order[next++]);
    };
    await Promise.all(Array.from({ length: parallel }, worker));
}

const idle = window.requestIdleCallback || (cb => setTimeout(cb, 200));

resizeCanvas();

// İlk kare <head>'deki preload ile zaten iniyor; çizilince arka plan belirir
const firstFrame = reduceMotion ? STATIC_FRAME : 0;
loadFrame(firstFrame, "high").then(() => {
    renderBg();
    canvas.classList.add("is-ready");
    if (!reduceMotion) idle(() => loadRest(loadOrder()));
});

gsap.registerPlugin(ScrollTrigger);   // main.js ScrollTrigger.refresh() kullanıyor
if (!reduceMotion) {
    gsap.to(boga, {
        frame: frameCount - 1,
        snap: "frame",
        ease: "none",
        scrollTrigger: {
            scrub: 1,
            start: "top top",
            end: "bottom bottom"
        },
        onUpdate: renderBg
    });
}

window.addEventListener("resize", () => {
    resizeCanvas();
    renderBg();
});
