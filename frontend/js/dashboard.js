Pages.dashboard = {
  async init(root) {
    root.innerHTML = Components.loading('Loading your inbox intelligence…');
    const render = async () => {
      const d = await Api.getDashboard(), s = d.stats;
      const list = (items, empty) => items.length ? items.map(Components.emailCard).join('') : `<div class="muted small">${esc(empty)}</div>`;
      root.innerHTML = `
        <h1>Dashboard</h1><p class="sub">Your inbox, summarised by AI. Nothing is ever sent without your approval.</p>
        ${s.unanalyzed ? `<div class="notice"><span>${s.unanalyzed} email(s) have not been analyzed yet.</span><button class="btn primary sm" id="analyze-btn">Analyze now</button></div>` : ''}
        <section class="hero"><h2>${s.important ? `${s.important} important email${s.important > 1 ? 's' : ''}` : 'Nothing important right now 🎉'}</h2>
          <ul><li><strong>${s.action_required}</strong> require action</li><li><strong>${s.pending_replies}</strong> repl${s.pending_replies === 1 ? 'y' : 'ies'} waiting for approval</li><li><strong>${s.upcoming_deadlines}</strong> upcoming deadline${s.upcoming_deadlines === 1 ? '' : 's'}</li></ul></section>
        <div class="stats">
          ${[['Total emails', s.total_emails, 'inbox.html'], ['Important', s.important, 'inbox.html?filter=important'], ['Urgent', s.urgent, 'inbox.html?filter=urgent'],
             ['Need action', s.action_required, 'inbox.html?filter=action'], ['Pending replies', s.pending_replies, 'replies.html'], ['Deadlines', s.upcoming_deadlines, 'inbox.html?filter=action']]
            .map(([l, n, href]) => `<div class="card stat"><a href="${href}"><div class="num">${n}</div><div class="label">${l}</div></a></div>`).join('')}
        </div>
        <div class="grid-2">
          <div><h2>Recent important emails</h2>${list(d.recent_important, 'No important emails.')}</div>
          <div><h2>Action required</h2>${list(d.action_required, 'You are all caught up.')}
            <h2 class="mt">Upcoming deadlines</h2>
            <div class="card">${d.upcoming_deadlines.length ? d.upcoming_deadlines.map((e) => `<a class="deadline" href="email.html?id=${e.id}"><span>${esc(e.subject)}</span><strong>${esc(Components.fmtDeadline(e.analysis))}</strong></a>`).join('') : '<span class="muted small">No upcoming deadlines.</span>'}</div></div>
        </div>`;
      const btn = document.getElementById('analyze-btn');
      if (btn) btn.onclick = () => Components.guard(btn, async () => { const r = await Api.analyzePending(); Components.toast(`Analyzed ${r.analyzed} email(s)${r.failed ? `, ${r.failed} failed` : ''}`, !!r.failed); await render(); Components.refreshBadges(); });
    };
    await render();
  },
};
