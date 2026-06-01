let timelineAnchor = null;
let timelineAssignments = [];
let timelineScheduleEntries = [];
let timelineInitialized = false;
let currentAssignmentId = null;

let stripSession = null;
let stripMarks = [];
let stripSegments = [];
let stripState = 'idle';
let stripUpdateInterval = null;

const STRIP_TOTAL_MS = 8 * 60 * 60 * 1000;

function initTimeline() {
    if (timelineInitialized) return;
    timelineInitialized = true;
    timelineAnchor = mondayOf(parseISO(TODAY_ISO));
    loadTimelineAssignments();
    loadTimelineSchedule();
    initStrip();
}

function initStrip() {
    loadStripSession();
}

function navigateTimeline(delta) {
    if (!timelineAnchor) timelineAnchor = mondayOf(new Date());
    timelineAnchor.setDate(timelineAnchor.getDate() + delta * 7);
    renderTimelineGrid();
}

function navigateTimelineToday() {
    timelineAnchor = mondayOf(new Date());
    renderTimelineGrid();
}

function renderTimelineGrid() {
    const grid = document.getElementById('timelineGrid');
    const title = document.getElementById('timelineTitle');
    if (!grid || !timelineAnchor) return;

    const days = [];
    for (let i = 0; i < 7; i++) {
        const d = new Date(timelineAnchor);
        d.setDate(d.getDate() + i);
        days.push(d);
    }

    const startStr = days[0].toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const endStr = days[6].toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    if (title) title.textContent = startStr + ' – ' + endStr;

    grid.innerHTML = '';
    const todayISO = TODAY_ISO;

    for (const day of days) {
        const iso = day.toISOString().slice(0, 10);
        const box = document.createElement('div');
        box.className = 'timeline-day-box';
        if (iso === todayISO) box.classList.add('timeline-day-today');

        box.dataset.date = iso;
        box.addEventListener('dragover', (e) => { e.preventDefault(); box.classList.add('timeline-day-dragover'); });
        box.addEventListener('dragleave', () => { box.classList.remove('timeline-day-dragover'); });
        box.addEventListener('drop', (e) => { e.preventDefault(); box.classList.remove('timeline-day-dragover'); dropOnTimelineDay(e, iso); });

        const header = document.createElement('div');
        header.className = 'timeline-day-header';
        header.textContent = WEEKDAY_LABELS[day.getDay()] + ' ' + day.getDate();

        const body = document.createElement('div');
        body.className = 'timeline-day-body';

        const entries = timelineScheduleEntries.filter(e => e.slot === iso);
        for (const entry of entries) {
            const assignment = timelineAssignments.find(a => a.id === entry.assignment_id);
            if (!assignment) continue;
            const chip = document.createElement('div');
            chip.className = 'timeline-chip';
            chip.style.backgroundColor = assignment.color || '#64748b';
            chip.textContent = assignment.project_code;
            chip.title = assignment.title;
            body.appendChild(chip);
        }

        box.appendChild(header);
        box.appendChild(body);
        grid.appendChild(box);
    }

    updateTimelineOutOfRange();
}

function updateTimelineOutOfRange() {
    const overlay = document.getElementById('timelineOutOfRangeOverlay');
    const msg = document.getElementById('timelineOutOfRangeMessage');
    if (!overlay || !msg || !timelineAnchor) return;
    if (!validRangeStart || !validRangeEnd) { overlay.classList.add('hidden'); return; }

    const weekStart = new Date(timelineAnchor);
    weekStart.setHours(0, 0, 0, 0);
    const weekEnd = new Date(timelineAnchor);
    weekEnd.setDate(weekEnd.getDate() + 6);
    weekEnd.setHours(0, 0, 0, 0);

    if (weekEnd < validRangeStart) {
        msg.textContent = 'The past is best left behind';
        overlay.classList.remove('hidden');
    } else if (weekStart > validRangeEnd) {
        msg.textContent = 'The future is yet to be made';
        overlay.classList.remove('hidden');
    } else {
        overlay.classList.add('hidden');
    }
}

function dropOnTimelineDay(e, iso) {
    const assignmentId = e.dataTransfer.getData('text/plain');
    if (!assignmentId) return;
    fetch('/api/timeline/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot: iso, assignment_id: assignmentId })
    }).then(r => { if (r.ok) loadTimelineSchedule(); });
}

async function loadTimelineAssignments() {
    try {
        const res = await fetch('/api/timeline/assignments');
        if (!res.ok) return;
        timelineAssignments = await res.json();
        renderAssignmentList();
        renderTimelineGrid();
        renderStripLine();
    } catch {}
}

async function loadTimelineSchedule() {
    try {
        const res = await fetch('/api/timeline/schedule');
        if (!res.ok) return;
        timelineScheduleEntries = await res.json();
        renderTimelineGrid();
    } catch {}
}

