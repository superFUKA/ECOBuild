// 部品「ビルド設定の表」。今までの GUI（modinfo.js の renderProfiles）と同じ並び・同じ見た目。
// C++ のオプションと Project ごとの上書きは、言葉にして見せる（見せ方）。何ができるかは、押した先のコマンドが決める。
const OPTION_LABEL = { architecture: 'アーキテクチャ', cpp_standard: 'C++', generator: '生成器', toolset: 'ツールセット', c_compiler: 'Cコンパイラ',
  cxx_compiler: 'C++コンパイラ', toolchain_file: 'ツールチェーン', windows_sdk: 'Windows SDK', test_parallel: 'テストの並列数',
  googletest_archive: 'GoogleTestのZIP', type: '形式', artifact_directory: '成果物の置き場所' };
const FORMS = { static: '静的', shared: '共有', interface: 'インターフェース' };
const optionText = (key, value) => {
  if (key === 'test_continue_on_failure') return value ? '' : 'テストの失敗で止める';
  if (key === 'fetch_git') return value ? '' : '依存先を自動でcloneしない';
  return `${OPTION_LABEL[key] || key} ${key === 'type' ? FORMS[value] || value : value}`;
};
const NO_WS = 'タスクブランチの作業空間がありません（タスク管理で「作業を開始」してください）';
const optionsText = (options) => Object.entries(options || {}).map(([key, value]) => optionText(key, value)).filter(Boolean);

export default {
  render(root, props, { h, emit, menu }) {
    // 追加・編集・上書き・削除は ecobuild.toml を変える：タスクブランチの作業空間がなければ灰色と理由（使うものは選べる）
    const spaces = props.workspaces;
    const readOnly = Array.isArray(spaces) && !spaces.some((w) => w.task != null && w.review == null);
    const lock = (button) => { if (readOnly) { button.disabled = true; button.title = NO_WS; } return button; };
    const off = readOnly ? { disabled: true, reason: NO_WS } : {};
    const add = lock(h('button', { type: 'button', class: 'primary' }, '＋ ビルド設定'));
    add.addEventListener('click', () => emit('add', { kind: props.kind || '' }));
    const head = h('div', { class: 'head' }, h('h3', {}, 'ビルド設定'), h('div', { class: 'actions' }, add));
    const top = [];
    if (readOnly) {
      const open = h('button', { type: 'button', class: 'small' }, 'タスク管理を開く');
      open.addEventListener('click', () => emit('open_tasks', {}));
      top.push(h('div', { class: 'banner info' }, h('span', {}, '変更はタスクブランチの作業空間で行います。作業空間がないので、今は見るだけです（このPCで使うビルド設定は選べます）。'), open));
    }
    if (props.error) return root.replaceChildren(...top, head, h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, `読めませんでした：${props.error}`)));
    if (!props.data) return root.replaceChildren(head, h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 読み込み中…'));

    const profiles = props.data.profiles || {};
    const selected = props.data.selected || null;
    const names = Object.keys(profiles);
    const cpp = props.kind === 'cpp';
    const parallel = cpp || props.kind === 'python';
    // 型で変わる列：ライブラリの形と Project ごとの上書きは C++ のもの
    const columns = ['このPCで使う', '名前', '構成', ...(cpp ? ['ライブラリ'] : []), ...(parallel ? ['並列数'] : []), ...(cpp ? ['そのほか・Projectごとの上書き'] : []), ''];
    const radio = (value, label, checked) => {
      const input = h('input', { type: 'radio', name: 'profile', value, checked });
      input.setAttribute('aria-label', label);
      input.addEventListener('change', () => { if (input.checked) emit('use', { name: value, stop: value === 'none' }); });
      return h('td', { class: 'narrow' }, input);
    };
    const link = (text, cls, onClick) => {
      const button = lock(h('button', { type: 'button', class: cls }, text));
      button.addEventListener('click', onClick);
      return button;
    };
    const body = h('tbody', {});
    for (const name of names) {
      const x = profiles[name] || {};
      const row = h('tr', {}, radio(name, `${name} を使う`, selected === name), h('td', {}, h('strong', {}, name)), h('td', {}, String(x.configuration ?? '')));
      if (cpp) row.append(h('td', {}, x.shared ? 'すべて共有' : '静的'));
      if (parallel) row.append(h('td', {}, String(x.parallel ?? '')));
      if (cpp) {
        const cell = h('td', {});
        const extra = optionsText(x.options);
        if (extra.length) cell.append(h('div', { class: 'sub' }, extra.join('・')));
        for (const [project, values] of Object.entries(x.projects || {})) {
          cell.append(h('div', { class: 'override' }, h('span', { class: 'pill' }, project), ` ${optionsText(values).join('・')} `,
            link('変更', 'link', () => emit('project', { name, project })),
            link('外す', 'link danger-text', () => emit('project_clear', { name, project }))));
        }
        row.append(cell);
      }
      const edit = link('編集…', 'small', () => emit('edit', { name, kind: props.kind || '' }));
      const more = h('button', { type: 'button', class: 'small more', title: 'そのほかの操作' }, '⋯');
      more.setAttribute('aria-label', `${name}：そのほかの操作`);
      const others = [...(cpp ? [{ id: 'project', label: 'Projectごとの上書き…', ...off }, { separator: true }] : []),
        { id: 'remove', label: '削除…', danger: true, ...off }];
      const pick = (picked) => {
        if (picked === 'edit') emit('edit', { name, kind: props.kind || '' });
        if (picked === 'project') emit('project', { name, project: '' });
        if (picked === 'remove') emit('remove', { name });
      };
      more.addEventListener('click', async (event) => pick(await menu(event, others)));
      // 行の右クリック：その行のボタン（編集…）と ⋯ の項目
      row.addEventListener('contextmenu', async (event) => {
        event.preventDefault();
        pick(await menu(event, [{ id: 'edit', label: '編集…', ...off }, { separator: true }, ...others]));
      });
      row.append(h('td', { class: 'row-actions' }, edit, more));
      body.append(row);
    }
    body.append(h('tr', {}, radio('none', '使わない', !selected), h('td', { class: 'sub', colSpan: columns.length - 1 }, '使わない（構成は Debug）')));
    const table = h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, ...columns.map((text, index) => h('th', index ? {} : { class: 'narrow' }, text)))), body);
    const out = [...top, head];
    if (!names.length) out.push(h('p', { class: 'empty' }, 'ビルド設定はまだありません。「＋ ビルド設定」で作ると、このPCで使うものを選べます。'));
    out.push(table);
    root.replaceChildren(...out);
  },
};
