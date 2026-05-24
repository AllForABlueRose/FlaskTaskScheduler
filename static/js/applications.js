let appCurrentFolder = '';
let appFiles = [];
let appSelectedFile = null;
let appCurrentPage = 0;
let appTotalPages = 0;
let appPdfDoc = null;
let appPdfRendering = false;
let appInitialized = false;
let appSwipeStartX = null;
let appApprovedTree = [];
let appApprovedMode = false;
let appApprovedFolder = '';
let appApprovedPath = [];

function initApplications(){
    if (appInitialized) return;
    appInitialized = true;
    const input = document.getElementById('appFolderInput');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') fetchApplicationFiles();
        });
    }
    wireAppSwipe();
    loadApprovedTree();
    const approvedArea = document.getElementById('appApprovalArea');
    if (approvedArea) {
        approvedArea.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            if (appApprovedPath.length > 0) {
                appApprovedPath.pop();
                renderApprovedGrid();
            }
        });
    }
}

function wireAppSwipe(){
    const area = document.getElementById('appPreviewArea');
    if (!area) return;
    area.addEventListener('pointerdown', (e) => {
        if (appTotalPages <= 1) return;
        appSwipeStartX = e.clientX;
        area.classList.add('app-preview-grabbing');
        area.setPointerCapture(e.pointerId);
    });
    area.addEventListener('pointerup', (e) => {
        area.classList.remove('app-preview-grabbing');
        if (appSwipeStartX === null) return;
        const delta = e.clientX - appSwipeStartX;
        appSwipeStartX = null;
        if (Math.abs(delta) < 60) return;
        navigateAppPage(delta < 0 ? 1 : -1);
    });
    area.addEventListener('pointercancel', () => {
        appSwipeStartX = null;
        area.classList.remove('app-preview-grabbing');
    });
}

async function fetchApplicationFiles(){
    const input = document.getElementById('appFolderInput');
    const status = document.getElementById('appFolderStatus');
    if (!input) return;
    const folder = input.value.trim();
    if (!folder){
        if (status){ status.textContent = 'Please enter a folder path'; status.classList.remove('hidden'); }
        return;
    }
    if (status) status.classList.add('hidden');

    try {
        const res = await fetch('/api/applications/files?folder=' + encodeURIComponent(folder));
        const data = await res.json();
        if (!res.ok){
            if (status){ status.textContent = data.error || 'Failed to fetch'; status.classList.remove('hidden'); }
            return;
        }
        appCurrentFolder = data.folder;
        appFiles = data.files;
        appSelectedFile = null;
        appCurrentPage = 0;
        appTotalPages = 0;
        appPdfDoc = null;
        renderAppFileList();
        clearAppPreview();
    } catch {
        if (status){ status.textContent = 'Network error'; status.classList.remove('hidden'); }
    }
}

function renderAppFileList(){
    const list = document.getElementById('appFileList');
    if (!list) return;
    list.innerHTML = '';
    if (!appFiles.length){
        list.innerHTML = '<div class="text-sm text-slate-500 italic">No supported files found</div>';
        return;
    }
    for (const file of appFiles){
        const row = document.createElement('div');
        row.className = 'app-file-row';
        if (appSelectedFile && appSelectedFile.name === file.name && !file.ghost) row.classList.add('app-file-selected');
        if (file.status === 'approved') row.classList.add('app-file-approved');
        if (file.status === 'flagged') row.classList.add('app-file-flagged');
        if (file.status === 'rejected') row.classList.add('app-file-rejected');
        if (file.ghost) row.classList.add('app-file-ghost');

        const badge = document.createElement('span');
        badge.className = 'app-file-type-badge type-' + file.type;
        badge.textContent = {image:'IMG', excel:'XLS', word:'DOC', pdf:'PDF'}[file.type] || '?';

        const nameEl = document.createElement('span');
        nameEl.className = 'app-file-name';
        nameEl.textContent = file.name;

        row.appendChild(badge);
        row.appendChild(nameEl);

        if (!file.ghost) {
            row.addEventListener('click', () => selectAppFile(file));
        }
        list.appendChild(row);
    }
}

function selectAppFile(file){
    appSelectedFile = file;
    appCurrentPage = 0;
    appTotalPages = 0;
    appPdfDoc = null;
    appApprovedMode = false;
    renderAppFileList();
    renderApprovedGrid();
    loadAppPreview();
    updateAppActionBar();
}

function clearAppPreview(){
    const area = document.getElementById('appPreviewArea');
    if (area) area.innerHTML = '<div class="text-sm text-slate-500 italic">Select a file to preview</div>';
    hideAppPageNav();
    updateAppPreviewCursor();
    updateAppActionBar();
}

function hideAppPageNav(){
    const nav = document.getElementById('appPageNav');
    if (nav) nav.classList.add('hidden');
}

function showAppPageNav(){
    const nav = document.getElementById('appPageNav');
    if (nav) nav.classList.remove('hidden');
}

function updateAppPageIndicator(text){
    const el = document.getElementById('appPageIndicator');
    if (el) el.textContent = text;
}

