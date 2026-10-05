const { JSDOM } = require('jsdom');
const BASE = 'http://localhost:8000';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
async function open(path) {
  const errors = [];
  const dom = await JSDOM.fromURL(BASE + path, { runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, BASE), o);
      w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
      w.addEventListener('error', e => errors.push(String(e.error || e.message)));
      w.prompt = () => '';
    } });
  await sleep(1200);
  return { w: dom.window, d: dom.window.document, errors };
}
let fails = 0;
const check = (name, cond) => { console.log((cond ? 'PASS ' : 'FAIL ') + name); if (!cond) fails++; };
(async () => {
  let { d, errors } = await open('/index.html');
  check('dashboard renders hero', /important email/.test(d.querySelector('.hero')?.textContent || ''));
  check('dashboard 6 stat cards', d.querySelectorAll('.stat').length === 6);
  check('dashboard shows email cards', d.querySelectorAll('.email-card').length > 0);
  check('sidebar has 6 nav links', d.querySelectorAll('.nav a').length === 6);
  check('dashboard no JS errors', errors.length === 0);

  ({ d, errors } = await open('/inbox.html'));
  check('inbox lists 9 emails', d.querySelectorAll('.email-card').length === 9);
  check('inbox has filter chips', d.querySelectorAll('.chip').length === 8);
  const urgent = [...d.querySelectorAll('.chip')].find(c => c.dataset.k === 'urgent'); urgent.click(); await sleep(800);
  check('urgent filter -> only urgent', d.querySelectorAll('.email-card').length >= 1 && [...d.querySelectorAll('.email-card')].every(c => c.querySelector('.b-urgent')));
  ({ d } = await open('/inbox.html?filter=action'));
  check('action filter page', d.querySelector('h1').textContent === 'Action Required' && d.querySelectorAll('.email-card').length >= 3);
  ({ d } = await open('/inbox.html?q=interview'));
  check('search q=interview -> 1 result', d.querySelectorAll('.email-card').length === 1);

  const list = await (await fetch(BASE + '/api/emails')).json();
  const interview = list.items.find(i => i.subject.includes('Interview'));
  ({ d, errors } = await open('/email.html?id=' + interview.id));
  check('email detail shows analysis', /Action required/.test(d.body.textContent) && d.querySelector('pre.body').textContent.includes('interview'));
  check('email detail has draft button', !!d.getElementById('draft-btn'));
  check('email detail no JS errors', errors.length === 0);

  const inj = list.items.find(i => i.subject.includes('Important notice'));
  ({ d } = await open('/email.html?id=' + inj.id));
  check('injection email flagged, no draft button', /Suspicious content/.test(d.body.textContent) && !d.getElementById('draft-btn'));

  // XSS: untrusted subject must be escaped
  

  ({ d, errors } = await open('/email.html?id=' + interview.id));
  d.getElementById('draft-btn').click(); await sleep(1500);
  ({ d, errors } = await open('/replies.html'));
  check('reply center shows a draft with textarea', d.querySelectorAll('textarea').length >= 1);
  check('reply center buttons present', ['save', 'regen', 'send', 'reject'].every(a => d.querySelector(`button[data-a="${a}"]`)));
  const ta = d.querySelector('textarea'); ta.value = 'Hello, I confirm Monday 10 AM. Thanks!';
  d.querySelector('button[data-a="send"]').click(); await sleep(300);
  check('confirm dialog opens before sending', d.getElementById('confirm-dialog').open === true);
  d.getElementById('confirm-dialog').returnValue = 'ok'; d.getElementById('confirm-dialog').dispatchEvent(new d.defaultView.Event('close')); await sleep(2000);
  const drafts = await (await fetch(BASE + '/api/replies')).json();
  const sent = drafts.items.find(x => x.status === 'sent');
  check('approve & send via UI -> sent in DB, edited text kept', !!sent && sent.body.startsWith('Hello, I confirm') && sent.modified === true && !!sent.approved_by);

  ({ d, errors } = await open('/settings.html'));
  check('settings renders rules for 11 categories', d.querySelectorAll('select[data-cat]').length === 11);
  check('settings shows demo mode + audit log', /Demo mailbox/.test(d.body.textContent) && d.querySelectorAll('.table tr').length > 2);
  const sel = d.querySelector('select[data-cat="newsletter"]'); sel.value = 'high'; sel.dispatchEvent(new d.defaultView.Event('change')); await sleep(800);
  const st = await (await fetch(BASE + '/api/settings')).json();
  check('priority rule saved from UI', st.priority_rules.newsletter === 'high');
  check('settings no JS errors', errors.length === 0);
  console.log(fails ? `\n${fails} FAILED` : '\nALL UI CHECKS PASSED'); process.exit(fails ? 1 : 0);
})();
