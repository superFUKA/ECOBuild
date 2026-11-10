// 部品「ファイルの木」（いくつも選べる）。パスからフォルダーの木を作る。
// フォルダーの名前の横の「選ぶ」で、フォルダーそのものを選べる（動かす・消す相手にする）。
// フォルダーのチェックは、中のファイル全部のチェック。フォルダーの開閉は、この部品の中だけの状態。
const OPENED = new WeakMap();  // 描く先 → 人が開いたフォルダー

function build(paths) {
  const top = { path: '', folders: new Map(), files: [], all: [] };
  for (const path of paths) {
    const names = path.split('/');
    let at = top;
    at.all.push(path);
    names.slice(0, -1).forEach((name, index) => {
      if (!at.folders.has(name)) at.folders.set(name, { path: names.slice(0, index + 1).join('/'), folders: new Map(), files: [], all: [] });
      at = at.folders.get(name);
      at.all.push(path);
    });
    at.files.push([names[names.length - 1], path]);
  }
  return top;
}

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.paths.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.paths.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    if (!OPENED.has(root)) OPENED.set(root, new Set());
    const opened = OPENED.get(root);
    const checked = new Set(props.checked);
    const plain = 'border:0;background:transparent;padding:.1rem .3rem';
    const line = 'display:flex;gap:.2rem;align-items:center';
    const holds = (folder) => props.selected !== null && (folder.path === props.selected || folder.all.includes(props.selected));
    const box = (paths, title) => {
      const on = paths.filter((path) => checked.has(path)).length;
      const input = h('input', { type: 'checkbox', title, checked: on === paths.length });
      input.indeterminate = on > 0 && on < paths.length;
      input.addEventListener('click', (event) => event.stopPropagation());  // フォルダーの開閉にしない
      input.addEventListener('change', () => {
        for (const path of paths) { if (input.checked) checked.add(path); else checked.delete(path); }
        emit('changed', { paths: props.paths.filter((path) => checked.has(path)) });
      });
      return input;
    };
    const name = (text, path, title) => {
      const on = path === props.selected;
      const button = h('button', { type: 'button', title, 'aria-selected': String(on), style: plain }, text);
      if (on) button.style.fontWeight = '600';
      button.addEventListener('click', (event) => { event.preventDefault(); emit('selected', { path }); });
      return button;
    };
    const draw = (folder) => {
      const list = h('ul', { style: 'padding-left:1rem;gap:.1rem;list-style:none;margin:0' });
      for (const [label, child] of [...folder.folders].sort()) {
        const head = h('summary', {}, h('span', { style: 'display:inline-flex;gap:.2rem;align-items:center' },
          box(child.all, '中のファイルを全部チェック'), label + '/', name('選ぶ', child.path, 'このフォルダーを選ぶ')));
        const details = h('details', {}, head, draw(child));
        details.open = opened.has(child.path) || holds(child);
        details.addEventListener('toggle', () => { if (details.open) opened.add(child.path); else opened.delete(child.path); });
        list.append(h('li', {}, details));
      }
      for (const [label, path] of folder.files.sort()) {
        list.append(h('li', { style: line }, box([path], 'チェック'), name(label, path, '選ぶ')));
      }
      return list;
    };
    const tree = draw(build(props.paths));
    tree.style.cssText = 'padding:0;max-height:22rem;overflow:auto;list-style:none;margin:0';
    root.replaceChildren(tree);
  },
};
