let eventsAnchor = null;
let eventsData = [];
let eventCategoriesCache = [];
let currentEventId = null;
let currentEventColor = '#3b82f6';
let eventsSidebarOpen = false;

function initEvents(){
    if (eventsAnchor === null) {
        const today = parseISO(TODAY_ISO);
        eventsAnchor = new Date(today.getFullYear(), today.getMonth(), 1);
    }
    renderEventsMonthHeader();
    wireEventsNav();
    wirePlannerDrop();
    loadEvents();
    loadEventCategories();
    renderEventsMonth();
}

async function loadEvents(){
    try {
        const res = await fetch('/api/events');
        if (!res.ok) return;
        eventsData = await res.json();
    } catch {
        return;
    }
    renderEventsMonth();
    renderScheduleEventChips();
}

async function loadEventCategories(){
    try {
        const res = await fetch('/api/event-categories');
        if (!res.ok) return;
        eventCategoriesCache = await res.json();
    } catch {}
}

function renderEventsMonthHeader(){
    const header = document.getElementById('eventsMonthHeader');
    if (!header || header.children.length) return;
    for (const label of WEEKDAY_LABELS) {
        const cell = document.createElement('div');
        cell.textContent = label;
        header.appendChild(cell);
    }
}

function wireEventsNav(){
    document.querySelectorAll('#eventsNav [data-events-nav]').forEach(btn => {
        if (btn.dataset.bound) return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', () => {
            const v = btn.dataset.eventsNav;
            if (v === 'today') navigateEventsToday();
            else navigateEventsMonth(parseInt(v, 10));
        });
    });
}

function navigateEventsMonth(delta){
    if (!eventsAnchor) return;
    eventsAnchor = new Date(eventsAnchor.getFullYear(), eventsAnchor.getMonth() + delta, 1);
    renderEventsMonth();
}

function navigateEventsToday(){
    const today = parseISO(TODAY_ISO);
    eventsAnchor = new Date(today.getFullYear(), today.getMonth(), 1);
    renderEventsMonth();
}

function renderEventsMonth(){
    if (!eventsAnchor) return;
    updateEventsTitle();
    renderEventsGrid();
    renderEventsBars();
    renderEventsList();
    updateEventsOutOfRange();
}

