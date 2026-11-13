// 部品「テストを作成の入力」。今までの GUI（gui/static/explorer.js の testDialog）と同じ並び：
// 場所（既定は --dry-run の場所。まだないフォルダーは「（新しいフォルダ）」）と名前を横に、下に「作成するファイル：…」か「… は既にあります。」。
const BAD_NAME = /[<>:"/\|?*\x00-\x1f]/;
const join = (dir, name) => (dir ? dir + '/' + name : name);
const dirOf = (path) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '');

export default {
  render(root, props, { h, emit, state }) {
    const box = h('div', { class: 'file-test' }, h('h2', {}, 'テストを作成'), h('p', { class: 'subject' }, props.path));
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => emit('cancel', {}));
    if (props.error || props.loading || !props.plan) {
      box.append(props.error ? h('p', { role: 'alert' }, props.error) : h('p', { class: 'muted' }, '読み込み中…'), h('div', { class: 'actions' }, cancel));
      return root.replaceChildren(box);
    }
    const suggested = (props.plan.paths || [])[0] || '';
    const defaultFolder = dirOf(suggested), defaultName = suggested.split('/').pop();
    if (state.folder === undefined) { state.folder = defaultFolder; state.name = defaultName; }
    // 場所の候補：テスト用 Project（既定の場所の一番上のフォルダー）の中のフォルダー
    const top = suggested.split('/')[0];
    const dirs = new Set();
    for (const path of props.files) {
      if (!path.startsWith(top + '/')) continue;
      path.split('/').slice(0, -1).forEach((_, i, names) => dirs.add(names.slice(0, i + 1).join('/')));
    }
    const folders = [...dirs].filter((dir) => !dir.split('/').some((name) => name.startsWith('.') || name === 'build')).sort((a, b) => a.localeCompare(b));
    const select = h('select', { 'aria-label': '場所' });
    if (!folders.includes(defaultFolder)) select.append(h('option', { value: defaultFolder }, `${defaultFolder}（新しいフォルダ）`));
    for (const dir of folders) select.append(h('option', { value: dir }, dir));
    select.value = state.folder;
    const input = h('input', { type: 'text', value: state.name, 'aria-label': '名前' });
    const preview = h('p', { class: 'preview' });
    const make = h('button', { type: 'button', class: 'primary' }, '作成');
    const target = () => join(state.folder, state.name.trim());
    const sync = () => {
      const name = state.name.trim();
      const bad = !name || BAD_NAME.test(name) || /[. ]$/.test(name);
      const there = !bad && props.files.includes(target());
      preview.textContent = bad ? (name ? '使用できない文字が含まれています。' : '名前を入力してください。') : there ? `${target()} は既にあります。` : '作成するファイル：' + target();
      preview.classList.toggle('bad', bad || there);
      make.disabled = bad || there;
    };
    const submit = () => { sync(); if (!make.disabled) emit('make', { to: target() === suggested ? '' : target() }); };
    select.addEventListener('change', () => { state.folder = select.value; sync(); });
    input.addEventListener('input', () => { state.name = input.value; sync(); });
    input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); submit(); } });
    make.addEventListener('click', submit);
    sync();
    box.append(h('div', { class: 'where' }, h('label', {}, '場所', select), h('label', { class: 'grow' }, '名前', input)), preview,
      h('div', { class: 'actions' }, cancel, make));
    root.replaceChildren(box);
    if (!state.focused) { state.focused = true; setTimeout(() => input.focus(), 0); }
  },
};
