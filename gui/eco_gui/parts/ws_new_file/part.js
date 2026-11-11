// 部品「新しいファイルの入力」。今までの GUI（gui/static/explorer.js の newFileDialog）と同じ並び：
// 場所と名前を横に、名前は ＋ でいくつも、下に「作成するファイル：…」。入力中の文字は、窓の中だけの状態。
const BAD_NAME = /[<>:"\\|?*\x00-\x1f]/;
const join = (dir, name) => (dir ? dir + '/' + name : name);

export default {
  render(root, props, { h, emit, state, redraw }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (!state.names) { state.names = ['']; state.folder = props.folder || ''; state.test = true; }
    const dirs = new Set(['']);
    for (const path of props.files) path.split('/').slice(0, -1).forEach((_, i, names) => dirs.add(names.slice(0, i + 1).join('/')));
    if (state.folder) dirs.add(state.folder);
    const folders = [...dirs].filter((dir) => !dir.split('/').some((name) => name.startsWith('.') || name === 'build') || dir === state.folder).sort((a, b) => a.localeCompare(b));

    const plan = () => {
      const names = state.names.map((name) => name.trim()).filter(Boolean);
      if (!names.length) return { error: '' };
      const bad = names.find((name) => BAD_NAME.test(name) || /[. /]$/.test(name) || name.startsWith('/'));
      if (bad) return { error: (names.length > 1 ? `${bad}：` : '') + '使用できない文字が含まれています。' };
      const paths = names.map((name) => join(state.folder, name));
      const twice = paths.find((path, i) => paths.indexOf(path) !== i);
      if (twice) return { error: `${twice} を2回作ろうとしています。名前が重なっていないか確かめてください。` };
      const there = paths.find((path) => props.files.includes(path));
      if (there) return { error: `${there} は既にあります。` };
      return { paths };
    };
    const preview = h('p', { class: 'new-file-preview' });
    const add = h('button', { type: 'button', class: 'primary' }, '作成');
    const sync = () => {
      const made = plan();
      preview.textContent = made.error !== undefined ? made.error : '作成するファイル：' + made.paths.join('、');
      preview.classList.toggle('bad', Boolean(made.error));
      add.disabled = made.error !== undefined;
    };
    const submit = () => { const made = plan(); if (made.paths) emit('add', { paths: made.paths, test: state.test }); };

    const select = h('select', { 'aria-label': '場所' });
    for (const dir of folders) { const option = h('option', { value: dir }, dir || '（ルート）'); option.selected = dir === state.folder; select.append(option); }
    select.addEventListener('change', () => { state.folder = select.value; sync(); });
    const names = h('div', { class: 'names' });
    state.names.forEach((name, i) => {
      const input = h('input', { type: 'text', value: name, placeholder: '例：notes.md（フォルダーごと書くと、フォルダーも作る）', 'aria-label': '名前' });
      input.addEventListener('input', () => { state.names[i] = input.value; sync(); });
      input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); submit(); } });
      const line = h('div', { class: 'name' }, input);
      if (state.names.length > 1) {
        const remove = h('button', { type: 'button', class: 'quiet', title: 'この名前を外す', 'aria-label': 'この名前を外す' }, '×');
        remove.addEventListener('click', () => { state.names.splice(i, 1); redraw(); });
        line.append(remove);
      }
      if (i === state.names.length - 1) {
        const more = h('button', { type: 'button', title: '名前をもう1つ足す', 'aria-label': '名前をもう1つ足す' }, '＋');
        more.addEventListener('click', () => { state.names.push(''); state.focus = true; redraw(); });
        line.append(more);
        if (state.focus || state.names.length === 1) setTimeout(() => input.focus(), 0);
        state.focus = false;
      }
      names.append(line);
    });
    const test = h('input', { type: 'checkbox' });
    test.checked = state.test;
    test.addEventListener('change', () => { state.test = test.checked; });
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => emit('cancel', {}));
    add.addEventListener('click', submit);
    sync();
    root.replaceChildren(h('div', { class: 'new-file' },
      h('h2', {}, '新しいファイル'),
      h('div', { class: 'where' }, h('label', {}, '場所', select), h('label', { class: 'grow' }, '名前', names)),
      h('label', { class: 'check' }, test, ' 対応するテストも作成する（ライブラリのヘッダー・ソース、src/<パッケージ>/ のソースのとき）'),
      preview,
      h('div', { class: 'actions' }, cancel, add)));
  },
};
