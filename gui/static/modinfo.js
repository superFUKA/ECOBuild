'use strict';
// Module-wide screen: Projects, dependencies and links, branches, build settings.
// Changes to managed files (ecobuild.toml, CMake files) run in a workspace chosen in the dialog (committed via PR).
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  let view = 'projects', place = '', data = {};
  const KIND = {static_library: 'ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', executable: '実行ファイル', app: '実行ファイル', test: 'テスト', bench: '性能測定'};
  const DEP_STATE = {aligned: ['記録の版', 'ok'], differs: ['記録と別の版', 'warn'], modified: ['未コミットの変更あり', 'warn'], working: ['作業版', ''], missing: ['cloneなし', 'bad']};
  const pill = (text, cls = '') => `<span class="mi-pill ${cls}">${esc(text)}</span>`;
  const head = (title, note, actions = '') => `<div class="mi-head"><div><h3>${title}</h3><p class="mi-note">${note}</p></div><div class="mi-actions">${actions}</div></div>`;
  const btn = (label, action, arg = '', cls = '') => `<button type="button" class="${cls}" data-mi="${action}" data-arg="${esc(arg)}">${label}</button>`;
  const here = () => place || MOD.root;
  const cli = args => ECO.cli(here(), args, {quiet: true});
  const short = sha => sha ? sha.slice(0, 8) : '-';

  // Which place to show (the module's clone, or a dedicated clone / workspace with uncommitted changes).
  function placeSelect() {
    const options = MOD.places.map(p => `<option value="${esc(p)}" ${MOD.keyOf(p) === MOD.keyOf(here()) ? 'selected' : ''}>${esc(MOD.states.get(MOD.keyOf(p))?.branch || p)}${MOD.keyOf(p) === MOD.keyOf(MOD.root) ? '' : '（' + esc(p.split(/[\\/]/).pop()) + '）'}</option>`).join('');
    return `<label class="mi-note" style="display:flex;gap:6px;align-items:center">表示する場所<select id="mi-place">${options}</select></label>`;
  }
  function renderDeps() {
    const deps = data.deps, projects = data.projects || [];
    if (deps.error) return head('依存先', '') + `<p class="mi-note">${esc(deps.error.message)}</p>`;
    return head('依存先', 'このモジュールが使う他のモジュール。リンク・更新・外すは管理ファイルが変わるので、作業空間でコミットしてPRで反映します。',
      btn('手元を記録に合わせる', 'deps-sync') + btn('すべて更新', 'deps-update') + btn('＋ リンク', 'link', '', 'primary')) +
      (deps.length ? `<table class="mi-table"><thead><tr><th>名前</th><th>記録の版</th><th>手元の版</th><th>状態</th><th>使っているProject</th><th></th></tr></thead><tbody>
      ${deps.map(d => { const [label, cls] = DEP_STATE[d.state] || [d.state, ''], users = projects.filter(p => p.links.includes(d.name)).map(p => p.name);
        return `<tr><td><strong>${esc(d.name)}</strong><div class="mi-sub">${esc(d.url)}</div></td><td class="mi-mono">${short(d.recorded)}</td><td class="mi-mono">${short(d.local)}${d.branch ? `<div class="mi-sub">${esc(d.branch)}</div>` : ''}</td><td>${pill(label, cls)}</td><td>${users.map(u => pill(u)).join(' ')}</td>
        <td class="mi-row-actions">${btn('更新', 'deps-update', d.name)}${btn('リンクを外す', 'unlink', d.name, 'danger-text')}</td></tr>`; }).join('')}</tbody></table>` : '<p class="eco-empty">依存先はありません。</p>');
  }
  function renderProjects() {
    const projects = data.projects, deps = Array.isArray(data.deps) ? data.deps : [];
    if (projects.error) return head('Project', '') + `<p class="mi-note">${esc(projects.error.message)}</p>`;
    return head('Project', 'モジュールの中のProject（ライブラリ・実行ファイル・テスト・性能測定）と、そのリンク。追加・削除・PCHは作業空間で行います。', btn('＋ Project', 'project-add', '', 'primary')) +
      (projects.length ? `<table class="mi-table"><thead><tr><th>名前</th><th>種類</th><th>場所</th><th>リンク</th><th></th></tr></thead><tbody>
      ${projects.map(p => `<tr><td><strong>${esc(p.name)}</strong></td><td>${pill(KIND[p.kind] || p.kind)}</td><td class="mi-mono">${esc(p.directory)}/</td><td>${p.links.map(l => pill('→ ' + l, deps.some(d => d.name === l) ? 'dep' : '')).join(' ')}</td>
        <td class="mi-row-actions">${btn('PCH', 'pch', p.name)}${btn('削除', 'project-remove', p.name, 'danger-text')}</td></tr>`).join('')}</tbody></table>
      <p class="mi-note">緑のリンクは依存先（他のモジュール）、灰色はこのモジュールの中のProject。</p>` : '<p class="eco-empty">Projectはありません。</p>');
  }
  function renderProfiles() {
    const p = data.profiles;
    if (p.error) return head('ビルド設定', '') + `<p class="mi-note">${esc(p.error.message)}</p>`;
    const names = Object.keys(p.profiles);
    return head('ビルド設定', '名前付きのビルド設定（構成・静的／共有・並列数）。定義は ecobuild.toml（作業空間で変更）、どれを使うかはこのPCだけの選択です（この場所の ecobuild.local.toml）。', btn('＋ ビルド設定', 'profile-add', '', 'primary')) +
      `<table class="mi-table"><thead><tr><th>このPCで使う</th><th>名前</th><th>構成</th><th>ライブラリ</th><th>並列数</th><th></th></tr></thead><tbody>
      ${names.map(n => { const x = p.profiles[n]; return `<tr><td><input type="radio" name="mi-profile" value="${esc(n)}" ${p.selected === n ? 'checked' : ''} aria-label="${esc(n)} を使う"></td><td><strong>${esc(n)}</strong></td><td>${esc(x.configuration)}</td><td>${x.shared ? '共有' : '静的'}</td><td>${x.parallel}</td>
        <td class="mi-row-actions">${btn('編集', 'profile-add', n)}${btn('削除', 'profile-remove', n, 'danger-text')}</td></tr>`; }).join('')}
      <tr><td><input type="radio" name="mi-profile" value="none" ${!p.selected ? 'checked' : ''} aria-label="使わない"></td><td colspan="5" class="mi-sub">使わない（構成は Debug）</td></tr></tbody></table>`;
  }
  function renderBranches() {
    const branches = data.branches, prs = Array.isArray(data.prs) ? data.prs : [];
    if (branches.error) return head('ブランチ', '') + `<p class="mi-note">${esc(branches.error.message)}</p>`;
    const names = new Set(branches.map(b => b.name));
    const roots = branches.filter(b => !b.base || !names.has(b.base));
    const node = (b, depth) => {
      const kids = branches.filter(c => c.base === b.name && c !== b), where = [b.local && '手元', b.remote && 'GitHub'].filter(Boolean).join('・');
      const pr = prs.find(x => x.head === b.name), n = /^task\/(\d+)$/.exec(b.name)?.[1];
      const actions = b.is_workspace ? (n ? `<button type="button" data-open-ws="${n}">作業空間を開く</button>` : '')
        : (pr ? btn('マージ', 'branch-merge', pr.number) : depth || b.base ? btn('反映するPRを作る', 'branch-submit', b.name) : '') + (depth || b.base ? btn('削除', 'branch-delete', b.name, 'danger-text') : '');
      return `<li><div class="mi-branch ${b.is_workspace ? 'ws' : ''}"><span class="mi-branch-name">${esc(b.name)}</span>${b.is_workspace ? pill('作業空間', 'ok') : pill('ブランチ')}
        <span class="mi-where">${where}</span>${pr ? pill(`PR #${pr.number} → ${pr.base}${pr.draft ? '・下書き' : ''}`, 'pr') : ''}<span class="mi-row-actions">${actions}</span></div>
        ${kids.length ? `<ul>${kids.map(k => node(k, depth + 1)).join('')}</ul>` : ''}</li>`;
    };
    return head('ブランチ', '作成元のつながりで並べた全体像。作業空間（task/〜）はタスクの作業用、それ以外は develop などの共有のブランチです。', btn('＋ ブランチ', 'branch-create', '', 'primary')) +
      `<ul class="mi-tree">${roots.map(b => node(b, 0)).join('')}</ul>`;
  }
  const VIEWS = {deps: renderDeps, projects: renderProjects, profiles: renderProfiles, branches: renderBranches};
  const LOADS = {
    projects: async () => { const [p, d] = await Promise.all([cli(['project', 'list']), cli(['deps', 'list'])]); data.projects = p.ok ? p.result : {error: p.error}; data.deps = d.ok ? d.result : {error: d.error}; },
    deps: async () => LOADS.projects(),
    profiles: async () => { const p = await cli(['profile', 'list']); data.profiles = p.ok ? p.result : {error: p.error}; },
    branches: async () => { const [b, p] = await Promise.all([cli(['branch', 'list']), cli(['pr', 'list'])]); data.branches = b.ok ? b.result : {error: b.error}; data.prs = p.ok ? p.result : []; },
  };
  async function render(reload = true) {
    for (const b of document.querySelectorAll('.mi-tabs [data-mi-view]')) b.setAttribute('aria-selected', String(b.dataset.miView === view));
    const main = el('mi-main');
    if (reload) { main.innerHTML = placeSelect() + ECO.loading(); await LOADS[view](); }
    main.innerHTML = placeSelect() + VIEWS[view]();
  }

  // Dialogs ---------------------------------------------------------------------------------------
  const workspaceField = () => {
    const places = MOD.workspacePlaces();
    const current = places.find(p => MOD.keyOf(p) === MOD.keyOf(here())) || places[0] || '';
    return {name: 'place', label: '変更する作業空間', type: 'select', value: current, options: places.map(p => [p, `${MOD.states.get(MOD.keyOf(p)).branch}（${p}）`]), help: '管理ファイルが変わります。作業空間でコミットし、PRで反映してください。'};
  };
  async function inWorkspace(title, fields, ok, build, {danger = false, intro = '', success} = {}) {
    if (!MOD.workspacePlaces().length) return ECO.dialog({title, body: '<p>管理ファイルを変える操作は作業空間で行います。タスク管理でタスクの「作業を開始」をしてから、もう一度行ってください。</p>'});
    await ECO.form({title, intro, fields: [...fields, workspaceField()], ok, danger, submit: async v => {
      const args = build(v); if (typeof args === 'string') return args;
      const doc = await ECO.run(v.place, args, {success});
      if (!doc) return 'うまくいきませんでした。';
      await MOD.reloadPlace(v.place); place = v.place; render();
    }});
  }
  const ACTIONS = {
    'deps-sync': () => ECO.run(here(), ['deps', 'sync'], {success: r => '依存先を記録の版に合わせました。' + (r?.length ? r.map(x => `${x.name}：${x.action}`).join('、') : ''), confirm: '手元の依存先を記録の版に合わせます。ないものはcloneし、作業版・変更のあるものは触りません。管理ファイルは変わりません。', title: '手元を記録に合わせる'}).then(doc => doc && render()),
    'deps-update': name => inWorkspace(name ? `依存先 ${name} を更新` : '依存先をすべて更新', [], '更新', () => ['deps', 'update', ...(name ? [name] : [])], {intro: '依存先の記録をGitHubの最新にし、手元のcloneと生成ファイルも合わせます。', success: '依存先を更新しました。'}),
    'link': () => inWorkspace('モジュールをリンク', [
      {name: 'repository', label: 'リポジトリ（名前、または 所有者/名前）', required: true},
      {name: 'project', label: 'リンクするProject', type: 'select', options: [['', '既定（ライブラリ）'], ...(Array.isArray(data.projects) ? data.projects.map(p => [p.name, p.name]) : [])]},
      {name: 'shared', label: '共有ライブラリとしてリンクする', type: 'checkbox'}], 'リンク',
      v => ['link', v.repository, ...(v.project ? ['--project', v.project] : []), ...(v.shared ? ['--shared'] : [])], {success: r => `${r.name} をリンクしました（${r.projects.join('、')}）。`}),
    'unlink': name => inWorkspace(`リンクを外す：${name}`, [], '外す', () => ['unlink', name], {danger: true, intro: '依存先のリンクを外します。手元のcloneは、記録の版のままなら消します（作業中・変更ありなら残します）。', success: `${name} のリンクを外しました。`}),
    'project-add': () => inWorkspace('Projectを追加', [
      {name: 'name', label: '名前（ディレクトリ名にもなる）', required: true},
      {name: 'kind', label: '種類', type: 'select', value: 'app', options: [['library', 'ライブラリ'], ['app', '実行ファイル'], ['test', 'テスト'], ['bench', '性能測定']]}], '追加',
      v => ['project', 'add', v.name, '--kind', v.kind], {success: r => `Projectを追加しました：${r.project || ''}`}),
    'project-remove': name => inWorkspace(`Projectを削除：${name}`, [], '削除', () => ['project', 'remove', name], {danger: true, intro: 'Projectを外し、そのディレクトリを削除します。他のProjectからのリンクも外します。', success: `${name} を削除しました。`}),
    'pch': name => inWorkspace(`プリコンパイル済みヘッダー：${name}`, [{name: 'mode', label: 'PCH', type: 'radio', value: 'on', options: [['on', '使う', `include/${name}/pch.h`], ['off', '使わない']]}], '保存',
      v => ['project', 'pch', name, ...(v.mode === 'off' ? ['--off'] : [])], {success: 'PCHの設定を変えました。'}),
    'profile-add': name => {
      const x = name && data.profiles?.profiles?.[name];
      return inWorkspace(name ? `ビルド設定：${name}` : 'ビルド設定を追加', [
        {name: 'name', label: '名前', required: true, value: name || ''},
        {name: 'configuration', label: '構成', type: 'select', value: x?.configuration || 'Debug', options: ['Debug', 'Release', 'RelWithDebInfo', 'MinSizeRel'].map(c => [c, c])},
        {name: 'parallel', label: '並列ビルドの数', type: 'number', min: 1, value: String(x?.parallel || 4)},
        {name: 'shared', label: 'ライブラリ（依存先を含む）を共有ライブラリにする', type: 'checkbox', value: x?.shared}], '保存',
        v => ['profile', 'add', v.name, '--configuration', v.configuration, '--parallel', v.parallel || '1', ...(v.shared ? ['--shared'] : [])], {success: 'ビルド設定を保存しました。'});
    },
    'profile-remove': name => inWorkspace(`ビルド設定を削除：${name}`, [], '削除', () => ['profile', 'remove', name], {danger: true, success: `${name} を削除しました。`}),
    'branch-create': () => ECO.form({title: 'ブランチを作る', intro: '作業空間でないブランチ（develop・release 等）を作り、GitHubへ反映します。', fields: [
      {name: 'name', label: 'ブランチ名（task/ で始まる名前は作業空間専用）', required: true, placeholder: '例：develop'},
      {name: 'base', label: '作成元', type: 'select', options: [['', '既定（default_base）'], ...(Array.isArray(data.branches) ? data.branches.filter(b => !b.is_workspace).map(b => [b.name, b.name]) : [])]}], ok: '作る',
      submit: async v => { if (!await ECO.run(here(), ['branch', 'create', v.name, ...(v.base ? ['--base', v.base] : [])], {success: `ブランチ ${v.name} を作りました。`})) return '作れませんでした。'; render(); }}),
    'branch-submit': name => ECO.form({title: `反映するPRを作る：${name}`, fields: [
      {name: 'into', label: '反映先', type: 'select', options: (Array.isArray(data.branches) ? data.branches.filter(b => !b.is_workspace && b.name !== name) : []).map(b => [b.name, b.name])},
      {name: 'title', label: 'PRのタイトル'}, {name: 'draft', label: '下書きにする', type: 'checkbox'}], ok: '作る',
      submit: async v => { if (!v.into) return '反映先を選んでください。'; if (!await ECO.run(here(), ['branch', 'submit', name, '--into', v.into, ...(v.title ? ['--title', v.title] : []), ...(v.draft ? ['--draft'] : [])], {success: r => `PR #${r.number} を作りました。`})) return '作れませんでした。'; render(); }}),
    'branch-merge': number => ECO.form({title: `ブランチのPR #${number} をマージ`, intro: 'ブランチ同士のPRを、マージコミットでマージします。', fields: [{name: 'ignore', label: 'CIが失敗していてもマージする', type: 'checkbox'}], ok: 'マージ',
      submit: async v => { if (!await ECO.run(here(), ['branch', 'merge', String(number), ...(v.ignore ? ['--ignore-checks'] : [])], {success: `PR #${number} をマージしました。`})) return 'マージできませんでした。'; render(); }}),
    'branch-delete': name => ECO.run(here(), ['branch', 'delete', name], {success: `ブランチ ${name} を削除しました。`}).then(doc => doc && render()),
  };
  el('modinfo-content').addEventListener('click', e => {
    const tab = e.target.closest('[data-mi-view]');
    if (tab) { view = tab.dataset.miView; render(); return; }
    const ws = e.target.closest('[data-open-ws]');
    if (ws) { MOD.openWorkspace(Number(ws.dataset.openWs)); return; }
    const action = e.target.closest('[data-mi]');
    if (action) ACTIONS[action.dataset.mi](action.dataset.arg);
  });
  el('modinfo-content').addEventListener('change', async e => {
    if (e.target.id === 'mi-place') { place = e.target.value; render(); }
    if (e.target.name === 'mi-profile') {
      const doc = await ECO.run(here(), ['profile', 'use', e.target.value], {success: e.target.value === 'none' ? 'ビルド設定を使わないようにしました。' : `このPCでは ${e.target.value} を使います。`});
      render(!doc);
    }
  });
  el('modinfo-content').addEventListener('contextmenu', e => {
    const row = e.target.closest('.mi-table tbody tr, .mi-branch'); if (!row) return;
    const buttons = [...row.querySelectorAll('[data-mi], [data-open-ws]')]; if (!buttons.length) return;
    e.preventDefault();
    ECO.menu(buttons.map(b => [b.textContent, () => b.click(), !b.disabled]), e.clientX, e.clientY);
  });
  pageHooks.modinfo = () => render();
})();
