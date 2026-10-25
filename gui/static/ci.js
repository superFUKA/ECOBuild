'use strict';
// モジュール › CI: the module's CI (GitHub Actions) — its settings and workflow (ci show; changed with ci init / ci remove, which
// write the workflow file: on a task branch, so in a workspace with one, then committed and submitted), its runs on every
// branch or one (ci status --all / --branch; the log of the failed steps, run again, run by hand on a branch) and the
// secrets the CI uses (ci secret). The reads run in the module's folder. Changing any of it is managing: admins only
// (account show; the others see it with the buttons grey).
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {state: null, runs: [], secrets: null, branches: [], url: '', branch: '', run: 0, access: null, loaded: false, error: ''};
  const pill = (text, cls = '') => `<span class="mi-pill ${cls}">${esc(text)}</span>`;
  const RUNS = 30;
  const runArgs = () => ['ci', 'status', ...(st.branch ? ['--branch', st.branch] : ['--all']), '--count', String(RUNS)];
  const CONCLUSIONS = {failure: '失敗', timed_out: '時間切れ', startup_failure: '起動できず', action_required: '要対応'};
  const EVENTS = {push: 'push', pull_request: '提出（PR）', workflow_dispatch: '手動', schedule: '定期'};
  const result = r => r.status !== 'completed' ? ['実行中', 'warn'] : ['success', 'skipped', 'neutral'].includes(r.conclusion) ? ['成功', 'ok']
    : r.conclusion === 'cancelled' ? ['取り消し', ''] : [CONCLUSIONS[r.conclusion] || r.conclusion || '失敗', 'bad'];
  const failed = r => r.status === 'completed' && result(r)[1] === 'bad';

  // Reads (cached: the kept answer shows at once, a newer one redraws).
  async function load() {
    const redraw = (key, fresh) => { if (fresh.ok) { st[key] = fresh.result; render(); } };
    const [state, runs, secrets, branches, module, access] = await Promise.all([
      ECO.query(MOD.root, ['ci', 'show'], fresh => redraw('state', fresh)),
      ECO.query(MOD.root, runArgs(), fresh => redraw('runs', fresh)),
      ECO.cli(MOD.root, ['ci', 'secret', 'list'], {quiet: true}),
      ECO.query(MOD.root, ['branch', 'list']),
      ECO.query(MOD.root, ['module', 'show']),
      ECO.access(MOD.root),
    ]);
    st.access = access;
    st.error = !state.ok ? state.error.message : !runs.ok ? runs.error.message : '';
    st.state = state.ok ? state.result : null;
    st.runs = runs.ok ? runs.result : [];
    st.secrets = secrets.ok ? secrets.result : null;
    st.branches = branches.ok ? branches.result.filter(b => b.remote).map(b => b.name) : [];
    st.url = module.ok ? module.result.url || '' : '';
    st.loaded = true;
    render();
  }
  async function loadRuns() {
    el('ci-runs').innerHTML = ECO.loading();
    const doc = await ECO.query(MOD.root, runArgs(), fresh => { if (fresh.ok) { st.runs = fresh.result; render(); } });
    st.runs = doc.ok ? doc.result : [];
    st.error = doc.ok ? '' : doc.error.message;
    render();
  }

  function settingsHtml() {
    const s = st.state;
    if (!s) return '<p class="mi-note">CIの設定を読めませんでした。</p>';
    if (!s.supported) return '<p class="mi-note">このモジュールの型は、CIのワークフローを用意できません。</p>';
    const [text, cls] = !s.exists ? ['ワークフローはありません', 'warn'] : s.edited ? ['手で編集されています', 'warn']
      : s.current ? ['今の設定のとおり', 'ok'] : ['今の設定と違います（作り直すと合います）', 'warn'];
    const row = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
    return `<div class="ci-card"><div class="ci-card-head"><div><strong>${esc(s.path)}</strong> ${pill(text, cls)}</div>
        <div class="mi-actions"><button type="button" data-ci-action="init">${s.exists ? '設定を変える…' : 'CIを用意する…'}</button>${s.exists ? '<button type="button" class="danger-text" data-ci-action="remove">CIをやめる…</button>' : ''}</div></div>
      <dl class="ci-settings">${row('OS', s.os ? esc(s.os.join('、')) : '型の既定')}${row('構成', esc(s.configurations.join('、')))}
        ${row('共有ライブラリ', s.shared ? 'その構成でもビルド・テストする' : 'しない')}
        ${row('push で動かすブランチ', s.branches ? esc(s.branches.join('、')) : `${esc(s.default_base)}（既定）`)}${row('提出（PR）・手動', '常に動く')}</dl></div>`;
  }
  function runsHtml() {
    if (!st.runs.length) return `<p class="mi-note">${st.branch ? `${esc(st.branch)} の` : ''}CIの実行はありません。</p>`;
    if (!st.runs.some(r => r.id === st.run)) st.run = 0;
    return `<table class="mi-table ci-runs"><thead><tr><th>結果</th><th>#</th><th>ブランチ</th><th>きっかけ</th><th>日時</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>${st.runs.map(r => {
      const [text, cls] = result(r);
      return `<tr data-ci-run="${r.id}" class="${r.id === st.run ? 'selected' : ''}" title="${esc(r.workflow)}">
        <td>${pill(text, cls)}</td><td>${r.id}</td><td class="ci-branch">${esc(r.branch)}</td><td>${esc(EVENTS[r.event] || r.event)}</td><td>${esc(ECO.localTime(r.created, true))}</td>
        <td class="ci-row-actions">${failed(r) ? `<button type="button" data-ci-action="logs">ログ</button>` : ''}<button type="button" data-ci-action="rerun"${r.status !== 'completed' ? ' disabled title="実行中です"' : ''}>再実行</button><button type="button" data-ci-action="open" title="GitHubで開く">↗</button></td></tr>`;
    }).join('')}</tbody></table>`;
  }
  function secretsHtml() {
    const list = st.secrets === null ? '<p class="mi-note">シークレットの一覧を読めませんでした（リポジトリの管理者の権限が要ります）。</p>'
      : st.secrets.length ? `<ul class="ci-secrets">${st.secrets.map(n => `<li><code>${esc(n)}</code><button type="button" class="danger-text" data-ci-secret="${esc(n)}">削除…</button></li>`).join('')}</ul>`
      : '<p class="mi-note">シークレットはありません。</p>';
    return `${list}<p class="mi-note">非公開の依存先を CI で取得するには、それを読めるトークンを ECOBUILD_DEPS_TOKEN に登録します。値は GitHub に送るだけで、表示も保存もしません。</p>`;
  }
  function render() {
    if (el('modinfo-content').hidden || el('ci-main').hidden) return;
    const main = el('ci-main');
    if (!st.loaded) { main.innerHTML = ECO.loading(); return; }
    // Running by hand needs the workflow on GitHub (ECOBuild's has workflow_dispatch).
    const runnable = !!st.state?.exists;
    const runTitle = runnable ? '' : 'CIのワークフローがありません（「CIを用意する…」で作り、提出して取り込みます）';
    const options = [['', 'すべてのブランチ'], ...st.branches.map(b => [b, b])];
    if (st.branch && !st.branches.includes(st.branch)) options.push([st.branch, st.branch]);
    main.innerHTML = `${st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : ''}
      <h4 class="br-section">設定</h4>${settingsHtml()}
      <p class="mi-note">手元でコミット・提出等のときに確かめることは「パイプライン」のタブで決めます。</p>
      <div class="ci-section-row"><h4 class="br-section">実行</h4>
        <select id="ci-branch" aria-label="ブランチ">${options.map(([v, l]) => `<option value="${esc(v)}" ${v === st.branch ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
        <span class="ci-section-end"><button type="button" id="ci-actions"${st.url ? '' : ' disabled'}>GitHub で見る ↗</button><button type="button" class="primary" id="ci-run"${runTitle ? ` title="${esc(runTitle)}"` : ''}${runnable ? '' : ' disabled'}>▶ 手動で実行</button></span></div>
      <div id="ci-runs">${runsHtml()}</div>
      <div class="ci-section-row"><h4 class="br-section">シークレット</h4><button type="button" data-ci-action="secret-set">＋ 登録</button></div>${secretsHtml()}`;
    gate();
  }
  // Greys what changes the CI for those who are not admins (looking at the runs and their logs stays).
  function gate() {
    if (ECO.isAdmin(st.access)) return;
    for (const b of [...el('ci-main').querySelectorAll('#ci-run'), ...el('ci-main').querySelectorAll('[data-ci-action=init], [data-ci-action=remove], [data-ci-action=rerun], [data-ci-action=secret-set], [data-ci-secret]')]) {
      b.disabled = true; b.title = ECO.adminNote;
    }
  }

  // Changing the workflow writes a file: on a task branch, in a workspace that has one (chosen here).
  function taskPlaces() {
    return MOD.workspacePlaces().filter(p => !MOD.states.get(MOD.keyOf(p))?.reviewing);
  }
  async function choosePlace(title) {
    const places = taskPlaces();
    if (!places.length) {
      if (await ECO.confirm({title, message: 'CIのワークフローはタスクブランチで変えます（コミットして提出し、取り込むと反映されます）。タスク管理で「作業を開始」して、タスクブランチを作ってください。', ok: 'タスク管理を開く'})) showModulePage('tasks');
      return null;
    }
    return places;
  }
  const placeOptions = places => places.map(p => { const s = MOD.states.get(MOD.keyOf(p)); return [p, `${s.branch}（${p}）`]; });
  const placeDefault = places => places.find(p => MOD.keyOf(p) === MOD.keyOf(MOD.activePlace() || '')) || places[0];
  async function initCi() {
    const places = await choosePlace('CIの設定'); if (!places) return;
    const s = st.state || {os: null, configurations: ['Debug'], shared: false, branches: null, default_base: 'main', edited: false};
    await ECO.form({title: s.exists ? 'CIの設定を変える' : 'CIを用意する', wide: true,
      intro: 'ワークフロー（.github/workflows/ecobuild.yml）を、この設定で作り直します。設定は ecobuild.toml の [ci] に残ります。',
      fields: [
        {name: 'place', label: '作り直すタスクブランチ（作業空間）', type: 'select', value: placeDefault(places), options: placeOptions(places)},
        {name: 'os', label: '動かすOS（どれも選ばなければ、今の設定のまま。初めは型の既定）', type: 'checks', value: s.os || [], options: [['windows', 'Windows'], ['linux', 'Linux']]},
        {name: 'configuration', label: 'ビルドする構成（カンマ区切り）', value: s.configurations.join(','), required: true, placeholder: '例：Debug,Release'},
        {name: 'shared', label: 'ライブラリを共有ライブラリにした構成でもビルド・テストする（C++）', type: 'checkbox', value: s.shared},
        {name: 'branches', label: `push で動かすブランチ（カンマ区切り。空欄なら今の設定のまま。初めは ${s.default_base}）`, value: (s.branches || []).join(','), placeholder: s.default_base},
        ...(s.edited ? [{name: 'force', label: '手で編集したワークフローを上書きする（編集した内容は失われます）', type: 'checkbox'}] : []),
      ], ok: s.exists ? '作り直す' : '作る',
      submit: async v => {
        if (s.edited && !v.force) return '手で編集されたワークフローです。上書きしてよければ印を付けてください。';
        const args = ['ci', 'init', '--configuration', v.configuration, '--shared', v.shared ? 'on' : 'off',
          ...(v.os.length ? ['--os', v.os.join(',')] : []), ...(v.branches ? ['--branches', v.branches] : []), ...(v.force ? ['--force'] : [])];
        const doc = await ECO.run(v.place, args, {success: 'ワークフローを作りました。コミットして提出すると反映されます。'});
        if (!doc) return 'ワークフローを作れませんでした。';
        const deps = doc.result.private_dependencies || [];
        if (deps.length) ECO.toast(`非公開の依存先（${deps.join('、')}）は CI の GITHUB_TOKEN では取得できません。読めるトークンをシークレット ECOBUILD_DEPS_TOKEN に登録してください。`, 'info', 12000);
        MOD.reloadPlace(v.place);
      }});
  }
  async function removeCi() {
    const places = await choosePlace('CIをやめる'); if (!places) return;
    await ECO.form({title: 'CIをやめる', danger: true, intro: 'ワークフロー（.github/workflows/ecobuild.yml）を消します。',
      fields: [{name: 'place', label: 'タスクブランチ（作業空間）', type: 'select', value: placeDefault(places), options: placeOptions(places)}], ok: '消す',
      submit: async v => {
        if (!await ECO.run(v.place, ['ci', 'remove'], {success: 'ワークフローを消しました。コミットして提出すると反映されます。'})) return '消せませんでした。';
        MOD.reloadPlace(v.place);
      }});
  }
  function dispatch() {
    const current = MOD.states.get(MOD.keyOf(MOD.activePlace() || ''))?.branch || '';   // the tab shown now's
    const branches = st.branches.length ? st.branches : [current].filter(Boolean);
    return ECO.form({title: 'CIを手動で実行', intro: 'GitHub にあるブランチの内容で CI を動かします（手元の未Pushのコミットは入りません）。',
      fields: [{name: 'branch', label: 'ブランチ', type: 'select', value: st.branch || (branches.includes(current) ? current : branches[0]), options: branches.map(b => [b, b])}], ok: '実行',
      submit: async v => {
        if (!v.branch) return 'ブランチを選んでください。';
        if (!await ECO.run(MOD.root, ['ci', 'run', '--branch', v.branch], {success: `${v.branch} で CI を実行しました。少しすると一覧に出ます。`})) return '実行できませんでした。';
        setTimeout(loadRuns, 4000);
      }});
  }
  async function runAction(action, r) {
    switch (action) {
      case 'open': if (r.url) window.open(r.url, '_blank', 'noopener'); return;
      case 'logs': {
        const doc = await ECO.cli(MOD.root, ['ci', 'logs', '--run', String(r.id)]);
        return doc.ok ? ECO.output(`#${r.id} の失敗した手順`, doc.result.log || '（ログはありません）', {sub: `${r.workflow}・${r.branch}`}) : ECO.showError(doc);
      }
      case 'rerun': {
        const v = await ECO.form({title: `#${r.id} をもう一度実行`,
          fields: failed(r) ? [{name: 'failed', label: '失敗したジョブだけを実行する', type: 'checkbox', value: true}] : [], ok: '実行'});
        if (!v) return;
        if (await ECO.run(MOD.root, ['ci', 'rerun', '--run', String(r.id), ...(v.failed ? ['--failed'] : [])], {success: `#${r.id} をもう一度実行しました。`})) setTimeout(loadRuns, 3000);
      }
    }
  }
  function setSecret() {
    return ECO.form({title: 'シークレットを登録', intro: 'CI で使う値を、このリポジトリのシークレットとして GitHub に登録します（同じ名前なら置き換え）。',
      fields: [{name: 'name', label: '名前', required: true, value: 'ECOBUILD_DEPS_TOKEN', suggestions: [['ECOBUILD_DEPS_TOKEN', '非公開の依存先を読むトークン']]},
        {name: 'value', label: '値', type: 'password', required: true}], ok: '登録',
      submit: async v => {
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(v.name)) return '名前は英数字と _ だけです（数字で始めない）。';
        const doc = await ECO.run(MOD.root, ['ci', 'secret', 'set', v.name], {stdin: v.value, success: `シークレット ${v.name} を登録しました。`});
        if (!doc) return '登録できませんでした。';
        await loadSecrets();
      }});
  }
  async function loadSecrets() {
    const doc = await ECO.cli(MOD.root, ['ci', 'secret', 'list'], {quiet: true});
    st.secrets = doc.ok ? doc.result : null; render();
  }

  const main = el('ci-main');
  main.addEventListener('click', e => {
    if (e.target.closest('#ci-run:not(:disabled)')) return dispatch();
    if (e.target.closest('#ci-actions:not(:disabled)')) { window.open(st.url.replace(/\.git$/, '') + '/actions', '_blank', 'noopener'); return; }
    const b = e.target.closest('[data-ci-action]'), row = e.target.closest('[data-ci-run]');
    const r = row && st.runs.find(x => x.id === Number(row.dataset.ciRun));
    if (b?.disabled) return;
    if (b && r) { st.run = r.id; runAction(b.dataset.ciAction, r); return; }
    if (b) {
      switch (b.dataset.ciAction) {
        case 'init': return initCi();
        case 'remove': return removeCi();
        case 'secret-set': return setSecret();
      }
    }
    const secret = e.target.closest('[data-ci-secret]');
    if (secret) {
      const name = secret.dataset.ciSecret;
      ECO.run(MOD.root, ['ci', 'secret', 'remove', name], {success: `シークレット ${name} を削除しました。`, confirm: `シークレット ${name} を GitHub から削除します。これを使う CI は動かなくなるかもしれません。`, title: 'シークレットを削除', ok: '削除する', danger: true})
        .then(doc => { if (doc) loadSecrets(); });
      return;
    }
    if (r) { st.run = r.id; for (const tr of main.querySelectorAll('[data-ci-run]')) tr.classList.toggle('selected', tr === row); }
  });
  main.addEventListener('dblclick', e => {
    const row = e.target.closest('[data-ci-run]'); if (!row || e.target.closest('button')) return;
    const r = st.runs.find(x => x.id === Number(row.dataset.ciRun)); if (r) runAction(failed(r) ? 'logs' : 'open', r);
  });
  main.addEventListener('change', e => { if (e.target.id === 'ci-branch') { st.branch = e.target.value; st.run = 0; loadRuns(); } });
  // Right-click a run: what its buttons do, and more.
  main.addEventListener('contextmenu', e => {
    const row = e.target.closest('[data-ci-run]'); if (!row) return;
    const r = st.runs.find(x => x.id === Number(row.dataset.ciRun)); if (!r) return;
    e.preventDefault(); st.run = r.id;
    for (const tr of main.querySelectorAll('[data-ci-run]')) tr.classList.toggle('selected', tr === row);
    ECO.menu([
      ['失敗した手順のログ', () => runAction('logs', r), failed(r)],
      ['もう一度実行…', () => runAction('rerun', r), r.status === 'completed'],
      ['GitHubで開く', () => runAction('open', r), !!r.url],
      '-',
      [`${r.branch} の実行だけを表示`, () => { st.branch = r.branch; loadRuns(); }, st.branch !== r.branch],
    ], e.clientX, e.clientY);
  });

  // The tab shows: read (once; 更新 reads again).
  window.MANAGE_CI = {show: () => { if (!st.loaded) { render(); load(); } else render(); }, reload: load};
  ECO.onChange(() => { if (st.loaded) { if (!main.hidden && !el('modinfo-content').hidden) load(); else st.loaded = false; } });
})();
