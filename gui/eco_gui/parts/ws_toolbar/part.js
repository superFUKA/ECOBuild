// 部品「作業空間のツールバー」。今までの GUI（workspace.html の .build-bar・build.js・workspace.js の renderSync）と同じ並び。
// 左：構成・ビルド設定（▾ で2段のメニュー・✓）、ビルド（▾）、テスト（▾）、▶ 実行。右：取り込む（▾）、アカウント、コンテナ。
const ICONS = {
  down: '<path d="M6 9l6 6 6-6"/>',
  build: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
  test: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3"/><path d="M7.5 15h9"/>',
  sync: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  account: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  container: '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
};
const ROLES = { admin: '管理者', maintain: '管理', write: '書き込み', triage: '整理', read: '読み取り' };

export default {
  render(root, props, { h, emit, menu, memory, state }) {
    const svg = (name, size = 15, width = 2) => {
      const box = h('span', { class: 'icon', 'aria-hidden': 'true' });
      box.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
      return box;
    };
    const down = () => svg('down', 14, 2.6);
    const under = (element) => { const r = element.getBoundingClientRect(); return { clientX: r.left, clientY: r.bottom + 4 }; };
    const act = (name, more = {}) => emit('action', { name, ...more });
    const s = props.status || {}, remote = props.remote || {};

    // 構成・ビルド設定
    const profiles = (props.profiles && props.profiles.profiles) || {}, used = (props.profiles && props.profiles.selected) || '';
    const chosen = props.configuration || '';
    const shown = chosen || (profiles[used] && profiles[used].configuration) || 'Debug';
    const config = h('button', { type: 'button', class: 'config-button', 'aria-haspopup': 'menu', 'aria-label': '構成・ビルド設定', 'data-tip': '構成・ビルド設定' },
      h('span', {}, shown + (used ? ` · ${used}` : '')), down());
    config.addEventListener('click', async () => {
      const mark = (on) => (on ? '✓ ' : '　');
      const names = ['Debug', 'Release', ...(props.module_type === 'cpp' ? ['RelWithDebInfo', 'MinSizeRel'] : [])];
      const id = await menu(under(config), [
        { heading: '構成' },
        { id: 'c:', label: mark(!chosen) + 'ビルド設定のまま' },
        ...names.map((name) => ({ id: 'c:' + name, label: mark(chosen === name) + name })),
        { separator: true }, { heading: 'ビルド設定（このPCで使う）' },
        { id: 'p:none', label: mark(!used) + '（使わない）' },
        ...Object.keys(profiles).map((name) => ({ id: 'p:' + name, label: mark(used === name) + name, hint: profiles[name].configuration || '' })),
        { separator: true }, { id: 'settings', label: 'ビルド設定を足す・試験を選ぶ…' },
      ]);
      if (id === 'settings') act('build_settings');
      else if (id && id.startsWith('c:')) act('configuration', { value: id.slice(2) });
      else if (id) act('profile', { value: id.slice(2) });
    });

    // ビルド・テスト（ボタンと ▾ をつなげる）
    const group = (label, name, icon, tip, items) => {
      const main = h('button', { type: 'button', class: 'tool-button', 'aria-label': label, 'data-tip': tip }, svg(icon));
      main.addEventListener('click', () => act(name));
      const more = h('button', { type: 'button', class: 'group-menu', 'aria-haspopup': 'menu', 'aria-label': `${label}のその他の操作`, 'data-tip': `${label}の操作` }, down());
      more.addEventListener('click', async () => {
        const id = await menu(under(more), items());
        if (id === 'test_failed') act(id, { tests: failedTests });
        else if (id) act(id);
      });
      return h('span', { class: 'build-group', role: 'group', 'aria-label': label }, main, more);
    };
    const build = group('ビルド', 'build', 'build', 'ビルド', () => [
      { id: 'build', label: 'ビルド' }, { id: 'rebuild', label: 'リビルド' }, { id: 'clean', label: 'クリーン' }, { separator: true },
      { id: 'check', label: '提出前の確認（生成ファイル・ビルド・テスト）' }]);
    const failedTests = ((props.last_test && props.last_test.cases) || []).filter((c) => !['passed', 'skipped'].includes(c.status)).map((c) => c.name);
    const failed = failedTests.length;
    const test = group('テスト', 'test', 'test', 'テスト（すべて）', () => [
      { id: 'test', label: 'すべてのテスト' },
      { id: 'test_failed', label: failed ? `失敗したテストだけ再実行（${failed} 件）` : '失敗したテストだけ再実行', disabled: failed === 0, reason: 'この画面で流したテストに、失敗したものはありません' },
      { id: 'test_pick', label: 'テストを選んで実行…' }]);
    const runIcon = h('span', { class: 'icon', 'aria-hidden': 'true' });
    runIcon.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24"><path d="M6 3.5l15 8.5-15 8.5z" fill="currentColor" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/></svg>';
    const run = h('button', { type: 'button', class: 'run-button', 'aria-label': '実行', 'data-tip': '実行' }, runIcon);
    run.addEventListener('click', () => act('run'));

    // 取り込む（提出の確認中は、取り込むものがないので出さない）
    const right = h('div', { class: 'bar-right' });
    if (!s.reviewing && ('branch' in s || 'task' in s)) {
      const behind = remote.base_behind || s.base_behind || s.behind || 0, clashes = (remote.base_conflicts || []).length;
      const label = h('span', { class: 'sync-label' });
      if (s.task && s.base) { label.append(s.base); if (s.base_at) label.append(' ', h('span', { class: 'sync-version' }, s.base_at.slice(0, 7))); } else label.append('取り込む');
      const stopped = '止まっている操作を、帯の「続ける」か「やめる」で終えてから取り込めます';
      const tip = s.merging ? stopped
        : (s.task ? `作成元 ${s.base || ''} の ${(s.base_at || '?').slice(0, 7)} まで取り込んでいます。押すと、取り込むバージョンを選べます` : 'GitHub の最新を取り込む')
          + (behind ? `（新しいコミット ${behind} 件${clashes ? `・取り込むと衝突するファイル ${clashes} 件：${remote.base_conflicts.join('、')}` : ''}）` : '');
      const main = h('button', { type: 'button', class: 'vs-button sync-button', 'data-tip': tip }, svg('sync'), label);
      if (behind) main.append(h('span', { class: 'sync-count' }, String(behind)));
      if (s.merging) main.disabled = true;
      main.addEventListener('click', () => act(s.task ? 'sync_pick' : 'sync'));
      const more = h('button', { type: 'button', class: 'vs-more', 'aria-haspopup': 'menu', 'aria-label': '取り込みのその他の操作', 'data-tip': 'ほかのブランチから取り込む・GitHub の最新を確認' }, down());
      more.addEventListener('click', async () => {
        const id = await menu(under(more), [
          { id: 'sync', label: '最新を取り込む', disabled: Boolean(s.merging), reason: stopped },
          { id: 'sync_pick', label: 'バージョン・ブランチを選んで取り込む…', disabled: !s.task || Boolean(s.merging), reason: s.merging ? stopped : 'タスクブランチでだけ選べます' },
          { separator: true }, { id: 'fetch', label: 'GitHub の最新を確認' },
        ]);
        if (id) act(id);
      });
      right.append(h('span', { class: 'vs-group sync-group' + (behind ? ' due' : '') + (clashes ? ' bad' : ''), role: 'group', 'aria-label': '取り込み' }, main, more));
    }

    // フォルダーを開く・Visual Studio で開く（▾ は、使う版を選ぶだけ。選んだ版は、この PC に覚える）
    const folder = h('button', { type: 'button', class: 'tool-button', 'aria-label': 'フォルダーを開く', 'data-tip': 'この作業空間のフォルダーを、エクスプローラーで開きます' }, svg('folder'));
    folder.addEventListener('click', () => act('open_folder'));
    right.append(folder);
    const STUDIOS = [['2026', 'Visual Studio 2026'], ['2022', 'Visual Studio 2022']];
    const usable = (version) => (props['vs' + version] || {}).can !== false;
    const version = memory.get('vs', '2026');
    if (props.vs_version !== version && state.told !== version) { state.told = version; act('vs_version', { value: version }); }  // ファイルを開くときも、この版で
    const openVs = h('button', { type: 'button', class: 'vs-button', 'data-tip': usable(version)
      ? `この作業空間を Visual Studio ${version} で開きます（ビルドで作られたソリューション。なければフォルダーとして）`
      : (props['vs' + version] || {}).reason || `Visual Studio ${version} が、この PC にありません` }, `VS${version}`);
    openVs.addEventListener('click', () => act('open_vs', { value: version }));
    const chooseVs = h('button', { type: 'button', class: 'vs-more', 'aria-haspopup': 'menu', 'aria-label': '開く Visual Studio の版を選ぶ', 'data-tip': '開く Visual Studio の版を選ぶ' }, down());
    chooseVs.addEventListener('click', async () => {
      const id = await menu(under(chooseVs), STUDIOS.map(([v, name]) => ({ id: v, label: (v === version ? '✓ ' : '　') + name + (usable(v) ? '' : '（このPCにありません）'),
        disabled: !usable(v), reason: (props['vs' + v] || {}).reason || '' })));
      if (id) { memory.set('vs', id); state.told = id; act('vs_version', { value: id }); }
    });
    right.append(h('span', { class: 'vs-group editor-group', role: 'group', 'aria-label': 'エディター' }, openVs, chooseVs));

    // アカウント・コンテナ
    const account = props.account || {};
    if (account.login) {
      const bound = account.workspace_account, role = ROLES[account.role] || account.role || '';
      const button = h('button', { type: 'button', class: 'tool-button container-button account-button' + (bound ? ' on' : ''),
        'data-tip': (bound ? `${bound}（この作業空間だけ）` : `${account.login}（gh の使用中）`) + (role ? `・役割：${role}` : '') }, svg('account'), h('span', {}, account.login));
      button.addEventListener('click', () => act('account'));
      right.append(button);
    }
    const box = props.container || {};
    if ('container' in box) {
      const tip = box.container ? `この作業空間はコンテナです（${box.state === 'running' ? '動いています' : box.state === 'stopped' ? '止まっています' : 'まだ作っていません'}）${box.image ? '・' + box.image : ''}`
        : box.docker_ready === false ? `Docker が使えません（${box.docker_detail || ''}）` : 'この作業空間は、この PC でビルド・実行します';
      const button = h('button', { type: 'button', class: 'tool-button container-button' + (box.container ? ' on' : ''), 'data-tip': tip }, svg('container'),
        h('span', {}, box.container ? 'コンテナ' : 'このPC'));
      button.addEventListener('click', () => act('container'));
      right.append(button);
    }

    // エージェント（この作業空間のエージェントの画面を開く）
    const agent = h('button', { type: 'button', class: 'vs-button agent-button', 'data-tip': 'この作業空間のエージェント（起動・会話・設定）の画面を開きます' }, 'エージェント');
    agent.addEventListener('click', () => act('agents'));
    right.append(h('span', { class: 'agent-group', role: 'group', 'aria-label': 'AI' }, agent));

    root.replaceChildren(h('div', { class: 'build-bar', role: 'toolbar', 'aria-label': 'ビルド・テスト・実行' },
      h('div', { class: 'bar-left' }, config, h('span', { class: 'bar-separator', 'aria-hidden': 'true' }), build, test),
      h('div', { class: 'bar-center' }, h('span', { class: 'run-group', role: 'group', 'aria-label': '実行' }, run)), right));
  },
};
