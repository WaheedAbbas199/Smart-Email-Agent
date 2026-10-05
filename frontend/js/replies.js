Pages.replies = {
  async init(root) {
    const focus = new URLSearchParams(location.search).get('email');
    root.innerHTML = `<h1>Reply Center</h1><p class="sub">Review, edit and approve AI drafts. Nothing is sent until you confirm.</p><div id="drafts"></div>`;
    const box = document.getElementById('drafts');
    const STATUS = { draft: ['b-action', 'Awaiting review'], approved: ['b-ok', 'Approved'], sending: ['b-medium', 'Sending…'], sent: ['b-ok', 'Sent'], rejected: ['b-low', 'Rejected'], failed: ['b-urgent', 'Send failed'] };

    const load = async () => {
      box.innerHTML = Components.loading();
      const { items } = await Api.getDrafts();
      items.sort((a, b) => (Number(String(b.email_id) === focus) - Number(String(a.email_id) === focus)));
      box.innerHTML = items.length ? items.map(card).join('') : Components.empty('No drafts yet', 'Open an email that needs a reply and click “Draft reply”.');
      items.forEach(wire);
      Components.refreshBadges();
    };

    const card = (d) => {
      const [cls, label] = STATUS[d.status] || ['b-low', d.status]; const locked = ['sent', 'rejected', 'sending'].includes(d.status);
      return `<div class="card mt" id="d${d.id}"><div class="flex"><strong>${esc(d.email.subject)}</strong><span class="badge ${cls}">${label}</span>${d.modified ? '<span class="badge b-low">edited</span>' : ''}
        <span class="muted small" style="margin-left:auto">To: ${esc(Components.senderName(d.email.sender))}</span></div>
        ${d.email.analysis ? `<p class="muted small">Original: ${esc(d.email.analysis.summary)}</p>` : ''}
        <label class="small muted" for="t${d.id}">Draft</label><textarea id="t${d.id}" ${locked ? 'disabled' : ''}>${esc(d.body)}</textarea>
        ${d.approved_by ? `<p class="small muted">Approved by ${esc(d.approved_by)} on ${esc(Components.fmtDate(d.approved_at))}</p>` : ''}
        ${d.send_result && d.send_result.error ? `<p class="small" style="color:var(--urgent)">${esc(d.send_result.error)}</p>` : ''}
        ${d.status === 'sent' ? `<p class="small muted">Sent ${esc(Components.fmtDate(d.sent_at))}${d.send_result && d.send_result.simulated ? ' (simulated in demo mode, nothing left your machine)' : ''}</p>` : ''}
        ${locked ? '' : `<div class="flex mt"><button class="btn" data-a="save">Save edit</button><button class="btn" data-a="regen">↻ Regenerate</button>
          <button class="btn primary" data-a="send">Approve &amp; Send</button><button class="btn danger" data-a="reject" style="margin-left:auto">Reject</button></div>`}</div>`;
    };

    const wire = (d) => {
      const el = document.getElementById(`d${d.id}`); if (!el) return;
      const text = () => document.getElementById(`t${d.id}`).value.trim();
      el.querySelectorAll('button[data-a]').forEach((b) => b.onclick = () => Components.guard(b, async () => {
        const act = b.dataset.a;
        if (act === 'save') { await Api.editReply(d.id, text()); Components.toast('Draft saved (needs approval before sending)'); }
        else if (act === 'regen') {
          const hint = prompt('Optional guidance for the new draft (e.g. "suggest a later time"):', '') ;
          if (hint === null) return;
          await Api.draftReply(d.email_id, { regenerate: true, instructions: hint || null }); Components.toast('New draft generated');
        } else if (act === 'reject') { await Api.rejectReply(d.id); Components.toast('Draft rejected'); }
        else if (act === 'send') {
          if (!text()) { Components.toast('Draft is empty', true); return; }
          const ok = await Components.confirmDialog('Send this email?', `This will approve the draft and send it to ${Components.senderName(d.email.sender)}. This cannot be undone.`, 'Approve & Send');
          if (!ok) return;
          if (text() !== d.body) await Api.editReply(d.id, text());
          await Api.approveReply(d.id); await Api.sendReply(d.id); Components.toast('Email sent');
        }
        await load();
      }));
    };
    await load();
  },
};
