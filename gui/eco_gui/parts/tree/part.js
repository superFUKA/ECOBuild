// 部品「ファイルの木」。パスからフォルダーの木を作る。フォルダーの開閉は、この部品の中だけの状態。
function build(paths) {
  const top = { folders: new Map(), files: [] };
  for (const path of paths) {
    const names = path.split('/');
    let at = top;
    for (const name of names.slice(0, -1)) {
      if (!at.folders.has(name)) at.folders.set(name, { folders: new Map(), files: [] });
      at = at.folders.get(name);
    }
    at.files.push([names[names.length - 1], path]);
  }
  return top;
}

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.paths.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.paths.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const holds = (folder) => [...folder.folders.values()].some(holds) || folder.files.some(([, path]) => path === props.selected);
    const draw = (folder) => {
      const list = h('ul', { style: 'padding-left:1rem;gap:.1rem' });
      for (const [name, child] of [...folder.folders].sort()) {
        const box = h('details', {}, h('summary', {}, name), draw(child));
        box.open = holds(child);  // 選んでいるファイルのあるフォルダーは開いておく
        list.append(h('li', {}, box));
      }
      for (const [name, path] of folder.files.sort()) {
        const on = path === props.selected;
        const button = h('button', { type: 'button', 'aria-selected': String(on), style: 'border:0;background:transparent;padding:.1rem .3rem' }, name);
        if (on) button.style.fontWeight = '600';
        button.addEventListener('click', () => emit('selected', { path }));
        list.append(h('li', {}, button));
      }
      return list;
    };
    const tree = draw(build(props.paths));
    tree.style.cssText = 'padding:0;max-height:22rem;overflow:auto';
    root.replaceChildren(tree);
  },
};
