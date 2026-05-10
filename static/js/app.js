const TODAY_STR = document.body.dataset.today;
const QUARTER_HEIGHT = 36;
const HOUR_HEIGHT = 144;

const SUN_ICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-5 h-5"><path fill-rule="evenodd" d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59zM21.75 12a.75.75 0 01-.75.75h-2.25a.75.75 0 010-1.5H21a.75.75 0 01.75.75zM17.834 18.894a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 10-1.061 1.06l1.59 1.591zM12 18a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-2.25A.75.75 0 0112 18zM7.758 17.303a.75.75 0 00-1.061-1.06l-1.591 1.59a.75.75 0 001.06 1.061l1.591-1.59zM6 12a.75.75 0 01-.75.75H3a.75.75 0 010-1.5h2.25A.75.75 0 016 12zM6.697 7.757a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 00-1.061 1.06l1.59 1.591z" clip-rule="evenodd" /></svg>`;
const MOON_ICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-5 h-5"><path fill-rule="evenodd" d="M9.528 1.718a.75.75 0 01.162.819A8.97 8.97 0 009 6a9 9 0 009 9 8.97 8.97 0 003.463-.69.75.75 0 01.981.98 10.503 10.503 0 01-9.694 6.46c-5.799 0-10.5-4.701-10.5-10.5 0-4.368 2.667-8.112 6.46-9.694a.75.75 0 01.818.162z" clip-rule="evenodd" /></svg>`;

let tasks = [];
let scheduleEntries = [];
let editingId = null;
let currentMode = 'day';
let currentView = 'week';

const ALL_DAYS = Array.from(document.querySelectorAll('.day-header')).map(el => el.dataset.day);
const VIEW_TITLES = { day: 'Day View', weekday: 'Weekday View', week: 'Full Week View' };

function isWeekendLabel(label){
    return label.startsWith('Sat') || label.startsWith('Sun');
}

function getVisibleDays(){
    if (currentView === 'day') return [TODAY_STR];
    if (currentView === 'weekday') return ALL_DAYS.filter(d => !isWeekendLabel(d));
    return ALL_DAYS;
}

function isTodayVisible(){
    if (currentView === 'weekday') return !isWeekendLabel(TODAY_STR);
    return true;
}

function hourInMode(h, mode){
    return mode === 'day' ? (h >= 8 && h < 20) : (h < 8 || h >= 20);
}

function applyVisibility(){
    const visibleDays = getVisibleDays();
    const visibleSet = new Set(visibleDays);

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
    grid.style.gridTemplateColumns = `4rem repeat(${visibleDays.length}, 1fr)`;
    grid.classList.toggle('grayed-out',
        currentView === 'weekday' && isWeekendLabel(TODAY_STR));
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
    currentView = view;
    applyVisibility();
    document.querySelectorAll('[data-view-btn]').forEach(b => {
        b.classList.toggle('active-view', b.dataset.viewBtn === view);
    });
    const title = document.getElementById('viewTitle');
    if (title) title.textContent = VIEW_TITLES[view] || '';
    updateNowLine();
}

function toggleMode(){
    applyMode(currentMode === 'day' ? 'night' : 'day');
}

window.onload = async () => {
    const hour = new Date().getHours();
    applyView('week');
    applyMode((hour >= 8 && hour < 20) ? 'day' : 'night');
    await loadTasks();
    await loadSchedule();
    updateNowLine();
    setInterval(updateNowLine, 30000);
    setInterval(async () => {
        await loadTasks();
        await loadSchedule();
    }, 5000);
};

async function loadTasks(){
    const res = await fetch('/tasks');
    if (res.status === 401) { location.href = '/'; return; }
    tasks = await res.json();
    renderTasks();
}

async function loadSchedule(){
    const res = await fetch('/schedule');
    if (res.status === 401) { location.href = '/'; return; }
    scheduleEntries = await res.json();
    renderSchedule();
}

