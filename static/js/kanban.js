let kanbanColumns = [];
let kanbanInitialized = false;
let currentKanbanCardId = null;
let currentKanbanColumnId = null;
let currentKanbanColor = '#3b82f6';
let kanbanDragCardId = null;

function initKanban(){
    kanbanInitialized = true;
    loadKanban();
}

async function loadKanban(){
    try {
        const res = await fetch('/api/kanban');
        if (!res.ok) return;
        const data = await res.json();
        kanbanColumns = data.columns || [];
    } catch {
        return;
    }
    renderKanban();
}

function findKanbanCard(id){
    for (const col of kanbanColumns){
        const card = col.cards.find(c => c.id === id);
        if (card) return card;
    }
    return null;
}

function renderKanban(){
    const board = document.getElementById('kanbanBoard');
    if (!board) return;
    board.innerHTML = '';
    for (const col of kanbanColumns) board.appendChild(renderColumn(col));
    board.appendChild(buildAddColumn());
}

function renderColumn(col){
    const el = document.createElement('div');
    el.className = 'kanban-column shrink-0';
    el.dataset.columnId = col.id;

    const header = document.createElement('div');
    header.className = 'kanban-col-header';

    const left = document.createElement('div');
    left.className = 'kanban-col-header-left';
    const title = document.createElement('span');
    title.className = 'kanban-col-title';
    title.textContent = col.title;
    title.title = 'Click to rename';
    title.addEventListener('click', () => startRenameColumn(col, title));
    const count = document.createElement('span');
    count.className = 'kanban-col-count';
    count.textContent = col.cards.length;
    left.appendChild(title);
    left.appendChild(count);

    const del = document.createElement('button');
    del.className = 'kanban-col-delete';
    del.textContent = '×';
    del.title = 'Delete column';
    del.addEventListener('click', () => deleteColumn(col));

    header.appendChild(left);
    header.appendChild(del);

    const cards = document.createElement('div');
    cards.className = 'kanban-col-cards';
    cards.dataset.columnId = col.id;
    cards.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        cards.classList.add('kanban-col-cards-over');
    });
    cards.addEventListener('dragleave', (e) => {
        if (!cards.contains(e.relatedTarget)) cards.classList.remove('kanban-col-cards-over');
    });
    cards.addEventListener('drop', (e) => onColumnDrop(e, col.id));
    for (const card of col.cards) cards.appendChild(renderCard(card));

    const addCard = document.createElement('button');
    addCard.className = 'kanban-col-add-card';
    addCard.textContent = '+ Add a card';
    addCard.addEventListener('click', () => openKanbanCardModal(col.id, null));

    el.appendChild(header);
    el.appendChild(cards);
    el.appendChild(addCard);
    return el;
}

function renderCard(card){
    const el = document.createElement('div');
    el.className = 'kanban-card';
    el.dataset.cardId = card.id;
    el.draggable = true;
    if (card.color) el.style.borderLeftColor = card.color;

    const title = document.createElement('div');
    title.className = 'kanban-card-title';
    title.textContent = card.title;
    el.appendChild(title);

    if (card.description){
        const desc = document.createElement('div');
        desc.className = 'kanban-card-desc';
        desc.textContent = card.description;
        el.appendChild(desc);
    }

    el.addEventListener('click', () => openKanbanCardModal(card.column_id, card.id));
    el.addEventListener('dragstart', (e) => {
        kanbanDragCardId = card.id;
        el.classList.add('kanban-card-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', card.id);
    });
    el.addEventListener('dragend', () => {
        kanbanDragCardId = null;
        el.classList.remove('kanban-card-dragging');
        document.querySelectorAll('.kanban-col-cards-over')
            .forEach(c => c.classList.remove('kanban-col-cards-over'));
    });
    return el;
}

function getDragAfterElement(container, y){
    const els = [...container.querySelectorAll('.kanban-card:not(.kanban-card-dragging)')];
    let closest = { offset: -Infinity, element: null };
    for (const el of els){
        const box = el.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset){
            closest = { offset, element: el };
        }
    }
    return closest.element;
}

async function onColumnDrop(e, columnId){
    e.preventDefault();
    e.currentTarget.classList.remove('kanban-col-cards-over');
    const cardId = kanbanDragCardId || e.dataTransfer.getData('text/plain');
    if (!cardId) return;

    const targetCol = kanbanColumns.find(c => c.id === columnId);
    if (!targetCol) return;

    // Pull the card out of whatever column currently holds it.
    let moved = null;
    for (const col of kanbanColumns){
        const idx = col.cards.findIndex(c => c.id === cardId);
        if (idx >= 0){ moved = col.cards.splice(idx, 1)[0]; break; }
    }
    if (!moved) return;

    const after = getDragAfterElement(e.currentTarget, e.clientY);
    let index;
    if (after == null){
        index = targetCol.cards.length;
    } else {
        index = targetCol.cards.findIndex(c => c.id === after.dataset.cardId);
        if (index < 0) index = targetCol.cards.length;
    }
    moved.column_id = columnId;
    targetCol.cards.splice(index, 0, moved);
    renderKanban();

    try {
        const res = await fetch(`/api/kanban/cards/${cardId}/move`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ column_id: columnId, position: index }),
        });
        if (!res.ok) await loadKanban();
    } catch {
        await loadKanban();
    }
}

// --- columns ---

