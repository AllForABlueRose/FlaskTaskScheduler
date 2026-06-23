// Traces: scrapbook-style guided image collection.
// A workflow is a reusable template; running one produces a workbook that the
// operator fills page by page by pasting/dropping images and adding notes.

let tracesInitialized = false;
let tracesMode = 'home';            // 'home' | 'define' | 'fill' | 'view'
let tracesWorkflows = { drafts: [], concluded: [] };
let tracesWorkbooks = [];
let tracesActiveWorkflow = null;    // {id,title,status,pages:[...]}
let tracesActiveWorkbook = null;    // {id,status,title,pages:[...]}
let tracesPageIndex = 0;
let tracesSkipped = [];

function initTraces(){
    loadTracesWorkflows();
    loadTracesWorkbooks();
    if (!tracesInitialized){
        tracesInitialized = true;
        document.addEventListener('paste', onTracesPaste);
    }
    renderTracesCenter();
}

// --- data loading ---

async function tracesGet(url){
    try {
        const res = await fetch(url);
        if (res.status === 401){ location.href = '/'; return null; }
        if (!res.ok) return null;
        return await res.json();
    } catch { return null; }
}

async function tracesSend(url, method, body){
    try {
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        if (res.status === 401){ location.href = '/'; return null; }
        if (!res.ok){
            const err = await res.json().catch(() => ({}));
            return { __error: err.error || ('request failed (' + res.status + ')') };
        }
        return await res.json().catch(() => ({}));
    } catch {
        return { __error: 'Network error' };
    }
}

async function loadTracesWorkflows(){
    const data = await tracesGet('/api/traces/workflows');
    if (data) tracesWorkflows = data;
    renderTracesLeft();
}

async function loadTracesWorkbooks(){
    const data = await tracesGet('/api/traces/workbooks');
    if (Array.isArray(data)) tracesWorkbooks = data;
    renderTracesRight();
}

async function reloadActiveWorkflow(){
    if (!tracesActiveWorkflow) return;
    const data = await tracesGet('/api/traces/workflows/' + tracesActiveWorkflow.id);
    if (data) tracesActiveWorkflow = data;
}

async function reloadActiveWorkbook(){
    if (!tracesActiveWorkbook) return;
    const data = await tracesGet('/api/traces/workbooks/' + tracesActiveWorkbook.id);
    if (data) tracesActiveWorkbook = data;
}

function activePages(){
    if (tracesMode === 'define') return (tracesActiveWorkflow && tracesActiveWorkflow.pages) || [];
    if (tracesMode === 'fill' || tracesMode === 'view') return (tracesActiveWorkbook && tracesActiveWorkbook.pages) || [];
    return [];
}

function clampPageIndex(){
    const n = activePages().length;
    if (tracesPageIndex < 0) tracesPageIndex = 0;
    if (tracesPageIndex > n - 1) tracesPageIndex = Math.max(0, n - 1);
}

// --- left panel: define + concluded workflows ---

