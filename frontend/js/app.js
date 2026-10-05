/* Bootstraps each page: renders shell, then runs the page module registered on window.Pages. */
window.Pages = window.Pages || {};
document.addEventListener('DOMContentLoaded', async () => {
  const page = document.body.dataset.page;
  const content = Components.shell(page);
  Components.refreshBadges();
  const mod = window.Pages[page];
  if (!mod) return;
  try { await mod.init(content); } catch (e) { content.innerHTML = Components.errorBox(e); }
});
