function hourInMode(h, mode){
    return mode === 'day' ? (h >= 8 && h < 20) : (h < 8 || h >= 20);
}

function applyVisibility(){
    const visibleSet = new Set(getVisibleDays());

    document.querySelectorAll('.day-header').forEach(el => {
        el.style.display = visibleSet.has(el.dataset.day) ? '' : 'none';
    });

    document.querySelectorAll('.hour-cell').forEach(el => {
        const h = parseInt(el.dataset.hour, 10);
        const day = el.dataset.day;
        const hourOk = hourInMode(h, currentMode);
        const dayOk = !day || visibleSet.has(day);
        el.style.display = (hourOk && dayOk) ? '' : 'none';
        el.style.order = currentMode === 'night' ? (h < 8 ? h + 24 : h) : '';
    });

    const grid = document.getElementById('calendarGrid');
    if (grid) {
        const n = Math.max(1, visibleSet.size);
        grid.style.gridTemplateColumns = `4rem repeat(${n}, 1fr)`;
        const today = parseISO(TODAY_ISO);
        const onCurrentWeek = isSameDate(displayedMonday(), mondayOf(today));
        const todayIsWeekend = today.getDay() === 0 || today.getDay() === 6;
        grid.classList.toggle('grayed-out',
            currentView === 'weekday' && onCurrentWeek && todayIsWeekend);
    }
}

function renderCalendarFrame(){
    const dates = displayedDates();
    const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    dates.forEach((d, i) => {
        const iso = isoDate(d);
        const dateLabel = `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')}`;
        const header = document.querySelector(`.day-header[data-day-index="${i}"]`);
        if (header) {
            header.dataset.day = iso;
            const nameEl = header.querySelector('.day-header-name');
            const dateEl = header.querySelector('.day-header-date');
            if (nameEl) nameEl.textContent = dayNames[d.getDay()];
            if (dateEl) dateEl.textContent = dateLabel;
            header.classList.toggle('is-today', iso === TODAY_ISO);
        }
        document.querySelectorAll(`.dropzone[data-day-index="${i}"]`).forEach(cell => {
            const h = cell.dataset.hour;
            cell.dataset.day = iso;
            cell.dataset.slot = `${iso}-${h}`;
        });
    });
    updateViewTitle();
    applyVisibility();
    renderSchedule();
    updateNowLine();
    updateOutOfRange();
}

function updateViewTitle(){
    const title = document.getElementById('viewTitle');
    if (!title) return;
    const fmt = (d, opts) => d.toLocaleDateString(undefined, opts);
    if (currentView === 'day') {
        title.textContent = fmt(dayAnchor, { weekday:'long', month:'long', day:'numeric', year:'numeric' });
        return;
    }
    const start = displayedMonday();
    const end = addDays(start, currentView === 'weekday' ? 4 : 6);
    const sameMonth = start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear();
    const startStr = fmt(start, { month: 'short', day: 'numeric' });
    const endStr = fmt(end, sameMonth ? { day: 'numeric' } : { month: 'short', day: 'numeric' });
    title.textContent = `${startStr} – ${endStr}, ${end.getFullYear()}`;
}

function updateOutOfRange(){
    const overlay = document.getElementById('outOfRangeOverlay');
    const msg = document.getElementById('outOfRangeMessage');
    if (!overlay || !msg) return;
    const vds = viewVisibleDates();
    if (!vds.length || !validRangeStart || !validRangeEnd) { overlay.classList.add('hidden'); return; }
    const start = vds[0];
    const end = vds[vds.length - 1];
    if (end < validRangeStart) {
        msg.textContent = 'The past is best left behind';
        overlay.classList.remove('hidden');
    } else if (start > validRangeEnd) {
        msg.textContent = 'The future is yet to be made';
        overlay.classList.remove('hidden');
    } else {
        overlay.classList.add('hidden');
    }
}

function navigateCalendar(direction){
    if (currentView === 'day') {
        dayAnchor = addDays(dayAnchor, direction);
    } else {
        weekAnchor = addDays(weekAnchor, direction * 7);
    }
    renderCalendarFrame();
}

function navigateToday(){
    const today = parseISO(TODAY_ISO);
    dayAnchor = today;
    weekAnchor = mondayOf(today);
    renderCalendarFrame();
}

function applyMode(mode){
    currentMode = mode;
    document.body.classList.toggle('night-mode', mode === 'night');
    applyVisibility();

    const btn = document.getElementById('modeToggle');
    if (btn) {
        const icon = mode === 'day' ? SUN_ICON : MOON_ICON;
        const label = mode === 'day' ? 'Day Mode' : 'Night Mode';
        btn.innerHTML = `${icon}<span class="hidden group-hover:inline">${label}</span>`;
    }
    updateNowLine();
}

function applyView(view){
    const prev = currentView;
    currentView = view;
    if (prev === 'day' && view !== 'day' && dayAnchor) {
        weekAnchor = mondayOf(dayAnchor);
    } else if (prev !== 'day' && view === 'day' && weekAnchor) {
        const today = parseISO(TODAY_ISO);
        const inWeek = today >= weekAnchor && today < addDays(weekAnchor, 7);
        dayAnchor = inWeek ? today : weekAnchor;
    }
    document.querySelectorAll('[data-view-btn]').forEach(b => {
        b.classList.toggle('active-view', b.dataset.viewBtn === view);
    });
    renderCalendarFrame();
}

function toggleMode(){
    applyMode(currentMode === 'day' ? 'night' : 'day');
}

function updateNowLine(){
    const grid = document.getElementById('calendarGrid');
    const line = document.getElementById('nowLine');
    if (!grid || !line) return;

    const now = new Date();
    const currentHour = now.getHours();

    if (!hourInMode(currentHour, currentMode) || !isTodayVisible()) {
        line.style.display = 'none';
        return;
    }

    const todayCell = grid.querySelector(`[data-slot="${TODAY_ISO}-${currentHour}"]`);
    if (!todayCell) {
        line.style.display = 'none';
        return;
    }

    const minutesIntoHour = now.getMinutes() + now.getSeconds() / 60;
    const top = todayCell.offsetTop + (minutesIntoHour / 60) * HOUR_HEIGHT;

    line.style.top = top + 'px';
    line.style.left = todayCell.offsetLeft + 'px';
    line.style.width = todayCell.offsetWidth + 'px';
    line.style.display = 'block';
}