function updateAppPreviewCursor(){
    const area = document.getElementById('appPreviewArea');
    if (!area) return;
    area.classList.toggle('app-preview-grabbable', appTotalPages > 1);
}

function updateAppActionBar(){
    const bar = document.getElementById('appActionBar');
    if (bar) {
        const show = appSelectedFile && !appSelectedFile.ghost && appSelectedFile.status !== 'rejected' && !appApprovedMode;
        bar.classList.toggle('hidden', !show);
    }
    const badge = document.getElementById('appApprovedBadge');
    if (badge) badge.classList.toggle('hidden', !appApprovedMode || !appSelectedFile);
}

function previewUrl(page){
    const folder = appApprovedMode ? appApprovedFolder : appCurrentFolder;
    let url = '/api/applications/file/preview?folder=' + encodeURIComponent(folder)
        + '&name=' + encodeURIComponent(appSelectedFile.name)
        + (page != null ? '&page=' + page : '');
    if (appApprovedMode) url += '&approved=1';
    return url;
}

async function loadAppPreview(){
    if (!appSelectedFile) return;
    const area = document.getElementById('appPreviewArea');
    if (!area) return;

    area.innerHTML = '<div class="text-sm text-slate-500">Loading...</div>';
    hideAppPageNav();

    const type = appSelectedFile.type;

    if (type === 'image'){
        const img = document.createElement('img');
        img.className = 'app-preview-image';
        img.src = previewUrl();
        img.alt = appSelectedFile.name;
        img.onload = () => {
            area.innerHTML = '';
            area.appendChild(img);
            appTotalPages = 1;
            updateAppPreviewCursor();
        };
        img.onerror = () => { area.innerHTML = '<div class="text-sm text-red-600">Failed to load image</div>'; };
        return;
    }

    if (type === 'pdf'){
        await loadAppPdf(area);
        return;
    }

    if (type === 'excel'){
        await loadAppExcel(area, appCurrentPage);
        return;
    }

    if (type === 'word'){
        await loadAppWord(area);
        return;
    }
}

async function loadAppPdf(area){
    if (typeof pdfjsLib === 'undefined'){
        area.innerHTML = '<div class="text-sm text-red-600">PDF viewer not available</div>';
        return;
    }
    try {
        const loadingTask = pdfjsLib.getDocument(previewUrl());
        appPdfDoc = await loadingTask.promise;
        appTotalPages = appPdfDoc.numPages;
        appCurrentPage = 1;
        area.innerHTML = '';
        const canvas = document.createElement('canvas');
        canvas.id = 'appPdfCanvas';
        area.appendChild(canvas);
        await renderAppPdfPage(appCurrentPage);
        showAppPageNav();
        updateAppPageIndicator('Page ' + appCurrentPage + ' of ' + appTotalPages);
        updateAppPreviewCursor();
    } catch {
        area.innerHTML = '<div class="text-sm text-red-600">Failed to load PDF</div>';
    }
}

async function renderAppPdfPage(num){
    if (!appPdfDoc || appPdfRendering) return;
    appPdfRendering = true;
    try {
        const page = await appPdfDoc.getPage(num);
        const container = document.getElementById('appPreviewArea');
        const canvas = document.getElementById('appPdfCanvas');
        if (!canvas || !container) return;
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = Math.min((container.clientWidth - 32) / baseViewport.width, 2);
        const viewport = page.getViewport({ scale });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext('2d');
        await page.render({ canvasContext: ctx, viewport }).promise;
        appCurrentPage = num;
        updateAppPageIndicator('Page ' + num + ' of ' + appTotalPages);
    } finally {
        appPdfRendering = false;
    }
}

async function loadAppExcel(area, page){
    try {
        const res = await fetch(previewUrl(page));
        if (!res.ok){
            const err = await res.json().catch(() => ({}));
            area.innerHTML = '<div class="text-sm text-red-600">' + escapeHtml(err.error || 'Failed to load') + '</div>';
            return;
        }
        const data = await res.json();
        renderAppExcel(area, data);
    } catch {
        area.innerHTML = '<div class="text-sm text-red-600">Network error</div>';
    }
}

function renderAppExcel(area, data){
    let html = '<div class="overflow-auto flex-1 min-h-0"><table class="app-excel-table"><thead><tr>';
    for (const h of data.headers) html += '<th>' + escapeHtml(h) + '</th>';
    html += '</tr></thead><tbody>';
    for (const row of data.rows){
        html += '<tr>';
        for (const cell of row) html += '<td>' + escapeHtml(cell) + '</td>';
        html += '</tr>';
    }
    html += '</tbody></table>';
    if (data.truncated) html += '<div class="text-xs text-slate-500 mt-2 italic">Showing first 500 rows</div>';
    html += '</div>';
    area.innerHTML = html;

    appCurrentPage = data.page;
    appTotalPages = data.total_pages;
    if (appTotalPages > 1){
        showAppPageNav();
        updateAppPageIndicator(data.page_label + ' (' + (data.page + 1) + '/' + data.total_pages + ')');
    } else {
        showAppPageNav();
        updateAppPageIndicator(data.page_label);
    }
    updateAppPreviewCursor();
}

