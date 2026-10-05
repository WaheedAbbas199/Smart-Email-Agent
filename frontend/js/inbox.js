Pages.inbox = {
  FILTERS: [['all', 'All'], ['urgent', 'Urgent'], ['high', 'High'], ['action', 'Action Required'], ['important', 'Important'], ['job', 'Job'], ['work', 'Work'], ['personal', 'Personal']],
  async init(root) {
    const qs = new URLSearchParams(location.search);
    const state = { filter: qs.get('filter') || 'all', q: qs.get('q') || '' };
    root.innerHTML = `<h1>${state.filter === 'action' ? 'Action Required' : state.filter === 'important' ? 'Important' : 'Inbox'}</h1>
      <p class="sub" id="inbox-sub">${state.q ? `Results for “${esc(state.q)}”` : 'Every email, analyzed and prioritised.'}</p>
      <div class="flex" style="margin-bottom:14px"><div class="chips" id="chips" style="margin:0"></div>
        <button class="btn sm" id="sync-btn" style="margin-left:auto">↻ Sync emails</button></div><div id="list"></div>`;
    const chips = document.getElementById('chips'), list = document.getElementById('list');
    const draw = () => { chips.innerHTML = this.FILTERS.map(([k, l]) => `<button class="chip ${k === state.filter ? 'active' : ''}" data-k="${k}">${l}</button>`).join(''); };
    const load = async () => {
      list.innerHTML = Components.loading();
      try {
        const { items } = await Api.getEmails({ filter: state.filter === 'all' ? '' : state.filter, q: state.q });
        list.innerHTML = items.length ? items.map(Components.emailCard).join('') : Components.empty('No emails match', 'Try another filter or sync your mailbox.');
      } catch (e) { list.innerHTML = Components.errorBox(e); }
    };
    chips.onclick = (ev) => { const k = ev.target.dataset.k; if (!k) return; state.filter = k; draw(); load(); };
    document.getElementById('sync-btn').onclick = (ev) => Components.guard(ev.target, async () => {
      const r = await Api.syncEmails(); const a = await Api.analyzePending();
      Components.toast(`${r.new_emails} new email(s), ${a.analyzed} analyzed`); await load(); Components.refreshBadges();
    });
    draw(); await load();
  },
};