function buildAddColumn(){
    const wrap = document.createElement('div');
    wrap.className = 'kanban-add-column shrink-0';
    const btn = document.createElement('button');
    btn.className = 'kanban-add-column-btn';
    btn.textContent = '+ Add a column';
    btn.addEventListener('click', () => {
        wrap.innerHTML = '';
        const input = document.createElement('input');
        input.className = 'kanban-add-column-input';
        input.placeholder = 'Column title';
        const actions = document.createElement('div');
        actions.className = 'kanban-add-column-actions';
        const add = document.createElement('button');
        add.className = 'kanban-add-column-confirm';
        add.textContent = 'Add';
        const cancel = document.createElement('button');
        cancel.className = 'kanban-add-column-cancel';
        cancel.textContent = 'Cancel';
        const submit = () => {
            const title = input.value.trim();
            if (!title){ renderKanban(); return; }
            createColumn(title);
        };
        add.addEventListener('click', submit);
        cancel.addEventListener('click', () => renderKanban());
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') submit();
            if (e.key === 'Escape') renderKanban();
        });
        actions.appendChild(add);
        actions.appendChild(cancel);
        wrap.appendChild(input);
        wrap.appendChild(actions);
        input.focus();
    });
    wrap.appendChild(btn);
    return wrap;
}

function startRenameColumn(col, titleEl){
    const input = document.createElement('input');
    input.className = 'kanban-col-title-input';
    input.value = col.title;
    let done = false;
    const finish = (save) => {
        if (done) return;
        done = true;
        const title = input.value.trim();
        if (save && title && title !== col.title){
            renameColumn(col.id, title);
        } else {
            renderKanban();
        }
    };
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') finish(true);
        if (e.key === 'Escape') finish(false);
    });
    input.addEventListener('blur', () => finish(true));
    titleEl.replaceWith(input);
    input.focus();
    input.select();
}

async function createColumn(title){
    try {
        const res = await fetch('/api/kanban/columns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
        if (!res.ok){
            const err = await res.json().catch(() => ({}));
            alert(err.error || 'Failed to add column');
            return;
        }
        await loadKanban();
    } catch {
        alert('Network error');
    }
}

async function renameColumn(id, title){
    try {
        const res = await fetch(`/api/kanban/columns/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
        if (!res.ok) return;
        await loadKanban();
    } catch {}
}

async function deleteColumn(col){
    const msg = col.cards.length
        ? `Delete column "${col.title}" and its ${col.cards.length} card(s)?`
        : `Delete column "${col.title}"?`;
    if (!confirm(msg)) return;
    try {
        const res = await fetch(`/api/kanban/columns/${col.id}`, { method: 'DELETE' });
        if (!res.ok) return;
        await loadKanban();
    } catch {}
}

// --- card modal ---

function openKanbanCardModal(columnId, cardId){
    currentKanbanColumnId = columnId || null;
    currentKanbanCardId = cardId || null;
    const modal = document.getElementById('kanbanCardModal');
    if (!modal) return;
    const titleEl = document.getElementById('kanbanCardModalTitle');
    const delBtn = document.getElementById('kanbanCardDeleteBtn');
    if (cardId){
        const card = findKanbanCard(cardId);
        if (!card) return;
        if (titleEl) titleEl.textContent = 'Edit Card';
        document.getElementById('kanbanCardTitle').value = card.title || '';
        document.getElementById('kanbanCardDescription').value = card.description || '';
        selectKanbanColor(card.color || '#3b82f6');
        if (delBtn) delBtn.classList.remove('hidden');
    } else {
        if (titleEl) titleEl.textContent = 'New Card';
        document.getElementById('kanbanCardTitle').value = '';
        document.getElementById('kanbanCardDescription').value = '';
        selectKanbanColor('#3b82f6');
        if (delBtn) delBtn.classList.add('hidden');
    }
    modal.classList.remove('hidden');
    document.getElementById('kanbanCardTitle').focus();
}

function closeKanbanModal(){
    const modal = document.getElementById('kanbanCardModal');
    if (modal) modal.classList.add('hidden');
}

function selectKanbanColor(color){
    currentKanbanColor = color;
    document.querySelectorAll('#kanbanColorPalette .kanban-color-swatch').forEach(b => {
        b.classList.toggle('kanban-color-swatch-selected', b.dataset.color === color);
    });
}

async function saveKanbanCard(){
    const title = document.getElementById('kanbanCardTitle').value.trim();
    if (!title){ alert('Title is required'); return; }
    const payload = {
        title,
        description: document.getElementById('kanbanCardDescription').value,
        color: currentKanbanColor,
    };
    let url, method;
    if (currentKanbanCardId){
        url = `/api/kanban/cards/${currentKanbanCardId}`;
        method = 'PUT';
    } else {
        url = '/api/kanban/cards';
        method = 'POST';
        payload.column_id = currentKanbanColumnId;
    }
    try {
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok){
            const err = await res.json().catch(() => ({}));
            alert(err.error || 'Failed to save card');
            return;
        }
        closeKanbanModal();
        await loadKanban();
    } catch {
        alert('Network error');
    }
}

async function deleteKanbanCardFromModal(){
    if (!currentKanbanCardId) return;
    if (!confirm('Delete this card?')) return;
    try {
        const res = await fetch(`/api/kanban/cards/${currentKanbanCardId}`, { method: 'DELETE' });
        if (!res.ok) return;
        closeKanbanModal();
        await loadKanban();
    } catch {}
}