function renderAssignmentList() {
    const list = document.getElementById('assignmentList');
    if (!list) return;
    list.innerHTML = '';
    if (!timelineAssignments.length) {
        list.innerHTML = '<div class="text-sm text-slate-500 italic">No assignments yet</div>';
        return;
    }
    for (const a of timelineAssignments) {
        const card = document.createElement('div');
        card.className = 'timeline-assignment-card';
        card.draggable = true;
        card.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('text/plain', a.id);
        });
        card.addEventListener('click', () => openAssignmentModal(a));

        const dot = document.createElement('span');
        dot.className = 'timeline-assignment-dot';
        dot.style.backgroundColor = a.color || '#64748b';

        const text = document.createElement('div');
        text.className = 'timeline-assignment-text';

        const code = document.createElement('span');
        code.className = 'timeline-assignment-code';
        code.textContent = a.project_code;

        const titleEl = document.createElement('span');
        titleEl.className = 'timeline-assignment-title';
        titleEl.textContent = a.title;

        text.appendChild(code);
        text.appendChild(titleEl);
        card.appendChild(dot);
        card.appendChild(text);
        list.appendChild(card);
    }
}

function openAssignmentModal(assignment) {
    const modal = document.getElementById('assignmentModal');
    const titleEl = document.getElementById('assignmentModalTitle');
    const codeInput = document.getElementById('assignmentCode');
    const titleInput = document.getElementById('assignmentTitle');
    const colorInput = document.getElementById('assignmentColor');
    const deleteBtn = document.getElementById('assignmentDeleteBtn');
    if (!modal) return;

    if (assignment) {
        currentAssignmentId = assignment.id;
        titleEl.textContent = 'Edit Assignment';
        codeInput.value = assignment.project_code;
        titleInput.value = assignment.title;
        colorInput.value = assignment.color || '#64748b';
        deleteBtn.classList.remove('hidden');
    } else {
        currentAssignmentId = null;
        titleEl.textContent = 'Create Assignment';
        codeInput.value = '';
        titleInput.value = '';
        colorInput.value = '#64748b';
        deleteBtn.classList.add('hidden');
    }
    modal.classList.remove('hidden');
}

function closeAssignmentModal() {
    const modal = document.getElementById('assignmentModal');
    if (modal) modal.classList.add('hidden');
    currentAssignmentId = null;
}

async function saveAssignment() {
    const project_code = document.getElementById('assignmentCode').value.trim();
    const title = document.getElementById('assignmentTitle').value.trim();
    const color = document.getElementById('assignmentColor').value;
    if (!project_code || !title) return;

    const url = currentAssignmentId
        ? '/api/timeline/assignment/' + currentAssignmentId
        : '/api/timeline/assignment';
    const method = currentAssignmentId ? 'PUT' : 'POST';

    const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_code, title, color })
    });
    if (res.ok) {
        closeAssignmentModal();
        await loadTimelineAssignments();
    }
}

async function deleteAssignment() {
    if (!currentAssignmentId) return;
    const res = await fetch('/api/timeline/assignment/' + currentAssignmentId, { method: 'DELETE' });
    if (res.ok) {
        closeAssignmentModal();
        await loadTimelineAssignments();
        await loadTimelineSchedule();
    }
}

// ── Strip session logic ──

async function loadStripSession() {
    try {
        const res = await fetch('/api/timeline/strip/today');
        if (!res.ok) return;
        const data = await res.json();
        stripSession = data.session;
        stripMarks = data.marks || [];
        stripSegments = data.segments || [];
        if (stripSession && !stripSession.stopped_at) {
            stripState = 'running';
            startStripInterval();
        } else {
            stripState = 'idle';
        }
        updateStripButtons();
        renderStripLine();
    } catch {}
}

function updateStripButtons() {
    const topBtn = document.getElementById('stripTopBtn');
    const botBtn = document.getElementById('stripBottomBtn');
    const lineContainer = document.getElementById('stripLineContainer');
    if (!topBtn || !botBtn || !lineContainer) return;

    topBtn.className = 'strip-btn';
    topBtn.disabled = stripState === 'marking';
    if (stripState === 'idle') {
        topBtn.classList.add('strip-btn-green');
        botBtn.classList.add('hidden');
        lineContainer.classList.add('hidden');
    } else if (stripState === 'running') {
        topBtn.classList.add('strip-btn-blue');
        botBtn.classList.remove('hidden');
        lineContainer.classList.remove('hidden');
    } else if (stripState === 'marking') {
        topBtn.classList.add('strip-btn-purple');
        botBtn.classList.remove('hidden');
        lineContainer.classList.remove('hidden');
    }
}

const STRIP_MARK_FLASH_MS = 600;

