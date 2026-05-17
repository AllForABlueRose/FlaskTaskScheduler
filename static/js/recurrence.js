const RECUR_MARKER = '↻ Recurs:';
let recurrenceTaskId = null;

function parseRecurrence(r){
    if (!r) return null;
    if (typeof r === 'string') {
        try { return JSON.parse(r); } catch { return null; }
    }
    return r;
}

function ordinal(n){
    if (n === -1) return 'last';
    return ({1:'first',2:'second',3:'third',4:'fourth',5:'fifth'}[n]) || `${n}th`;
}

function describeRecurrence(rec){
    if (!rec) return '';
    const time = rec.time || '09:00';
    const dur = Math.max(15, parseInt(rec.duration, 10) || 60);
    const durStr = dur >= 60 && dur % 60 === 0 ? `${dur/60}h` : `${dur}m`;
    const dayName = i => WEEKDAY_LABELS[i];
    const joinDays = arr => (arr && arr.length ? arr.slice().sort((a,b)=>a-b).map(dayName).join(', ') : '');

    let phrase;
    switch (rec.type) {
        case 'daily':
            phrase = `daily at ${time}`;
            break;
        case 'weekday':
            phrase = `every weekday at ${time}`;
            break;
        case 'weekly':
            phrase = `weekly on ${joinDays(rec.daysOfWeek) || 'Sun'} at ${time}`;
            break;
        case 'monthly':
            if (rec.monthlyMode === 'weekday') {
                phrase = `the ${ordinal(rec.nth)} ${WEEKDAY_FULL[rec.nthWeekday] || 'Sunday'} of every month at ${time}`;
            } else {
                phrase = `on day ${rec.dayOfMonth || 1} of every month at ${time}`;
            }
            break;
        case 'custom': {
            const n = Math.max(1, rec.interval || 1);
            const unitSingular = { days: 'day', weeks: 'week', months: 'month' }[rec.unit] || 'day';
            const unit = n === 1 ? unitSingular : `${n} ${unitSingular}s`;
            const prefix = `every ${unit}`;
            if (rec.unit === 'weeks') {
                phrase = `${prefix} on ${joinDays(rec.daysOfWeek) || 'Sun'} at ${time}`;
            } else if (rec.unit === 'months') {
                if (rec.monthlyMode === 'weekday') {
                    phrase = `${prefix} on the ${ordinal(rec.nth)} ${WEEKDAY_FULL[rec.nthWeekday] || 'Sunday'} at ${time}`;
                } else {
                    phrase = `${prefix} on day ${rec.dayOfMonth || 1} at ${time}`;
                }
            } else {
                phrase = `${prefix} at ${time}`;
            }
            break;
        }
        default:
            phrase = `at ${time}`;
    }
    return `${phrase} (${durStr})`;
}

function buildRecurrenceTags(existingTags, rec){
    const known = new Set(['recurring','daily','weekday','weekly','monthly','custom']);
    const set = new Set(
        (existingTags || '')
            .split(',')
            .map(s => s.trim())
            .filter(Boolean)
            .filter(t => !known.has(t.toLowerCase()))
    );
    if (rec) {
        set.add('recurring');
        set.add(rec.type);
    }
    return [...set].join(', ');
}

function buildRecurrenceDescription(existingDescription, rec){
    const lines = (existingDescription || '').split('\n');
    const filtered = lines.filter(l => !l.trim().startsWith(RECUR_MARKER));
    while (filtered.length && !filtered[filtered.length - 1].trim()) filtered.pop();
    if (rec) {
        const text = `${RECUR_MARKER} ${describeRecurrence(rec)}`;
        return (filtered.length ? [...filtered, '', text] : [text]).join('\n');
    }
    return filtered.join('\n');
}

function buildWeekdayButtons(containerId, scope){
    const container = document.getElementById(containerId);
    if (!container || container.dataset.built === '1') return;
    container.innerHTML = WEEKDAY_LABELS.map((label, i) => `
        <button type="button" class="rec-weekday-btn" data-rec-weekday="${i}" data-rec-scope="${scope}"
                onclick="toggleRecWeekday(this)">${label}</button>
    `).join('');
    container.dataset.built = '1';
}

