const footerYear = document.getElementById("footerYear");
if (footerYear) footerYear.textContent = new Date().getFullYear();

// scrollToSection nav.js'te tanımlı

const matchMeta = {
    alanya: { home: 'FENERBAHÇE', away: 'ALANYASPOR', score: '2 - 1', minute: "89'", league: 'Trendyol Süper Lig' },
    slavia: { home: 'FENERBAHÇE', away: 'SLAVIA PRAG', score: 'v', minute: 'Ön İzleme', league: 'UEFA Avrupa Kupası' },
    gs: { home: 'GALATASARAY', away: 'FENERBAHÇE', score: 'v', minute: 'Derbi Özel', league: 'Trendyol Süper Lig' }
};

function openSimulation(matchKey) {
    const data = matchMeta[matchKey] || matchMeta.alanya;
    const wrapper = document.getElementById("simulasyonWrapper");

    document.querySelectorAll('.recent-match-card').forEach(c => c.classList.remove('active-card'));
    const activeCard = document.getElementById('card-' + matchKey);
    if (activeCard) activeCard.classList.add('active-card');

    document.getElementById("simHomeTeam").innerText = data.home;
    document.getElementById("simAwayTeam").innerText = data.away;
    document.getElementById("simScore").innerText = data.score;
    document.getElementById("matchMinute").innerHTML = icon("radio") + esc(data.minute);
    document.getElementById("simLeagueName").innerText = data.league;

    wrapper.classList.add("open");
    switchTab('pitchTab');
    if (typeof simStartFeed === 'function') simStartFeed(matchKey, data);

    setTimeout(() => {
        if (typeof resizePitch === 'function') resizePitch();
        ScrollTrigger.refresh();
        scrollToSection('simulasyonWrapper');
    }, 80);
}

function closeSimulation() {
    const wrapper = document.getElementById("simulasyonWrapper");
    wrapper.classList.remove("open");
    setTimeout(() => ScrollTrigger.refresh(), 200);
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active-content'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    
    const contentEl = document.getElementById(tabId);
    const btnEl = document.getElementById('btn-' + tabId);
    if (contentEl) contentEl.classList.add('active-content');
    if (btnEl) btnEl.classList.add('active');

    if (tabId === 'pitchTab') {
        setTimeout(() => {
            if (typeof resizePitch === 'function') resizePitch();
        }, 50);
    }
}

// PWA: service worker (sw.js). Yerelde geliştirmeyi önbellek karıştırmasın diye sadece
// canlı sitede; yerelde denemek için adrese ?sw=1 eklenir.
if ('serviceWorker' in navigator && (location.protocol === 'https:' || /[?&]sw=1/.test(location.search))) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

// Takvim aboneliği bağlantıları: yerelde yerel backend'e işaret etsin (index.html'deki varsayılan canlı adres)
(function () {
    if (typeof API_BASE === 'undefined') return;
    const ics = `${API_BASE}/api/calendar.ics`;
    const webcal = ics.replace(/^https?:/, 'webcal:');
    document.querySelectorAll('[data-cal]').forEach(a => {
        a.href = { webcal, https: ics, google: `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(webcal)}` }[a.dataset.cal];
    });
    document.addEventListener('click', e => {
        const open = document.querySelector('.fx-cal-add[open]');
        if (open && !open.contains(e.target)) open.removeAttribute('open');
    });
})();