async function onStripTopClick() {
    if (stripState === 'marking') return;
    if (stripState === 'idle') {
        const res = await fetch('/api/timeline/strip/start', { method: 'POST' });
        if (!res.ok) return;
        const data = await res.json();
        stripSession = data.session;
        stripMarks = [];
        stripSegments = data.segments || [];
        stripState = 'running';
        updateStripButtons();
        renderStripLine();
        startStripInterval();
        return;
    }
    if (stripState === 'running') {
        stripState = 'marking';
        updateStripButtons();
        let ok = false;
        try {
            const res = await fetch('/api/timeline/strip/mark', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: stripSession.id })
            });
            if (res.ok) {
                const data = await res.json();
                stripMarks = data.marks;
                stripSegments = data.segments;
                renderStripLine();
                ok = true;
            }
        } catch {}
        if (!ok) {
            stripState = 'running';
            updateStripButtons();
            return;
        }
        setTimeout(() => {
            if (stripState === 'marking') {
                stripState = 'running';
                updateStripButtons();
            }
        }, STRIP_MARK_FLASH_MS);
    }
}

async function onStripStopClick() {
    if (!stripSession) return;
    const res = await fetch('/api/timeline/strip/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: stripSession.id })
    });
    if (!res.ok) return;
    const data = await res.json();
    stripSession = data.session;
    stripState = 'idle';
    stopStripInterval();
    updateStripButtons();
    renderStripLine();
}

function startStripInterval() {
    stopStripInterval();
    const scheduleNext = () => {
        const n = new Date();
        const delay = (60 - n.getSeconds()) * 1000 - n.getMilliseconds();
        stripUpdateInterval = setTimeout(() => {
            if (stripSession && !stripSession.stopped_at) {
                renderStripLine();
            }
            scheduleNext();
        }, delay);
    };
    scheduleNext();
}

function stopStripInterval() {
    if (stripUpdateInterval) {
        clearTimeout(stripUpdateInterval);
        stripUpdateInterval = null;
    }
}

function renderStripLine() {
    const line = document.getElementById('stripLine');
    const container = document.getElementById('stripLineContainer');
    if (!line || !container) return;
    if (!stripSession) { line.style.height = '0'; line.innerHTML = ''; return; }

    const startTime = new Date(stripSession.started_at).getTime();
    const now = stripSession.stopped_at ? new Date(stripSession.stopped_at).getTime() : Date.now();
    const elapsedMs = Math.max(0, now - startTime);
    const elapsedRatio = Math.min(1.0, elapsedMs / STRIP_TOTAL_MS);

    line.style.height = (elapsedRatio * 100) + '%';
    line.innerHTML = '';

    if (elapsedRatio === 0) return;

    const points = [startTime];
    for (const m of stripMarks) {
        points.push(new Date(m.marked_at).getTime());
    }
    points.push(now);

    for (let i = 0; i < points.length - 1; i++) {
        const segStart = points[i];
        const segEnd = points[i + 1];
        const segStartRatio = (segStart - startTime) / STRIP_TOTAL_MS;
        const segEndRatio = Math.min(elapsedRatio, (segEnd - startTime) / STRIP_TOTAL_MS);
        const segHeightPct = elapsedRatio > 0 ? ((segEndRatio - segStartRatio) / elapsedRatio) * 100 : 0;

        const segRecord = stripSegments.find(s => s.segment_index === i);
        const assignment = segRecord && segRecord.assignment_id
            ? timelineAssignments.find(a => a.id === segRecord.assignment_id)
            : null;

        // Mark point before segment (except for the first segment which gets a start dot)
        if (i === 0) {
            const startDot = document.createElement('div');
            startDot.className = 'strip-point strip-point-start';
            startDot.addEventListener('mouseenter', (ev) => showStripPointHover(ev, startTime));
            startDot.addEventListener('mousemove', moveHover);
            startDot.addEventListener('mouseleave', hideHover);
            line.appendChild(startDot);
        }

        const segEl = document.createElement('div');
        segEl.className = 'strip-segment';
        segEl.style.height = segHeightPct + '%';
        segEl.style.backgroundColor = assignment ? assignment.color : '';
        segEl.dataset.segmentId = segRecord ? segRecord.id : '';
        segEl.dataset.segmentIndex = i;

        segEl.addEventListener('dragover', (e) => { e.preventDefault(); segEl.classList.add('strip-segment-dragover'); });
        segEl.addEventListener('dragleave', () => { segEl.classList.remove('strip-segment-dragover'); });
        segEl.addEventListener('drop', (e) => { e.preventDefault(); segEl.classList.remove('strip-segment-dragover'); dropOnStripSegment(e, segRecord); });

        const capturedStart = segStart;
        const capturedEnd = segEnd;
        const capturedAssignment = assignment;
        segEl.addEventListener('mouseenter', (ev) => showStripSegmentHover(ev, capturedStart, capturedEnd, capturedAssignment));
        segEl.addEventListener('mousemove', moveHover);
        segEl.addEventListener('mouseleave', hideHover);

        line.appendChild(segEl);

        // Mark dot after segment (between segments)
        if (i < points.length - 2) {
            const dotEl = document.createElement('div');
            dotEl.className = 'strip-point strip-point-mark';
            const markRecord = stripMarks[i];
            const markTime = points[i + 1];
            dotEl.addEventListener('mouseenter', (ev) => showStripPointHover(ev, new Date(markRecord.marked_at).getTime()));
            dotEl.addEventListener('mousemove', moveHover);
            dotEl.addEventListener('mouseleave', hideHover);
            dotEl.addEventListener('mousedown', (ev) => startMarkDrag(ev, markRecord));
            line.appendChild(dotEl);
        }
    }

    // End / progressing point
    const isProgressing = !stripSession.stopped_at;
    const endDot = document.createElement('div');
    endDot.className = 'strip-point ' + (isProgressing ? 'strip-point-progressing' : 'strip-point-end');
    endDot.addEventListener('mouseenter', (ev) => showStripPointHover(ev, isProgressing ? Date.now() : now));
    endDot.addEventListener('mousemove', moveHover);
    endDot.addEventListener('mouseleave', hideHover);
    if (isProgressing) {
        const label = document.createElement('div');
        label.className = 'strip-progressing-label';
        const d = new Date();
        label.textContent = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
        endDot.appendChild(label);
    }
    line.appendChild(endDot);
}

