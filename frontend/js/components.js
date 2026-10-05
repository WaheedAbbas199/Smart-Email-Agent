window.Pages = window.Pages || {};  // page modules register here (components.js loads before page scripts)
/* Shared UI helpers. All dynamic text goes through esc(): email content is untrusted (XSS). */
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const Components = (() => {
  const NAV = [
    ['dashboard', 'index.html', '📊', 'Dashboard'], ['inbox', 'inbox.html', '📥', 'Inbox'],
    ['action', 'inbox.html?filter=action', '✅', 'Action Required'], ['important', 'inbox.html?filter=important', '⭐', 'Important'],
    ['replies', 'replies.html', '✉️', 'Reply Center'], ['settings', 'settings.html', '⚙️', 'Settings'],
  ];
  const fmtDate = (iso) => { const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z')); return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  const fmtDeadline = (a) => a.deadline_date ? `${new Date(a.deadline_date + 'T00:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}${a.deadline_time ? ' ' + a.deadline_time : ''}` : (a.deadline_text || '');
  const senderName = (s) => (s.replace(/<.*?>/, '').trim() || s);

  function shell(active) {
    const qs = new URLSearchParams(location.search);
    const activeKey = active === 'inbox' ? (qs.get('filter') === 'action' ? 'action' : qs.get('filter') === 'important' ? 'important' : 'inbox') : active;
    document.getElementById('shell').innerHTML = `
      <div class="layout">
        <aside class="sidebar" id="sidebar">
          <div class="brand"><span class="logo">✦</span> Smart Email Agent</div>
          <nav class="nav">${NAV.map(([k, href, ic, label]) => `<a href="${href}" class="${k === activeKey ? 'active' : ''}"><span>${ic}</span>${label}${k === 'replies' ? '<span class="count" id="nav-replies" hidden></span>' : ''}</a>`).join('')}</nav>
        </aside>
        <div class="main">
          <header class="topbar">
            <button class="btn sm menu-btn" id="menu-btn" aria-label="Open menu">☰</button>
            <form class="search" id="search-form" role="search"><input type="search" id="search-input" placeholder="Search emails…" aria-label="Search emails" value="${esc(qs.get('q') || '')}"></form>
            <span class="spacer"></span>
            <a class="bell" href="replies.html" title="Replies waiting for approval" aria-label="Notifications">🔔<span class="dot" id="bell-dot" hidden></span></a>
            <div class="avatar" id="avatar" title="Account">U</div>
          </header>
          <main class="content" id="content"></main>
        </div>
      </div>
      <div class="toast-wrap" id="toasts" aria-live="polite"></div>
      <dialog id="confirm-dialog"><form method="dialog"><h2 id="cd-title"></h2><p id="cd-msg" class="muted"></p>
        <div class="flex" style="justify-content:flex-end"><button class="btn" value="cancel">Cancel</button><button class="btn primary" value="ok" id="cd-ok"></button></div></form></dialog>`;
    document.getElementById('menu-btn').onclick = () => document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('search-form').onsubmit = (e) => { e.preventDefault(); const q = document.getElementById('search-input').value.trim(); location.href = `inbox.html${q ? '?q=' + encodeURIComponent(q) : ''}`; };
    return document.getElementById('content');
  }

  async function refreshBadges() {
    try {
      const [{ stats }, s] = await Promise.all([Api.getDashboard(), Api.getSettings()]);
      const n = stats.pending_replies;
      const nav = document.getElementById('nav-replies'), dot = document.getElementById('bell-dot');
      nav.textContent = dot.textContent = n; nav.hidden = dot.hidden = !n;
      document.getElementById('avatar').textContent = (s.account.name || s.account.email || 'U')[0].toUpperCase();
    } catch (_) { /* non-critical */ }
  }

  const loading = (msg = 'Loading…') => `<div class="state"><div class="spinner"></div>${esc(msg)}</div>`;
  const empty = (title, hint = '') => `<div class="state"><div style="font-size:34px">📭</div><strong>${esc(title)}</strong><div>${esc(hint)}</div></div>`;
  const errorBox = (e) => `<div class="error-box" role="alert">⚠️ ${esc(e.message || e)}</div>`;
  const priorityBadge = (p) => `<span class="badge b-${esc(p)}">${esc(p)}</span>`;
  const categoryBadge = (c) => `<span class="badge b-cat">${esc(c)}</span>`;

  function emailCard(e) {
    const a = e.analysis;
    return `<a class="card email-card" href="email.html?id=${e.id}">
      <div class="row"><span class="subject">${esc(e.subject || '(no subject)')}</span>
        ${a ? categoryBadge(a.category) + priorityBadge(a.priority) + (a.action_required ? '<span class="badge b-action">Action required</span>' : '') + (a.uncertain ? '<span class="badge b-low">uncertain</span>' : '') : '<span class="badge b-low">Not analyzed</span>'}
        <span class="date">${esc(fmtDate(e.received_at))}</span></div>
      <div class="sender">${esc(senderName(e.sender))}</div>
      ${a ? `<p class="summary">${esc(a.summary)}</p>` : ''}</a>`;
  }

  function toast(msg, isErr = false) {
    const el = document.createElement('div'); el.className = 'toast' + (isErr ? ' err' : ''); el.textContent = msg;
    document.getElementById('toasts').appendChild(el); setTimeout(() => el.remove(), 4000);
  }

  function confirmDialog(title, message, okLabel) {
    return new Promise((resolve) => {
      const d = document.getElementById('confirm-dialog');
      document.getElementById('cd-title').textContent = title; document.getElementById('cd-msg').textContent = message;
      document.getElementById('cd-ok').textContent = okLabel;
      d.onclose = () => resolve(d.returnValue === 'ok'); d.showModal();
    });
  }

  async function guard(btn, fn) {
    if (btn) btn.disabled = true;
    try { return await fn(); } catch (e) { toast(e.message || 'Something went wrong', true); }
    finally { if (btn) btn.disabled = false; }
  }
  return { shell, refreshBadges, loading, empty, errorBox, priorityBadge, categoryBadge, emailCard, toast, confirmDialog, guard, fmtDate, fmtDeadline, senderName };
})();
