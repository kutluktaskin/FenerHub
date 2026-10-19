/* Menü: tek sayfa düzeni, kaydırırken aktif bölüm (scrollspy) ve mobil hamburger menü */
(function () {
  const links = document.getElementById("navLinks");
  const toggle = document.getElementById("navToggle");
  const sectionButtons = [...document.querySelectorAll(".nav-links [data-section]")];
  const sections = sectionButtons
    .map(b => document.getElementById(b.dataset.section))
    .filter(Boolean);
  const mobileMenu = window.matchMedia("(max-width: 900px)");

  // ---- Mobil menü ----
  function setMenu(open, { focus = false } = {}) {
    if (!toggle) return;
    links.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Menüyü kapat" : "Menüyü aç");
    toggle.innerHTML = icon(open ? "x" : "menu");
    if (open && focus) links.querySelector("button")?.focus();
  }

  toggle?.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") !== "true";
    setMenu(open, { focus: open });
  });

  // Menüden bir şey seçilince ya da dışarı tıklanınca kapanır
  links.addEventListener("click", e => {
    if (e.target.closest("button") && mobileMenu.matches) setMenu(false);
  });
  document.addEventListener("click", e => {
    if (!links.classList.contains("is-open")) return;
    if (!e.target.closest(".nav-links") && !e.target.closest("#navToggle")) setMenu(false);
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && links.classList.contains("is-open")) {
      setMenu(false);
      toggle.focus();
    }
  });
  mobileMenu.addEventListener("change", () => setMenu(false));

  // ---- Bölüme kaydırma ----
  // scroll-margin-top CSS'te tanımlı; sabit menünün altında durur
  window.scrollToSection = function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    if (sections.includes(el)) history.replaceState(null, "", "#" + id);
  };

  // ---- Scrollspy: ekranın ortasından geçen bölüm aktif ----
  function setActive(id) {
    sectionButtons.forEach(b => {
      const on = b.dataset.section === id;
      b.classList.toggle("is-active", on);
      if (on) b.setAttribute("aria-current", "true");
      else b.removeAttribute("aria-current");
    });
  }

  const visible = new Set();
  const observer = new IntersectionObserver(entries => {
    entries.forEach(e => e.isIntersecting ? visible.add(e.target.id) : visible.delete(e.target.id));
    // Sayfa sonundaysa son bölüm aktif olsun
    const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4;
    const current = atBottom
      ? sections[sections.length - 1].id
      : sections.map(s => s.id).find(id => visible.has(id));
    if (current) setActive(current);
  }, { rootMargin: "-45% 0px -50% 0px" });
  sections.forEach(s => observer.observe(s));
  window.addEventListener("scroll", () => {
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
      setActive(sections[sections.length - 1].id);
    }
  }, { passive: true });

  setActive(sections.some(s => "#" + s.id === location.hash) ? location.hash.slice(1) : sections[0]?.id);
})();