function renderTracesLeft(){
    const el = document.getElementById('tracesLeft');
    if (!el) return;
    el.innerHTML = '';

    const head = document.createElement('div');
    head.className = 'traces-panel-head';
    head.textContent = 'Workflows';
    el.appendChild(head);

    const body = document.createElement('div');
    body.className = 'traces-panel-body';

    const define = document.createElement('button');
    define.className = 'traces-define-btn';
    define.textContent = '+ Define new workflow';
    define.addEventListener('click', defineNewWorkflow);
    body.appendChild(define);

    if (tracesWorkflows.concluded.length){
        const label = document.createElement('div');
        label.className = 'traces-subhead';
        label.textContent = 'Start a run';
        body.appendChild(label);
        for (const wf of tracesWorkflows.concluded){
            const item = document.createElement('button');
            item.className = 'traces-wf-item';
            if (tracesMode === 'fill' && tracesActiveWorkbook && tracesActiveWorkbook.workflow_id === wf.id){
                item.classList.add('traces-wf-item-active');
            }
            const t = document.createElement('span');
            t.className = 'traces-wf-title';
            t.textContent = wf.title || '(untitled)';
            const c = document.createElement('span');
            c.className = 'traces-wf-count';
            c.textContent = wf.page_count + 'p';
            item.appendChild(t);
            item.appendChild(c);
            item.title = 'Start a new run from this workflow';
            item.addEventListener('click', () => startWorkbook(wf.id));
            body.appendChild(item);
        }
    }

    if (tracesWorkflows.drafts.length){
        const label = document.createElement('div');
        label.className = 'traces-subhead';
        label.textContent = 'Drafts';
        body.appendChild(label);
        for (const wf of tracesWorkflows.drafts){
            const row = document.createElement('div');
            row.className = 'traces-draft-row';
            const open = document.createElement('button');
            open.className = 'traces-draft-item';
            open.textContent = wf.title || '(untitled draft)';
            open.title = 'Continue editing';
            open.addEventListener('click', () => editDraft(wf.id));
            const del = document.createElement('button');
            del.className = 'traces-draft-delete';
            del.textContent = '×';
            del.title = 'Delete draft';
            del.addEventListener('click', () => deleteWorkflow(wf.id));
            row.appendChild(open);
            row.appendChild(del);
            body.appendChild(row);
        }
    }

    el.appendChild(body);
}

// --- right panel: records of all runs ---

const TRACES_STATUS_META = {
    in_progress: { cls: 'traces-wb-grey', label: 'In progress' },
    incomplete:  { cls: 'traces-wb-grey', label: 'Incomplete' },
    complete:    { cls: 'traces-wb-green', label: '✓ Complete' },
    errata:      { cls: 'traces-wb-yellow', label: 'Errata' },
};

function renderTracesRight(){
    const el = document.getElementById('tracesRight');
    if (!el) return;
    el.innerHTML = '';

    const head = document.createElement('div');
    head.className = 'traces-panel-head';
    head.textContent = 'Records';
    el.appendChild(head);

    const body = document.createElement('div');
    body.className = 'traces-panel-body';

    if (!tracesWorkbooks.length){
        const empty = document.createElement('div');
        empty.className = 'traces-empty';
        empty.textContent = 'No runs yet.';
        body.appendChild(empty);
    }

    for (const wb of tracesWorkbooks){
        const meta = TRACES_STATUS_META[wb.status] || TRACES_STATUS_META.in_progress;
        const card = document.createElement('div');
        card.className = 'traces-wb-card ' + meta.cls;
        if (tracesActiveWorkbook && tracesActiveWorkbook.id === wb.id){
            card.classList.add('traces-wb-card-active');
        }

        const title = document.createElement('div');
        title.className = 'traces-wb-title';
        title.textContent = wb.title || '(untitled)';
        card.appendChild(title);

        const badge = document.createElement('div');
        badge.className = 'traces-wb-badge';
        badge.textContent = meta.label;
        card.appendChild(badge);

        const actions = document.createElement('div');
        actions.className = 'traces-wb-actions';
        const viewBtn = document.createElement('button');
        viewBtn.className = 'traces-wb-btn';
        viewBtn.textContent = 'View';
        viewBtn.addEventListener('click', () => openWorkbook(wb.id, 'view'));
        actions.appendChild(viewBtn);
        if (wb.status === 'incomplete' || wb.status === 'in_progress'){
            const resumeBtn = document.createElement('button');
            resumeBtn.className = 'traces-wb-btn traces-wb-btn-primary';
            resumeBtn.textContent = 'Resume';
            resumeBtn.addEventListener('click', () => openWorkbook(wb.id, 'fill'));
            actions.appendChild(resumeBtn);
        }
        card.appendChild(actions);
        body.appendChild(card);
    }

    el.appendChild(body);
}

// --- center panel ---

