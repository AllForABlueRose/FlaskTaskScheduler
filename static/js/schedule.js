let resizeState = null;
let currentChipEntryId = null;
let currentChipTaskId = null;

async function loadSchedule(){
    const res = await fetch('/api/schedule');
    if (res.status === 401) { location.href = '/'; return; }
    scheduleEntries = await res.json();
    renderSchedule();
}

function parseSlot(slot){
    const parts = slot.split('-');
    const quarter = parseInt(parts.pop(), 10);
    const hour = parseInt(parts.pop(), 10);
    const day = parts.join('-');
    return { day, hour, quarter };
}

function clearChips(){
    document.querySelectorAll('.scheduled-chip').forEach(c => c.remove());
}

function layoutDayItems(items){
    items.sort((a, b) => a.startQ - b.startQ || a.endQ - b.endQ);

    const result = [];
    let cluster = [];
    let clusterEnd = -1;

    const finalize = () => {
        if (cluster.length === 0) return;
        const columnEnds = [];
        cluster.forEach(it => {
            let col = 0;
            while (col < columnEnds.length && columnEnds[col] > it.startQ) col++;
            it.column = col;
            columnEnds[col] = it.endQ;
        });
        const totalColumns = columnEnds.length;
        cluster.forEach(it => {
            it.totalColumns = totalColumns;
            result.push(it);
        });
    };

    for (const item of items) {
        if (item.startQ >= clusterEnd) {
            finalize();
            cluster = [];
            clusterEnd = item.endQ;
        } else {
            clusterEnd = Math.max(clusterEnd, item.endQ);
        }
        cluster.push(item);
    }
    finalize();

    return result;
}

function renderSchedule(){
    clearChips();

    const byDay = {};
    scheduleEntries.forEach(entry => {
        const { day, hour, quarter } = parseSlot(entry.slot);
        const task = tasks.find(t => t.id === entry.task_id);
        if (!task) return;
        const duration = Math.max(1, parseInt(entry.duration, 10) || 1);
        const startQ = hour * 4 + quarter;
        const endQ = startQ + duration;
        if (!byDay[day]) byDay[day] = [];
        byDay[day].push({ entry, task, day, hour, quarter, duration, startQ, endQ });
    });

    Object.values(byDay).forEach(items => {
        layoutDayItems(items).forEach(it => {
            const cell = document.querySelector(`[data-slot="${it.day}-${it.hour}"]`);
            if (cell) renderChip(cell, it);
        });
    });
}

function renderChip(cell, item){
    const { entry, task, quarter, duration } = item;
    const top = quarter * QUARTER_HEIGHT;
    const height = duration * QUARTER_HEIGHT;
    const widthPct = 100 / item.totalColumns;
    const leftPct = item.column * widthPct;
    const isRecurring = !!entry.is_recurring;

    const hasOverride = entry.input !== null && entry.input !== undefined;
    const overrideMark = hasOverride ? ' <span title="Per-occurrence input" class="opacity-90">·</span>' : '';

    if (isRecurring) {
        const html = `
            <div class="scheduled-chip recurring-chip absolute rounded-lg px-1.5 py-0.5 text-sm text-white shadow overflow-hidden leading-tight cursor-pointer"
                 style="background:${task.color}; top:${top + 1}px; height:${height - 2}px; left:calc(${leftPct}% + 1px); width:calc(${widthPct}% - 2px); z-index:4;"
                 data-entry-id="${entry.id}"
                 data-task-id="${task.id}"
                 onclick="openChipModal(${entry.id})"
                 onmouseenter="showHover(event)"
                 onmousemove="moveHover(event)"
                 onmouseleave="hideHover()">
                <div class="truncate font-semibold">↻ ${escapeHtml(task.name)}${overrideMark}</div>
            </div>
        `;
        cell.insertAdjacentHTML('beforeend', html);
        return;
    }

    const html = `
        <div class="scheduled-chip absolute rounded-lg px-1.5 py-0.5 text-sm text-white shadow cursor-move overflow-hidden leading-tight"
             style="background:${task.color}; top:${top + 1}px; height:${height - 2}px; left:calc(${leftPct}% + 1px); width:calc(${widthPct}% - 2px); z-index:5;"
             draggable="true"
             data-entry-id="${entry.id}"
             data-task-id="${task.id}"
             data-slot="${entry.slot}"
             data-duration="${duration}"
             ondragstart="dragScheduled(event)"
             ondragend="endScheduledDrag(event)"
             onclick="openChipModal(${entry.id})"
             onmouseenter="showHover(event)"
             onmousemove="moveHover(event)"
             onmouseleave="hideHover()">
            <div class="truncate font-semibold pr-5">${escapeHtml(task.name)}${overrideMark}</div>
            <button onmousedown="event.stopPropagation()"
                    onclick="event.stopPropagation();removeScheduled(${entry.id})"
                    draggable="false"
                    class="absolute top-0 right-1 leading-none text-base text-white/90 hover:text-white">×</button>
            <div class="absolute bottom-0 left-0 right-0 h-2 cursor-ns-resize bg-black/30 hover:bg-black/50"
                 onmousedown="startResize(event, this.parentElement)"
                 draggable="false"></div>
        </div>
    `;
    cell.insertAdjacentHTML('beforeend', html);
}

