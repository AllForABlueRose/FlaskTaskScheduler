function tabFromPath(){
    if (location.pathname.startsWith('/events')) return 'events';
    if (location.pathname.startsWith('/applications')) return 'applications';
    if (location.pathname.startsWith('/timeline')) return 'timeline';
    if (location.pathname.startsWith('/schedule')) return 'schedule';
    return null;
}

function setActiveTabButton(name){
    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('tab-btn-active', b.dataset.tab === name);
    });
    const titles = { schedule: 'Scheduler', events: 'Events', applications: 'Applications', timeline: 'Timeline' };
    document.title = titles[name] || 'Scheduler';
}

function onTabEntered(name){
    if (name === 'events' && typeof renderEventsMonth === 'function') {
        renderEventsMonth();
    }
    if (name === 'schedule') {
        if (typeof updateNowLine === 'function') updateNowLine();
        if (typeof renderScheduleEventChips === 'function') renderScheduleEventChips();
    }
    if (name === 'applications' && typeof initApplications === 'function') {
        initApplications();
    }
    if (name === 'timeline' && typeof initTimeline === 'function') {
        initTimeline();
    }
}

function switchTab(name, opts){
    opts = opts || {};
    const next = document.getElementById('view-' + name);
    if (!next) return;
    setActiveTabButton(name);
    const current = document.querySelector('.view:not(.view-hidden)');
    if (current === next) {
        onTabEntered(name);
        return;
    }

    if (current && !opts.immediate) {
        current.classList.add('view-fading');
        setTimeout(() => {
            current.classList.add('view-hidden');
            current.classList.remove('view-fading');
            next.classList.add('view-fading');
            next.classList.remove('view-hidden');
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    next.classList.remove('view-fading');
                    onTabEntered(name);
                });
            });
        }, 150);
    } else {
        if (current) current.classList.add('view-hidden');
        next.classList.remove('view-hidden');
        onTabEntered(name);
    }
}

function initTabs(){
    const initialTab = document.body.dataset.initialTab || 'schedule';
    setActiveTabButton(initialTab);

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const tab = btn.dataset.tab;
            if (!tab) return;
            const url = btn.getAttribute('href');
            if (tabFromPath() !== tab) {
                history.pushState({ tab }, '', url);
            }
            switchTab(tab);
        });
    });

    window.addEventListener('popstate', (e) => {
        const tab = (e.state && e.state.tab) || tabFromPath() || 'schedule';
        switchTab(tab, { immediate: true });
    });

    history.replaceState({ tab: initialTab }, '', location.pathname);
}