function renderTracesCenter(){
    const el = document.getElementById('tracesCenter');
    if (!el) return;
    el.innerHTML = '';

    if (tracesMode === 'home'){
        const home = document.createElement('div');
        home.className = 'traces-home';
        home.textContent = 'Define a workflow on the left, or start a run from a concluded one.';
        el.appendChild(home);
        return;
    }

    const pages = activePages();
    clampPageIndex();
    const page = pages[tracesPageIndex] || null;
    const isDefine = tracesMode === 'define';
    const isView = tracesMode === 'view';
    const isExtra = page && page.kind === 'extra';

    // Title row
    const titleRow = document.createElement('div');
    titleRow.className = 'traces-title-row';
    if (isDefine){
        const input = document.createElement('input');
        input.className = 'traces-wf-title-input';
        input.placeholder = 'Workflow title';
        input.value = (tracesActiveWorkflow && tracesActiveWorkflow.title) || '';
        input.addEventListener('change', () => saveWorkflowTitle(input.value));
        titleRow.appendChild(input);
    } else {
        const h = document.createElement('div');
        h.className = 'traces-wb-heading';
        h.textContent = (tracesActiveWorkbook && tracesActiveWorkbook.title) || '';
        titleRow.appendChild(h);
        const status = document.createElement('span');
        const meta = TRACES_STATUS_META[tracesActiveWorkbook && tracesActiveWorkbook.status] || {};
        status.className = 'traces-status-pill ' + (meta.cls || '');
        status.textContent = meta.label || '';
        titleRow.appendChild(status);
    }
    el.appendChild(titleRow);

    // Skip banner (fill mode only)
    if (tracesMode === 'fill' && tracesSkipped.length){
        const banner = document.createElement('div');
        banner.className = 'traces-banner';
        const txt = document.createElement('span');
        const titles = tracesSkipped.map(p => p.title || '(untitled)').join(', ');
        txt.textContent = 'You skipped required page(s): ' + titles + '. Return and paste the image.';
        banner.appendChild(txt);
        const jump = document.createElement('button');
        jump.className = 'traces-banner-btn';
        jump.textContent = 'Go to first skipped';
        jump.addEventListener('click', () => {
            const first = tracesSkipped[0];
            const idx = pages.findIndex(p => p.id === first.id);
            if (idx >= 0){ tracesPageIndex = idx; recomputeSkips(); renderTracesCenter(); }
        });
        banner.appendChild(jump);
        el.appendChild(banner);
    }

    if (!page){
        const empty = document.createElement('div');
        empty.className = 'traces-home';
        empty.textContent = isDefine
            ? 'This workflow has no pages yet. Add the first page below.'
            : 'This run has no pages.';
        el.appendChild(empty);
        el.appendChild(buildTracesButtons(pages, page));
        return;
    }

    // Page indicator
    const indicator = document.createElement('div');
    indicator.className = 'traces-page-indicator';
    indicator.textContent = 'Page ' + (tracesPageIndex + 1) + ' of ' + pages.length
        + (isExtra ? '  (extra)' : '');
    el.appendChild(indicator);

    // Page title
    if (isDefine || isExtra){
        const pt = document.createElement('input');
        pt.className = 'traces-page-title-input';
        pt.placeholder = 'Page title';
        pt.value = page.title || '';
        pt.addEventListener('change', () => savePageField(page, 'title', pt.value));
        el.appendChild(pt);
    } else {
        const pt = document.createElement('div');
        pt.className = 'traces-page-title';
        pt.textContent = page.title || '(untitled page)';
        el.appendChild(pt);
    }

    // Image / paste zone
    const zone = document.createElement('div');
    zone.className = 'traces-zone';
    zone.tabIndex = 0;
    const shownSha = isDefine ? page.sample_sha256 : page.image_sha256;
    const shownUrl = isDefine ? page.sample_url : page.image_url;
    if (shownSha && shownUrl){
        const img = document.createElement('img');
        img.className = 'traces-zone-img';
        img.src = shownUrl;
        img.alt = 'page image';
        zone.appendChild(img);
    } else {
        const ph = document.createElement('div');
        ph.className = 'traces-zone-placeholder';
        ph.textContent = isDefine
            ? 'Paste, drop, or the sample image will appear here'
            : (isView ? 'No image' : 'Paste (Ctrl+V) or drop the required image here');
        zone.appendChild(ph);
    }
    if (!isView){
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
            zone.classList.add('traces-zone-over');
        });
        zone.addEventListener('dragleave', (e) => {
            if (!zone.contains(e.relatedTarget)) zone.classList.remove('traces-zone-over');
        });
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('traces-zone-over');
            const file = e.dataTransfer.files && e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) handleImageFile(file);
            else {
                const text = e.dataTransfer.getData('text/plain');
                if (text) appendNote(page, text);
            }
        });
    }
    el.appendChild(zone);

    // Bottom: explanation + notes
    const bottom = document.createElement('div');
    bottom.className = 'traces-bottom';

    const expBox = document.createElement('div');
    expBox.className = 'traces-bottom-box';
    const expLabel = document.createElement('div');
    expLabel.className = 'traces-bottom-label';
    expLabel.textContent = 'Explanation';
    expBox.appendChild(expLabel);
    if (isDefine || isExtra){
        const exp = document.createElement('textarea');
        exp.className = 'traces-bottom-area';
        exp.placeholder = 'What kind of image goes here?';
        exp.value = page.explanation || '';
        exp.addEventListener('change', () => savePageField(page, 'explanation', exp.value));
        expBox.appendChild(exp);
    } else {
        const exp = document.createElement('div');
        exp.className = 'traces-bottom-text';
        exp.textContent = page.explanation || '(no explanation)';
        expBox.appendChild(exp);
        if (page.sample_url){
            const sample = document.createElement('img');
            sample.className = 'traces-sample-thumb';
            sample.src = page.sample_url;
            sample.alt = 'sample';
            sample.title = 'Sample image';
            expBox.appendChild(sample);
        }
    }
    bottom.appendChild(expBox);

    // Notes (not in define mode -- templates carry no run notes)
    if (!isDefine){
        const notesBox = document.createElement('div');
        notesBox.className = 'traces-bottom-box';
        const notesLabel = document.createElement('div');
        notesLabel.className = 'traces-bottom-label';
        notesLabel.textContent = 'Notes';
        notesBox.appendChild(notesLabel);
        if (isView){
            const n = document.createElement('div');
            n.className = 'traces-bottom-text';
            n.textContent = page.notes || '(no notes)';
            notesBox.appendChild(n);
        } else {
            const n = document.createElement('textarea');
            n.className = 'traces-bottom-area';
            n.placeholder = 'Add notes if needed';
            n.value = page.notes || '';
            n.addEventListener('change', () => savePageField(page, 'notes', n.value));
            notesBox.appendChild(n);
        }
        bottom.appendChild(notesBox);
    }

    el.appendChild(bottom);
    el.appendChild(buildTracesButtons(pages, page));
}