function buildWeekdayDropdown(selectId){
    const el = document.getElementById(selectId);
    if (!el || el.dataset.built === '1') return;
    el.innerHTML = WEEKDAY_FULL.map((label, i) => `<option value="${i}">${label}</option>`).join('');
    el.dataset.built = '1';
}

function toggleRecWeekday(btn){
    btn.classList.toggle('recurrence-day-active');
    refreshRecSummary();
}

function getSelectedWeekdays(scope){
    return [...document.querySelectorAll(`[data-rec-scope="${scope}"].recurrence-day-active`)]
        .map(b => parseInt(b.dataset.recWeekday, 10));
}

function setSelectedWeekdays(scope, days){
    const set = new Set(days || []);
    [...document.querySelectorAll(`[data-rec-scope="${scope}"]`)].forEach(b => {
        b.classList.toggle('recurrence-day-active', set.has(parseInt(b.dataset.recWeekday, 10)));
    });
}

function updateRecurrenceVisibility(){
    const freq = document.getElementById('recFrequency').value;
    document.getElementById('recWeekly').classList.toggle('hidden', freq !== 'weekly');
    document.getElementById('recMonthly').classList.toggle('hidden', freq !== 'monthly');
    document.getElementById('recCustom').classList.toggle('hidden', freq !== 'custom');
    if (freq === 'monthly') updateMonthlyMode('rec');
    if (freq === 'custom') updateCustomUnit();
    refreshRecSummary();
}

function updateMonthlyMode(scope){
    const modeEl = document.getElementById(scope + 'MonthlyMode');
    if (!modeEl) return;
    const mode = modeEl.value;
    document.getElementById(scope + 'MonthlyDay').classList.toggle('hidden', mode !== 'day');
    document.getElementById(scope + 'MonthlyWeekday').classList.toggle('hidden', mode !== 'weekday');
    refreshRecSummary();
}

function updateCustomUnit(){
    const unit = document.getElementById('recUnit').value;
    document.getElementById('recCustomWeekdays').classList.toggle('hidden', unit !== 'weeks');
    document.getElementById('recCustomMonthly').classList.toggle('hidden', unit !== 'months');
    if (unit === 'months') updateMonthlyMode('recCustom');
    refreshRecSummary();
}

function collectRecurrence(){
    const freq = document.getElementById('recFrequency').value;
    const time = document.getElementById('recTime').value || '09:00';
    const duration = Math.max(15, parseInt(document.getElementById('recDuration').value, 10) || 60);
    const rec = { type: freq, time, duration };

    if (freq === 'weekday') {
        rec.daysOfWeek = [1,2,3,4,5];
    } else if (freq === 'weekly') {
        let days = getSelectedWeekdays('weekly');
        if (days.length === 0) days = [new Date().getDay()];
        rec.daysOfWeek = days;
    } else if (freq === 'monthly') {
        rec.monthlyMode = document.getElementById('recMonthlyMode').value;
        if (rec.monthlyMode === 'day') {
            rec.dayOfMonth = clampInt(document.getElementById('recDayOfMonth').value, 1, 31, 1);
        } else {
            rec.nth = parseInt(document.getElementById('recNth').value, 10);
            rec.nthWeekday = parseInt(document.getElementById('recNthWeekday').value, 10);
        }
    } else if (freq === 'custom') {
        rec.interval = Math.max(1, parseInt(document.getElementById('recInterval').value, 10) || 1);
        rec.unit = document.getElementById('recUnit').value;
        if (rec.unit === 'weeks') {
            let days = getSelectedWeekdays('custom');
            if (days.length === 0) days = [new Date().getDay()];
            rec.daysOfWeek = days;
        } else if (rec.unit === 'months') {
            rec.monthlyMode = document.getElementById('recCustomMonthlyMode').value;
            if (rec.monthlyMode === 'day') {
                rec.dayOfMonth = clampInt(document.getElementById('recCustomDayOfMonth').value, 1, 31, 1);
            } else {
                rec.nth = parseInt(document.getElementById('recCustomNth').value, 10);
                rec.nthWeekday = parseInt(document.getElementById('recCustomNthWeekday').value, 10);
            }
        }
    }
    return rec;
}

