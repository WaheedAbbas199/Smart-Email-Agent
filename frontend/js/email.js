Pages.email = {
  async init(root) {
    const id = new URLSearchParams(location.search).get('id');
    if (!id) { root.innerHTML = Components.empty('No email selected'); return; }
    root.innerHTML = Components.loading();
    const render = async () => {
      const e = await Api.getEmail(id), a = e.analysis;
      root.innerHTML = `<p><a href="inbox.html">← Back to inbox</a></p><h1>${esc(e.subject || '(no subject)')}</h1>
        <p class="sub">From ${esc(e.sender)} · ${esc(Components.fmtDate(e.received_at))}</p>
        <div class="grid-2"><div class="card"><h2>Message</h2><pre class="body">${esc(e.body)}</pre></div>
        <div class="card"><h2>AI analysis</h2>${a ? `
          <div class="flex">${Components.categoryBadge(a.category)}${Components.priorityBadge(a.priority)}${a.action_required ? '<span class="badge b-action">Action required</span>' : '<span class="badge b-ok">No action needed</span>'}${a.injection_flagged ? '<span class="badge b-urgent">Suspicious content</span>' : ''}</div>
          <p>${esc(a.summary)}</p>
          ${a.key_points.length ? `<strong>Key points</strong><ul class="clean">${a.key_points.map((k) => `<li>${esc(k)}</li>`).join('')}</ul>` : ''}
          ${a.action_items.length ? `<p><strong>Action items</strong></p><ul class="clean">${a.action_items.map((k) => `<li>${esc(k)}</li>`).join('')}</ul>` : ''}
          <dl class="kv mt"><dt>Deadline</dt><dd>${esc(Components.fmtDeadline(a) || '—')}</dd>
            <dt>Meeting</dt><dd>${a.meeting_details ? esc([a.meeting_details.date, a.meeting_details.time, a.meeting_details.location].filter(Boolean).join(' · ')) : '—'}</dd>
            <dt>Priority reason</dt><dd>${esc(a.priority_reason)}</dd><dt>Category reason</dt><dd>${esc(a.category_reason)}</dd>
            <dt>Analyzed by</dt><dd>${esc(a.model)}${a.uncertain ? ' (uncertain classification)' : ''}</dd></dl>
          <div class="flex mt"><button class="btn" id="re-btn">↻ Re-analyze</button>
            ${a.reply_required && !a.injection_flagged ? '<button class="btn primary" id="draft-btn">✉️ Draft reply</button>' : ''}</div>`
          : `<p class="muted">This email has not been analyzed yet.</p><button class="btn primary" id="re-btn">Analyze now</button>`}</div></div>`;
      const re = document.getElementById('re-btn');
      if (re) re.onclick = () => Components.guard(re, async () => { await Api.analyzeEmail(id); Components.toast('Analysis updated'); await render(); });
      const dr = document.getElementById('draft-btn');
      if (dr) dr.onclick = () => Components.guard(dr, async () => { await Api.draftReply(id); location.href = `replies.html?email=${id}`; });
    };
    await render();
  },
};