function buildTracesButtons(pages, page){
    const bar = document.createElement('div');
    bar.className = 'traces-buttons';

    const prev = document.createElement('button');
    prev.className = 'traces-btn';
    prev.textContent = '‹ Prev';
    prev.disabled = tracesPageIndex <= 0;
    prev.addEventListener('click', () => navPage(-1));
    bar.appendChild(prev);

    const next = document.createElement('button');
    next.className = 'traces-btn';
    next.textContent = 'Next ›';
    next.disabled = tracesPageIndex >= pages.length - 1;
    next.addEventListener('click', () => navPage(1));
    bar.appendChild(next);

    const spacer = document.createElement('div');
    spacer.className = 'traces-btn-spacer';
    bar.appendChild(spacer);

    if (tracesMode === 'define'){
        const add = document.createElement('button');
        add.className = 'traces-btn';
        add.textContent = '+ Add page';
        add.addEventListener('click', addTemplatePage);
        bar.appendChild(add);

        if (page){
            const del = document.createElement('button');
            del.className = 'traces-btn traces-btn-danger';
            del.textContent = 'Delete page';
            del.addEventListener('click', () => deleteTemplatePage(page));
            bar.appendChild(del);
        }

        const conclude = document.createElement('button');
        conclude.className = 'traces-btn traces-btn-primary';
        conclude.textContent = 'Conclude workflow';
        conclude.addEventListener('click', concludeWorkflow);
        bar.appendChild(conclude);
    } else if (tracesMode === 'fill'){
        const addExtra = document.createElement('button');
        addExtra.className = 'traces-btn';
        addExtra.textContent = '+ Add extra page';
        addExtra.disabled = !page;
        addExtra.addEventListener('click', () => addExtraPage(page));
        bar.appendChild(addExtra);

        if (page && page.kind === 'extra'){
            const del = document.createElement('button');
            del.className = 'traces-btn traces-btn-danger';
            del.textContent = 'Delete extra';
            del.addEventListener('click', () => deleteExtraPage(page));
            bar.appendChild(del);
        }

        const seal = document.createElement('button');
        seal.className = 'traces-btn traces-btn-primary';
        seal.textContent = 'Conclude & seal';
        seal.addEventListener('click', sealWorkbook);
        bar.appendChild(seal);
    } else if (tracesMode === 'view'){
        const wb = tracesActiveWorkbook;
        if (wb && wb.status !== 'in_progress'){
            const reopen = document.createElement('button');
            reopen.className = 'traces-btn traces-btn-primary';
            reopen.textContent = 'Reopen';
            reopen.addEventListener('click', reopenWorkbook);
            bar.appendChild(reopen);
        }
    }
    return bar;
}

