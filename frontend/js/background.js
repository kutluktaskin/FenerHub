const canvas = document.getElementById("bogaCanvas");
const context = canvas.getContext("2d");

function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
}

const frameCount = 400;  // frames klasöründeki kare sayısıyla aynı olmalı
const currentFrame = index => `./frames/frame_${(index + 1).toString().padStart(4, '0')}.jpg`;

const images = [];
const boga = { frame: 0 };
let finishedImages = 0;      // yüklenen + yüklenemeyen
let preloaderClosed = false;

// Yükleme ekranını kapatır. Birden fazla kez çağrılsa da bir kez çalışır.
function closePreloader() {
    if (preloaderClosed) return;
    preloaderClosed = true;
    resizeCanvas();
    renderBg();
    gsap.to("#preloader", {
        opacity: 0,
        duration: 0.6,
        onComplete: () => {
            document.getElementById("preloader").style.display = "none";
        }
    });
}

function onImageDone() {
    finishedImages++;
    if (finishedImages === frameCount) closePreloader();
}

for (let i = 0; i < frameCount; i++) {
    const img = new Image();
    img.onload = onImageDone;
    img.onerror = onImageDone;   // kare bulunamasa bile sayılır, sayfa takılmaz
    img.src = currentFrame(i);
    images.push(img);
}

// Güvenlik ağı: kareler 8 saniyede bitmezse sayfayı yine de aç
setTimeout(closePreloader, 8000);

gsap.registerPlugin(ScrollTrigger);

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

function renderBg() {
    const img = nearestLoaded(Math.round(boga.frame));
    if (!img) return;   // hiç kare yoksa arka plan düz renk kalır

    context.clearRect(0, 0, canvas.width, canvas.height);
    const scale = Math.max(canvas.width / img.width, canvas.height / img.height);
    const x = (canvas.width / 2) - (img.width / 2) * scale;
    const y = (canvas.height / 2) - (img.height / 2) * scale;
    context.drawImage(img, x, y, img.width * scale, img.height * scale);
}

window.addEventListener("resize", () => {
    resizeCanvas();
    renderBg();
});