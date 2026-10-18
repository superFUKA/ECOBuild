'use strict';
// The log of a module, a file or a folder (ecobuild log), with the changes of the commit chosen (ecobuild show).
const LOG = (() => {
  const {esc} = ECO;
  const matches = (c, query) => !query || [c.sha, c.subject, c.author, c.issue ? '#' + c.issue : ''].some(v => String(v).toLowerCase().includes(query));
  // A log view (the workspace's ログ tab, the log window log.html): the commits on the left (search, ↑↓, read more), the chosen one's
  // changes on the right, its files folded one by one (path: the files under it open first). menu(c, x, y): a commit's
  // menu (right click, or 操作 ▾). show(commits, more): the commits read (more: there may be more); onMore: read more.
  function view(box, {dir, path = '', selected = '', menu = null, onMore}) {
    box.classList.add('log-view');
    box.innerHTML = `<div class="log-side"><input type="search" class="log-search" placeholder="件名・作成者・SHA・#タスクで絞り込み" aria-label="ログを絞り込む">
      <ul class="log-entries" role="listbox" tabindex="0" aria-label="コミット"><li class="muted">読み込んでいます…</li></ul><button type="button" class="log-more" hidden>さらに読み込む</button></div><div class="log-main"></div>`;
    const list = box.querySelector('.log-entries'), main = box.querySelector('.log-main'), search = box.querySelector('.log-search'), more = box.querySelector('.log-more');
    const diffs = new Map();
    let entries = null, chosen = selected, drawn = '';
    const visible = () => (entries || []).filter(c => matches(c, search.value.trim().toLowerCase()));
    const commit = sha => (entries || []).find(c => c.sha === sha);
    const renderList = () => {
      if (!entries) return;
      list.innerHTML = visible().map(c => `<li role="option" data-sha="${esc(c.sha)}" aria-selected="${c.sha === chosen}"${menu ? ' title="右クリックで操作"' : ''}><code>${esc(c.sha.slice(0, 8))}</code><span class="log-subject">${esc(c.subject)}</span>
        <small>${esc(c.author)}・${esc(ECO.localTime(c.date, true))}${c.issue ? `・#${c.issue}` : ''}</small></li>`).join('')
        || `<li class="muted">${entries.length ? '一致するコミットはありません。' : 'ログはありません。'}</li>`;
    };
    const choose = async sha => {
      chosen = sha; drawn = sha; renderList();
      list.querySelector('[aria-selected=true]')?.scrollIntoView({block: 'nearest'});
      if (!sha) { main.innerHTML = ''; return; }
      if (!diffs.has(sha)) {
        main.innerHTML = '<p class="muted">読み込んでいます…</p>';
        const doc = await ECO.cli(dir, ['show', sha], {quiet: true});
        diffs.set(sha, doc.ok ? doc.result : `読み込めませんでした：${doc.error.message}`);
      }
      if (chosen !== sha) return;
      main.innerHTML = `<div class="log-commit"><strong>${esc(commit(sha)?.subject || sha.slice(0, 8))}</strong>${menu && commit(sha) ? '<button type="button" data-menu>操作 ▾</button>' : ''}<button type="button" data-copy="${esc(sha)}">SHAをコピー</button>
        <button type="button" data-fold="open">すべて開く</button><button type="button" data-fold="close">すべて閉じる</button></div>${ECO.diffHtml(diffs.get(sha), {focus: path})}`;
      main.scrollTop = 0;
    };
    list.addEventListener('click', e => { const row = e.target.closest('[data-sha]'); if (row) choose(row.dataset.sha); });
    list.addEventListener('contextmenu', e => {
      const c = commit(e.target.closest('[data-sha]')?.dataset.sha);
      if (c && menu) { e.preventDefault(); if (c.sha !== chosen) choose(c.sha); menu(c, e.clientX, e.clientY); }
    });
    list.addEventListener('keydown', e => {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      e.preventDefault();
      const shown = visible(), i = shown.findIndex(c => c.sha === chosen), next = shown[Math.max(0, Math.min(shown.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))];
      if (next && next.sha !== chosen) choose(next.sha);
    });
    main.addEventListener('click', e => {
      const copy = e.target.closest('[data-copy]'), fold = e.target.closest('[data-fold]')?.dataset.fold, button = e.target.closest('[data-menu]');
      if (copy) ECO.copyText(copy.dataset.copy);
      if (fold) main.querySelectorAll('details.eco-file').forEach(f => { f.open = fold === 'open'; });
      if (button && commit(chosen)) { const r = button.getBoundingClientRect(); menu(commit(chosen), r.left, r.bottom + 4); }
    });
    search.addEventListener('input', renderList);
    more.addEventListener('click', () => { more.disabled = true; onMore(); });
    return {
      show(commits, hasMore) {
        entries = commits; more.hidden = !hasMore; more.disabled = false;
        // The chosen commit stays; one gone (after ここまで戻す) gives way to the newest. The one asked for may be older.
        if (!chosen || (!commit(chosen) && chosen !== selected)) choose(entries[0]?.sha || '');
        else if (drawn !== chosen) choose(chosen);
        else renderList();
      },
      error(message) { list.innerHTML = `<li class="muted">読み込めませんでした：${esc(message)}</li>`; more.disabled = false; },
      focus() { list.focus(); },
    };
  }
  return {view};
})();
