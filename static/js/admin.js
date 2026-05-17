let resetPasswordUserId = null;

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