function clampInt(v, min, max, fallback){
    const n = parseInt(v, 10);
    if (Number.isNaN(n)) return fallback;
    return Math.max(min, Math.min(max, n));
}

function refreshRecSummary(){
    const el = document.getElementById('recSummary');
    if (!el) return;
    try {
        el.textContent = 'Will recur ' + describeRecurrence(collectRecurrence());
    } catch {
        el.textContent = '';
    }
}

function ensureRecurrenceModalBuilt(){
    buildWeekdayButtons('recWeeklyDays', 'weekly');
    buildWeekdayButtons('recCustomWeekdayDays', 'custom');
    buildWeekdayDropdown('recNthWeekday');
    buildWeekdayDropdown('recCustomNthWeekday');
    if (!document.getElementById('recFrequency').dataset.bound) {
        ['recInterval','recDayOfMonth','recCustomDayOfMonth','recNth','recCustomNth','recNthWeekday','recCustomNthWeekday','recTime','recDuration'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('input', refreshRecSummary);
            if (el) el.addEventListener('change', refreshRecSummary);
        });
        document.getElementById('recFrequency').dataset.bound = '1';
    }
}

function openRecurrenceModal(taskId){
    const task = tasks.find(t => t.id === taskId);
    if (!task) return;
    recurrenceTaskId = taskId;
    ensureRecurrenceModalBuilt();

    const rec = parseRecurrence(task.recurrence);
    document.getElementById('recurrenceTaskName').textContent = task.name || '';

    document.getElementById('recFrequency').value = rec?.type || 'daily';
    document.getElementById('recTime').value = rec?.time || '09:00';
    document.getElementById('recDuration').value = rec?.duration || 60;

    setSelectedWeekdays('weekly', rec?.type === 'weekly' ? rec.daysOfWeek : []);
    setSelectedWeekdays('custom', rec?.type === 'custom' && rec?.unit === 'weeks' ? rec.daysOfWeek : []);

    document.getElementById('recMonthlyMode').value = (rec?.type === 'monthly' && rec.monthlyMode) || 'day';
    document.getElementById('recDayOfMonth').value = (rec?.type === 'monthly' && rec.monthlyMode === 'day' && rec.dayOfMonth) || 1;
    document.getElementById('recNth').value = (rec?.type === 'monthly' && rec.monthlyMode === 'weekday' && rec.nth) || 1;
    document.getElementById('recNthWeekday').value = (rec?.type === 'monthly' && rec.monthlyMode === 'weekday' && rec.nthWeekday) || 1;

    document.getElementById('recInterval').value = (rec?.type === 'custom' && rec.interval) || 2;
    document.getElementById('recUnit').value = (rec?.type === 'custom' && rec.unit) || 'days';
    document.getElementById('recCustomMonthlyMode').value = (rec?.type === 'custom' && rec.unit === 'months' && rec.monthlyMode) || 'day';
    document.getElementById('recCustomDayOfMonth').value = (rec?.type === 'custom' && rec.unit === 'months' && rec.monthlyMode === 'day' && rec.dayOfMonth) || 1;
    document.getElementById('recCustomNth').value = (rec?.type === 'custom' && rec.unit === 'months' && rec.monthlyMode === 'weekday' && rec.nth) || 1;
    document.getElementById('recCustomNthWeekday').value = (rec?.type === 'custom' && rec.unit === 'months' && rec.monthlyMode === 'weekday' && rec.nthWeekday) || 1;

    document.getElementById('recRemoveBtn').classList.toggle('hidden', !rec);

    updateRecurrenceVisibility();
    document.getElementById('recurrenceModal').classList.remove('hidden');
}

function closeRecurrenceModal(){
    document.getElementById('recurrenceModal').classList.add('hidden');
    recurrenceTaskId = null;
}