// --- navigation & skip detection ---

function navPage(delta){
    const pages = activePages();
    const target = tracesPageIndex + delta;
    if (target < 0 || target > pages.length - 1) return;
    tracesPageIndex = target;
    recomputeSkips();
    renderTracesCenter();
}

function recomputeSkips(){
    if (tracesMode !== 'fill' || !tracesActiveWorkbook){ tracesSkipped = []; return; }
    const pages = tracesActiveWorkbook.pages || [];
    const current = pages[tracesPageIndex];
    const currentBase = current ? current.base_position : Infinity;
    tracesSkipped = pages.filter(p =>
        p.kind === 'template' && p.base_position < currentBase && !p.image_sha256);
}

// --- workflow (template) actions ---

async function defineNewWorkflow(){
    const data = await tracesSend('/api/traces/workflows', 'POST', { title: '' });
    if (!data || data.__error){ alert((data && data.__error) || 'Failed'); return; }
    tracesActiveWorkflow = data;
    tracesActiveWorkbook = null;
    tracesMode = 'define';
    tracesPageIndex = 0;
    await loadTracesWorkflows();
    renderTracesCenter();
}

async function editDraft(workflowId){
    const data = await tracesGet('/api/traces/workflows/' + workflowId);
    if (!data){ alert('Failed to load draft'); return; }
    tracesActiveWorkflow = data;
    tracesActiveWorkbook = null;
    tracesMode = 'define';
    tracesPageIndex = 0;
    renderTracesLeft();
    renderTracesCenter();
}

async function saveWorkflowTitle(title){
    if (!tracesActiveWorkflow) return;
    const data = await tracesSend('/api/traces/workflows/' + tracesActiveWorkflow.id, 'PUT', { title });
    if (data && data.__error){ alert(data.__error); return; }
    tracesActiveWorkflow.title = title.trim();
    renderTracesLeft();
}

async function addTemplatePage(){
    if (!tracesActiveWorkflow) return;
    const data = await tracesSend('/api/traces/workflows/' + tracesActiveWorkflow.id + '/pages', 'POST',
        { title: '', explanation: '' });
    if (!data || data.__error){ alert((data && data.__error) || 'Failed'); return; }
    await reloadActiveWorkflow();
    tracesPageIndex = (tracesActiveWorkflow.pages || []).length - 1;
    renderTracesLeft();
    renderTracesCenter();
}

