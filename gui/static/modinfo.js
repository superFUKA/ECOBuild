'use strict';
// Module-wide screen: overview (module show), Projects, dependencies and links (deps tree), branches, build settings.
// Changes to managed files (ecobuild.toml, CMake files) run in a workspace chosen in the dialog (committed via PR).
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  let view = 'overview', place = '', data = {};
  const KIND = {static_library: 'ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', executable: '実行ファイル', app: '実行ファイル', test: 'テスト', bench: '性能測定'};
  // deps list --fetch: what changed on GitHub (outside ECOBuild).
  const DEP_REMOTE = {ok: ['GitHubにある', 'ok'], archived: ['アーカイブ済み（更新されない）', 'warn'], moved: ['名前が変わった', 'warn'], gone: ['GitHubにない', 'bad'], unknown: ['確認できない', '']};
  let depsFetched = false;
  const DEP_STATE = {aligned: ['記録の版', 'ok'], differs: ['記録と別の版', 'warn'], modified: ['未コミットの変更あり', 'warn'], working: ['作業版', ''], missing: ['cloneなし', 'bad']};
  const pill = (text, cls = '') => `<span class="mi-pill ${cls}">${esc(text)}</span>`;
  const head = (title, note, actions = '') => `<div class="mi-head"><div><h3>${title}</h3><p class="mi-note">${note}</p></div><div class="mi-actions">${actions}</div></div>`;
  const btn = (label, action, arg = '', cls = '') => `<button type="button" class="${cls}" data-mi="${action}" data-arg="${esc(arg)}">${label}</button>`;
  const here = () => place || MOD.root;
  const cli = args => ECO.cli(here(), args, {quiet: true});
  const short = sha => sha ? sha.slice(0, 8) : '-';
  // The modules on GitHub (ecobuild module list) to choose from when linking, except this one and the ones linked already.
  let modulesOnGithub = null;
  async function githubModules() {
    if (!modulesOnGithub) { const doc = await ECO.cli(null, ['module', 'list'], {quiet: true}); modulesOnGithub = doc.ok ? doc.result : []; }
    const linked = new Set((Array.isArray(data.deps) ? data.deps : []).map(d => d.name.toLowerCase()));
    return modulesOnGithub.filter(g => { const name = g.repository.split('/').pop().toLowerCase(); return name !== MOD.name?.toLowerCase() && !linked.has(name); })
      .map(g => [g.repository, g.description || g.type]);
  }

  // Which place to show (the module's clone, or a dedicated clone / workspace with uncommitted changes).
  function placeSelect() {
    const options = MOD.places.map(p => `<option value="${esc(p)}" ${MOD.keyOf(p) === MOD.keyOf(here()) ? 'selected' : ''}>${esc(MOD.states.get(MOD.keyOf(p))?.branch || p)}${MOD.keyOf(p) === MOD.keyOf(MOD.root) ? '' : '（' + esc(p.split(/[\\/]/).pop()) + '）'}</option>`).join('');
    if (MOD.places.length < 2) return '';   // only the module's clone: nothing to choose
    return `<div class="mi-place"><label class="mi-note">表示する場所<select id="mi-place">${options}</select></label></div>`;
  }
  // 概要: ecobuild module show.
  function renderOverview() {
    const r = data.info;
    if (r.error) return head('概要', '') + `<p class="mi-note">${esc(r.error.message)}</p>`;
    const visibility = r.private === true ? pill('非公開') : r.private === false ? pill('公開') : '';
    const archived = r.archived ? pill('アーカイブ済み（読み取り専用）', 'warn') : '';
    const row = (label, value) => `<tr><th scope="row">${label}</th><td>${value}</td></tr>`;
    return head(`${esc(r.name)}`, '型・場所・GitHubのリポジトリ・Project・依存先', '') +
      `<table class="mi-table mi-overview"><tbody>
      ${row('型', pill(r.type))}
      ${row('場所', `<span class="mi-mono">${esc(r.root)}</span>`)}
      ${row('GitHubのリポジトリ', r.repository || r.url ? `${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.repository || r.url)}</a>` : esc(r.repository)} ${visibility} ${archived}` : '<span class="mi-sub">不明</span>')}
      ${row('作業空間の作成元', `<span class="mi-mono">${esc(r.default_base)}</span>`)}
      ${row('Project', r.projects.length ? r.projects.map(p => pill(p)).join(' ') : '<span class="mi-sub">なし</span>')}
      ${row('依存先', r.dependencies.length ? r.dependencies.map(d => pill(d, 'dep')).join(' ') + ` <button type="button" class="mi-link" data-mi-view="deps">依存関係の図</button>` : '<span class="mi-sub">なし</span>')}
      </tbody></table>${data.infoNotices?.length ? `<p class="mi-note">${data.infoNotices.map(esc).join('<br>')}</p>` : ''}`;
  }
  // The dependency graph (ecobuild deps tree): the dependencies of the dependencies too; one seen again is not expanded.
  function renderTree() {
    const t = data.tree;
    if (!t) return '';
    if (t.error) return `<h4 class="mi-subhead">依存関係の図</h4><p class="mi-note">${esc(t.error.message)}</p>`;
    if (!t.direct.length) return '';
    const nodes = new Map(t.nodes.map(n => [n.name, n])), shown = new Set();
    const walk = names => `<ul>${names.map(name => {
      const n = nodes.get(name) || {name, revision: '', present: false, depends_on: []};
      const again = shown.has(name) && n.depends_on.length; shown.add(name);
      const note = !n.present ? pill('cloneなし（その先は不明）', 'bad') : again ? pill('上に同じ') : '';
      return `<li><div class="mi-branch"><span class="mi-branch-name">${esc(name)}</span><span class="mi-mono mi-sub">${short(n.revision)}</span>${note}</div>${!again && n.depends_on.length ? walk(n.depends_on) : ''}</li>`;
    }).join('')}</ul>`;
    return `<h4 class="mi-subhead">依存関係の図</h4><p class="mi-note">依存先の依存先も含めた全体です。2回目以降に出てくるものは、その先を省きます。</p>
      <ul class="mi-tree"><li><div class="mi-branch ws"><span class="mi-branch-name">${esc(t.module)}</span>${pill('このモジュール', 'ok')}</div>${walk(t.direct)}</li></ul>`;
  }
  function renderDeps() {
    const deps = data.deps, projects = data.projects || [];
    if (deps.error) return head('依存先', '') + `<p class="mi-note">${esc(deps.error.message)}</p>`;
    return head('依存先', 'このモジュールが使う他のモジュールです。リンク・更新・リンク解除は管理ファイルを変更するため、作業空間でコミットし、PRで反映します。',
      btn(depsFetched ? 'GitHubをもう一度確認' : 'GitHubと照らし合わせる', 'deps-fetch') + btn('手元を記録に合わせる', 'deps-sync') + btn('すべて更新', 'deps-update') + btn('＋ リンク', 'link', '', 'primary')) +
      (deps.length ? `<table class="mi-table"><thead><tr><th>名前</th><th>記録の版</th><th>手元の版</th><th>状態</th>${depsFetched ? '<th>GitHub</th>' : ''}<th>使っているProject</th><th></th></tr></thead><tbody>
      ${deps.map(d => { const [label, cls] = DEP_STATE[d.state] || [d.state, ''], users = projects.filter(p => p.links.includes(d.name)).map(p => p.name);
        return `<tr><td><strong>${esc(d.name)}</strong><div class="mi-sub">${esc(d.url)}</div></td><td class="mi-mono">${short(d.recorded)}</td><td class="mi-mono">${short(d.local)}${d.branch ? `<div class="mi-sub">${esc(d.branch)}</div>` : ''}</td><td>${pill(label, cls)}</td>${depsFetched ? `<td>${remoteCell(d)}</td>` : ''}<td>${users.map(u => pill(u)).join(' ')}</td>
        <td class="mi-row-actions">${btn('更新', 'deps-update', d.name)}${btn('リンクを外す', 'unlink', d.name, 'danger-text')}</td></tr>`; }).join('')}</tbody></table>` + renderTree() : '<p class="eco-empty">依存先はありません。</p>');
  }
  function remoteCell(d) {
    if (!d.remote) return '';
    const [label, cls] = DEP_REMOTE[d.remote] || [d.remote, ''];
    const notes = [];
    if (d.remote === 'moved') notes.push(`現在の名前は ${esc(d.moved_to)}（GitHubの転送で取得できます）`);
    if (d.remote === 'gone') notes.push('このモジュールを新しくcloneすると、この依存先を取得できません');
    if (d.latest && d.latest !== d.recorded) notes.push(`新しい版 <span class="mi-mono">${short(d.latest)}</span> があります（「更新」で記録を更新できます）`);
    return pill(label, cls) + notes.map(n => `<div class="mi-sub">${n}</div>`).join('');
  }
  function renderProjects() {
    const projects = data.projects, deps = Array.isArray(data.deps) ? data.deps : [];
    if (projects.error) return head('Project', '') + `<p class="mi-note">${esc(projects.error.message)}</p>`;
    const settings = data.settings, main = settings?.main_project;
    return head('Project', 'モジュール内のProject（ライブラリ・実行ファイル・テスト・性能測定）とそのリンクです。設定の変更は作業空間で行います（管理ファイルが変わるので、コミットしてPRで反映します）。',
      (settings ? btn('モジュールの設定', 'module-settings') : '') + btn('＋ Project', 'project-add', '', 'primary')) +
      (projects.length ? `<table class="mi-table"><thead><tr><th>名前</th><th>種類</th><th>場所</th><th>リンク</th><th></th></tr></thead><tbody>
      ${projects.map(p => `<tr><td><strong>${esc(p.name)}</strong>${p.name === main ? ' ' + pill('main', 'ok') : ''}</td><td>${pill(KIND[p.kind] || p.kind)}</td><td class="mi-mono">${esc(p.directory)}/</td><td>${p.links.map(l => pill('→ ' + l, deps.some(d => d.name === l) ? 'dep' : '')).join(' ')}</td>
        <td class="mi-row-actions">${btn('設定', 'project-settings', p.name)}${btn('リンク', 'project-link', p.name)}${btn('PCH', 'pch', p.name)}${btn('移動', 'project-move', p.name)}${btn('削除', 'project-remove', p.name, 'danger-text')}</td></tr>`).join('')}</tbody></table>
      <p class="mi-note">緑のリンクは依存先（他のモジュール）、灰色はこのモジュール内のProjectです。main は他のモジュールからリンクされるProjectです。CMakeのパッケージ等のリンクは「設定」で見られます。</p>` : '<p class="eco-empty">Projectはありません。</p>') +
      renderTemplates();
  }
  // File templates (template list): what ecobuild file add makes a new file from.
  function renderTemplates() {
    const templates = data.settings?.templates;
    if (!templates) return '';
    return `<h4 class="mi-subhead">ファイルテンプレート</h4><div class="mi-head"><p class="mi-note">新しいファイルを作るときの元になる内容です。{{header}}・{{name}}・{{suite}}・{{project}} は作るときに置き換わります。ECOBuildの既定のもの（header・source 等）は同じ名前で登録すると差し替えられます。</p><div class="mi-actions">${btn('＋ テンプレート', 'template-add')}</div></div>
      <table class="mi-table"><thead><tr><th>名前</th><th>ファイル</th><th></th></tr></thead><tbody>
      ${Object.entries(templates).map(([name, t]) => `<tr><td><strong>${esc(name)}</strong>${t.builtin ? ' ' + pill('既定') : ''}</td><td class="mi-mono">${esc(t.path)}</td><td class="mi-row-actions">${btn('差し替え', 'template-add', name)}${t.builtin ? '' : btn('削除', 'template-remove', name, 'danger-text')}</td></tr>`).join('')}</tbody></table>`;
  }
  // The C++ options of a build setting and its overrides for Projects, in words.
  const OPTION_LABEL = {architecture: 'アーキテクチャ', cpp_standard: 'C++', generator: '生成器', toolset: 'ツールセット', c_compiler: 'Cコンパイラ', cxx_compiler: 'C++コンパイラ',
    toolchain_file: 'ツールチェーン', test_parallel: 'テストの並列数', googletest_archive: 'GoogleTestのZIP', type: '形式', artifact_directory: '成果物の置き場所'};
  const optionText = (key, value) => key === 'test_continue_on_failure' ? (value ? '' : 'テストの失敗で止める') : key === 'fetch_git' ? (value ? '' : '依存先を自動でcloneしない')
    : `${OPTION_LABEL[key] || key} ${key === 'type' ? {static: '静的', shared: '共有', interface: 'インターフェース'}[value] || value : value}`;
  const optionsText = options => Object.entries(options || {}).map(([k, v]) => optionText(k, v)).filter(Boolean);
  function renderProfiles() {
    const p = data.profiles;
    if (p.error) return head('ビルド設定', '') + `<p class="mi-note">${esc(p.error.message)}</p>`;
    const names = Object.keys(p.profiles);
    return head('ビルド設定', '名前付きのビルド設定（構成・静的／共有・並列数・C++の規格・コンパイラ等）と、Projectごとの上書きです。定義は ecobuild.toml にあり、作業空間で変更します。どれを使うかはこのPCだけの設定です（この場所の ecobuild.local.toml）。', btn('＋ ビルド設定', 'profile-add', '', 'primary')) +
      `<table class="mi-table"><thead><tr><th>このPCで使う</th><th>名前</th><th>構成</th><th>ライブラリ</th><th>並列数</th><th>そのほか・Projectごとの上書き</th><th></th></tr></thead><tbody>
      ${names.map(n => { const x = p.profiles[n], extra = optionsText(x.options), overrides = Object.entries(x.projects || {});
        return `<tr><td><input type="radio" name="mi-profile" value="${esc(n)}" ${p.selected === n ? 'checked' : ''} aria-label="${esc(n)} を使う"></td><td><strong>${esc(n)}</strong></td><td>${esc(x.configuration)}</td><td>${x.shared ? 'すべて共有' : '静的'}</td><td>${x.parallel}</td>
        <td>${extra.length ? `<div class="mi-sub">${extra.map(esc).join('・')}</div>` : ''}${overrides.map(([project, values]) => `<div>${pill(project)} ${esc(optionsText(values).join('・'))} ${btn('変更', 'profile-project', n + '\n' + project, 'mi-link')}${btn('外す', 'profile-project-clear', n + '\n' + project, 'mi-link danger-text')}</div>`).join('')}</td>
        <td class="mi-row-actions">${btn('編集', 'profile-add', n)}${btn('Projectごとの上書き', 'profile-project', n + '\n')}${btn('削除', 'profile-remove', n, 'danger-text')}</td></tr>`; }).join('')}
      <tr><td><input type="radio" name="mi-profile" value="none" ${!p.selected ? 'checked' : ''} aria-label="使わない"></td><td colspan="6" class="mi-sub">使わない（構成は Debug）</td></tr></tbody></table>`;
  }
  function renderBranches() {
    const branches = data.branches;
    if (branches.error) return head('ブランチ', '') + `<p class="mi-note">${esc(branches.error.message)}</p>`;
    const names = new Set(branches.map(b => b.name));
    const roots = branches.filter(b => !b.base || !names.has(b.base));
    const node = (b, depth) => {
      const kids = branches.filter(c => c.base === b.name && c !== b), where = [b.local && '手元', b.remote && 'GitHub'].filter(Boolean).join('・');
      const pr = b.submission, n = /^task\/(\d+)$/.exec(b.name)?.[1];
      const actions = b.is_workspace ? (n ? `<button type="button" data-open-ws="${n}">作業空間を開く</button>` : '')
        : (pr ? btn('取り込む', 'branch-merge', b.name) : depth || b.base ? btn('提出する', 'branch-submit', b.name) : '') + (depth || b.base ? btn('削除', 'branch-delete', b.name, 'danger-text') : '');
      return `<li><div class="mi-branch ${b.is_workspace ? 'ws' : ''}"><span class="mi-branch-name">${esc(b.name)}</span>${b.is_workspace ? pill('作業空間', 'ok') : pill('ブランチ')}
        <span class="mi-where">${where}</span>${pr ? pill(`${pr.draft ? '下書きの' : ''}${pr.partial ? '中間' : ''}提出 → ${b.submitted_to}`, 'pr') : ''}<span class="mi-row-actions">${actions}</span></div>
        ${kids.length ? `<ul>${kids.map(k => node(k, depth + 1)).join('')}</ul>` : ''}</li>`;
    };
    return head('ブランチ', '作成元のつながりで並べたブランチの全体像です。作業空間（task/〜）はタスクの作業用、それ以外は develop などの共有ブランチです。', btn('履歴をTortoiseGitで見る', 'branch-log') + btn('＋ ブランチ', 'branch-create', '', 'primary')) +
      `<ul class="mi-tree">${roots.map(b => node(b, 0)).join('')}</ul>`;
  }
  const VIEWS = {overview: renderOverview, deps: renderDeps, projects: renderProjects, profiles: renderProfiles, branches: renderBranches};
  const LOADS = {
    projects: async () => {
      const [p, d, m] = await Promise.all([cli(['project', 'list']), cli(['deps', 'list', ...(depsFetched ? ['--fetch'] : [])]), cli(['module', 'settings'])]);
      data.projects = p.ok ? p.result : {error: p.error}; data.deps = d.ok ? d.result : {error: d.error}; data.settings = m.ok ? m.result : null;
    },
    overview: async () => { const r = await cli(['module', 'show']); data.info = r.ok ? r.result : {error: r.error}; data.infoNotices = r.notices || []; },
    deps: async () => { const [, t] = await Promise.all([LOADS.projects(), cli(['deps', 'tree'])]); data.tree = t.ok ? t.result : {error: t.error}; },
    profiles: async () => { const p = await cli(['profile', 'list']); data.profiles = p.ok ? p.result : {error: p.error}; },
    branches: async () => { const b = await cli(['branch', 'list']); data.branches = b.ok ? b.result : {error: b.error}; },
  };
  let rendering = 0;
  // A tab read once is shown again as it was when switching back (the 更新 button, a change made here or another place
  // shown reads it again).
  const loaded = new Set(), loadKey = () => view + '|' + MOD.keyOf(here());
  const show = () => render(!loaded.has(loadKey()));
  async function render(reload = true) {
    for (const b of document.querySelectorAll('.mi-tabs [data-mi-view]')) b.setAttribute('aria-selected', String(b.dataset.miView === view));
    const main = el('mi-main'), mine = ++rendering, shown = view;
    if (reload) { const key = loadKey(); main.innerHTML = placeSelect() + ECO.loading(); await LOADS[shown](); loaded.add(key); }
    if (mine !== rendering) return;   // another tab was chosen while loading: that render shows it
    main.innerHTML = placeSelect() + VIEWS[shown]();
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
      // build may give several commands (run in order; the success message after the last).
      const commands = Array.isArray(args[0]) ? args : [args];
      for (const [i, command] of commands.entries()) {
        if (!await ECO.run(v.place, command, i === commands.length - 1 ? {success} : {})) { if (i) { await MOD.reloadPlace(v.place); place = v.place; render(); } return '失敗しました。'; }
      }
      await MOD.reloadPlace(v.place); place = v.place; render();
    }});
  }
  // project show of a Project in the place shown.
  async function details(name) {
    const doc = await cli(['project', 'show', name]);
    if (!doc.ok) { ECO.showError(doc); return null; }
    return doc.result;
  }
  const CONFIGURATIONS = ['Debug', 'Release', 'RelWithDebInfo', 'MinSizeRel'];
  const ACTIONS = {
    'deps-fetch': () => { depsFetched = true; view = 'deps'; return render(); },
    'deps-sync': () => ECO.run(here(), ['deps', 'sync'], {success: r => '依存先を記録の版に合わせました。' + (r?.length ? r.map(x => `${x.name}：${x.action}`).join('、') : ''), confirm: '手元の依存先を記録の版に合わせます。手元にないものはcloneし、作業版や変更のあるものはそのままにします。管理ファイルは変更しません。', title: '手元を記録に合わせる'}).then(doc => doc && render()),
    'deps-update': name => inWorkspace(name ? `依存先 ${name} を更新` : '依存先をすべて更新', [], '更新', () => ['deps', 'update', ...(name ? [name] : [])], {intro: '依存先の記録をGitHubの最新に更新し、手元のcloneと生成ファイルも合わせます。', success: '依存先を更新しました。'}),
    'link': async () => inWorkspace('モジュールをリンク', [
      {name: 'repository', label: 'リポジトリ（名前、または 所有者/名前）', required: true, more: githubModules()},
      {name: 'project', label: 'リンクするProject', type: 'select', options: [['', '既定（テスト用を除いて1つならそれ）'], ...(Array.isArray(data.projects) ? data.projects.filter(p => p.kind !== 'test').map(p => [p.name, `${p.name}（${KIND[p.kind] || p.kind}）`]) : [])],
        help: 'リンクされるのは、相手のモジュールで最初に作ったProjectです（ライブラリである必要があります）。'},
      {name: 'shared', label: '共有ライブラリとしてリンクする', type: 'checkbox'}], 'リンク',
      v => ['deps', 'add', v.repository, ...(v.project ? ['--project', v.project] : []), ...(v.shared ? ['--shared'] : [])], {success: r => `${r.name} をリンクしました（${r.projects.join('、')}）。`}),
    'unlink': name => inWorkspace(`リンクを外す：${name}`, [], '外す', () => ['deps', 'remove', name], {danger: true, intro: '依存先のリンクを外します。手元のcloneは、記録の版のままなら削除します（作業中や変更がある場合は残します）。', success: `${name} のリンクを外しました。`}),
    'project-add': () => {
      // app・test・bench link a library of this module (test・bench need one); a library gets its test Project.
      const libraries = (Array.isArray(data.projects) ? data.projects : []).filter(p => /library/.test(p.kind)).map(p => [p.name, p.name]);
      return inWorkspace('Projectを追加', [
        {name: 'name', label: '名前（ディレクトリ名にもなる）', required: true, row: 'project'},
        {name: 'kind', label: '種類', type: 'select', value: 'app', row: 'project', options: [['library', 'ライブラリ'], ['app', '実行ファイル'], ['test', 'テスト'], ['bench', '性能測定']]},
        {name: 'link', label: 'リンクするライブラリ', type: 'select', showIf: v => v.kind !== 'library',
          options: [...(libraries.length === 1 ? [] : [['', libraries.length ? '選んでください' : 'なし']]), ...libraries],
          help: libraries.length ? 'テスト・性能測定にはライブラリが必要です。' : 'このモジュールにライブラリがありません（テスト・性能測定は作れません）。'},
        {name: 'test', label: '組のテスト用Project（名前Test）も作る', type: 'checkbox', value: true, showIf: v => v.kind === 'library'}], '追加',
        v => {
          if ((v.kind === 'test' || v.kind === 'bench') && !v.link) return libraries.length ? 'リンクするライブラリを選んでください。' : 'ライブラリがないため、テスト・性能測定のProjectは作れません。';
          return ['project', 'add', v.name, '--kind', v.kind, ...(v.kind !== 'library' && v.link ? ['--link', v.link] : []), ...(v.kind === 'library' && !v.test ? ['--no-test'] : [])];
        }, {success: r => `Projectを追加しました：${r.project || ''}`});
    },
    'project-remove': name => inWorkspace(`Projectを削除：${name}`, [], '削除', () => ['project', 'remove', name, '--yes'], {danger: true, intro: 'Projectを外し、そのディレクトリを削除します。他のProjectからのリンクも外します。最初に作ったProjectを外すと、他のモジュールからリンクできなくなります。', success: `${name} を削除しました。`}),
    'pch': async name => {
      const d = await details(name); if (!d) return;
      const on = d.pch.headers.length || d.pch.system_headers.length, standard = `include/${name}/pch.h`;
      const own = d.pch.headers.length === 1 && d.pch.headers[0] === standard && !d.pch.system_headers.length;
      return inWorkspace(`プリコンパイル済みヘッダー：${name}`, [
        {name: 'mode', label: 'PCH', type: 'radio', value: !on ? 'off' : own ? 'on' : 'custom', options: [['on', '使う', `${standard} を作って使う`], ['custom', '入れるヘッダーを指定する', 'Projectのヘッダー・標準や外部のヘッダー'], ['off', '使わない']]},
        {name: 'headers', label: 'Projectのヘッダー（Projectからの相対、カンマ区切り）', value: d.pch.headers.join(', '), placeholder: `例：include/${name}/common.h`, showIf: v => v.mode === 'custom'},
        {name: 'system', label: '標準・外部のヘッダー（<> で読むもの、カンマ区切り）', value: d.pch.system_headers.join(', '), placeholder: '例：vector, string, memory', showIf: v => v.mode === 'custom'}], '保存',
        v => {
          if (v.mode === 'off') return ['project', 'pch', name, '--off'];
          if (v.mode === 'on') return ['project', 'pch', name];
          const headers = ECO.commaList(v.headers), system = ECO.commaList(v.system);
          if (!headers.length && !system.length) return '入れるヘッダーを1つ以上入力してください。';
          return ['project', 'pch', name, ...(headers.length ? ['--header', headers.join(',')] : []), ...(system.length ? ['--system', system.join(',')] : [])];
        }, {success: 'PCHの設定を変更しました。'});
    },
    // Project settings (project show / project set): what is saved for the Project. Definitions and include
    // directories belong to each form of a library (static・shared・interface): one set while they are the same.
    'project-settings': async name => {
      const d = await details(name); if (!d) return;
      const kinds = Object.keys(d.types), same = kinds.every(k => JSON.stringify(d.types[k]) === JSON.stringify(d.types[kinds[0]]));
      const groups = same ? [{label: '', types: [], values: d.types[kinds[0]]}] : kinds.map(k => ({label: `（${k}）`, types: [k], values: d.types[k]}));
      const library = d.kind.endsWith('library'), executable = d.kind === 'executable';
      const ENTRY = ['main', 'wmain', 'WinMain', 'wWinMain'], entry = ENTRY.includes(d.entry_point) ? d.entry_point : 'other';
      const defaultFolder = data.settings?.folders?.projects, folderNow = d.folder === defaultFolder ? '' : d.folder || '';
      const list = values => values.join(', ');
      const fields = [
        {name: 'sources', label: 'ソースディレクトリ（Projectからの相対、カンマ区切り。中のファイルがビルドに入る）', value: list(d.source_directories)},
        ...groups.flatMap((g, i) => [
          {type: 'section', label: '定義・インクルード' + g.label, note: same && kinds.length > 1 ? `ライブラリの形式（${kinds.join('・')}）すべてに使います` : ''},
          {name: `defines${i}`, label: '定義（このProjectだけ。例：USE_FOO, LEVEL=2）', value: list(g.values.defines)},
          {name: `public${i}`, label: '公開する定義（使う側にも伝わる）', value: list(g.values.public_defines)},
          {name: `includes${i}`, label: 'インクルードディレクトリ（Projectからの相対）', value: list(g.values.include_directories)},
          {type: 'section', end: true}]),
        ...(executable ? [
          {name: 'entry', label: '入口の関数', type: 'select', row: 'entry', value: entry, options: [['main', 'main（コンソール）'], ['wmain', 'wmain（コンソール）'], ['WinMain', 'WinMain（GUI）'], ['wWinMain', 'wWinMain（GUI）'], ['other', 'その他（MSVC の /ENTRY）']]},
          {name: 'entryOther', label: '関数名', row: 'entry', value: entry === 'other' ? d.entry_point : '', showIf: v => v.entry === 'other'},
          {name: 'gui', label: 'GUIアプリにする（コンソールを出さない）', type: 'checkbox', value: d.gui, showIf: v => v.entry === 'other'}] : []),
        {name: 'systemLibs', label: 'OSのライブラリ（名前、カンマ区切り。例：ws2_32, d3d11）', value: list(d.system_libraries)},
        ...(library ? [{name: 'exportAll', label: 'Windowsで共有ライブラリのすべての関数を書き出す（dllexport を書かなくてよい）', type: 'checkbox', value: d.export_all_symbols}] : []),
        ...(d.folder !== null ? [{name: 'folder', label: 'Visual Studio のソリューションフォルダー（/ 区切り。空なら既定）', value: folderNow, placeholder: defaultFolder || 'Projects'}] : []),
      ];
      // The CLI adds and removes items: send the differences from what is saved.
      const diff = (option, before, text) => {
        const after = ECO.commaList(text), added = after.filter(x => !before.includes(x)), removed = before.filter(x => !after.includes(x));
        return [...(added.length ? [`--add-${option}`, added.join(',')] : []), ...(removed.length ? [`--remove-${option}`, removed.join(',')] : [])];
      };
      return inWorkspace(`Projectの設定：${name}`, fields, '保存', v => {
        const common = [...diff('source-dir', d.source_directories, v.sources), ...diff('system-lib', d.system_libraries, v.systemLibs)];
        if (executable) {
          const entryPoint = v.entry === 'other' ? v.entryOther.trim() : v.entry;
          if (!entryPoint) return '入口の関数名を入力してください。';
          if (entryPoint !== d.entry_point) common.push('--entry-point', entryPoint);
          if (v.entry === 'other' && v.gui !== d.gui) common.push('--gui', v.gui ? 'on' : 'off');
        }
        if (library && v.exportAll !== d.export_all_symbols) common.push('--export-all', v.exportAll ? 'on' : 'off');
        if (d.folder !== null && v.folder.trim() !== folderNow) common.push(...(v.folder.trim() ? ['--folder', v.folder.trim()] : ['--clear-folder']));
        // One project set per group of forms (the definitions of each form differ); the rest goes with the first.
        const commands = groups.map((g, i) => [...diff('define', g.values.defines, v[`defines${i}`]), ...diff('public-define', g.values.public_defines, v[`public${i}`]),
          ...diff('include', g.values.include_directories, v[`includes${i}`])]).map((changes, i) => changes.length ? ['project', 'set', name, ...(groups[i].types.length ? ['--type', groups[i].types.join(',')] : []), ...changes] : null).filter(Boolean);
        if (common.length) commands.unshift(['project', 'set', name, ...common]);
        return commands.length ? commands : '変更はありません。';
      }, {intro: `${esc(KIND[d.kind] || d.kind)}・${esc(d.directory)}/` + (d.links.length ? `<br>リンク：${d.links.map(l => esc(l.name)).join('、')}（「リンク」で変更）` : ''), success: `${name} の設定を保存しました。`});
    },
    // Links of a Project (project link / unlink): a library of this module, a CMake package or source, or built files.
    // Other modules (GitHub repositories) are linked on the 依存先 tab (ecobuild deps add).
    'project-link': async name => {
      const d = await details(name); if (!d) return;
      const libraries = (Array.isArray(data.projects) ? data.projects : []).filter(p => p.name !== name && /library/.test(p.kind)).map(p => [p.name, p.name]);
      const LINK_KIND = {project: 'このモジュール', module: '依存先のモジュール', package: 'CMakeのパッケージ', cmake: 'CMakeのソース', file: 'ビルド済みのファイル'};
      const linked = d.links.map(l => [l.id, `${l.name}（${LINK_KIND[l.kind] || l.kind}${l.as ? '・' + l.as : ''}${l.target && l.target !== l.name ? '・' + l.target : ''}）`]);
      const adding = kind => v => v.action === 'add' && (!kind || kind.split('|').includes(v.kind));
      return inWorkspace(`リンク：${name}`, [
        {name: 'action', label: '操作', type: 'radio', inline: true, value: 'add', options: [['add', 'リンクを足す'], ...(linked.length ? [['remove', 'リンクを外す']] : [])]},
        {name: 'remove', label: '外すリンク', type: 'select', options: linked, showIf: v => v.action === 'remove', help: '依存先のモジュールを丸ごと外すには「依存先」タブの「リンクを外す」を使います。'},
        {name: 'kind', label: 'リンクするもの', type: 'radio', value: libraries.length ? 'project' : 'package', showIf: adding(), options: [
          ['project', 'このモジュールのライブラリ', libraries.length ? '' : 'ほかにライブラリのProjectがありません'], ['package', 'CMakeのパッケージ', 'find_package で見つけるもの（<名前>Config.cmake）'],
          ['cmake', 'CMakeのソース', 'add_subdirectory するフォルダー'], ['file', 'ビルド済みのファイル', '.lib・.dll 等']]},
        {name: 'library', label: 'ライブラリ', type: 'select', row: 'lib', options: libraries, showIf: adding('project')},
        {name: 'as', label: '形式', type: 'select', row: 'lib', options: [['', '相手の作成時の形式'], ['static', '静的'], ['shared', '共有'], ['interface', 'インターフェース']], showIf: adding('project')},
        {name: 'package', label: 'パッケージ名', row: 'pkg', placeholder: '例：fmt', showIf: adding('package')},
        {name: 'directory', label: 'Config.cmake のあるディレクトリ（Projectからの相対）', row: 'pkg', showIf: adding('package')},
        {name: 'cmake', label: 'CMakeのソースのディレクトリ（Projectからの相対）', showIf: adding('cmake')},
        {name: 'target', label: 'CMakeのターゲット', placeholder: '例：fmt::fmt', showIf: adding('package|cmake')},
        {name: 'fileType', label: '形式', type: 'select', row: 'file', options: [['static', '静的'], ['shared', '共有'], ['interface', 'インターフェース（ヘッダーだけ）']], showIf: adding('file')},
        {name: 'files', label: 'ファイル（構成=パス、カンマ区切り）', row: 'file', placeholder: 'Debug=lib/foo_d.lib, Release=lib/foo.lib', showIf: adding('file')},
        {name: 'implib', label: '共有ライブラリのインポートライブラリ（構成=パス、カンマ区切り）', showIf: v => adding('file')(v) && v.fileType === 'shared'},
        {name: 'include', label: 'インクルードディレクトリ（Projectからの相対、カンマ区切り）', showIf: adding('file')}], '保存',
        v => {
          if (v.action === 'remove') return v.remove ? ['project', 'unlink', v.remove, '--project', name] : '外すリンクを選んでください。';
          const args = ['project', 'link', '--project', name], joined = text => ECO.commaList(text).join(',');
          if (v.kind === 'project') return v.library ? [...args, v.library, ...(v.as ? ['--type', v.as] : [])] : 'リンクするライブラリを選んでください。';
          if (v.kind === 'package') return v.package.trim() && v.target.trim() && v.directory.trim() ? [...args, '--package', v.package.trim(), '--target', v.target.trim(), '--directory', v.directory.trim()] : 'パッケージ名・ディレクトリ・ターゲットを入力してください。';
          if (v.kind === 'cmake') return v.cmake.trim() && v.target.trim() ? [...args, '--cmake', v.cmake.trim(), '--target', v.target.trim()] : 'ディレクトリとターゲットを入力してください。';
          if (v.fileType !== 'interface' && !v.files.trim()) return 'ライブラリのファイルを入力してください。';
          return [...args, '--type', v.fileType, ...(v.files.trim() ? ['--file', joined(v.files)] : []), ...(v.implib.trim() ? ['--implib', joined(v.implib)] : []), ...(v.include.trim() ? ['--include', joined(v.include)] : [])];
        }, {intro: linked.length ? `いまのリンク：${linked.map(([, l]) => esc(l)).join('、')}` : 'リンクはまだありません。', success: 'リンクを変更しました。'});
    },
    'project-move': name => inWorkspace(`Projectを移動：${name}`, [{name: 'destination', label: '移動先のディレクトリ（モジュールからの相対。まだないもの）', required: true, placeholder: `例：libs/${name}`}], '移動',
      v => ['project', 'move', name, v.destination.trim()], {intro: 'Projectのディレクトリを移します（名前は変わりません）。', success: `${name} を移しました。`}),
    // Module-wide settings (module settings): which Project other modules link (main) and the solution folders' names.
    'module-settings': () => {
      const m = data.settings, f = m.folders, libraries = (Array.isArray(data.projects) ? data.projects : []).filter(p => /library/.test(p.kind) || p.name === m.main_project)
        .map(p => [p.name, /library/.test(p.kind) ? p.name : `${p.name}（ライブラリではないため、リンクはできません）`]);
      return inWorkspace('モジュールの設定', [
        {name: 'main', label: '他のモジュールからリンクされるProject（main）', type: 'select', value: m.main_project || '', options: [...libraries, ['', 'なし（他のモジュールからリンクできない）']], help: 'ライブラリのProjectだけを選べます。'},
        ...(f ? [{type: 'section', label: 'Visual Studio のソリューションフォルダー'},
          {name: 'projects', label: '自分のProject', row: 'f1', value: f.projects}, {name: 'linked', label: 'リンク先のモジュール', row: 'f1', value: f.linked_projects},
          {name: 'external', label: 'CMake・GoogleTest 等', row: 'f2', value: f.external}, {type: 'section', end: true}] : [])], '保存',
        v => {
          const args = ['module', 'settings'];
          if (v.main !== (m.main_project || '')) args.push(...(v.main ? ['--main', v.main] : ['--no-main']));
          if (f) for (const [key, option, before] of [['projects', '--projects-folder', f.projects], ['linked', '--linked-folder', f.linked_projects], ['external', '--external-folder', f.external]]) if (v[key].trim() && v[key].trim() !== before) args.push(option, v[key].trim());
          return args.length > 2 ? args : '変更はありません。';
        }, {success: 'モジュールの設定を保存しました。'});
    },
    'template-add': name => inWorkspace(name ? `テンプレートを差し替え：${name}` : 'テンプレートを追加', [
      {name: 'name', label: '名前（英字で始まる英数字と _）', required: true, value: name || ''},
      {name: 'source', label: '元にするファイル（絶対パス、またはモジュールからの相対パス）', required: true}], '登録',
      v => ['template', 'add', v.name.trim(), v.source.trim()], {intro: 'ファイルの中の {{header}}・{{name}}・{{suite}}・{{project}} は、作るときに置き換わります。', success: 'テンプレートを登録しました。'}),
    'template-remove': name => inWorkspace(`テンプレートを削除：${name}`, [], '削除', () => ['template', 'remove', name], {danger: true, success: `${name} を削除しました。`}),
    'profile-add': name => {
      const x = name && data.profiles?.profiles?.[name], o = x?.options || {};
      const text = (field, label, row, extra = {}) => ({name: field, label, row, value: o[field] ?? '', ...extra});
      return inWorkspace(name ? `ビルド設定：${name}` : 'ビルド設定を追加', [
        {name: 'name', label: '名前', required: true, value: name || ''},
        {name: 'configuration', label: '構成', type: 'select', row: 'build', value: x?.configuration || 'Debug', options: CONFIGURATIONS.map(c => [c, c])},
        {name: 'parallel', label: '並列ビルドの数', type: 'number', row: 'build', min: 1, value: String(x?.parallel || 4)},
        {name: 'shared', label: 'ライブラリ（依存先を含む）をすべて共有ライブラリにする', type: 'checkbox', value: x?.shared, help: 'ライブラリごとに決めるには、下の「Projectごとの上書き」で形式を指定します。'},
        {type: 'section', label: 'C++・コンパイラ', note: '空なら既定', collapsed: true, open: ['architecture', 'cpp_standard', 'generator', 'toolset', 'c_compiler', 'cxx_compiler', 'toolchain_file'].some(k => o[k])},
        {name: 'cpp_standard', label: 'C++の規格', type: 'select', row: 'cpp', value: String(o.cpp_standard || ''), options: [['', '既定（20）'], ['17', 'C++17'], ['20', 'C++20'], ['23', 'C++23']]},
        {name: 'architecture', label: 'アーキテクチャ', type: 'select', row: 'cpp', value: o.architecture || '', options: [['', '既定'], ['x64', 'x64'], ['Win32', 'Win32'], ['ARM64', 'ARM64']]},
        {name: 'generator', label: 'CMakeの生成器', type: 'select', row: 'gen', value: o.generator || '', options: [['', '既定（OSごと）'], ...['Visual Studio 18 2026', 'Visual Studio 17 2022', 'Ninja Multi-Config'].map(g => [g, g]), ...(o.generator && !['Visual Studio 18 2026', 'Visual Studio 17 2022', 'Ninja Multi-Config'].includes(o.generator) ? [[o.generator, o.generator]] : [])]},
        text('toolset', 'ツールセット', 'gen', {placeholder: 'v143、14.44 等'}),
        text('c_compiler', 'Cコンパイラ（Ninjaだけ）', 'cc', {placeholder: '名前か絶対パス'}), text('cxx_compiler', 'C++コンパイラ（Ninjaだけ）', 'cc', {placeholder: '例：clang++'}),
        text('toolchain_file', 'CMakeのツールチェーンファイル（絶対パス）'),
        {type: 'section', end: true},
        {type: 'section', label: 'テスト・依存先', note: '空なら既定', collapsed: true, open: ['test_parallel', 'googletest_archive', 'test_continue_on_failure', 'fetch_git'].some(k => k in o)},
        {name: 'test_parallel', label: 'テストを並列に実行する数', type: 'number', min: 1, value: o.test_parallel ? String(o.test_parallel) : '', placeholder: '1'},
        {name: 'stop', label: 'テスト用のProjectが失敗したら、残りのテストを実行しない', type: 'checkbox', value: o.test_continue_on_failure === false},
        text('googletest_archive', 'GoogleTestのZIP（オフラインで使う。空ならダウンロード）'),
        {name: 'noFetch', label: '足りない依存先を、ビルドの前に自動でcloneしない', type: 'checkbox', value: o.fetch_git === false},
        {type: 'section', end: true}], '保存',
        v => ['profile', 'add', v.name, '--configuration', v.configuration, '--parallel', v.parallel || '1', ...(v.shared ? ['--shared'] : []),
          ...[['cpp_standard', '--cpp-standard'], ['architecture', '--architecture'], ['generator', '--generator'], ['toolset', '--toolset'], ['c_compiler', '--c-compiler'], ['cxx_compiler', '--cxx-compiler'],
            ['toolchain_file', '--toolchain-file'], ['test_parallel', '--test-parallel'], ['googletest_archive', '--googletest-archive']].flatMap(([key, option]) => String(v[key] ?? '').trim() ? [option, String(v[key]).trim()] : []),
          ...(v.stop ? ['--stop-on-test-failure'] : []), ...(v.noFetch ? ['--no-fetch'] : [])], {success: 'ビルド設定を保存しました。'});
    },
    // Overrides of a build setting for one Project (profile project): the form of a library, its C++ standard, etc.
    'profile-project': async key => {
      const [name, project] = key.split('\n'), x = data.profiles?.profiles?.[name]; if (!x) return;
      if (!Array.isArray(data.projects)) await LOADS.projects();
      const projects = Array.isArray(data.projects) ? data.projects : [], current = project ? x.projects[project] || {} : {};
      return inWorkspace(`Projectごとの上書き：${name}`, [
        {name: 'project', label: 'Project', type: 'select', value: project || '', options: project ? [[project, project]] : [['', '選んでください'], ...projects.map(p => [p.name, `${p.name}（${KIND[p.kind] || p.kind}）`])]},
        {name: 'type', label: 'ライブラリの形式（使う側のリンクもこの形式になる）', type: 'select', row: 'a', value: current.type || '', options: [['', '上書きしない'], ['static', '静的'], ['shared', '共有'], ['interface', 'インターフェース']]},
        {name: 'cpp_standard', label: 'C++の規格', type: 'select', row: 'a', value: String(current.cpp_standard || ''), options: [['', '上書きしない'], ['17', 'C++17'], ['20', 'C++20'], ['23', 'C++23']]},
        {name: 'artifact_directory', label: '成果物の置き場所（ビルドツリーからの相対）', value: current.artifact_directory || ''},
        {name: 'test_parallel', label: 'テストを並列に実行する数（テスト用Project）', type: 'number', row: 'b', min: 1, value: current.test_parallel ? String(current.test_parallel) : ''},
        {name: 'googletest_archive', label: 'GoogleTestのZIP（テスト用Project）', row: 'b', value: current.googletest_archive || ''}], '保存',
        v => {
          if (!v.project) return 'Projectを選んでください。';
          const values = [['type', '--type'], ['cpp_standard', '--cpp-standard'], ['artifact_directory', '--artifact-directory'], ['test_parallel', '--test-parallel'], ['googletest_archive', '--googletest-archive']]
            .flatMap(([k, option]) => String(v[k] ?? '').trim() ? [option, String(v[k]).trim()] : []);
          return ['profile', 'project', name, v.project, ...(values.length ? values : ['--clear'])];
        }, {intro: '指定した項目で置き換えます（空にした項目は上書きしません。すべて空なら上書きを外します）。構成・生成器・アーキテクチャはモジュール全体で1つです。', success: '上書きを保存しました。'});
    },
    'profile-project-clear': key => { const [name, project] = key.split('\n'); return inWorkspace(`上書きを外す：${name} の ${project}`, [], '外す', () => ['profile', 'project', name, project, '--clear'], {success: '上書きを外しました。'}); },
    'profile-remove': name => inWorkspace(`ビルド設定を削除：${name}`, [], '削除', () => ['profile', 'remove', name], {danger: true, success: `${name} を削除しました。`}),
    // The branches' history with their merges (all branches) is drawn by TortoiseGit (ecobuild log --all --gui).
    'branch-log': async () => { const doc = await cli(['log', '--all', '--gui']); if (!doc.ok) ECO.showError(doc); },
    'branch-create': () => ECO.form({title: 'ブランチを作成', intro: '作業空間以外のブランチ（develop・release など）を作成し、GitHubに反映します。', fields: [
      {name: 'name', label: 'ブランチ名（task/ で始まる名前は作業空間専用）', required: true, placeholder: '例：develop'},
      {name: 'base', label: '作成元', type: 'select', options: [['', '既定（default_base）'], ...(Array.isArray(data.branches) ? data.branches.filter(b => !b.is_workspace).map(b => [b.name, b.name]) : [])]}], ok: '作成',
      submit: async v => { if (!await ECO.run(here(), ['branch', 'create', v.name, ...(v.base ? ['--base', v.base] : [])], {success: `ブランチ ${v.name} を作成しました。`})) return '作成できませんでした。'; render(); }}),
    'branch-submit': name => ECO.form({title: `提出する：${name}`, fields: [
      {name: 'into', label: '取り込み先', type: 'select', options: (Array.isArray(data.branches) ? data.branches.filter(b => !b.is_workspace && b.name !== name) : []).map(b => [b.name, b.name])},
      {name: 'title', label: '提出の題名'}], ok: '提出',
      submit: async v => { if (!v.into) return '取り込み先を選んでください。'; if (!await ECO.run(here(), ['branch', 'submit', name, '--into', v.into, ...(v.title ? ['--title', v.title] : [])], {success: `${name} を ${v.into} へ提出しました。`})) return '提出できませんでした。'; render(); }}),
    'branch-merge': name => ECO.form({title: `${name} の提出を取り込む`, intro: 'ブランチ同士の提出を、マージコミットで取り込みます。', fields: [{name: 'ignore', label: 'CIが失敗していても取り込む', type: 'checkbox'}], ok: '取り込む',
      submit: async v => { if (!await ECO.run(here(), ['branch', 'merge', name, ...(v.ignore ? ['--ignore-checks'] : [])], {success: `${name} の提出を取り込みました。`})) return '取り込めませんでした。'; render(); }}),
    'branch-delete': name => ECO.run(here(), ['branch', 'delete', name], {success: `ブランチ ${name} を削除しました。`}).then(doc => doc && render()),
  };
  el('modinfo-content').addEventListener('click', e => {
    const tab = e.target.closest('[data-mi-view]');
    if (tab) { view = tab.dataset.miView; show(); return; }
    const ws = e.target.closest('[data-open-ws]');
    if (ws) { MOD.openWorkspace(Number(ws.dataset.openWs)); return; }
    const action = e.target.closest('[data-mi]');
    if (action) ACTIONS[action.dataset.mi](action.dataset.arg);
  });
  el('modinfo-content').addEventListener('change', async e => {
    if (e.target.id === 'mi-place') { place = e.target.value; loaded.clear(); render(); }
    if (e.target.name === 'mi-profile') {
      const doc = await ECO.run(here(), ['profile', 'use', e.target.value], {success: e.target.value === 'none' ? 'ビルド設定の使用をやめました。' : `このPCではビルド設定 ${e.target.value} を使います。`});
      render(!doc);
    }
  });
  el('modinfo-content').addEventListener('contextmenu', e => {
    const row = e.target.closest('.mi-table tbody tr, .mi-branch'); if (!row) return;
    const buttons = [...row.querySelectorAll('[data-mi], [data-open-ws]')]; if (!buttons.length) return;
    e.preventDefault();
    ECO.menu(buttons.map(b => [b.textContent, () => b.click(), !b.disabled]), e.clientX, e.clientY);
  });
  pageHooks.modinfo = show;
  el('mi-reload').addEventListener('click', () => { loaded.clear(); render(); });
})();
