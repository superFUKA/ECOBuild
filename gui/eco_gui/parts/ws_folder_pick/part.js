// 部品「移動先のフォルダー」。今までの GUI（gui/static/explorer.js の moveChosenDialog）と同じ：動かすものの一覧と、移動先のフォルダーの欄。
const dirOf = (path) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '');

export default {
  render(root, props, { h, emit, state, lib }) {
    const box = h('div', { class: 'pick' }, h('h2', {}, `${props.paths.length} 件を移動`));
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => emit('cancel', {}));
    if (props.error || (props.loading && !props.files.length)) {
      box.append(props.error ? h('p', { role: 'alert' }, props.error) : h('p', { class: 'muted' }, '読み込み中…'), h('div', { class: 'actions' }, cancel));
      return root.replaceChildren(box);
    }
    const tops = lib.ws.projects(props.projects).map((project) => project.top).filter(Boolean);
    const inside = (dir) => !tops.length || tops.some((top) => dir === top || dir.startsWith(top + '/'));
    const moving = props.paths;
    const dirs = new Set(tops.length ? [] : ['']);
    for (const path of [...props.files, ...(props.folders || []).map((dir) => dir + '/x')]) {
      path.split('/').slice(0, -1).forEach((_, i, names) => dirs.add(names.slice(0, i + 1).join('/')));
    }
    const folders = [...dirs].filter((dir) => inside(dir) && !dir.split('/').some((name) => name.startsWith('.') || name === 'build')
      && !moving.some((path) => dir === path || dir.startsWith(path + '/'))).sort((a, b) => a.localeCompare(b));
    if (state.into === undefined || !folders.includes(state.into)) {
      const near = dirOf(moving[0] || '');
      state.into = folders.includes(near) ? near : folders[0] || '';
    }
    const select = h('select', { 'aria-label': '移動先のフォルダ' });
    for (const dir of folders) select.append(h('option', { value: dir }, dir || '（作業空間の一番上）'));
    select.value = state.into;
    const go = h('button', { type: 'button', class: 'primary' }, '移動');
    const sync = () => { go.disabled = !folders.length || moving.every((path) => dirOf(path) === state.into); };
    select.addEventListener('change', () => { state.into = select.value; sync(); });
    go.addEventListener('click', () => emit('move', { into: state.into || '.' }));  // 一番上は「.」（空だと引数が渡らない）
    sync();
    box.append(h('ul', { class: 'targets' }, ...moving.map((path) => h('li', {}, path))),
      h('label', { class: 'where' }, '移動先のフォルダ', select),
      folders.length ? '' : h('p', { class: 'muted' }, '移せるフォルダがありません。'),
      h('div', { class: 'actions' }, cancel, go));
    root.replaceChildren(box);
  },
};