function formatChipSlot(entry){
    const parts = entry.slot.split('-');
    const quarter = parseInt(parts.pop(), 10);
    const hour = parseInt(parts.pop(), 10);
    const dateStr = parts.join('-');
    const d = parseISO(dateStr);
    const dayName = WEEKDAY_LABELS[d.getDay()];
    const minutes = quarter * 15;
    const timeStr = `${String(hour).padStart(2,'0')}:${String(minutes).padStart(2,'0')}`;
    const duration = Math.max(1, parseInt(entry.duration, 10) || 1);
    const durMins = duration * 15;
    const durStr = durMins >= 60 && durMins % 60 === 0 ? `${durMins/60} h` : `${durMins} min`;
    const dateLabel = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    return `${dayName}, ${dateLabel} · ${timeStr} · ${durStr}`;
}

function openChipModal(entryId){
    const entry = scheduleEntries.find(e => e.id === entryId);
    if (!entry) return;
    const task = tasks.find(t => t.id === entry.task_id);
    if (!task) return;

    currentChipEntryId = entryId;
    currentChipTaskId = task.id;

    document.getElementById('chipTaskName').textContent =
        (entry.is_recurring ? '↻ ' : '') + (task.name || '');
    document.getElementById('chipSlotInfo').textContent = formatChipSlot(entry);

    const useDefault = entry.input === null || entry.input === undefined;
    const inputEl = document.getElementById('chipInput');
    const useDefaultEl = document.getElementById('chipUseDefault');
    useDefaultEl.checked = useDefault;
    inputEl.value = useDefault ? '' : entry.input;
    inputEl.placeholder = task.input || '(no default input)';
    inputEl.disabled = useDefault;

    document.getElementById('chipRuleSection').classList.toggle('hidden', !entry.is_recurring);
    document.getElementById('chipModal').classList.remove('hidden');
}

function closeChipModal(){
    document.getElementById('chipModal').classList.add('hidden');
    currentChipEntryId = null;
    currentChipTaskId = null;
}

function toggleChipUseDefault(){
    const useDefault = document.getElementById('chipUseDefault').checked;
    const inputEl = document.getElementById('chipInput');
    inputEl.disabled = useDefault;
    if (useDefault) inputEl.value = '';
}