async function saveRecurrence(){
    if (!recurrenceTaskId) return;
    const task = tasks.find(t => t.id === recurrenceTaskId);
    if (!task) return;
    const existing = parseRecurrence(task.recurrence);
    const rec = collectRecurrence();
    rec.startDate = existing?.startDate || new Date().toISOString().slice(0, 10);
    const payload = {
        recurrence: rec,
        tags: buildRecurrenceTags(task.tags, rec),
        description: buildRecurrenceDescription(task.description, rec),
    };
    const res = await fetch(`/task/${recurrenceTaskId}/recurrence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.ok) {
        const updated = await res.json();
        const idx = tasks.findIndex(t => t.id === recurrenceTaskId);
        if (idx !== -1) tasks[idx] = updated; else tasks.push(updated);
        await loadSchedule();
        renderTasks();
    }
    closeRecurrenceModal();
}

async function removeRecurrence(){
    if (!recurrenceTaskId) return;
    const task = tasks.find(t => t.id === recurrenceTaskId);
    if (!task) return;
    const payload = {
        recurrence: null,
        tags: buildRecurrenceTags(task.tags, null),
        description: buildRecurrenceDescription(task.description, null),
    };
    const res = await fetch(`/task/${recurrenceTaskId}/recurrence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.ok) {
        const updated = await res.json();
        const idx = tasks.findIndex(t => t.id === recurrenceTaskId);
        if (idx !== -1) tasks[idx] = updated;
        await loadSchedule();
        renderTasks();
    }
    closeRecurrenceModal();
}

function allowDropRecurring(ev){
    ev.preventDefault();
    document.getElementById('recurringArea').classList.add('recurring-expanded');
}

function leaveRecurring(ev){
    const area = document.getElementById('recurringArea');
    if (ev.relatedTarget && area.contains(ev.relatedTarget)) return;
    area.classList.remove('recurring-expanded');
}

function dropRecurring(ev){
    ev.preventDefault();
    document.getElementById('recurringArea').classList.remove('recurring-expanded');

    let resolvedId = null;
    const movePayload = ev.dataTransfer.getData('application/x-scheduled');
    if (movePayload) {
        try { resolvedId = JSON.parse(movePayload).taskId || null; } catch {}
    }
    if (!resolvedId) resolvedId = ev.dataTransfer.getData('text/plain');
    if (!resolvedId) return;
    if (!tasks.find(t => t.id === resolvedId)) return;
    openRecurrenceModal(resolvedId);
}

function renderRecurring(){
    const list = document.getElementById('recurringList');
    const count = document.getElementById('recurringCount');
    if (!list) return;
    const recurring = tasks.filter(t => parseRecurrence(t.recurrence));
    if (count) count.textContent = recurring.length ? `${recurring.length} active` : 'drop a task here';
    list.innerHTML = recurring.map(t => {
        const rec = parseRecurrence(t.recurrence);
        return `
            <div class="p-3 rounded-xl cursor-pointer flex flex-col gap-2 relative"
                 style="background:${t.color};color:white"
                 draggable="true"
                 ondragstart="dragTask(event)"
                 data-task-id="${t.id}"
                 onclick="openRecurrenceModal('${t.id}')">
                <div class="min-w-0">
                    <div class="font-bold truncate">↻ ${escapeHtml(t.name)}</div>
                    <div class="text-xs truncate opacity-90">${escapeHtml(describeRecurrence(rec))}</div>
                </div>
                <div class="flex flex-wrap gap-1">
                    <button draggable="false"
                        onclick="event.stopPropagation();editTask('${t.id}')"
                        class="bg-white/25 hover:bg-white/40 px-2 py-1 rounded text-xs flex-1 min-w-[4.5rem]">Edit</button>
                    <button draggable="false"
                        onclick="event.stopPropagation();deleteTask('${t.id}')"
                        class="bg-white/25 hover:bg-white/40 px-2 py-1 rounded text-xs flex-1 min-w-[4.5rem]">Delete</button>
                </div>
            </div>
        `;
    }).join('');
}
