// 部品「共有ブランチの木」。ブランチを名前のフォルダーで入れ子にして並べる（ブランチが先、フォルダーが後。名前の順）。
// 行の印：既定・届いている提出の件数（閉じたフォルダーは中の合計）・GitHub にない／GitHub だけ（雲）・提出 → 先。
// モジュールではないブランチは淡く、取り込み済みで手元だけのものはさらに淡く。
const CLOUD = '<path d="M4.5 12.5h7a3 3 0 0 0 .4-6 4 4 0 0 0-7.6-1A3.3 3.3 0 0 0 4.5 12.5z" fill="none" stroke="currentColor" stroke-width="1.3"/>';
const ICONS = { remote: CLOUD, local: CLOUD + '<path d="M2 2l12 12" stroke="currentColor" stroke-width="1.3"/>' };

const parents = (name) => name.split('/').slice(0, -1).map((_, i, parts) => parts.slice(0, i + 1).join('/'));
const isOpen = (s) => !!s && s.state === 'open';

export default {
  render(root, props, { h, emit, memory, redraw }) {
    const shared = props.branches.filter((b) => !b.is_task_branch);
    if (props.error && shared.length === 0) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    if (props.loading && shared.length === 0) return root.replaceChildren(h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 読み込み中…'));
    if (shared.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '共有ブランチはありません。'));

    const def = props.default_base;
    const selected = shared.some((b) => b.name === props.selected) ? props.selected
      : (shared.find((b) => b.name === def) || shared[0]).name;
    // 届いている提出：タスクの提出（作成元がそのブランチ）と、ブランチの提出（提出先がそのブランチ）
    const incoming = (name) => props.submissions.filter((t) => isOpen(t.submission) && t.submission.base === name).length
      + shared.filter((b) => isOpen(b.submission) && b.submitted_to === name).length;

    // 開いているフォルダー（この PC に覚える）。選んでいるブランチのフォルダーは、初めて見るときに開く
    const open = new Set(memory.get('folders', []));
    const revealed = memory.get('revealed', '');
    if (revealed !== selected) {
      for (const path of parents(selected)) open.add(path);
      memory.set('folders', [...open]);
      memory.set('revealed', selected);
    }
    const toggle = (path, show) => {
      if (show === undefined ? !open.has(path) : show) open.add(path); else open.delete(path);
      memory.set('folders', [...open]);
      redraw();
    };

    const top = { folders: new Map(), branches: [] };
    for (const b of shared) {
      let node = top;
      for (const path of parents(b.name)) {
        if (!node.folders.has(path)) node.folders.set(path, { path, folders: new Map(), branches: [] });
        node = node.folders.get(path);
      }
      node.branches.push(b);
    }
    const inside = (node) => [...node.branches, ...[...node.folders.values()].flatMap(inside)];
    const byName = (a, b) => a.localeCompare(b, 'ja');
    const icon = (kind, label) => {
      const box = h('span', { class: 'where', 'aria-label': label });
      box.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true">' + ICONS[kind] + '</svg>';
      return box;
    };

    const side = h('div', { class: 'side', role: 'tablist', 'aria-orientation': 'vertical', 'aria-label': '共有ブランチ' });
    const walk = (node, depth) => {
      for (const b of [...node.branches].sort((x, y) => byName(x.name, y.name))) {
        const n = incoming(b.name);
        const where = !b.remote ? 'GitHub にない（手元だけ' + (b.merged ? '・既定の作成元に取り込み済み' : '') + '）' : !b.local ? 'GitHub だけ（手元にない）' : '';
        const on = b.name === selected;
        const row = h('button', { type: 'button', role: 'tab', class: ['branch', b.unusable ? 'other' : '', !b.remote && b.merged ? 'done' : ''].filter(Boolean).join(' '),
          'aria-selected': String(on), tabindex: on ? '0' : '-1', style: '--depth:' + depth,
          title: [b.name, b.unusable ? 'ECOBuild のモジュールではない' : '', where, n ? '届いている提出 ' + n + ' 件' : ''].filter(Boolean).join('\n') },
        h('span', { class: 'name' }, b.name.split('/').pop()));
        row.dataset.branch = b.name;
        if (b.name === def) row.append(h('span', { class: 'pill ok' }, '既定'));
        if (where) row.append(icon(b.remote ? 'remote' : 'local', where));
        if (n) row.append(h('span', { class: 'count' }, String(n)));
        if (isOpen(b.submission)) row.append(h('small', { class: 'sub' }, '提出 → ' + b.submitted_to));
        row.addEventListener('click', () => emit('selected', { name: b.name }));
        side.append(row);
      }
      for (const f of [...node.folders.values()].sort((x, y) => byName(x.path, y.path))) {
        const shown = open.has(f.path);
        const all = inside(f);
        const n = shown ? 0 : all.reduce((sum, b) => sum + incoming(b.name), 0);
        const holds = !shown && parents(selected).includes(f.path);
        const row = h('button', { type: 'button', class: holds ? 'folder holds' : 'folder', 'aria-expanded': String(shown), tabindex: '-1',
          style: '--depth:' + depth, title: f.path + '/' },
        h('span', { class: 'name' }, h('span', { class: 'caret', 'aria-hidden': 'true' }, shown ? '▾' : '▸'), f.path.split('/').pop()),
        h('span', { class: 'folder-count' }, String(all.length)));
        row.dataset.folder = f.path;
        if (n) row.append(h('span', { class: 'count' }, String(n)));
        row.addEventListener('click', () => toggle(f.path));
        side.append(row);
        if (shown) walk(f, depth + 1);
      }
    };
    walk(top, 0);

    // 木のキー：↑↓ で行を移る（ブランチは着いたら選ぶ）、→ でフォルダーを開く、← で閉じる・上のフォルダーへ
    side.addEventListener('keydown', (event) => {
      if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      const row = event.target.closest('button');
      if (!row) return;
      event.preventDefault();
      const rows = [...side.querySelectorAll('button')];
      const folder = row.dataset.folder;
      if (event.key === 'ArrowRight') {
        if (folder !== undefined && !open.has(folder)) toggle(folder, true);
        return;
      }
      if (event.key === 'ArrowLeft') {
        if (folder !== undefined && open.has(folder)) return toggle(folder, false);
        const up = parents(folder !== undefined ? folder : row.dataset.branch).pop();
        const target = rows.find((item) => item.dataset.folder === up);
        if (target) target.focus();
        return;
      }
      const next = rows[rows.indexOf(row) + (event.key === 'ArrowDown' ? 1 : -1)];
      if (!next) return;
      next.focus();
      if (next.dataset.branch !== undefined) emit('selected', { name: next.dataset.branch });
    });
    root.replaceChildren(side);
  },
};
