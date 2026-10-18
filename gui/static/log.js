'use strict';
// The log window (log.html?dir=…&path=…): the log of a file or folder in a window of its own (the explorer's 「ログ」),
// so that several can be open side by side and moved freely. Reading only: no commit menu (the workspace's ログ tab has it).
// It reads again when a command ran in another window (a commit, a reset).
(() => {
  const dir = ECO.params.get('dir') || '', path = ECO.params.get('path') || '';
  const name = path || dir.replace(/[\\/]+$/, '').split(/[\\/]/).pop();
  document.title = `ログ：${name} — ECOBuild`;
  document.getElementById('log-title').textContent = `ログ：${path || '全体'}`;
  document.getElementById('log-where').textContent = dir;
  let count = 50;
  const view = LOG.view(document.getElementById('log'), {dir, path, onMore: () => { count += 50; load(); }});
  async function load() {
    const doc = await ECO.cli(dir, ['log', ...(path ? [path] : []), '--count', String(count)], {quiet: true});
    if (doc.ok) view.show(doc.result, doc.result.length >= count); else view.error(doc.error.message);
  }
  load();
  ECO.onChange(load);
  setTimeout(() => view.focus());
})();
