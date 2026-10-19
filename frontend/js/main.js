function scrollToSection(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const navHeight = 90;
    const y = el.getBoundingClientRect().top + window.pageYOffset - navHeight;
    window.scrollTo({ top: y, behavior: 'smooth' });
}

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
    document.getElementById("matchMinute").innerText = "🔴 " + data.minute;
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