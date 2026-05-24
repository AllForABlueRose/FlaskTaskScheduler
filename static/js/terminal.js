let terminalPollTimer = null;
let terminalHideTimer = null;
let terminalCursor = 0;
let terminalChordOn = false;
const TERMINAL_HIDE_DELAY_MS = 30000;

function isTerminalVisible(){
    const panel = document.getElementById('terminalPanel');
    return !!panel && panel.classList.contains('terminal-panel-open');
}

function toggleTerminalChord(){
    setTerminalChord(!terminalChordOn);
}

function setTerminalChord(on){
    terminalChordOn = on;
    document.body.classList.toggle('terminal-chord-on', on);
    if (!on) {
        clearTerminalHideTimer();
        hideTerminalPanel({ immediate: true });
    }
}

function showTerminalPanel(){
    if (!terminalChordOn) return;
    const panel = document.getElementById('terminalPanel');
    const tab = document.getElementById('terminalTab');
    if (!panel) return;
    clearTerminalHideTimer();
    panel.classList.add('terminal-panel-open');
    if (tab) tab.classList.add('terminal-tab-hidden-by-panel');
    startTerminalPoll();
}

function hideTerminalPanel(opts){
    opts = opts || {};
    const panel = document.getElementById('terminalPanel');
    const tab = document.getElementById('terminalTab');
    if (!panel) return;
    panel.classList.remove('terminal-panel-open');
    if (tab) tab.classList.remove('terminal-tab-hidden-by-panel');
    stopTerminalPoll();
}

function startTerminalHideTimer(){
    if (!terminalChordOn) return;
    clearTerminalHideTimer();
    terminalHideTimer = setTimeout(() => {
        terminalHideTimer = null;
        hideTerminalPanel();
    }, TERMINAL_HIDE_DELAY_MS);
}

function clearTerminalHideTimer(){
    if (terminalHideTimer) {
        clearTimeout(terminalHideTimer);
        terminalHideTimer = null;
    }
}

function initTerminalHover(){
    const tab = document.getElementById('terminalTab');
    const panel = document.getElementById('terminalPanel');
    if (!tab || !panel) return;

    const enter = () => {
        if (!terminalChordOn) return;
        showTerminalPanel();
    };
    const leave = () => {
        if (!terminalChordOn) return;
        startTerminalHideTimer();
    };

    tab.addEventListener('mouseenter', enter);
    tab.addEventListener('mouseleave', leave);
    panel.addEventListener('mouseenter', enter);
    panel.addEventListener('mouseleave', leave);
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
                toggleTerminalChord();
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