async function deleteTemplatePage(page){
    if (!confirm('Delete this page?')) return;
    const data = await tracesSend('/api/traces/pages/' + page.id, 'DELETE');
    if (data && data.__error){ alert(data.__error); return; }
    await reloadActiveWorkflow();
    clampPageIndex();
    renderTracesCenter();
}

async function concludeWorkflow(){
    if (!tracesActiveWorkflow) return;
    const data = await tracesSend('/api/traces/workflows/' + tracesActiveWorkflow.id + '/conclude', 'POST', {});
    if (!data || data.__error){ alert((data && data.__error) || 'Failed to conclude'); return; }
    tracesMode = 'home';
    tracesActiveWorkflow = null;
    await loadTracesWorkflows();
    renderTracesCenter();
}

async function deleteWorkflow(workflowId){
    if (!confirm('Delete this draft workflow?')) return;
    const data = await tracesSend('/api/traces/workflows/' + workflowId, 'DELETE');
    if (data && data.__error){ alert(data.__error); return; }
    if (tracesActiveWorkflow && tracesActiveWorkflow.id === workflowId){
        tracesActiveWorkflow = null;
        tracesMode = 'home';
        renderTracesCenter();
    }
    await loadTracesWorkflows();
}

// --- workbook (run) actions ---

async function startWorkbook(workflowId){
    const data = await tracesSend('/api/traces/workbooks', 'POST', { workflow_id: workflowId });
    if (!data || data.__error){ alert((data && data.__error) || 'Failed to start'); return; }
    tracesActiveWorkbook = data;
    tracesActiveWorkflow = null;
    tracesMode = 'fill';
    tracesPageIndex = 0;
    recomputeSkips();
    await loadTracesWorkbooks();
    renderTracesLeft();
    renderTracesCenter();
}

async function openWorkbook(workbookId, mode){
    const data = await tracesGet('/api/traces/workbooks/' + workbookId);
    if (!data){ alert('Failed to load run'); return; }
    tracesActiveWorkbook = data;
    tracesActiveWorkflow = null;
    tracesMode = mode === 'fill' ? 'fill' : 'view';
    tracesPageIndex = 0;
    recomputeSkips();
    renderTracesRight();
    renderTracesCenter();
}

async function addExtraPage(page){
    if (!tracesActiveWorkbook || !page) return;
    const data = await tracesSend('/api/traces/workbooks/' + tracesActiveWorkbook.id + '/add-extra', 'POST',
        { after_page_id: page.id });
    if (!data || data.__error){ alert((data && data.__error) || 'Failed'); return; }
    const newId = data.id;
    await reloadActiveWorkbook();
    const idx = (tracesActiveWorkbook.pages || []).findIndex(p => p.id === newId);
    if (idx >= 0) tracesPageIndex = idx;
    recomputeSkips();
    await loadTracesWorkbooks();
    renderTracesCenter();
}

async function deleteExtraPage(page){
    if (!confirm('Delete this extra page?')) return;
    const data = await tracesSend(
        '/api/traces/workbooks/' + tracesActiveWorkbook.id + '/pages/' + page.id, 'DELETE');
    if (data && data.__error){ alert(data.__error); return; }
    await reloadActiveWorkbook();
    clampPageIndex();
    recomputeSkips();
    await loadTracesWorkbooks();
    renderTracesCenter();
}

async function sealWorkbook(){
    if (!tracesActiveWorkbook) return;
    const data = await tracesSend('/api/traces/workbooks/' + tracesActiveWorkbook.id + '/seal', 'POST', {});
    if (!data || data.__error){ alert((data && data.__error) || 'Failed to seal'); return; }
    if (data.status === 'incomplete'){
        alert('Sealed as INCOMPLETE. Missing image on: ' + (data.missing_pages || []).join(', '));
    } else if (data.status === 'errata'){
        alert('Sealed as ERRATA (extra pages were added).');
    } else {
        alert('Sealed as COMPLETE.');
    }
    await reloadActiveWorkbook();
    tracesMode = 'view';
    recomputeSkips();
    await loadTracesWorkbooks();
    renderTracesCenter();
}

