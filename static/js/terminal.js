let terminalPollTimer = null;
let terminalCursor = 0;

function isTerminalVisible(){
    const panel = document.getElementById('terminalPanel');
    return panel && !panel.classList.contains('hidden');
}

function toggleTerminal(){
    const panel = document.getElementById('terminalPanel');
    if (!panel) return;
    if (isTerminalVisible()) {
        panel.classList.add('hidden');
        stopTerminalPoll();
    } else {
        panel.classList.remove('hidden');
        startTerminalPoll();
    }
}

async function pollTerminalLogs(){
    if (!isTerminalVisible()) return;
    try {
        const res = await fetch(`/logs?since=${terminalCursor}`);
        if (!res.ok) return;
        const data = await res.json();
        terminalCursor = data.cursor;
        appendTerminalEntries(data.entries || []);
    } catch {}
}

function startTerminalPoll(){
    pollTerminalLogs();
    if (terminalPollTimer) clearInterval(terminalPollTimer);
    terminalPollTimer = setInterval(pollTerminalLogs, 1500);
}

function stopTerminalPoll(){
    if (terminalPollTimer) clearInterval(terminalPollTimer);
    terminalPollTimer = null;
}

function appendTerminalEntries(entries){
    if (!entries.length) return;
    const output = document.getElementById('terminalOutput');
    if (!output) return;
    const atBottom = output.scrollTop + output.clientHeight >= output.scrollHeight - 10;
    for (const e of entries) {
        const line = document.createElement('div');
        const statusClass =
            e.status >= 500 ? 'text-red-400' :
            e.status >= 400 ? 'text-amber-400' :
            e.status >= 300 ? 'text-yellow-300' :
                              'text-emerald-400';
        line.innerHTML =
            `<span class="text-slate-500">[${escapeHtml(e.time)}]</span> ` +
            `<span class="text-sky-300">${escapeHtml(e.user)}</span> ` +
            `<span class="text-slate-300">${escapeHtml(e.method)}</span> ` +
            `<span>${escapeHtml(e.path)}</span> ` +
            `<span class="${statusClass}">→ ${e.status}</span>`;
        output.appendChild(line);
    }
    while (output.children.length > 500) output.removeChild(output.firstChild);
    if (atBottom) output.scrollTop = output.scrollHeight;
}

(function setupTerminalChord(){
    const REQUIRED_CODES = new Set(['KeyM', 'KeyD', 'KeyX']);
    const downCodes = new Set();
    let firedThisChord = false;

    document.addEventListener('keydown', (e) => {
        if (!REQUIRED_CODES.has(e.code)) return;
        downCodes.add(e.code);
        if (e.ctrlKey && e.shiftKey) {
            e.preventDefault();
            if (downCodes.size === REQUIRED_CODES.size && !firedThisChord) {
                firedThisChord = true;
                toggleTerminal();
            }
        }
    });

    document.addEventListener('keyup', (e) => {
        if (!REQUIRED_CODES.has(e.code)) return;
        downCodes.delete(e.code);
        if (downCodes.size === 0) firedThisChord = false;
    });

    window.addEventListener('blur', () => {
        downCodes.clear();
        firedThisChord = false;
    });
})();
