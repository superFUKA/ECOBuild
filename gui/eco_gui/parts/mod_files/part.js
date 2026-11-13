// 部品「モジュールのファイルの木」。今までの GUI（modinfo.js の fileTree）と同じ並び・同じ見た目。
// いちばん上の段から。フォルダーはその場で開く（開いたものは窓の中で覚える）。ファイルは既定のアプリで開く（opened）。
export default {
  render(root, props, { h, emit, state, redraw }) {
    if (props.error) return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, `ファイルを読めませんでした：${props.error}`)));
    if (props.loading && !props.files.length) return root.replaceChildren(h('p', { class: 'note', role: 'status' }, '読み込み中…'));
    state.open = state.open || {};
    const missing = new Set(props.missing || []), generated = new Set(props.generated || []);
    // フォルダー → 中のフォルダーとファイル（ファイルの道筋から組む）
    const children = new Map([['', { dirs: new Set(), files: [] }]]);
    const parent = (path) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '');
    const folder = (path) => {
      if (!children.has(path)) {
        children.set(path, { dirs: new Set(), files: [] });
        folder(parent(path)).dirs.add(path);
      }
      return children.get(path);
    };
    for (const file of props.files) if (!missing.has(file)) folder(parent(file)).files.push(file);
    const name = (path) => path.slice(path.lastIndexOf('/') + 1);
    const byName = (a, b) => name(a).localeCompare(name(b), 'ja', { sensitivity: 'base' });
    const count = (path) => { const c = children.get(path); return c.dirs.size + c.files.length; };
    const open = (file) => emit('opened', { path: file });
    const level = (path) => {
      const c = children.get(path);
      const items = [];
      for (const d of [...c.dirs].sort(byName)) {
        const opened = !!state.open[d];
        const button = h('button', { type: 'button', class: 'file dir', 'aria-expanded': String(opened) },
          h('span', { class: 'caret', 'aria-hidden': 'true' }, opened ? '▾' : '▸'), h('span', { class: 'icon', 'aria-hidden': 'true' }, '▤'), name(d),
          h('small', {}, count(d) ? `${count(d)} 項目` : '空'));
        button.addEventListener('click', () => { state.open[d] = !opened; redraw(); });
        items.push(h('li', {}, button, opened ? level(d) : ''));
      }
      for (const file of [...c.files].sort(byName)) {
        const mark = generated.has(file);
        const button = h('button', { type: 'button', class: mark ? 'file generated' : 'file', title: 'ダブルクリック（Enter）で開く' },
          h('span', { class: 'caret', 'aria-hidden': 'true' }), h('span', { class: 'icon', 'aria-hidden': 'true' }, '▫'), name(file), mark ? h('small', {}, '生成ファイル') : '');
        button.addEventListener('dblclick', () => open(file));
        button.addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); open(file); } });
        const openButton = h('button', { type: 'button', class: 'small open', tabindex: '-1' }, '開く');
        openButton.addEventListener('click', () => open(file));
        items.push(h('li', { class: 'row' }, button, openButton));
      }
      return h('ul', {}, ...items);
    };
    root.replaceChildren(h('div', { class: 'files' }, count('') ? level('') : h('p', { class: 'note' }, 'ファイルはありません。')));
  },
};