function escapeHtml(s){
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
             onmouseenter="showHover(event)"
             onmousemove="moveHover(event)"
             onmouseleave="hideHover()">
            <div class="truncate font-semibold pr-5">${escapeHtml(task.name)}</div>
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

function openModal(task){
    if (task) {
        editingId = task.id;
        taskName.value = task.name || '';
        taskDescription.value = task.description || '';
        taskTags.value = task.tags || '';
        taskColor.value = task.color || '#3b82f6';
        taskCode.value = task.code || '';
        taskInput.value = task.input || '';
        document.getElementById("saveBtn").textContent = "Update";
    } else {
        editingId = null;
        taskName.value = '';
        taskDescription.value = '';
        taskTags.value = '';
        taskColor.value = '#3b82f6';
        taskCode.value = '';
        taskInput.value = '';
        document.getElementById("saveBtn").textContent = "Save";
    }
    updateInputVisibility();
    document.getElementById("taskModal").classList.remove("hidden");
}

function updateInputVisibility(){
    const hasCode = taskCode.value.trim().length > 0;
    document.getElementById("taskInputSection").classList.toggle("hidden", !hasCode);
}

function closeModal(){
    document.getElementById("taskModal").classList.add("hidden");
    editingId = null;
}

function toggleCode(){
    document.getElementById("taskCode").classList.toggle("hidden");
}

async function saveTask(){
    const payload = {
        name: taskName.value,
        description: taskDescription.value,
        tags: taskTags.value,
        color: taskColor.value,
        code: taskCode.value,
        input: taskCode.value.trim() ? taskInput.value : ''
    };

    if (editingId) {
        const id = editingId;
        const res = await fetch('/task/' + id, {
            method:'PUT',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
        });
        const task = await res.json();
        const idx = tasks.findIndex(t => t.id === id);
        if (idx !== -1) tasks[idx] = task;
        renderSchedule();
    } else {
        const res = await fetch('/task', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify(payload)
        });
        const task = await res.json();
        tasks.push(task);
    }

    renderTasks();
    closeModal();
}

function editTask(id){
    const task = tasks.find(t => t.id === id);
    if (task) openModal(task);
}

async function deleteTask(id){
    if (!confirm('Delete this task?')) return;
    await fetch('/task/' + id, {method:'DELETE'});
    tasks = tasks.filter(t => t.id !== id);
    scheduleEntries = scheduleEntries.filter(e => e.task_id !== id);
    renderTasks();
    renderSchedule();
}

function renderTasks(){
    taskList.innerHTML = tasks.map(t=>`
        <div
            id="${t.id}"
            draggable="true"
            ondragstart="dragTask(event)"
            class="p-3 rounded-xl cursor-move flex flex-col gap-2"
            style="background:${t.color};color:white">
            <div class="min-w-0">
                <div class="font-bold truncate">${escapeHtml(t.name)}</div>
                <div class="text-xs truncate">${escapeHtml(t.tags || '')}</div>
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
    `).join("");
}

function dragTask(ev){
    const id = ev.currentTarget.id;
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", id);
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

    const res = await fetch('/schedule', {
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
    await fetch('/schedule/remove', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ id })
    });
    scheduleEntries = scheduleEntries.filter(e => e.id !== id);
    renderSchedule();
    hideHover();
}

