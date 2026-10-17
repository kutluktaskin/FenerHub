const canvas = document.getElementById("bogaCanvas");
const context = canvas.getContext("2d");

function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
}

const frameCount = 400; 
const currentFrame = index => `./frames/frame_${(index + 1).toString().padStart(4, '0')}.jpg`;

const images = [];
const boga = { frame: 0 };
let loadedImages = 0;

for (let i = 0; i < frameCount; i++) {
    const img = new Image();
    img.src = currentFrame(i);
    img.onload = () => {
        loadedImages++;
        if (loadedImages === frameCount) {
            gsap.to("#preloader", {
                opacity: 0, 
                duration: 0.6, 
                onComplete: () => {
                    document.getElementById("preloader").style.display = "none";
                    resizeCanvas();
                    renderBg();
                }
            });
        }
    };
    images.push(img);
}

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

function renderBg() {
    const img = images[Math.round(boga.frame)];
    if (!img || !img.complete) return; 

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