function updateEventsTitle(){
    const el = document.getElementById('eventsTitle');
    if (!el) return;
    el.textContent = eventsAnchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

function renderEventsGrid(){
    const body = document.getElementById('eventsMonthBody');
    if (!body) return;
    body.innerHTML = '';

    const year = eventsAnchor.getFullYear();
    const month = eventsAnchor.getMonth();
    const firstOfMonth = new Date(year, month, 1);
    firstOfMonth.setHours(0, 0, 0, 0);
    const leadingBlanks = firstOfMonth.getDay();
    const gridStart = addDays(firstOfMonth, -leadingBlanks);
    const today = parseISO(TODAY_ISO);

    for (let i = 0; i < 42; i++) {
        const d = addDays(gridStart, i);
        const cell = document.createElement('div');
        cell.className = 'events-day';
        if (d.getMonth() !== month) cell.classList.add('events-day-outside');
        if (isSameDate(d, today)) cell.classList.add('events-day-today');
        if (validRangeStart && validRangeEnd && (d < validRangeStart || d > validRangeEnd)) {
            cell.classList.add('events-day-out-of-range');
        }
        cell.dataset.day = isoDate(d);
        const num = document.createElement('span');
        num.className = 'events-day-num';
        num.textContent = String(d.getDate());
        cell.appendChild(num);
        body.appendChild(cell);
    }
}

function renderEventsBars(){
    const body = document.getElementById('eventsMonthBody');
    if (!body || !eventsAnchor) return;
    body.querySelectorAll('.events-bar').forEach(el => el.remove());
    if (!eventsData.length) return;

    const year = eventsAnchor.getFullYear();
    const month = eventsAnchor.getMonth();
    const firstOfMonth = new Date(year, month, 1);
    firstOfMonth.setHours(0, 0, 0, 0);
    const leadingBlanks = firstOfMonth.getDay();
    const gridStart = addDays(firstOfMonth, -leadingBlanks);
    const gridEnd = addDays(gridStart, 41);

    const items = [];
    const DAY_MS = 24 * 3600 * 1000;
    for (const ev of eventsData) {
        const evStart = parseISO(ev.start_date);
        const evEnd = parseISO(ev.end_date);
        if (evEnd < gridStart || evStart > gridEnd) continue;
        const clipStart = evStart < gridStart ? gridStart : evStart;
        const clipEnd = evEnd > gridEnd ? gridEnd : evEnd;
        const startIdx = Math.round((clipStart - gridStart) / DAY_MS);
        const endIdx = Math.round((clipEnd - gridStart) / DAY_MS);

        const segments = [];
        let i = startIdx;
        while (i <= endIdx) {
            const row = Math.floor(i / 7);
            const col = i % 7;
            const rowEnd = row * 7 + 6;
            const segLast = Math.min(endIdx, rowEnd);
            segments.push({
                row,
                colStart: col,
                colEnd: segLast - row * 7,
                capStart: i === startIdx && evStart >= gridStart,
                capEnd: segLast === endIdx && evEnd <= gridEnd,
            });
            i = segLast + 1;
        }
        items.push({ ev, segments, startIdx, endIdx });
    }

    items.sort((a, b) => a.startIdx - b.startIdx || a.endIdx - b.endIdx);

    const lanesByRow = [[], [], [], [], [], []];
    for (const item of items) {
        let lane = 0;
        while (lane < 12) {
            let conflict = false;
            for (const seg of item.segments) {
                for (const occ of lanesByRow[seg.row]) {
                    if (occ.lane === lane && !(occ.colEnd < seg.colStart || occ.colStart > seg.colEnd)) {
                        conflict = true;
                        break;
                    }
                }
                if (conflict) break;
            }
            if (!conflict) break;
            lane++;
        }
        item.lane = lane;
        for (const seg of item.segments) {
            lanesByRow[seg.row].push({ lane, colStart: seg.colStart, colEnd: seg.colEnd });
        }
    }

    const colW = 100 / 7;
    const insetPx = 3;
    for (const item of items) {
        for (const seg of item.segments) {
            const bar = document.createElement('div');
            bar.className = 'events-bar';
            if (!seg.capStart) bar.classList.add('events-bar-no-cap-start');
            if (!seg.capEnd) bar.classList.add('events-bar-no-cap-end');
            const leftPct = seg.colStart * colW;
            const widthPct = (seg.colEnd - seg.colStart + 1) * colW;
            const leftInset = seg.capStart ? insetPx : 0;
            const rightInset = seg.capEnd ? insetPx : 0;
            bar.style.left = `calc(${leftPct}% + ${leftInset}px)`;
            bar.style.width = `calc(${widthPct}% - ${leftInset + rightInset}px)`;
            bar.style.top = `calc(var(--events-row-h) * ${seg.row} + 2.1rem + ${item.lane} * 1.45rem)`;
            bar.style.backgroundColor = item.ev.color || '#64748b';
            bar.textContent = item.ev.title;
            bar.dataset.eventId = item.ev.id;
            bar.addEventListener('click', (e) => {
                e.stopPropagation();
                openEventModal(item.ev.id);
            });
            bar.addEventListener('mouseenter', (e) => showEventHover(e, item.ev));
            bar.addEventListener('mousemove', moveEventHover);
            bar.addEventListener('mouseleave', hideEventHover);
            body.appendChild(bar);
        }
    }
}

function hexToRgba(hex, alpha){
    if (!hex || typeof hex !== 'string' || !hex.startsWith('#') || hex.length !== 7) {
        return `rgba(100,116,139,${alpha})`;
    }
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}

const UNCATEGORIZED_KEY = '__uncategorized__';
const UNCATEGORIZED_COLOR = '#64748b';

function renderEventsList(){
    const list = document.getElementById('eventsList');
    if (!list) return;
    list.innerHTML = '';
    if (!eventsData.length) {
        const empty = document.createElement('div');
        empty.className = 'text-sm text-slate-500 italic';
        empty.textContent = 'No events yet.';
        list.appendChild(empty);
        return;
    }

    const groups = new Map();
    for (const ev of eventsData) {
        const raw = (ev.category || '').trim();
        const key = raw || UNCATEGORIZED_KEY;
        if (!groups.has(key)) {
            groups.set(key, {
                key,
                name: raw || 'Uncategorized',
                color: raw ? (ev.color || UNCATEGORIZED_COLOR) : UNCATEGORIZED_COLOR,
                events: [],
            });
        }
        groups.get(key).events.push(ev);
    }

    const sortedGroups = [...groups.values()].sort((a, b) => {
        if (a.key === UNCATEGORIZED_KEY) return 1;
        if (b.key === UNCATEGORIZED_KEY) return -1;
        return a.name.localeCompare(b.name);
    });

    for (const group of sortedGroups) {
        const box = document.createElement('div');
        box.className = 'events-group-box';
        box.style.backgroundColor = hexToRgba(group.color, 0.18);
        box.style.borderColor = hexToRgba(group.color, 0.38);

        const title = document.createElement('div');
        title.className = 'events-group-title';
        title.textContent = group.name;
        title.style.color = group.color;
        box.appendChild(title);

        const sortedEvents = [...group.events].sort(
            (a, b) => a.start_date.localeCompare(b.start_date)
        );
        for (const ev of sortedEvents) {
            const row = document.createElement('div');
            row.className = 'events-list-row';
            row.innerHTML =
                `<div class="events-list-stripe" style="background-color: ${escapeHtml(ev.color || UNCATEGORIZED_COLOR)};"></div>` +
                `<div class="events-list-text">` +
                    `<div class="font-medium truncate">${escapeHtml(ev.title)}</div>` +
                    `<div class="text-xs text-slate-500">${escapeHtml(formatEventDates(ev))}</div>` +
                `</div>`;
            row.addEventListener('click', () => openEventModal(ev.id));
            box.appendChild(row);
        }
        list.appendChild(box);
    }
}

function formatEventDates(ev){
    if (ev.start_date === ev.end_date) return ev.start_date;
    return `${ev.start_date} → ${ev.end_date}`;
}

function eventsByDay(){
    const map = new Map();
    for (const ev of eventsData) {
        const start = parseISO(ev.start_date);
        const end = parseISO(ev.end_date);
        if (!(start instanceof Date) || isNaN(start)) continue;
        if (!(end instanceof Date) || isNaN(end)) continue;
        let d = new Date(start);
        d.setHours(0, 0, 0, 0);
        while (d <= end) {
            const iso = isoDate(d);
            if (!map.has(iso)) map.set(iso, []);
            map.get(iso).push(ev);
            d = addDays(d, 1);
        }
    }
    return map;
}

function renderScheduleEventChips(){
    const headers = document.querySelectorAll('.day-header');
    if (!headers.length) return;
    const byDay = eventsByDay();
    headers.forEach(header => {
        let container = header.querySelector('.day-header-events');
        if (!container) {
            container = document.createElement('div');
            container.className = 'day-header-events';
            header.appendChild(container);
        }
        container.innerHTML = '';
        const day = header.dataset.day;
        if (!day) return;
        const events = byDay.get(day) || [];
        for (const ev of events) {
            const chip = document.createElement('div');
            chip.className = 'day-event-chip';
            chip.style.backgroundColor = ev.color || UNCATEGORIZED_COLOR;
            chip.textContent = ev.title;
            chip.addEventListener('mouseenter', (e) => showEventHover(e, ev));
            chip.addEventListener('mousemove', moveEventHover);
            chip.addEventListener('mouseleave', hideEventHover);
            container.appendChild(chip);
        }
    });
}

function showEventHover(e, ev){
    const panel = document.getElementById('hoverPanel');
    if (!panel) return;
    const cat = ev.category
        ? `<div class="text-slate-300 text-xs mt-1">${escapeHtml(ev.category)}</div>`
        : '';
    const desc = ev.description
        ? `<div class="mt-2 whitespace-pre-wrap">${escapeHtml(ev.description)}</div>`
        : '';
    panel.innerHTML =
        `<div class="font-semibold">${escapeHtml(ev.title)}</div>` +
        `<div class="text-slate-300 text-xs mt-1">${escapeHtml(formatEventDates(ev))}</div>` +
        cat + desc;
    panel.classList.remove('hidden');
    moveEventHover(e);
}

function moveEventHover(e){
    const panel = document.getElementById('hoverPanel');
    if (!panel) return;
    const pad = 12;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    const w = panel.offsetWidth || 320;
    const h = panel.offsetHeight || 100;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
    panel.style.left = `${x}px`;
    panel.style.top = `${y}px`;
}

function hideEventHover(){
    const panel = document.getElementById('hoverPanel');
    if (panel) panel.classList.add('hidden');
}

function openEventModal(eventId){
    const modal = document.getElementById('eventModal');
    if (!modal) return;
    currentEventId = eventId || null;
    const titleEl = document.getElementById('eventModalTitle');
    const deleteBtn = document.getElementById('eventDeleteBtn');
    if (eventId) {
        const ev = eventsData.find(e => e.id === eventId);
        if (!ev) return;
        if (titleEl) titleEl.textContent = 'Edit Event';
        document.getElementById('eventTitle').value = ev.title || '';
        document.getElementById('eventStart').value = ev.start_date || '';
        document.getElementById('eventEnd').value = ev.end_date || '';
        document.getElementById('eventCategory').value = ev.category || '';
        document.getElementById('eventDescription').value = ev.description || '';
        selectEventColor(ev.color || '#3b82f6');
        if (deleteBtn) deleteBtn.classList.remove('hidden');
    } else {
        if (titleEl) titleEl.textContent = 'New Event';
        document.getElementById('eventTitle').value = '';
        document.getElementById('eventStart').value = TODAY_ISO;
        document.getElementById('eventEnd').value = TODAY_ISO;
        document.getElementById('eventCategory').value = '';
        document.getElementById('eventDescription').value = '';
        selectEventColor('#3b82f6');
        if (deleteBtn) deleteBtn.classList.add('hidden');
    }
    hideCategorySuggest();
    modal.classList.remove('hidden');
}

function closeEventModal(){
    const modal = document.getElementById('eventModal');
    if (modal) modal.classList.add('hidden');
    hideCategorySuggest();
}

function selectEventColor(color){
    currentEventColor = color;
    document.querySelectorAll('#eventColorPalette .event-color-swatch').forEach(b => {
        b.classList.toggle('event-color-swatch-selected', b.dataset.color === color);
    });
}

async function saveEvent(){
    const payload = {
        title: document.getElementById('eventTitle').value,
        start_date: document.getElementById('eventStart').value,
        end_date: document.getElementById('eventEnd').value,
        category: document.getElementById('eventCategory').value,
        color: currentEventColor,
        description: document.getElementById('eventDescription').value,
    };
    const url = currentEventId ? `/api/events/${currentEventId}` : '/api/events';
    const method = currentEventId ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            alert(err.error || 'Failed to save event');
            return;
        }
        closeEventModal();
        await loadEvents();
        await loadEventCategories();
    } catch {
        alert('Network error');
    }
}