let resizeState = null;

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

    const res = await fetch('/schedule', {
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

async function refreshAdminUsers(){
    const res = await fetch('/admin/users');
    if (!res.ok) return;
    const users = await res.json();
    const pending = users.filter(u => u.status === 'pending');
    const active = users.filter(u => u.status === 'active');

    const fmtDate = s => {
        const d = new Date(s.endsWith('Z') ? s : s + 'Z');
        return isNaN(d) ? s : d.toLocaleString();
    };

    const pendingEl = document.getElementById('pendingUsers');
    pendingEl.innerHTML = pending.length === 0
        ? '<div class="text-slate-500 text-sm">No pending requests.</div>'
        : pending.map(u => `
            <div class="flex items-center justify-between border rounded p-2">
                <div>
                    <div class="font-semibold">${escapeHtml(u.username)}</div>
                    <div class="text-xs text-slate-500">requested ${fmtDate(u.created_at)}</div>
                </div>
                <div class="flex gap-2">
                    <button onclick="approveUser(${u.id})" class="bg-green-600 text-white px-3 py-1 rounded text-sm">Approve</button>
                    <button onclick="rejectUser(${u.id})" class="bg-red-600 text-white px-3 py-1 rounded text-sm">Reject</button>
                </div>
            </div>
        `).join('');

    document.getElementById('activeUsers').innerHTML = active.map(u => `
        <div class="flex items-center justify-between border rounded p-2">
            <div>
                <div class="font-semibold">
                    ${escapeHtml(u.username)}
                    ${u.role === 'admin' ? '<span class="ml-2 text-xs bg-slate-900 text-white px-1.5 py-0.5 rounded">admin</span>' : ''}
                </div>
                <div class="text-xs text-slate-500">registered ${fmtDate(u.created_at)}</div>
            </div>
            <div class="flex gap-2">
                <button onclick="resetPassword(${u.id}, '${escapeHtml(u.username)}')" class="bg-slate-900 text-white px-3 py-1 rounded text-sm">Reset password</button>
                ${u.role !== 'admin' ? `<button onclick="revokeUser(${u.id})" class="bg-red-600 text-white px-3 py-1 rounded text-sm">Revoke</button>` : ''}
            </div>
        </div>
    `).join('');
}

async function openAdminPanel(){
    await refreshAdminUsers();
    document.getElementById('adminPanel').classList.remove('hidden');
}

function closeAdminPanel(){
    document.getElementById('adminPanel').classList.add('hidden');
}

async function approveUser(id){
    await fetch(`/admin/users/${id}/approve`, { method: 'POST' });
    await refreshAdminUsers();
}

async function rejectUser(id){
    await fetch(`/admin/users/${id}/reject`, { method: 'POST' });
    await refreshAdminUsers();
}

async function revokeUser(id){
    if (!confirm('Revoke this user? Their account will be deleted.')) return;
    await fetch(`/admin/users/${id}`, { method: 'DELETE' });
    await refreshAdminUsers();
}

let resetPasswordUserId = null;

function resetPassword(id, username){
    resetPasswordUserId = id;
    document.getElementById('resetPasswordTarget').textContent = `User: ${username}`;
    document.getElementById('resetPasswordInput').value = '';
    document.getElementById('resetPasswordError').classList.add('hidden');
    document.getElementById('resetPasswordModal').classList.remove('hidden');
    setTimeout(() => document.getElementById('resetPasswordInput').focus(), 0);
}

function closeResetPassword(){
    document.getElementById('resetPasswordModal').classList.add('hidden');
    resetPasswordUserId = null;
}

async function submitResetPassword(){
    if (resetPasswordUserId === null) return;
    const pwd = document.getElementById('resetPasswordInput').value;
    const err = document.getElementById('resetPasswordError');
    if (!pwd) {
        err.textContent = 'Password cannot be empty.';
        err.classList.remove('hidden');
        return;
    }
    const res = await fetch(`/admin/users/${resetPasswordUserId}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd })
    });
    if (res.ok) {
        closeResetPassword();
    } else {
        err.textContent = 'Failed to update password.';
        err.classList.remove('hidden');
    }
}

(function setupAdminTrigger(){
    const trigger = document.getElementById('adminTrigger');
    if (!trigger) return;

    let startY = null;
    let dragged = false;

    trigger.addEventListener('mousedown', (e) => {
        startY = e.clientY;
        dragged = false;
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (startY === null) return;
        if (Math.abs(e.clientY - startY) > 5) dragged = true;
    });

    document.addEventListener('mouseup', (e) => {
        if (startY === null) return;
        const dy = e.clientY - startY;
        startY = null;
        if (dragged && dy > 120) openAdminPanel();
    });

    trigger.addEventListener('click', (e) => { e.preventDefault(); });
})();

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

    const todayCell = grid.querySelector(`[data-slot="${TODAY_STR}-${currentHour}"]`);
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
