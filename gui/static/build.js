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
      get('build-project').innerHTML = '<option value="">すべてのProject</option>' + j.result.map(x => `<option value="${esc(x.name)}" data-kind="${esc(x.kind)}">${esc(x.name)}（${esc(x.kind)}）</option>`).join('');
      if (j.result.some(x => x.name === chosen)) get('build-project').value = chosen;
      showTarget();
    }
  }
  // The Project to build・run・test: ▾ next to ▶ chooses it (a menu); its name shows on hover. The value is kept in the
  // hidden select (build-project), which runAction reads.
  // The same ▾ also holds the arguments for 実行 (a type without Projects has only these).
  function showTarget() {
    const select = get('build-project'), name = select.selectedOptions[0]?.textContent, runArgs = get('build-run-args').value;
    get('build-project-pick').dataset.tip = [name ? `対象：${name}` : '実行の設定', runArgs ? `引数：${runArgs}` : ''].filter(Boolean).join('　');
    get('build-project-pick').classList.toggle('chosen', !!select.value || !!runArgs);
  }
  get('build-project-pick').addEventListener('click', () => {
    const select = get('build-project'), r = get('build-project-pick').getBoundingClientRect(), runArgs = get('build-run-args');
    const projects = [...select.options].map(o => [(o.value === select.value ? '✓ ' : '　') + o.textContent, () => { select.value = o.value; showTarget(); }]);
    ECO.menu([...projects, ...(projects.length ? ['-'] : []), [runArgs.value ? `実行時の引数：${runArgs.value}…` : '実行時の引数…', () => ECO.form({
      title: '実行時の引数', intro: '「実行」で、プログラムに渡す引数です（空白で区切る）。この画面を閉じるまで使います。',
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
  function begin(title, command) {
    const run = {id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, title, command, state: 'run', started: Date.now(), lines: [], progress: []};
    runs.unshift(run); runs.splice(10);
    WS.footer.reveal(OUTPUT_PANEL); publish();
    return run;
  }
  function finish(run, state, lines, stderr) {
    Object.assign(run, {state, ended: Date.now(), lines: [...toolLines(stderr).filter(l => l.text.trim()).map(l => ({...l, kind: l.kind || 'muted'})), ...lines]});
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
      finish(run, 'bad', [{text: e.message, kind: 'bad', head: true}, ...(e.hint ? [{text: e.hint, kind: '', head: true}] : []), ...(detail ? [{text: '', kind: ''}, ...toolLines(detail)] : [])], doc.stderr);
    } else {
      const r = doc.result, failed = (action === 'test' && r.failed) || (action === 'run' && r.returncode) || (action === 'check' && r.items.some(i => !i.ok));
      finish(run, failed ? 'bad' : 'ok', resultLines(action, r), doc.stderr);
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
    const fromProfile = selectedProfile && profiles[selectedProfile] ? `ビルド設定のまま（${profiles[selectedProfile].configuration}）` : '既定（Debug）';
    const help = features.configurationHelp || {};
    const configurations = [...config.options].map(o => [mark(o.value === config.value) + (o.value ? o.textContent : fromProfile), () => { config.value = o.value; showSetting(); }, true,
      o.value ? help[o.value] || '' : 'ビルド設定の構成（なければ Debug）']);
    const names = [...profile.options].map(o => [mark(o.value === (selectedProfile || 'none')) + o.textContent, () => {
      if (o.value === (selectedProfile || 'none')) return;
      profile.value = o.value; profile.dispatchEvent(new Event('change'));
    }, !busy]);
    ECO.menu([['構成', null], ...configurations, '-', ['ビルド設定（このPCで使う）', null],
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
    ECO.menu(EDITORS.map(([version, name]) => [`${version === current ? '✓ ' : '　'}${name}${installed.includes(version) ? '' : '（このPCにありません）'}`,
      () => { ECO.setVsVersion(version); showVs(); }, installed.includes(version)]), r.right - 220, r.bottom + 4);
  });
  // AI (coding agent): ecobuild agent start opens it in a new window at the workspace's root and returns at once.
  // The command to start (--agent) is kept per PC; empty means ECOBuild's default. Only on a task branch (as the CLI).
  const AGENT_KEY = 'ecobuild-gui-agent';
  const agentCommand = () => { try { return localStorage.getItem(AGENT_KEY) || ''; } catch (e) { return ''; } };
  const setAgentCommand = command => { try { localStorage.setItem(AGENT_KEY, command); } catch (e) { /* storage blocked */ } };
  // The workspace as a container (ecobuild container …): the agent and the builds then run inside it. The button in the
  // bar shows it and has the container's operations and its own settings. The images are the hub's (ECOBuild × type).
  let box = null;
  // Started and stopped by ECOBuild itself (on a build or the agent; WSL stops it when idle): running or stopped, it is
  // ready to use. So the menu has no start/stop (ecobuild container start/stop remain).
  const boxState = b => b.state === 'none' ? 'まだ作っていません（使うときに作ります）' : b.state === 'unknown' ? '状態が分かりません' : '準備済み';
  const loadContainer = async () => {
    const doc = await WS.cli(['container', 'status'], {quiet: true}); box = doc.ok ? doc.result : null;
    const button = get('container-button');
    button.classList.toggle('on', !!box?.container);
    get('container-label').textContent = box?.container ? 'コンテナ' : 'このPC';
    button.dataset.tip = !box ? 'コンテナの状態を読めませんでした' : box.container
      ? `この作業空間はコンテナ（${boxState(box)}）。AI・ビルド・テストは中で動きます`
      : 'この作業空間はこのPCで動きます（コンテナにすると AI・ビルドを隔離できます）';
    showAgent();
  };
  const boxRun = (args, options) => WS.run(['container', ...args], options).then(doc => { loadContainer(); return doc; });
  function containerSettings() {
    return ECO.form({title: 'このコンテナの設定', intro: 'この作業空間のコンテナだけの設定です（このPCだけ。コミットしません）。使わせないものは、このPCの設定（ecobuild config set agent_deny）に足されます。',
      fields: [
        {name: 'deny', label: 'AI に使わせないもの（Claude Code の許可の規則を ; で区切る。空欄ならなし）', value: (box?.deny || []).join(';'), placeholder: '例：Bash(git push --force:*);WebFetch', focus: true},
        {name: 'image', label: '使うイメージ（空欄なら型のイメージ。変えると次に動かすときに作り直します）', value: box?.custom_image || '', placeholder: '例：ecobuild-cpp:9ecd459d4955'}],
      ok: '保存',
      submit: v => boxRun(['set', ...(v.deny.trim() ? ['--deny', v.deny.trim()] : ['--no-deny']), ...(v.image.trim() ? ['--image', v.image.trim()] : ['--default-image'])], {success: '設定を保存しました。'})});
  }
  get('container-button').addEventListener('click', () => {
    const r = get('container-button').getBoundingClientRect(), ready = !!box?.docker_ready;
    const noDocker = ready ? '' : `Docker が使えません（${box?.docker_detail || '状態を読めませんでした'}）。ecobuild setup --docker で導入できます`;
    const items = box?.container ? [
      [`コンテナ：${boxState(box)}${box.image ? '（' + box.image + '）' : ''}`, null],
      ...(box.state === 'none' ? [['前もって作る（初めて使うときの待ち時間をなくす。イメージから作ると数分）', () => boxRun(['start'], {busy: 'コンテナを作っています…', success: 'コンテナを作りました。'}), ready, noDocker]] : []),
      ...(box.state === 'none' ? [] : [
        ['作り直す', async () => { if (await boxRun(['remove'], {confirm: 'コンテナを消してから作り直します（作業空間のファイルは残ります。コンテナの中で入れたものは消えます）。', title: 'コンテナを作り直す'})) await boxRun(['start'], {busy: 'コンテナを作り直しています…', success: 'コンテナを作り直しました。'}); }, ready, noDocker],
        ['消す', () => boxRun(['remove'], {confirm: 'コンテナを消します（作業空間のファイルは残ります。コンテナの中で入れたものは消えます。次に使うときにまた作ります）。', title: 'コンテナを消す', success: 'コンテナを消しました。'}), ready, noDocker]]),
      '-',
      ['このコンテナの設定…', containerSettings],
      ['コンテナのイメージ（ハブの設定）', () => ECO.action('open', {page: 'settings'}).catch(e => ECO.toast(e.message, 'bad'))],
      '-',
      ['コンテナをやめる（このPCで動かす）', () => boxRun(['off'], {confirm: 'この作業空間をコンテナにするのをやめ、コンテナを消します（作業空間のファイルは残ります。コンテナの中で入れたものは消えます）。', title: 'コンテナをやめる', success: 'コンテナをやめました。AI・ビルドはこのPCで動きます。'})],
    ] : [
      ['この作業空間はこのPCで動きます', null],
      ['コンテナにする（AI・ビルドを隔離）', () => boxRun(['on'], {success: 'コンテナにしました。AI・ビルド・テストはコンテナの中で動きます（AI は確認なし）。'}), ready, noDocker],
    ];
    ECO.menu(items, r.left, r.bottom + 4);
  });
  const showAgent = () => {
    const s = WS.status, ready = !!(s && s.task && !s.reviewing), command = agentCommand();
    get('agent-start').disabled = !ready;
    const where = box?.container ? 'この作業空間のコンテナの中で、AIを確認なしに新しい画面で起動します' : 'この作業空間のルートで、AIを新しい画面で起動します';
    get('agent-start').title = ready ? `${where}（${command || '既定のエージェント'}）`
      : !s ? '作業空間の状態を読み込んでいます' : 'エージェントはタスクブランチの作業空間でだけ起動できます（タスク管理で「作業を開始」してください）';
  };
  // In the Electron app the agent opens as a tab of the app's agents window (its terminal runs ecobuild agent start
  // --here: the container is made ready there, the progress shows in the tab). Elsewhere a new console window.
  // Each press opens a new agent. Its name is asked first (empty: the workspace's name and the task); a name given
  // also becomes the conversation's name (Claude Code's /rename), so it shows by that name in the list to resume.
  const agentShell = () => (window.ecobuildShell || (() => { try { return window.top.ecobuildShell; } catch (e) { return null; } })())?.agents;
  const defaultAgentName = () => (WS.dir.replaceAll('\\', '/').split('/').filter(Boolean).pop() || 'エージェント') + (WS.status?.task ? ` #${WS.status.task}` : '');
  const nameField = () => ({name: 'name', label: '名前（空欄なら既定の名前。入れた名前は会話の名前にもなります）', value: '', placeholder: defaultAgentName()});
  // role 'lead': the 進行役 (only talks with the user; hands what was decided to the one 管理役 under it, which makes the
  // 作業役 = child tasks in their own workspaces; does not edit). It gets a window of its own with its tab fixed at the left.
  // The agent always runs in the container: a workspace that is not one is made so (container on) when it starts.
  async function startAgent(command = agentCommand(), typed, role = '') {
    // The workspace is a frame of the module window: the Electron bridge is on the top window.
    const shell = agentShell();
    const title = role === 'lead' ? '進行役を起動' : 'エージェントを起動';
    if (shell) {
      if (typed === undefined) {
        const v = await ECO.form({title, intro: role === 'lead' ? '進行役は、ユーザーとのやりとりに特化した役です。決めたことを自分の下の管理役に命令し、管理役が作業役（子タスクと、その作業空間）に任せて進めます。自分ではファイルを編集せず、作業役も直接作りません。新しい窓で開きます。コンテナでない作業空間は、自動でコンテナにします。' : undefined,
          fields: [{...nameField(), focus: true}], ok: '起動'});
        if (!v) return;   // cancelled
        typed = v.name.trim();
      }
      const name = typed || defaultAgentName();
      try { const tab = await shell.open({dir: WS.dir, agent: command, name, title: !!typed, role}); say(`エージェントの窓で開きました：${tab?.name || name}`); }
      catch (e) { ECO.toast(e.message, 'bad'); }
      return;
    }
    if (box?.container) say('コンテナを用意しています（最初の1回はイメージを作るので数分かかります）…');
    const doc = await WS.cli(['agent', 'start', ...(command ? ['--agent', command] : []), ...(role ? ['--role', role] : [])]);
    if (!doc.ok) return ECO.showError(doc);
    say(`エージェントを起動しました：${doc.result.command.join(' ')}（新しい画面で動いています）`);
  }
  get('agent-start').addEventListener('click', () => startAgent());
  // Resuming is Claude Code's (claude --resume <id>): the chosen command's options (model …) are kept. The tab takes the
  // conversation's name (no name is asked).
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
      ...list.map(c => [`${c.title}　${when(c.updated)}`, () => startAgent(`${base} --resume ${c.id}`, c.title), true,
        `発言 ${c.prompts}${c.branch ? `・${c.branch}` : ''}・${c.id}`]),
      '-',
      ['最後の会話の続きから', () => startAgent(`${base} --continue`, ''), list.length > 0],
      ['Claude の一覧で選ぶ', () => startAgent(`${base} --resume`, ''), true, 'Claude Code の再開の画面で選びます（検索・プレビューができます）'],
    ], x, y);
  }
  get('agent-more').addEventListener('click', () => {
    const r = get('agent-more').getBoundingClientRect(), ready = !get('agent-start').disabled;
    ECO.menu([
      ...(claudeCommand() ? [['進行役を起動…', () => startAgent(agentCommand(), undefined, 'lead'), ready,
        'ユーザーとの話に特化し、決めたことを下の管理役に命令するエージェント（管理役が作業役に任せて進めます）。新しい窓で開きます'],
        ['会話を選んで再開…', () => chooseConversation(r.right - 320, r.bottom + 4), ready,
        'これまでの会話から選び、その続きからエージェントを起動します'], '-'] : []),
      ['起動するコマンドを指定…', () => ECO.form({title: 'エージェントを起動', intro: '起動するエージェントのコマンドです（引数は空白で区切る）。このPCで覚えておき、「エージェント」のボタンでも使います。', fields: [
        {name: 'command', label: 'コマンド（空欄なら既定のエージェント）', value: agentCommand(), placeholder: '例：claude', focus: true},
        ...(ready && agentShell() ? [nameField()] : [])], ok: ready ? '起動' : '保存',
        submit: async v => { setAgentCommand(v.command.trim()); showAgent(); if (ready) await startAgent(v.command.trim(), (v.name || '').trim()); }})],
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
