// 部品「CI の設定のカード」。今までの GUI の CI の設定（.ci-card）と同じに描く。
export default {
  render(root, props, { h, emit }) {
    const s = props.data;
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    if (!s.path) return root.replaceChildren(h('p', { role: 'status' }, props.loading ? '読み込み中…' : 'CIの設定を読めませんでした。'));
    if (s.supported === false) return root.replaceChildren(h('p', { class: 'note' }, 'このモジュールの型は、CIのワークフローを用意できません。'));
    const state = !s.exists ? ['ワークフローはありません', 'warn'] : s.edited ? ['手で編集されています', 'warn']
      : s.current ? ['今の設定のとおり', 'ok'] : ['今の設定と違います（作り直すと合います）', 'warn'];
    const configurations = s.configurations || [];
    const now = { os: (s.os || []).join(','), configuration: configurations.join(','), shared: s.shared ? 'on' : 'off', branches: (s.branches || []).join(',') };
    const button = (action, label, cls) => {
      const item = h('button', { type: 'button', class: cls }, label);
      item.addEventListener('click', () => emit('action', { action, ...now }));
      return item;
    };
    const actions = h('div', { class: 'actions' }, button('init', s.exists ? '設定を変える…' : 'CIを用意する…', ''));
    if (s.exists) actions.append(button('remove', 'CIをやめる…', 'danger-text'));
    const list = h('dl', { class: 'settings' });
    const row = (name, value) => list.append(h('dt', {}, name), h('dd', {}, value));
    row('OS', s.os ? s.os.join('、') : '型の既定');
    row('構成', configurations.join('、'));
    row('共有ライブラリ', s.shared ? 'その構成でもビルド・テストする' : 'しない');
    row('push で動かすブランチ', s.branches ? s.branches.join('、') : (s.default_base || '') + '（既定）');
    row('提出（PR）・手動', '常に動く');
    root.replaceChildren(h('div', { class: 'ci-card' },
      h('div', { class: 'head' }, h('div', {}, h('strong', {}, s.path), ' ', h('span', { class: 'pill ' + state[1] }, state[0])), actions), list));
  },
};
