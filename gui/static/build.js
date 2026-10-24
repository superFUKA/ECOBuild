'use strict';
// Build / test / run toolbar of a place. Runs ecobuild build・test・run・rebuild・clean・check and shows the result.
// What it offers follows the module's type (the configurations; Visual Studio only for types that make a solution).
// It also starts the AI (coding agent) in the workspace: ecobuild agent start.
WS.onRefresh(renderPrDetail);
(() => {
  const LABEL = {build: 'ビルド', rebuild: 'リビルド', clean: 'クリーン', test: 'テスト', run: '実行', check: '提出前の確認'};
  const CHECK = {generated: '生成ファイルが最新', conflict_markers: '衝突マーカーがない', build: 'ビルド', test: 'テスト'};
  let profiles = {}, selectedProfile = null, busy = false, features = ECO.typeFeatures('');

  async function loadOptions() {
    const [p, j, type] = await Promise.all([WS.cli(['profile', 'list'], {quiet: true}), WS.cli(['project', 'list'], {quiet: true}), ECO.moduleType(WS.dir)]);
    features = ECO.typeFeatures(type);
    const config = get('build-config'), chosen = config.value;
    config.innerHTML = '<option value="">ビルド設定のまま</option>' + features.configurations.map(c => `<option>${esc(c)}</option>`).join('');
    config.value = features.configurations.includes(chosen) ? chosen : '';
    get('vs-group').hidden = !features.solution;
    if (p.ok) {
      profiles = p.result.profiles; selectedProfile = p.result.selected;
      const names = Object.keys(profiles);
      get('build-profile').innerHTML = names.map(n => `<option value="${esc(n)}">${esc(n)}（${esc(profiles[n].configuration)}${profiles[n].shared ? '・共有' : ''}）</option>`).join('') + '<option value="none">使わない</option>';
      get('build-profile').value = selectedProfile || 'none';
      get('build-profile').disabled = !names.length; get('build-profile').title = names.length ? '' : 'ビルド設定はありません（モジュールの窓の左の「設定」で追加できます）';
    }
    showSetting();
    if (j.ok) {
      const chosen = get('build-project').value;
      get('build-project').innerHTML = '<option value="">すべてのProject</option>' + j.result.map(x => `<option value="${esc(x.name)}" data-kind="${esc(x.kind)}">${esc(x.name)}（${esc(PROJECT_KIND_LABEL[x.kind] || x.kind)}）</option>`).join('');
      if (j.result.some(x => x.name === chosen)) get('build-project').value = chosen;
      showTarget();
    }
  }
  // The Project to build・run・test: ▾ next to ▶ chooses it (a menu); its name shows next to ▾ (as Visual Studio's startup
  // project). The value is kept in the hidden select (build-project), which runAction reads.
  // The same ▾ also holds the arguments for 実行 (a type without Projects has only these).
  function showTarget() {
    const select = get('build-project'), name = select.selectedOptions[0]?.textContent, runArgs = get('build-run-args').value;
    get('build-project-pick').dataset.tip = [name ? `対象：${name}` : '実行の設定', runArgs ? `引数：${runArgs}` : ''].filter(Boolean).join('　');
    get('build-project-pick').classList.toggle('chosen', !!select.value || !!runArgs);
    const shown = get('build-project-pick').querySelector('.run-target-name');
    shown.textContent = select.value; shown.hidden = !select.value;
  }
  // A menu of choices: the chosen one has ✓ in a column of its own (the names line up). An item's text starts with
  // '✓ ' (chosen) or '　' (not); ECO.menu draws the text, the mark is put in its column after.
  function choiceMenu(items, x, y) {
    ECO.menu(items, x, y);
    const el = [...document.querySelectorAll('.eco-menu')].pop();
    for (const b of el?.querySelectorAll('button') || []) {
      const text = b.textContent, on = text.startsWith('✓ ');
      if (!on && !text.startsWith('　')) continue;
      const mark = document.createElement('span'); mark.className = 'menu-check'; mark.textContent = on ? '✓' : '';
      b.textContent = text.slice(on ? 2 : 1); b.prepend(mark);
    }
  }
  get('build-project-pick').addEventListener('click', () => {
    const select = get('build-project'), r = get('build-project-pick').getBoundingClientRect(), runArgs = get('build-run-args');
    const projects = [...select.options].map(o => [(o.value === select.value ? '✓ ' : '　') + o.textContent, () => { select.value = o.value; showTarget(); }]);
    choiceMenu([...projects, ...(projects.length ? ['-'] : []), [runArgs.value ? `実行時の引数：${runArgs.value}…` : '実行時の引数…', () => ECO.form({
      title: '実行時の引数', intro: 'この画面を閉じるまで使います。',
      fields: [{name: 'args', label: '引数', value: runArgs.value, placeholder: '例：--size 3', focus: true}], ok: '決定',
      submit: v => { runArgs.value = (v.args || '').trim(); showTarget(); }})]], r.left, r.bottom + 4);
  });
  showTarget();
  get('build-menu').addEventListener('click', () => {
    const r = get('build-menu').getBoundingClientRect();
    ECO.menu([['ビルド', () => runAction('build')], ['リビルド', () => runAction('rebuild')], ['クリーン', () => runAction('clean')], '-',
      ['提出前の確認（生成ファイル・ビルド・テスト）', () => runAction('check')]].map(item => item === '-' ? item : [...item, !busy]), r.left, r.bottom + 4);
  });

  // 出力: the runs (newest first, the last 10) are kept here and drawn by OUTPUT.view, in the footer or in a window
  // the 出力 tab was dragged out to (panels.js). A run shows its progress while it runs.
  const runs = [], toolLines = OUTPUT.toolLines;
  const OUTPUT_PANEL = {id: 'output:' + WS.dir.replaceAll('\\', '/').toLowerCase(), kind: 'output', dir: WS.dir, module: WS.module || WS.dir, title: '出力'};
  WS.footer = PANELS.footer(get('footer'), {home: WS.dir, heightKey: 'ecobuild-gui-output-height'});
  PANELS.source(OUTPUT_PANEL, () => runs);
  const publish = () => PANELS.publish(OUTPUT_PANEL.id);
  // 出力 in the toolbar (Ctrl+J, as VS Code's panel) shows or hides the footer with the output (after × too).
  const outputButton = get('toggle-output');
  const toggleOutput = () => { if (!WS.footer.toggle(OUTPUT_PANEL)) ECO.toast('出力は別の窓に出ています。', 'info'); };
  outputButton.addEventListener('click', toggleOutput);
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && !e.shiftKey && !e.altKey && !e.metaKey && e.key.toLowerCase() === 'j') { e.preventDefault(); toggleOutput(); }
  });
  const showOutputState = () => outputButton.setAttribute('aria-pressed', String(!get('footer').hidden && WS.footer.has(OUTPUT_PANEL.id)));
  new MutationObserver(showOutputState).observe(get('footer'), {attributes: true, attributeFilter: ['hidden']});
  // A container workspace builds and runs in Linux (the container's): the run's title says so.
  function begin(title, command) {
    if (box?.container) title += '（コンテナ・Linux）';
    const run = {id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, title, command, state: 'run', started: Date.now(), lines: [], progress: []};
    runs.unshift(run); runs.splice(10);
    WS.footer.reveal(OUTPUT_PANEL); publish();
    return run;
  }
  // The lines at the end: ecobuild's progress, the output of the tools and programs it ran (shown while it ran; output:
  // when the result does not have it already, as a build's or a passing test's), then the result.
  function finish(run, state, lines, stderr, output = '') {
    const ran = output.trim() ? [...toolLines(output), {text: '', kind: ''}] : [];
    Object.assign(run, {state, ended: Date.now(), lines: [...toolLines(stderr).filter(l => l.text.trim()).map(l => ({...l, kind: l.kind || 'muted'})), ...ran, ...lines]});
    WS.footer.reveal(OUTPUT_PANEL); publish();
  }
  function resultLines(action, r) {
    const where = `${r.project || '全体'}（${r.configuration}${r.profile ? '、' + r.profile : ''}）`;
    if (action === 'test') {
      const order = {failed: 0, skipped: 1, passed: 2};
      return [{text: `${where}：成功 ${r.passed}・失敗 ${r.failed}・スキップ ${r.skipped}`, kind: r.failed ? 'bad' : 'ok', head: true},
        ...[...r.cases].sort((a, b) => (order[a.status] ?? 1) - (order[b.status] ?? 1)).map(c => c.status === 'failed' ? {text: `✗ ${c.name}`, kind: 'bad'}
          : c.status === 'passed' ? {text: `✓ ${c.name}`, kind: 'ok'} : {text: `- ${c.name}（${c.status}）`, kind: 'muted'})];
    }
    if (action === 'run') return [{text: `${where} 終了コード ${r.returncode}`, kind: r.returncode ? 'bad' : 'ok', head: true}, {text: '', kind: ''}, ...(r.output ? toolLines(r.output) : [{text: '（出力なし）', kind: 'muted'}])];
    if (action === 'check') return r.items.flatMap(i => [{text: `${i.ok ? '✓' : '✗'} ${CHECK[i.name] || i.name}`, kind: i.ok ? 'ok' : 'bad'}, ...(i.detail ? toolLines(i.detail).map(l => ({...l, text: '  ' + l.text})) : [])]);
    const done = {build: 'ビルドしました', rebuild: 'リビルドしました', clean: 'クリーンしました'}[action];
    return [{text: `${done}：${where}`, kind: 'ok', head: true}, ...(r.artifacts?.length ? [{text: '成果物：', kind: 'muted'}, ...r.artifacts.map(a => ({text: '  ' + a, kind: ''}))] : [])];
  }

  // project: this Project only (the explorer's menu on a Project), without changing the target chosen next to ▶.
  async function runAction(action, only = '') {
    if (busy) return;
    const project = only || get('build-project').value, configuration = get('build-config').value;
    // ▶ on a test Project runs its tests, as Visual Studio does (ecobuild run is for executables only).
    if (action === 'run' && project && [...get('build-project').options].find(o => o.value === project)?.dataset.kind === 'test') action = 'test';
    const args = action === 'check' ? ['check'] : [action, ...(project ? ['--project', project] : []), ...(configuration ? ['--configuration', configuration] : [])];
    if (action === 'run' && get('build-run-args').value.trim()) args.push('--arguments', get('build-run-args').value.trim());
    busy = true; document.querySelectorAll('[data-build]').forEach(b => { b.disabled = true; });
    const run = begin(LABEL[action] + (project ? `：${project}` : ''), 'ecobuild ' + args.join(' '));
    const doc = await WS.cli(args, {onProgress: lines => { run.progress = lines; publish(); }});
    busy = false; document.querySelectorAll('[data-build]').forEach(b => { b.disabled = false; });
    if (!doc.ok) {
      const e = doc.error, detail = ECO.detailText(e.details);
      finish(run, 'bad', [{text: e.message, kind: 'bad', head: true}, ...(e.hint ? [{text: e.hint, kind: '', head: true}] : []), ...(detail ? [{text: '', kind: ''}, ...toolLines(detail)] : [])], doc.stderr, detail ? '' : doc.tool_output || '');
    } else {
      const r = doc.result, failed = (action === 'test' && r.failed) || (action === 'run' && r.returncode) || (action === 'check' && r.items.some(i => !i.ok));
      finish(run, failed ? 'bad' : 'ok', resultLines(action, r), doc.stderr, action === 'run' ? '' : doc.tool_output || '');
    }
    if (['build', 'rebuild', 'clean', 'check'].includes(action)) WS.refresh();
  }
  document.querySelector('.build-bar').addEventListener('click', e => { const b = e.target.closest('[data-build]'); if (b) runAction(b.dataset.build); });
  get('build-profile').addEventListener('change', async e => {
    const doc = await WS.run(['profile', 'use', e.target.value], {success: e.target.value === 'none' ? 'ビルド設定の使用をやめました。' : `このPCではビルド設定 ${e.target.value} を使います。`, refresh: false});
    if (!doc) e.target.value = selectedProfile || 'none'; else selectedProfile = e.target.value === 'none' ? null : e.target.value;
    showSetting();
  });
  // 構成・ビルド設定: one button like Visual Studio's configuration box. It shows the configuration a build uses (the one
  // chosen here, else the build setting's, else Debug) and the build setting; ▾ chooses both (a menu with two parts).
  // The values stay in the hidden selects (build-config: this screen only; build-profile: profile use, kept on this PC).
  function showSetting() {
    const configuration = get('build-config').value, profile = selectedProfile && profiles[selectedProfile];
    const used = configuration || profile?.configuration || 'Debug';
    get('build-setting-text').textContent = used + (selectedProfile ? ` · ${selectedProfile}` : '');
    get('build-setting').dataset.tip = selectedProfile ? `構成・ビルド設定（${selectedProfile}）` : '構成・ビルド設定';
  }
  get('build-setting').addEventListener('click', () => {
    const r = get('build-setting').getBoundingClientRect(), config = get('build-config'), profile = get('build-profile');
    const mark = on => on ? '✓ ' : '　';
    // Without a build setting the default is Debug itself (no item of its own); with one, 「ビルド設定のまま」 uses its configuration.
    const using = selectedProfile && profiles[selectedProfile], hasDebug = [...config.options].some(o => o.value === 'Debug');
    const help = features.configurationHelp || {};
    const configurations = [...config.options].filter(o => o.value || using || !hasDebug)
      .map(o => [mark(o.value === config.value || (!using && hasDebug && !config.value && o.value === 'Debug')) + (o.value ? o.textContent : using ? `ビルド設定のまま（${using.configuration}）` : '既定（Debug）'),
        () => { config.value = o.value; showSetting(); }, true, o.value ? help[o.value] || '' : 'ビルド設定の構成（なければ Debug）']);
    const names = [...profile.options].map(o => [mark(o.value === (selectedProfile || 'none')) + o.textContent, () => {
      if (o.value === (selectedProfile || 'none')) return;
      profile.value = o.value; profile.dispatchEvent(new Event('change'));
    }, !busy]);
    choiceMenu([['構成', null], ...configurations, '-', ['ビルド設定（このPCで使う）', null],
      ...(names.length > 1 ? names : [['　ありません（左の「設定」で追加）', null, false]])], r.left, r.bottom + 4);
  });
  // "Open in editor" split button: the button opens with the chosen editor; ▾ only chooses which one (it does not open).
  // The choice is kept per PC; Visual Studio 2026 by default.
  const EDITORS = [['2026', 'Visual Studio 2026'], ['2022', 'Visual Studio 2022']];
  let installed = null;
  const showVs = () => { get('open-vs').textContent = `VS${ECO.vsVersion()}`; };
  const openVs = version => ECO.openInVisualStudio(WS.dir, {version, build: async () => { await runAction('build'); return runs[0]?.state === 'ok' ? {} : null; }});
  showVs();
  get('open-vs').addEventListener('click', () => openVs(ECO.vsVersion()));
  get('choose-vs').addEventListener('click', async () => {
    installed ??= await ECO.call('vs-versions').catch(() => EDITORS.map(([v]) => v));
    const r = get('choose-vs').getBoundingClientRect(), current = ECO.vsVersion();
    choiceMenu(EDITORS.map(([version, name]) => [`${version === current ? '✓ ' : '　'}${name}${installed.includes(version) ? '' : '（このPCにありません）'}`,
      () => { ECO.setVsVersion(version); showVs(); }, installed.includes(version)]), r.right - 220, r.bottom + 4);
  });
  // AI (coding agent): ecobuild agent start --as <registration> opens it in a new window at the workspace's root and returns
  // at once. Only a registration a person may start (human_start) is offered; the last one chosen is kept per PC, as is the
  // command to start (--program; empty means claude). Only on a task branch (as the CLI).
  const AGENT_KEY = 'ecobuild-gui-agent', REGISTRATION_KEY = 'ecobuild-gui-agent-registration';
  const agentCommand = () => { try { return localStorage.getItem(AGENT_KEY) || ''; } catch (e) { return ''; } };
  const setAgentCommand = command => { try { localStorage.setItem(AGENT_KEY, command); } catch (e) { /* storage blocked */ } };
  const lastRegistration = () => { try { return localStorage.getItem(REGISTRATION_KEY) || ''; } catch (e) { return ''; } };
  const setLastRegistration = name => { try { localStorage.setItem(REGISTRATION_KEY, name); } catch (e) { /* storage blocked */ } };
  // The workspace as a container (ecobuild container …): the agent and the builds then run inside it. The button in the
  // bar shows it and has the container's operations and its own settings. The images are the hub's (ECOBuild × type).
  let box = null;
  // Started and stopped by ECOBuild itself (on a build or the agent; WSL stops it when idle): running or stopped, it is
  // ready to use. So the menu has no start/stop (ecobuild container start/stop remain).
  const boxState = b => b.state === 'none' ? 'まだ作っていません（使うときに作ります）' : b.state === 'unknown' ? '状態が分かりません' : '準備済み';
  // Starting an agent makes a workspace that is not a container one (ecobuild agent start: container on), so the builds
  // run in Linux from then on: said once, when the state read after the start shows it (the CLI's own line, when it was
  // read). Read again after the start, on the workspace's refresh (also when its window gets the focus) and after the
  // button's operations.
  let switching = null, containerRead = 0;
  const SWITCHED = 'エージェントはコンテナの中で動かすので、この作業空間をコンテナにしました';
  const loadContainer = async () => {
    containerRead = Date.now();
    const doc = await WS.cli(['container', 'status'], {quiet: true}); box = doc.ok ? doc.result : null;
    const button = get('container-button');
    button.classList.toggle('on', !!box?.container);
    get('container-label').textContent = box?.container ? 'コンテナ' : 'このPC';
    button.dataset.tip = !box ? 'コンテナの状態を読めませんでした' : box.container
      ? `コンテナ（Linux）：ビルド・テスト・実行はコンテナの中で動きます（${boxState(box)}）`
      : 'このPCで動いています';
    if (switching && box?.container) {
      ECO.toast(`${switching.text || SWITCHED}。以後のビルド・テスト・実行も、コンテナ（Linux）の中で動きます（このPCで動かすには「コンテナ」の「コンテナをやめる」）。`, 'info', 15000);
      switching = null;
    }
    showAgent();
  };
  WS.onRefresh(() => { if (Date.now() - containerRead > 5000) loadContainer(); });
  const boxRun = (args, options) => { switching = null; return WS.run(['container', ...args], options).then(doc => { loadContainer(); return doc; }); };
  function containerSettings() {
    return ECO.form({title: 'このコンテナの設定', intro: 'このPCだけの設定です（コミットしません）。',
      fields: [
        {name: 'deny', label: 'AI に使わせないもの', value: (box?.deny || []).join(';'), placeholder: '例：Bash(git push --force:*);WebFetch', focus: true},
        {name: 'image', label: '使うイメージ（空欄なら型のイメージ。変えると次に動かすときに作り直します）', value: box?.custom_image || '', placeholder: '例：ecobuild-cpp:9ecd459d4955'}],
      ok: '保存',
      submit: v => boxRun(['set', ...(v.deny.trim() ? ['--deny', v.deny.trim()] : ['--no-deny']), ...(v.image.trim() ? ['--image', v.image.trim()] : ['--default-image'])], {success: '設定を保存しました。'})});
  }
  // The image editor: the module's environment (.ecobuild/container/Dockerfile) of this workspace. Reading works on any
  // branch and without Docker; saving is on a task branch only and 試しに作る needs Docker (the editor greys them with
  // the reason). After a save the file shows in the commit panel. The module's settings (コンテナ) open it here too.
  const openImageEditor = () => IMAGE_EDITOR.open(WS.dir, {changed: () => { WS.refresh(); loadContainer(); }});
  window.openImageEditor = openImageEditor;
  const imageItem = ['イメージ（Dockerfile）…', openImageEditor, true, 'モジュールの環境（.ecobuild/container/Dockerfile）を見る・編集する（保存はタスクブランチで）・試しに作る'];
  get('container-button').addEventListener('click', () => {
    const r = get('container-button').getBoundingClientRect(), ready = !!box?.docker_ready;
    const noDocker = ready ? '' : `Docker が使えません（${box?.docker_detail || '状態を読めませんでした'}）。ecobuild setup --docker で導入できます`;
    const items = box?.container ? [
      [`コンテナ：${boxState(box)}${box.image ? '（' + box.image + '）' : ''}`, null],
      ...(box.state === 'none' ? [['前もって作る', () => boxRun(['start'], {busy: 'コンテナを作っています…', success: 'コンテナを作りました。'}), ready, ready ? '初めて使うときの待ち時間をなくす（イメージから作ると数分）' : noDocker]] : []),
      ...(box.state === 'none' ? [] : [
        ['作り直す', async () => { if (await boxRun(['remove'], {confirm: 'コンテナを消してから作り直します（作業空間のファイルは残ります。コンテナの中で入れたものは消えます）。', title: 'コンテナを作り直す'})) await boxRun(['start'], {busy: 'コンテナを作り直しています…', success: 'コンテナを作り直しました。'}); }, ready, noDocker],
        ['消す', () => boxRun(['remove'], {confirm: 'コンテナを消します（作業空間のファイルは残ります。コンテナの中で入れたものは消えます。次に使うときにまた作ります）。', title: 'コンテナを消す', success: 'コンテナを消しました。'}), ready, noDocker]]),
      '-',
      imageItem,
      ['このコンテナの設定…', containerSettings],
      ['コンテナのイメージ（ハブの設定）', () => ECO.action('open', {page: 'settings'}).catch(e => ECO.toast(e.message, 'bad'))],
      '-',
      ['コンテナをやめる（このPCで動かす）', () => boxRun(['off'], {confirm: 'この作業空間をコンテナにするのをやめ、コンテナを消します（作業空間のファイルは残ります。コンテナの中で入れたものは消えます）。', title: 'コンテナをやめる', success: 'コンテナをやめました。AI・ビルドはこのPCで動きます。'})],
    ] : [
      ['この作業空間はこのPCで動きます', null],
      ['コンテナにする（AI・ビルドを隔離）', () => boxRun(['on'], {success: 'コンテナにしました。AI・ビルド・テストはコンテナの中で動きます（AI は確認なし）。'}), ready, noDocker],
      '-',
      imageItem,
    ];
    ECO.menu(items, r.left, r.bottom + 4);
  });
  const showAgent = () => {
    const s = WS.status, ready = !!(s && s.task && !s.reviewing), command = agentCommand();
    get('agent-start').disabled = !ready;
    const where = box?.container ? 'コンテナの中で起動・確認なし' : '起動';
    get('agent-start').dataset.tip = ready ? `${where}：${command || 'claude'}`
      : !s ? '作業空間の状態を読み込んでいます' : 'エージェントはタスクブランチの作業空間でだけ起動できます（タスク管理で「作業を開始」してください）';
  };
  // In the Electron app the agent opens as a tab of the app's agents window (its terminal runs ecobuild agent start
  // --here --as <registration>: the container is made ready there, the progress shows in the tab). Elsewhere a new
  // console window. Each press opens a new agent (an ID of its own; any number in one workspace). Its registration and
  // name are asked first (empty name: the workspace's name and the task); a name given also becomes the conversation's
  // name (Claude Code's /rename), so it shows by that name in the list to resume. A registration that may start children
  // gets a window of its own in the app, where its children show (チーム).
  const agentShell = () => (window.ecobuildShell || (() => { try { return window.top.ecobuildShell; } catch (e) { return null; } })())?.agents;
  const defaultAgentName = () => (WS.dir.replaceAll('\\', '/').split('/').filter(Boolean).pop() || 'エージェント') + (WS.status?.task ? ` #${WS.status.task}` : '');
  const nameField = () => ({name: 'name', label: '名前', value: '', placeholder: defaultAgentName()});
  // The registrations a person may start in this workspace (the module's, as taken in: ecobuild agent registry list
  // --in-force, human_start). The module page エージェント changes them.
  async function startable() {
    const doc = await ECO.cli(WS.dir, ['agent', 'registry', 'list', '--in-force'], {quiet: true});
    if (!doc.ok) { ECO.showError(doc); return null; }
    const found = doc.result.filter(r => r.human_start);
    if (!found.length) ECO.toast('人が起動できるエージェントの登録がありません。モジュールの「エージェント」で「人が起動できる」を選んでください。', 'bad', 10000);
    return found.length ? found : null;
  }
  const registrationLabel = r => (r.title && r.title !== r.name ? `${r.title}（${r.name}）` : r.name) + (r.children?.length ? '　子を起動できる' : '');
  // The registration to use without asking (resuming the last conversation): the last chosen, else the first.
  async function defaultRegistration() {
    const found = await startable(); if (!found) return null;
    return found.find(r => r.name === lastRegistration()) || found[0];
  }
  // registration: the registration object to start ({name, children}), '' to resume a conversation by its id (its record
  // knows the registration), or undefined to ask for it (and the name).
  async function startAgent(command = agentCommand(), typed, registration) {
    if (registration === undefined) {
      const found = await startable(); if (!found) return;
      const chosen = found.find(r => r.name === lastRegistration()) || found[0];
      const v = await ECO.form({title: 'エージェントを起動', intro: box?.container ? '' : 'この作業空間は自動でコンテナにします。',
        fields: [{name: 'registration', label: '起動するエージェント', type: 'select', value: chosen.name, options: found.map(r => [r.name, registrationLabel(r)])},
                 ...(agentShell() ? [{...nameField(), focus: true}] : [])], ok: '起動'});
      if (!v) return;   // cancelled
      registration = found.find(r => r.name === v.registration) || chosen;
      setLastRegistration(registration.name);
      typed = (v.name || '').trim();
    }
    const as = registration ? registration.name : '';
    if (box && !box.container) switching = {text: ''};
    // The workspace is a frame of the module window: the Electron bridge is on the top window.
    const shell = agentShell();
    if (shell) {
      const name = typed || defaultAgentName();
      try {
        const tab = await shell.open({dir: WS.dir, agent: command, name, title: !!typed, registration: as, team: !!registration?.children?.length});
        say(`エージェントの窓で開きました：${tab?.name || name}`);
        // its terminal runs ecobuild agent start --here, which makes the workspace a container in a moment
        for (const ms of [2000, 6000, 15000]) setTimeout(() => { if (switching) loadContainer(); }, ms);
      } catch (e) { switching = null; ECO.toast(e.message, 'bad'); }
      return;
    }
    if (box?.container) say('コンテナを用意しています（最初の1回はイメージを作るので数分かかります）…');
    const doc = await WS.cli(['agent', 'start', ...(as ? ['--as', as] : []), ...(command ? ['--program', command] : [])],
      {onProgress: lines => { const line = lines.find(l => /コンテナにします/.test(l)); if (switching && line) switching.text = line.trim().replace(/[。…]+$/, '').replace(/にします（container on）$/, 'にしました'); }});
    if (switching) loadContainer();
    if (!doc.ok) return ECO.showError(doc);
    say(`エージェント「${doc.result.name}」（${doc.result.id}）を起動しました（新しい画面で動いています）`);
  }
  get('agent-start').addEventListener('click', () => startAgent(agentCommand(), undefined, undefined));
  // Resuming is Claude Code's (claude --resume <id>): the chosen command's options (model …) are kept. The tab takes the
  // conversation's name (no name is asked); the conversation's record knows its registration.
  const claudeCommand = () => { const command = agentCommand(); return !command ? 'claude' : /^claude(\s|$)/.test(command) ? command : null; };
  const when = iso => { const d = new Date(iso); return isNaN(d) ? '' : `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
  // The workspace's conversations (ecobuild agent conversations: in the container, the ones on this branch), newest first.
  async function chooseConversation(x, y) {
    const base = claudeCommand();
    const doc = await WS.cli(['agent', 'conversations'], {quiet: true});
    if (!doc.ok) return ECO.showError(doc);
    const list = doc.result.conversations;
    ECO.menu([
      [list.length ? '再開する会話（新しい順）' : (doc.result.note || 'この作業空間の会話はまだありません'), null],
      // a registration is passed too: the CLI uses the conversation's record if it has one, otherwise this registration
      ...list.map(c => [`${c.title}　${when(c.updated)}`, async () => { const r = await defaultRegistration(); if (r) startAgent(`${base} --resume ${c.id}`, c.title, r); }, true,
        `発言 ${c.prompts}${c.branch ? `・${c.branch}` : ''}・${c.id}`]),
      '-',
      // --continue: the CLI needs a registration (the last conversation may be no agent's record yet)
      ['最後の会話の続きから', async () => { const r = await defaultRegistration(); if (r) startAgent(`${base} --continue`, '', r); }, list.length > 0],
      ['Claude の一覧で選ぶ', async () => { const r = await defaultRegistration(); if (r) startAgent(`${base} --resume`, '', r); }, true, 'Claude Code の再開の画面で選びます（検索・プレビューができます）'],
    ], x, y);
  }
  get('agent-more').addEventListener('click', () => {
    const r = get('agent-more').getBoundingClientRect(), ready = !get('agent-start').disabled;
    ECO.menu([
      ...(claudeCommand() ? [['会話を選んで再開…', () => chooseConversation(r.right - 320, r.bottom + 4), ready], '-'] : []),
      ['起動するコマンドを指定…', () => ECO.form({title: '起動するコマンド', intro: 'このPCで覚えておきます。', fields: [
        {name: 'command', label: 'コマンド（空欄なら claude）', value: agentCommand(), placeholder: '例：claude --model opus', focus: true}], ok: '保存',
        submit: v => { setAgentCommand(v.command.trim()); showAgent(); }})],
      ['エージェントの登録（モジュールの「エージェント」）', () => ECO.action('open', {module: WS.dir, page: 'agents'}).catch(e => ECO.toast(e.message, 'bad')), true,
        '起動できるエージェント（文書・渡すツール・人が起動できるか・起動してよい子）は、モジュールの「エージェント」で変えます（ハブの設定はこのPCのプリセット）'],
      ['AGENTS.md を作る', () => WS.run(['agent', 'init'], {success: 'AGENTS.md を作りました。コミットしてください。'}).then(doc => doc && WS.reloadFiles?.()), ready],
      ['AI向けの作業の手順を見る', async () => { const doc = await WS.cli(['agent', 'guide'], {quiet: true}); return doc.ok ? ECO.output('AI向けの作業の手順', doc.result.text) : ECO.showError(doc); }],
    ], r.right - 240, r.bottom + 4);
  });
  WS.onRefresh(showAgent);
  showAgent();
  loadContainer();

  loadOptions();   // the build settings and Projects do not need the status
  WS.reloadBuildOptions = loadOptions;
  WS.buildProject = (action, project) => runAction(action, project);
  // The explorer's 「実行の対象にする」: the target next to ▶ (as Visual Studio's startup project).
  WS.setTarget = project => {
    const select = get('build-project');
    if (![...select.options].some(o => o.value === project)) return false;
    select.value = project; showTarget(); return true;
  };
})();