async function saveChipInput(){
    if (currentChipEntryId === null) return;
    const useDefault = document.getElementById('chipUseDefault').checked;
    const input = useDefault ? null : document.getElementById('chipInput').value;
    const res = await fetch(`/api/schedule/${currentChipEntryId}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input }),
    });
    if (res.ok) {
        const idx = scheduleEntries.findIndex(e => e.id === currentChipEntryId);
        if (idx !== -1) scheduleEntries[idx].input = input;
        renderSchedule();
    }
    closeChipModal();
}

function editRuleFromChip(){
    if (!currentChipTaskId) return;
    const tid = currentChipTaskId;
    closeChipModal();
    openRecurrenceModal(tid);
}

function editTaskFromChip(){
    if (!currentChipTaskId) return;
    const tid = currentChipTaskId;
    closeChipModal();
    editTask(tid);
}

function allowDrop(ev){
    ev.preventDefault();
}

function quarterFromEvent(ev, cell){
    const rect = cell.getBoundingClientRect();
    const y = ev.clientY - rect.top;
    return Math.max(0, Math.min(3, Math.floor(y / QUARTER_HEIGHT)));
}

async function dropTask(ev){
    ev.preventDefault();

    const cell = ev.currentTarget;
    const cellSlot = cell.dataset.slot;
    const quarter = quarterFromEvent(ev, cell);
    const slot = `${cellSlot}-${quarter}`;

    let taskId, duration = 1, entryId = null;

    const movePayload = ev.dataTransfer.getData("application/x-scheduled");
    if (movePayload) {
        const m = JSON.parse(movePayload);
        taskId = m.taskId;
        duration = m.duration || 1;
        entryId = m.entryId;
        if (m.oldSlot === slot) return;
    } else {
        taskId = ev.dataTransfer.getData("text/plain");
    }

    const res = await fetch('/api/schedule', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ id: entryId, taskId, slot, duration })
    });

    if (!res.ok) {
        console.error('schedule failed', res.status, await res.text());
        return;
    }

    const entry = await res.json();

    if (entryId) {
        const idx = scheduleEntries.findIndex(e => e.id === entryId);
        if (idx !== -1) scheduleEntries[idx] = entry;
        else scheduleEntries.push(entry);
    } else {
        scheduleEntries.push(entry);
    }

    renderSchedule();
}

function dragScheduled(ev){
    const chip = ev.currentTarget;
    const data = {
        entryId: parseInt(chip.dataset.entryId, 10),
        taskId: chip.dataset.taskId,
        oldSlot: chip.dataset.slot,
        duration: parseInt(chip.dataset.duration, 10) || 1,
    };
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("application/x-scheduled", JSON.stringify(data));
    ev.dataTransfer.setData("text/plain", chip.dataset.taskId);
    chip.style.opacity = "0.5";
    hideHover();
}

function endScheduledDrag(ev){
    ev.currentTarget.style.opacity = "";
}

async function removeScheduled(entryId){
    const id = parseInt(entryId, 10);
    await fetch('/api/schedule/remove', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ id })
    });
    scheduleEntries = scheduleEntries.filter(e => e.id !== id);
    renderSchedule();
    hideHover();
}

function startResize(ev, chipEl){
    ev.preventDefault();
    ev.stopPropagation();
    chipEl.draggable = false;
    resizeState = {
        chipEl,
        startY: ev.clientY,
        startHeight: chipEl.offsetHeight,
    };
    document.addEventListener('mousemove', onResizeMove);
    document.addEventListener('mouseup', onResizeEnd);
}

function onResizeMove(ev){
    if (!resizeState) return;
    const dy = ev.clientY - resizeState.startY;
    const newHeight = Math.max(QUARTER_HEIGHT, resizeState.startHeight + dy);
    resizeState.chipEl.style.height = newHeight + 'px';
}

async function onResizeEnd(ev){
    if (!resizeState) return;
    document.removeEventListener('mousemove', onResizeMove);
    document.removeEventListener('mouseup', onResizeEnd);

    const { chipEl } = resizeState;
    const newHeight = chipEl.offsetHeight;
    const newDuration = Math.max(1, Math.round(newHeight / QUARTER_HEIGHT));
    chipEl.draggable = true;

    const entryId = parseInt(chipEl.dataset.entryId, 10);
    const taskId = chipEl.dataset.taskId;
    const slot = chipEl.dataset.slot;
    resizeState = null;

    const res = await fetch('/api/schedule', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ id: entryId, taskId, slot, duration: newDuration })
    });

    if (res.ok) {
        const entry = await res.json();
        const idx = scheduleEntries.findIndex(e => e.id === entryId);
        if (idx !== -1) scheduleEntries[idx] = entry;
    }
    renderSchedule();
}

function showHover(ev){
    const chip = ev.currentTarget;
    const task = tasks.find(t => t.id === chip.dataset.taskId);
    if (!task) return;
    const panel = document.getElementById('hoverPanel');
    panel.innerHTML = `
        <div class="font-bold text-sm mb-1">${escapeHtml(task.name)}</div>
        ${task.description ? `<div class="mb-1 whitespace-pre-wrap">${escapeHtml(task.description)}</div>` : ''}
        ${task.tags ? `<div class="italic text-slate-300 mb-1">${escapeHtml(task.tags)}</div>` : ''}
        ${task.code ? `<pre class="bg-black/40 p-2 rounded mt-1 max-h-40 overflow-auto whitespace-pre-wrap">${escapeHtml(task.code)}</pre>` : ''}
    `;
    panel.classList.remove('hidden');
    moveHover(ev);
}

function moveHover(ev){
    const panel = document.getElementById('hoverPanel');
    if (panel.classList.contains('hidden')) return;
    const rect = panel.getBoundingClientRect();
    let x = ev.clientX + 14;
    let y = ev.clientY + 14;
    if (x + rect.width > window.innerWidth) x = ev.clientX - rect.width - 14;
    if (y + rect.height > window.innerHeight) y = ev.clientY - rect.height - 14;
    panel.style.left = Math.max(0, x) + 'px';
    panel.style.top = Math.max(0, y) + 'px';
}

function hideHover(){
    document.getElementById('hoverPanel').classList.add('hidden');
}