async function reopenWorkbook(){
    if (!tracesActiveWorkbook) return;
    const data = await tracesSend('/api/traces/workbooks/' + tracesActiveWorkbook.id + '/reopen', 'POST', {});
    if (!data || data.__error){ alert((data && data.__error) || 'Failed to reopen'); return; }
    await reloadActiveWorkbook();
    tracesMode = 'fill';
    tracesPageIndex = 0;
    recomputeSkips();
    await loadTracesWorkbooks();
    renderTracesCenter();
}

// --- saving page fields ---

async function savePageField(page, field, value){
    const v = value;
    if (tracesMode === 'define'){
        const body = {}; body[field] = v;
        const data = await tracesSend('/api/traces/pages/' + page.id, 'PUT', body);
        if (data && data.__error){ alert(data.__error); return; }
        page[field] = field === 'title' ? v.trim() : v;
    } else {
        const body = {}; body[field] = v;
        const data = await tracesSend(
            '/api/traces/workbooks/' + tracesActiveWorkbook.id + '/pages/' + page.id, 'PUT', body);
        if (data && data.__error){ alert(data.__error); return; }
        page[field] = v;
    }
}

function appendNote(page, text){
    if (tracesMode === 'view' || tracesMode === 'define') return;
    const merged = page.notes ? (page.notes + '\n' + text) : text;
    savePageField(page, 'notes', merged).then(() => renderTracesCenter());
}

// --- image handling: paste, compress, upload, apply ---

function onTracesPaste(e){
    const view = document.getElementById('view-traces');
    if (!view || view.classList.contains('view-hidden')) return;
    if (tracesMode !== 'define' && tracesMode !== 'fill') return;
    const items = (e.clipboardData && e.clipboardData.items) || [];
    for (const item of items){
        if (item.type && item.type.startsWith('image/')){
            const file = item.getAsFile();
            if (file){ e.preventDefault(); handleImageFile(file); return; }
        }
    }
    // Text-only paste -> append to notes on the current fill page.
    const text = e.clipboardData && e.clipboardData.getData('text/plain');
    if (text && tracesMode === 'fill'){
        const page = activePages()[tracesPageIndex];
        if (page){ e.preventDefault(); appendNote(page, text); }
    }
}

async function handleImageFile(file){
    const page = activePages()[tracesPageIndex];
    if (!page) return;
    let dataUrl;
    try { dataUrl = await compressTracesImage(file); }
    catch { alert('Could not read image'); return; }
    const up = await tracesSend('/api/traces/blobs', 'POST', { data_url: dataUrl });
    if (!up || up.__error){ alert((up && up.__error) || 'Upload failed'); return; }
    const sha = up.sha256;
    if (tracesMode === 'define'){
        const data = await tracesSend('/api/traces/pages/' + page.id, 'PUT', { sample_sha256: sha });
        if (data && data.__error){ alert(data.__error); return; }
        page.sample_sha256 = sha;
        page.sample_url = '/api/traces/blobs/' + sha;
    } else {
        const data = await tracesSend(
            '/api/traces/workbooks/' + tracesActiveWorkbook.id + '/pages/' + page.id, 'PUT',
            { image_sha256: sha });
        if (data && data.__error){ alert(data.__error); return; }
        page.image_sha256 = sha;
        page.image_url = '/api/traces/blobs/' + sha;
        recomputeSkips();
    }
    renderTracesCenter();
}

function compressTracesImage(file){
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
            URL.revokeObjectURL(url);
            let w = img.naturalWidth, h = img.naturalHeight;
            const max = 1600;
            if (w > max || h > max){
                const scale = Math.min(max / w, max / h);
                w = Math.round(w * scale);
                h = Math.round(h * scale);
            }
            const canvas = document.createElement('canvas');
            canvas.width = w; canvas.height = h;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            resolve(canvas.toDataURL('image/jpeg', 0.85));
        };
        img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('bad image')); };
        img.src = url;
    });
}