async function deleteEventFromModal(){
    if (!currentEventId) return;
    if (!confirm('Delete this event?')) return;
    try {
        const res = await fetch(`/api/events/${currentEventId}`, { method: 'DELETE' });
        if (!res.ok) return;
        closeEventModal();
        await loadEvents();
        await loadEventCategories();
    } catch {}
}

function onEventCategoryInput(){
    const input = document.getElementById('eventCategory');
    const dd = document.getElementById('eventCategorySuggest');
    if (!input || !dd) return;
    const q = input.value.trim().toLowerCase();
    let matches = eventCategoriesCache;
    if (q) {
        matches = matches.filter(c => c.name.toLowerCase().includes(q) && c.name.toLowerCase() !== q);
    }
    matches = matches.slice(0, 6);
    if (!matches.length) { dd.classList.add('hidden'); return; }
    dd.innerHTML = '';
    for (const cat of matches) {
        const opt = document.createElement('div');
        opt.className = 'events-cat-suggest-row';
        opt.innerHTML =
            `<span class="events-cat-suggest-swatch" style="background-color: ${escapeHtml(cat.color || '#64748b')};"></span>` +
            `<span>${escapeHtml(cat.name)}</span>`;
        opt.addEventListener('mousedown', (e) => {
            e.preventDefault();
            selectCategorySuggestion(cat);
        });
        dd.appendChild(opt);
    }
    dd.classList.remove('hidden');
}

