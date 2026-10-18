(function () {
  const SECTIONS = ['yakindakiMaclar', 'takimIstatistikBolumu', 'puanlar', 'fikstur'];
  const navButtons = document.querySelectorAll('.nav-links button');

  document.body.classList.add('tabs-on');

  function setActiveButton(btn) {
    navButtons.forEach(b => b.classList.toggle('is-active', b === btn));
  }

  function showSection(id) {
    const target = document.getElementById(id);
    if (!target) return;

    // id bir bölüm değilse (örn. 'simulasyon'), onu içeren bölümü aç
    const sectionEl = SECTIONS.includes(id) ? target : target.closest('.page-section');
    if (!sectionEl) return;

    SECTIONS.forEach(s => {
      const el = document.getElementById(s);
      if (el) el.classList.toggle('active', el === sectionEl);
    });

    if (SECTIONS.includes(id)) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      history.replaceState(null, '', '#' + id);
    } else {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    if (window.ScrollTrigger) setTimeout(() => ScrollTrigger.refresh(), 50);
  }

  // Menüdeki onclick="scrollToSection(...)" artık bölüm değiştirir
  window.scrollToSection = showSection;

  // Simülasyon butonları önce Yakın Maçlar bölümünü açsın
  const originalOpen = window.openSimulation;
  if (typeof originalOpen === 'function') {
    window.openSimulation = function (...args) {
      showSection('yakindakiMaclar');
      return originalOpen.apply(this, args);
    };
  }

  navButtons.forEach(btn => btn.addEventListener('click', () => setActiveButton(btn)));

  // Açılışta: URL'deki #hash ya da varsayılan Yakın Maçlar
  const initial = SECTIONS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'yakindakiMaclar';
  showSection(initial);
  window.scrollTo(0, 0);
  navButtons.forEach(b => {
    if ((b.getAttribute('onclick') || '').includes(`'${initial}'`)) setActiveButton(b);
  });
})();