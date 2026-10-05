Pages.settings = {
  async init(root) {
    const NOTIFY = { notify_urgent: 'Notify me about urgent emails', notify_action_required: 'Notify me when action is required', notify_reply_ready: 'Notify me when a reply draft is ready' };
    const oauthMsg = new URLSearchParams(location.search).get('oauth');
    const render = async () => {
      const s = await Api.getSettings(), acc = s.account, actions = (await Api.getActions()).items.slice(0, 12);
      root.innerHTML = `<h1>Settings</h1><p class="sub">Teach the agent how you prioritise.</p>
        ${oauthMsg ? `<div class="notice">Gmail: ${esc(oauthMsg)}</div>` : ''}
        <div class="grid-2"><div>
          <div class="card"><h2>Connected account</h2><dl class="kv"><dt>Account</dt><dd>${esc(acc.email)}</dd><dt>Mode</dt><dd>${acc.demo_mode ? 'Demo mailbox (mock emails, sends are simulated)' : 'Live Gmail'}</dd>
            <dt>Gmail</dt><dd>${acc.gmail_connected ? '<span class="badge b-ok">Connected</span>' : '<span class="badge b-low">Not connected</span>'}</dd><dt>AI engine</dt><dd>${esc(acc.llm)}</dd></dl>
            <div class="flex mt">${acc.gmail_connected ? '<button class="btn danger sm" id="disc">Disconnect Gmail</button>' : `<a class="btn primary sm" href="/api/auth/google/login" ${acc.oauth_configured ? '' : 'aria-disabled="true" title="Set GOOGLE_CLIENT_ID/SECRET first"'}>Connect Gmail</a>`}</div>
            ${!acc.oauth_configured ? '<p class="small muted">Google OAuth is not configured. See README → Google OAuth setup.</p>' : ''}</div>
          <div class="card mt"><h2>Priority rules</h2><p class="small muted">Override the AI's priority for a category. Leave on “AI decides” for default behaviour.</p>
            ${s.categories.map((c) => `<div class="switch"><label for="r-${c}" style="text-transform:capitalize">${c}</label><select id="r-${c}" data-cat="${c}" style="width:150px"><option value="">AI decides</option>${s.priorities.map((p) => `<option value="${p}" ${s.priority_rules[c] === p ? 'selected' : ''}>${p}</option>`).join('')}</select></div>`).join('')}
            <p class="small muted mt">Rules apply the next time an email is analyzed.</p></div>
          <div class="card mt"><h2>Notifications</h2>${Object.entries(NOTIFY).map(([k, l]) => `<div class="switch"><label for="n-${k}">${l}</label><input type="checkbox" id="n-${k}" data-key="${k}" ${s.settings[k] ? 'checked' : ''}></div>`).join('')}</div>
        </div><div class="card"><h2>Agent activity (audit log)</h2>${actions.length ? `<table class="table"><tr><th>Action</th><th>Result</th><th>ms</th></tr>${actions.map((a) => `<tr><td>${esc(a.action)}</td><td>${a.success ? '✅' : '❌'}</td><td>${a.latency_ms ?? ''}</td></tr>`).join('')}</table>` : '<span class="muted">No activity yet.</span>'}</div></div>`;
      root.querySelectorAll('select[data-cat]').forEach((el) => el.onchange = () => Components.guard(el, async () => { await Api.updateSettings({ priority_rules: { [el.dataset.cat]: el.value || null } }); Components.toast('Rule saved'); }));
      root.querySelectorAll('input[data-key]').forEach((el) => el.onchange = () => Components.guard(el, async () => { await Api.updateSettings({ settings: { [el.dataset.key]: el.checked } }); Components.toast('Preference saved'); }));
      const d = document.getElementById('disc'); if (d) d.onclick = () => Components.guard(d, async () => { await Api.disconnect(); await render(); });
    };
    await render();
  },
};