function selectCategorySuggestion(cat){
    document.getElementById('eventCategory').value = cat.name;
    if (cat.color) selectEventColor(cat.color);
    hideCategorySuggest();
}

function hideCategorySuggest(){
    const dd = document.getElementById('eventCategorySuggest');
    if (dd) dd.classList.add('hidden');
}

function toggleEventsSidebar(){
    const aside = document.getElementById('eventsSidebar');
    if (!aside) return;
    const nowHidden = aside.classList.toggle('hidden');
    eventsSidebarOpen = !nowHidden;
    const label = document.getElementById('eventsSidebarToggleLabel');
    if (label) label.innerHTML = nowHidden ? 'Events &#x25B8;' : 'Events &#x25C2;';
}

function updateEventsOutOfRange(){
    const overlay = document.getElementById('eventsOutOfRangeOverlay');
    const msg = document.getElementById('eventsOutOfRangeMessage');
    if (!overlay || !msg || !eventsAnchor) return;
    if (!validRangeStart || !validRangeEnd) { overlay.classList.add('hidden'); return; }

    const year = eventsAnchor.getFullYear();
    const month = eventsAnchor.getMonth();
    const firstOfMonth = new Date(year, month, 1);
    const lastOfMonth = new Date(year, month + 1, 0);
    firstOfMonth.setHours(0, 0, 0, 0);
    lastOfMonth.setHours(0, 0, 0, 0);

    if (lastOfMonth < validRangeStart) {
        msg.textContent = 'The past is best left behind';
        overlay.classList.remove('hidden');
    } else if (firstOfMonth > validRangeEnd) {
        msg.textContent = 'The future is yet to be made';
        overlay.classList.remove('hidden');
    } else {
        overlay.classList.add('hidden');
    }
}

