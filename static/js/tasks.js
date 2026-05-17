let editingId = null;

async function loadTasks(){
    const res = await fetch('/tasks');
    if (res.status === 401) { location.href = '/'; return; }
    tasks = await res.json();
    renderTasks();
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
    const standard = tasks.filter(t => !parseRecurrence(t.recurrence));
    taskList.innerHTML = standard.map(t=>`
        <div
            id="${t.id}"
            draggable="true"
            ondragstart="dragTask(event)"
            class="p-3 rounded-xl cursor-move flex flex-col gap-2 relative"
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
    renderRecurring();
    renderSchedule();
}

function dragTask(ev){
    const id = ev.currentTarget.dataset.taskId || ev.currentTarget.id;
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", id);
}

function allowDropStandard(ev){
    ev.preventDefault();
    document.getElementById('standardArea')?.classList.add('drop-target-active');
}

function leaveStandard(ev){
    const area = document.getElementById('standardArea');
    if (!area) return;
    if (ev.relatedTarget && area.contains(ev.relatedTarget)) return;
    area.classList.remove('drop-target-active');
}

async function dropStandard(ev){
    ev.preventDefault();
    document.getElementById('standardArea')?.classList.remove('drop-target-active');

    let taskId = null;
    const movePayload = ev.dataTransfer.getData('application/x-scheduled');
    if (movePayload) {
        try { taskId = JSON.parse(movePayload).taskId || null; } catch {}
    }
    if (!taskId) taskId = ev.dataTransfer.getData('text/plain');
    if (!taskId) return;
    const task = tasks.find(t => t.id === taskId);
    if (!task || !parseRecurrence(task.recurrence)) return;

    const payload = {
        recurrence: null,
        tags: buildRecurrenceTags(task.tags, null),
        description: buildRecurrenceDescription(task.description, null),
    };
    const res = await fetch(`/task/${taskId}/recurrence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (res.ok) {
        const updated = await res.json();
        const idx = tasks.findIndex(t => t.id === taskId);
        if (idx !== -1) tasks[idx] = updated;
        await loadSchedule();
        renderTasks();
    }
}