async function loadAppWord(area){
    try {
        const res = await fetch(previewUrl());
        if (!res.ok){
            const err = await res.json().catch(() => ({}));
            area.innerHTML = '<div class="text-sm text-red-600">' + escapeHtml(err.error || 'Failed to load') + '</div>';
            return;
        }
        const data = await res.json();
        area.innerHTML = '<div class="app-word-content">' + data.html + '</div>';
        appCurrentPage = 0;
        appTotalPages = 1;
        hideAppPageNav();
        updateAppPreviewCursor();
    } catch {
        area.innerHTML = '<div class="text-sm text-red-600">Network error</div>';
    }
}

function navigateAppPage(delta){
    if (!appSelectedFile) return;
    const type = appSelectedFile.type;

    if (type === 'pdf' && appPdfDoc){
        const next = appCurrentPage + delta;
        if (next < 1 || next > appTotalPages) return;
        renderAppPdfPage(next);
        return;
    }

    if (type === 'excel'){
        const next = appCurrentPage + delta;
        if (next < 0 || next >= appTotalPages) return;
        appCurrentPage = next;
        const area = document.getElementById('appPreviewArea');
        if (area) loadAppExcel(area, next);
        return;
    }
}

async function setAppFileStatus(status){
    if (!appSelectedFile || !appCurrentFolder) return;
    try {
        const res = await fetch('/api/applications/file/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                folder: appCurrentFolder,
                filename: appSelectedFile.name,
                status: status,
            }),
        });
        if (!res.ok){
            const err = await res.json().catch(() => ({}));
            alert(err.error || 'Failed to set status');
            return;
        }
    } catch {
        alert('Network error');
        return;
    }

    if (status === 'dismissed'){
        appSelectedFile = null;
        clearAppPreview();
    }

    await refetchAppFiles();
    if (status === 'approved') await loadApprovedTree();
}

async function loadApprovedTree(){
    try {
        const res = await fetch('/api/applications/approved-tree');
        if (!res.ok) return;
        const data = await res.json();
        appApprovedTree = data.tree;
        renderApprovedGrid();
    } catch {}
}

function getApprovedItems(){
    let items = appApprovedTree;
    for (const seg of appApprovedPath){
        const node = items.find(n => n.name === seg);
        if (!node || !node.children) return [];
        items = node.children;
    }
    return items;
}

function renderApprovedGrid(){
    const container = document.getElementById('appApprovedTree');
    if (!container) return;
    container.innerHTML = '';
    if (!appApprovedTree.length){
        container.innerHTML = '<div class="text-sm text-slate-500 italic">No approved files yet</div>';
        return;
    }
    const items = getApprovedItems();
    if (!items.length){
        container.innerHTML = '<div class="text-sm text-slate-500 italic">Empty folder</div>';
        return;
    }
    const grid = document.createElement('div');
    grid.className = 'app-icon-grid';
    for (const item of items){
        const isFolder = !!item.children;
        const card = document.createElement('div');
        card.className = 'app-icon-card';

        const isSelected = !isFolder && appApprovedMode && appSelectedFile
            && appSelectedFile.name === item.name
            && appApprovedFolder === appApprovedPath.join('/');
        if (isSelected) card.classList.add('app-icon-selected');

        const icon = document.createElement('div');
        if (isFolder){
            icon.className = 'app-icon-folder';
        } else {
            icon.className = 'app-icon-file app-icon-file-' + item.type;
            icon.textContent = {image:'IMG', excel:'XLS', word:'DOC', pdf:'PDF'}[item.type] || '';
        }

        const label = document.createElement('div');
        label.className = 'app-icon-label';
        label.textContent = item.name;

        card.appendChild(icon);
        card.appendChild(label);

        if (isFolder){
            card.addEventListener('click', () => {
                appApprovedPath.push(item.name);
                renderApprovedGrid();
            });
        } else {
            card.addEventListener('click', () => {
                selectApprovedFile(item);
            });
        }
        grid.appendChild(card);
    }
    container.appendChild(grid);
}

function selectApprovedFile(file){
    appSelectedFile = file;
    appCurrentPage = 0;
    appTotalPages = 0;
    appPdfDoc = null;
    appApprovedMode = true;
    appApprovedFolder = appApprovedPath.join('/');
    renderAppFileList();
    renderApprovedGrid();
    loadAppPreview();
    updateAppActionBar();
}

async function refetchAppFiles(){
    if (!appCurrentFolder) return;
    try {
        const res = await fetch('/api/applications/files?folder=' + encodeURIComponent(appCurrentFolder));
        if (!res.ok) return;
        const data = await res.json();
        appFiles = data.files;

        if (appSelectedFile) {
            const still = appFiles.find(f => f.name === appSelectedFile.name && !f.ghost);
            if (still) appSelectedFile = still;
            else { appSelectedFile = null; clearAppPreview(); }
        }
        renderAppFileList();
        updateAppActionBar();
    } catch {}
}