/* ── Planner CSV Import ── */

function wirePlannerDrop(){
    const zone = document.getElementById('plannerDropZone');
    const input = document.getElementById('plannerFileInput');
    if (!zone || !input) return;

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
    });
    input.addEventListener('change', () => {
        if (input.files.length) handlePlannerFile(input.files[0]);
        input.value = '';
    });

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        const file = (e.dataTransfer.files || [])[0];
        if (file) handlePlannerFile(file);
    });
}

function handlePlannerFile(file){
    const name = file.name.toLowerCase();
    if (!name.endsWith('.csv') && !name.endsWith('.txt')) {
        setPlannerStatus('error', 'Please use a CSV file (save the Excel export as CSV first)');
        return;
    }
    const reader = new FileReader();
    reader.onload = () => processPlannerCSV(reader.result);
    reader.onerror = () => setPlannerStatus('error', 'Failed to read file');
    reader.readAsText(file);
}

function parsePlannerCSV(text){
    const lines = [];
    let current = [];
    let field = '';
    let inQuotes = false;

    for (let i = 0; i < text.length; i++){
        const ch = text[i];
        if (inQuotes){
            if (ch === '"' && text[i + 1] === '"'){ field += '"'; i++; }
            else if (ch === '"') inQuotes = false;
            else field += ch;
        } else {
            if (ch === '"') inQuotes = true;
            else if (ch === ',') { current.push(field); field = ''; }
            else if (ch === '\r' || ch === '\n') {
                if (ch === '\r' && text[i + 1] === '\n') i++;
                current.push(field);
                field = '';
                if (current.length > 1 || current[0] !== '') lines.push(current);
                current = [];
            } else field += ch;
        }
    }
    current.push(field);
    if (current.length > 1 || current[0] !== '') lines.push(current);

    if (lines.length < 2) return [];
    const headers = lines[0].map(h => h.trim());
    const rows = [];
    for (let i = 1; i < lines.length; i++){
        const row = {};
        for (let j = 0; j < headers.length; j++){
            row[headers[j]] = (lines[i][j] || '').trim();
        }
        rows.push(row);
    }
    return rows;
}

function findColumn(row, ...candidates){
    const keys = Object.keys(row);
    for (const c of candidates){
        const lower = c.toLowerCase();
        const match = keys.find(k => k.toLowerCase() === lower);
        if (match && row[match]) return row[match];
    }
    return '';
}

