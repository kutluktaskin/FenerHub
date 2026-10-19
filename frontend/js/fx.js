/* Arayüz efektleri: ilerleyici geliştirme. Tarayıcı bir özelliği desteklemiyorsa
   sayfa aynı içeriği animasyonsuz gösterir; hiçbir veri bu dosyaya bağlı değildir.
   - Kaydırınca belirme: CSS animation-timeline: view(), yoksa IntersectionObserver
   - Sayarak gelme: [data-count] öğeleri görünür olunca 0'dan hedefe sayar
   - Popover: [popover].fx-pop öğelerini açan butonun yanına yerleştirir
   - Geçiş: View Transitions API varsa DOM değişikliğini animasyonla yapar */
(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const motionOK = () => !reduceMotion.matches;
  const root = document.documentElement;

  // ---- Kaydırınca belirme ----
  const cssScrollTimeline = window.CSS && CSS.supports("animation-timeline: view()");
  if (!cssScrollTimeline && motionOK() && "IntersectionObserver" in window) {
    root.classList.add("js-reveal");
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) { e.target.classList.add("is-visible"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    document.querySelectorAll(".reveal").forEach(el => io.observe(el));
  }

  // ---- Sayarak gelme ----
  const ease = t => 1 - Math.pow(1 - t, 3);
  function runCount(el) {
    const target = Number(el.dataset.count);
    const prefix = el.dataset.prefix || "", suffix = el.dataset.suffix || "";
    if (!Number.isFinite(target) || !motionOK()) { el.textContent = prefix + target + suffix; return; }
    const dur = 900, t0 = performance.now();
    const step = now => {
      const t = Math.min(1, (now - t0) / dur);
      el.textContent = prefix + Math.round(target * ease(t)) + suffix;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  const countIO = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) { countIO.unobserve(e.target); runCount(e.target); }
    });
  }, { threshold: 0.6 }) : null;

  // Bir kapsayıcıdaki [data-count] öğelerini izle (içerik veriden çizildikten sonra çağrılır).
  // Aynı öğe ikinci kez sayılmaz; yenilemelerde sayı doğrudan yazılır.
  function observeCounts(container) {
    (container || document).querySelectorAll("[data-count]:not([data-counted])").forEach(el => {
      el.dataset.counted = "1";
      if (!countIO || !motionOK()) { runCount(el); return; }
      el.textContent = (el.dataset.prefix || "") + "0" + (el.dataset.suffix || "");
      countIO.observe(el);
    });
  }

  // ---- Popover yerleşimi ----
  const popoverOK = typeof HTMLElement !== "undefined" && HTMLElement.prototype.hasOwnProperty("popover");
  if (!popoverOK) root.classList.add("no-popover");

  function placePopover(pop) {
    const invoker = document.querySelector(`[popovertarget="${pop.id}"]`);
    if (!invoker) return;
    const r = invoker.getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight, gap = 8;
    const vw = document.documentElement.clientWidth, vh = window.innerHeight;
    let top = r.bottom + gap;
    if (top + ph > vh - gap && r.top - gap - ph > gap) top = r.top - gap - ph;   // altta yer yoksa üstte
    const left = Math.min(Math.max(gap, r.left + r.width / 2 - pw / 2), vw - pw - gap);
    pop.style.top = `${Math.round(top)}px`;
    pop.style.left = `${Math.round(left)}px`;
  }
  if (popoverOK) {
    // toggle olayı kabarcıklanmaz; yakalama aşamasında dinlenir
    document.addEventListener("toggle", e => {
      if (e.target.matches && e.target.matches(".fx-pop") && e.newState === "open") placePopover(e.target);
    }, true);
    // Sabit konumlu popover kaydırmada butondan kopmasın: kaydırınca kapanır
    window.addEventListener("scroll", () => {
      document.querySelectorAll(".fx-pop:popover-open").forEach(p => p.hidePopover());
    }, { passive: true, capture: true });
  }

  // ---- Ekran dışındaki sürekli animasyonları duraklat (data-pause-offscreen) ----
  if ("IntersectionObserver" in window) {
    const pauseIO = new IntersectionObserver(entries => {
      entries.forEach(e => e.target.classList.toggle("is-paused", !e.isIntersecting));
    });
    document.querySelectorAll("[data-pause-offscreen]").forEach(el => pauseIO.observe(el));
  }

  // ---- Görünüm geçişi ----
  function transition(update) {
    if (!document.startViewTransition || !motionOK()) { update(); return; }
    document.startViewTransition(update);
  }

  window.fx = { observeCounts, transition, popoverOK, motionOK };
})();