function startMarkDrag(e, mark) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const line = document.getElementById('stripLine');
    if (!line || !stripSession) return;
    const startTime = new Date(stripSession.started_at).getTime();
    const getEndTime = () => stripSession.stopped_at ? new Date(stripSession.stopped_at).getTime() : Date.now();
    const idx = stripMarks.findIndex(m => m.id === mark.id);
    if (idx < 0) return;
    let lastClientY = e.clientY;
    document.body.style.cursor = 'ns-resize';

    function neighbours() {
        const prev = idx === 0 ? startTime : new Date(stripMarks[idx - 1].marked_at).getTime();
        const next = idx === stripMarks.length - 1 ? getEndTime() : new Date(stripMarks[idx + 1].marked_at).getTime();
        return { prev, next };
    }

    function onMove(ev) {
        const rect = line.getBoundingClientRect();
        if (rect.height <= 0) return;
        const span = getEndTime() - startTime;
        if (span <= 0) return;
        const msPerPx = span / rect.height;
        const deltaPx = ev.clientY - lastClientY;
        const { prev, next } = neighbours();
        let newTime = new Date(mark.marked_at).getTime() + deltaPx * msPerPx;
        // Strict bounds: cannot bypass adjacent points. 1s epsilon keeps strict ordering.
        if (newTime <= prev) newTime = prev + 1000;
        if (newTime >= next) newTime = next - 1000;
        mark.marked_at = new Date(newTime).toISOString();
        lastClientY = ev.clientY;
        renderStripLine();
    }

    function onUp() {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = '';
        fetch('/api/timeline/strip/mark/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mark_id: mark.id, marked_at: mark.marked_at })
        }).then(r => { if (!r.ok) loadStripSession(); });
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
}

function showStripPointHover(ev, timestamp) {
    const panel = document.getElementById('hoverPanel');
    if (!panel) return;
    const d = new Date(timestamp);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    panel.innerHTML = '<div class="font-bold text-sm">' + hh + ':' + mm + '</div>';
    panel.classList.remove('hidden');
    moveHover(ev);
}

function showStripSegmentHover(ev, startMs, endMs, assignment) {
    const panel = document.getElementById('hoverPanel');
    if (!panel) return;
    const fmt = (ms) => {
        const d = new Date(ms);
        return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    };
    const timeRange = fmt(startMs) + ' – ' + fmt(endMs);
    const name = assignment
        ? escapeHtml(assignment.project_code + ': ' + assignment.title)
        : 'Drag assignment here to note this segment';
    panel.innerHTML = '<div class="font-bold text-sm mb-1">' + timeRange + '</div><div class="text-slate-300">' + name + '</div>';
    panel.classList.remove('hidden');
    moveHover(ev);
}

function dropOnStripSegment(e, segRecord) {
    const assignmentId = e.dataTransfer.getData('text/plain');
    if (!assignmentId || !segRecord) return;
    fetch('/api/timeline/strip/segment/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ segment_id: segRecord.id, assignment_id: assignmentId })
    }).then(r => {
        if (r.ok) {
            segRecord.assignment_id = assignmentId;
            renderStripLine();
        }
    });
}