function parsePlannerDate(str){
    if (!str) return null;
    const s = str.trim();
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
    const slash = s.split('/');
    if (slash.length === 3){
        const [a, b, c] = slash.map(Number);
        if (isNaN(a) || isNaN(b) || isNaN(c)) return null;
        const year = c > 100 ? c : c + 2000;
        if (a > 12) return `${year}-${String(b).padStart(2, '0')}-${String(a).padStart(2, '0')}`;
        return `${year}-${String(a).padStart(2, '0')}-${String(b).padStart(2, '0')}`;
    }
    return null;
}

async function processPlannerCSV(text){
    const rows = parsePlannerCSV(text);
    if (!rows.length){
        setPlannerStatus('error', 'No data rows found in CSV');
        return;
    }

    const sample = rows[0];
    const hasTitle = findColumn(sample, 'Task Name', 'Task name', 'Title', 'Name');
    if (!hasTitle && !Object.keys(sample).some(k => k.toLowerCase().includes('task'))){
        setPlannerStatus('error', 'Could not find a "Task Name" column');
        return;
    }

    const items = [];
    let skippedCompleted = 0;
    let skippedNoDates = 0;

    for (const row of rows){
        const progress = findColumn(row, 'Progress', 'Status', 'Percent Complete');
        if (/completed|100%/i.test(progress)){
            skippedCompleted++;
            continue;
        }

        const title = findColumn(row, 'Task Name', 'Task name', 'Title', 'Name');
        if (!title) continue;

        const startRaw = findColumn(row, 'Start Date', 'Start date', 'StartDate');
        const dueRaw = findColumn(row, 'Due Date', 'Due date', 'DueDate');
        const startDate = parsePlannerDate(startRaw);
        const dueDate = parsePlannerDate(dueRaw);

        if (!startDate && !dueDate){
            skippedNoDates++;
            continue;
        }

        const bucket = findColumn(row, 'Bucket Name', 'Bucket name', 'Bucket');
        const description = findColumn(row, 'Description', 'Notes');
        const catColor = categoryColor(bucket);

        items.push({
            title,
            start_date: startDate || dueDate,
            end_date: dueDate || startDate,
            category: bucket || null,
            color: catColor,
            description: description || null,
        });
    }

    if (!items.length){
        const parts = [];
        if (skippedCompleted) parts.push(`${skippedCompleted} completed`);
        if (skippedNoDates) parts.push(`${skippedNoDates} without dates`);
        setPlannerStatus('error', 'No active tasks to import' + (parts.length ? ` (${parts.join(', ')})` : ''));
        return;
    }

    setPlannerStatus(null, 'Importing...');

    try {
        const res = await fetch('/api/events/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(items),
        });
        if (!res.ok){
            const err = await res.json().catch(() => ({}));
            setPlannerStatus('error', err.error || 'Import failed');
            return;
        }
        const result = await res.json();
        const parts = [];
        if (result.imported) parts.push(`${result.imported} imported`);
        if (result.skipped) parts.push(`${result.skipped} skipped`);
        if (skippedCompleted) parts.push(`${skippedCompleted} completed`);
        if (skippedNoDates) parts.push(`${skippedNoDates} without dates`);
        setPlannerStatus('success', parts.join(', '));
        await loadEvents();
        await loadEventCategories();
    } catch {
        setPlannerStatus('error', 'Network error during import');
    }
}

function categoryColor(name){
    if (!name) return '#3b82f6';
    const lower = name.toLowerCase();
    const match = eventCategoriesCache.find(c => c.name.toLowerCase() === lower);
    return match ? (match.color || '#3b82f6') : '#3b82f6';
}

let plannerStatusTimer = null;
function setPlannerStatus(type, message){
    const zone = document.getElementById('plannerDropZone');
    const text = document.getElementById('plannerDropText');
    if (!zone || !text) return;
    zone.classList.remove('drop-success', 'drop-error');
    if (type) zone.classList.add(type === 'success' ? 'drop-success' : 'drop-error');
    text.textContent = message;
    clearTimeout(plannerStatusTimer);
    if (type) {
        plannerStatusTimer = setTimeout(() => {
            zone.classList.remove('drop-success', 'drop-error');
            text.textContent = 'Drop a Planner CSV here to import tasks';
        }, 6000);
    }
}
