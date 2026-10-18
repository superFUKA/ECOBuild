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

  // 出力 (under the work area, as an IDE's output pane): what a build・test・run・check reported, line by line. Errors and
  // warnings are colored and counted (the counts show only them); a file(line) in a line opens in Visual Studio. The
  // search box narrows the lines; the pane's height is dragged at its top edge (kept on this PC), ⤢ enlarges it.
  // The last 10 outputs stay (「履歴」). A line: {text, kind} — ok・bad・warn・muted, or the kind read from the text;
  // head: ecobuild's own message (colored, not counted).
  const runs = [], HEIGHT_KEY = 'ecobuild-gui-output-height';
  let shown = null, onlyProblems = false, ticker = null;
  const pane = get('build-output'), text = get('build-output-text'), search = get('build-output-search');
  // A tool's summary (Build FAILED. / 2 Error(s) / 0 個の警告) is not counted: the lines it counts are.
  const kindOf = line => /^\s*(Build (FAILED|succeeded)\.?|\d+ (Warning|Error)\(s\)|\d+ 個の(警告|エラー))\s*$|\b0 (errors?|warnings?)\b/i.test(line) ? 'muted'
    : /\b(fatal )?error\b|\bFAILED\b|エラー|^Traceback |^E {3}/i.test(line) ? 'bad' : /\bwarning\b|警告/i.test(line) ? 'warn' : '';
  const toolLines = (output, kind = null) => String(output || '').replace(/\r/g, '').replace(/\n+$/, '').split('\n').map(t => ({text: t, kind: kind ?? kindOf(t)}));
  // A file and line in a compiler's or Python's message: C:\…\a.cpp(12,5)・src/a.cpp:12:5・File "…\a.py", line 12.
  const SOURCE = 'c|cc|cpp|cxx|c\\+\\+|h|hh|hpp|hxx|inl|ixx|ipp|py|pyi|cmake|txt|toml|json|cs|rs|js|ts';
  const FILE_AT = new RegExp(`File "([^"]+)", line (\\d+)|((?:[A-Za-z]:)?[\\w.\\-\\\\/]*\\.(?:${SOURCE}))(?:\\((\\d+)(?:,\\d+)?\\)|:(\\d+)(?::\\d+)?)`, 'gi');
  const inWorkspace = path => {
    const p = path.replaceAll('\\', '/'), root = WS.dir.replaceAll('\\', '/').replace(/\/+$/, '') + '/';
    if (p.toLowerCase().startsWith(root.toLowerCase())) return p.slice(root.length);
    return /^([A-Za-z]:|\/)/.test(p) ? '' : p.replace(/^\.\//, '');
  };
  const mark = (s, q) => {
    if (!q) return esc(s);
    let out = '', at = 0, i; const low = s.toLowerCase();
    while ((i = low.indexOf(q, at)) >= 0) { out += esc(s.slice(at, i)) + `<mark>${esc(s.slice(i, i + q.length))}</mark>`; at = i + q.length; }
    return out + esc(s.slice(at));
  };
  const lineHtml = (s, q) => {
    let out = '', at = 0;
    for (const m of s.matchAll(FILE_AT)) {
      const relative = inWorkspace(m[1] || m[3]), line = m[2] || m[4] || m[5];
      if (!relative) continue;
      out += mark(s.slice(at, m.index), q) + `<a href="#" data-open="${esc(relative)}" title="${esc(relative)} を開く（${line} 行目）">${mark(m[0], q)}</a>`;
      at = m.index + m[0].length;
    }
    return out + mark(s.slice(at), q);
  };
  const seconds = run => (((run.ended || Date.now()) - run.started) / 1000).toFixed(run.ended ? 1 : 0) + ' 秒';
  function render({follow = false} = {}) {
    const run = shown; if (!run) return;
    pane.hidden = false;
    get('build-output-title').textContent = run.title;
    get('build-output-state').textContent = run.state === 'ok' ? '成功' : run.state === 'run' ? '実行中…' : '失敗';
    get('build-output-state').className = 'build-state ' + (run.state === 'run' ? 'run' : run.state);
    get('build-output-time').textContent = seconds(run);
    const lines = [{text: run.command, kind: 'muted'}, ...(run.state === 'run' ? (run.progress || []).map(t => ({text: t, kind: 'muted'})) : run.lines)];
    const errors = lines.filter(l => l.kind === 'bad' && !l.head).length, warnings = lines.filter(l => l.kind === 'warn' && !l.head).length;
    get('build-output-counts').innerHTML = (errors ? `<span class="bad">エラー ${errors}</span>` : '') + (warnings ? `<span class="warn">警告 ${warnings}</span>` : '');
    get('build-output-counts').hidden = !errors && !warnings;
    const q = search.value.trim().toLowerCase();
    const visible = lines.filter(l => (!onlyProblems || l.kind === 'bad' || l.kind === 'warn') && (!q || l.text.toLowerCase().includes(q)));
    text.innerHTML = visible.map(l => `<span class="line ${l.kind || ''}${l.head ? ' head' : ''}">${lineHtml(l.text, q) || ' '}</span>`).join('')
      || `<span class="line muted">${onlyProblems ? 'エラー・警告はありません。' : '一致する行はありません。'}</span>`;
    get('build-output-shown').textContent = visible.length < lines.length ? `${visible.length} / ${lines.length} 行` : '';
    if (follow) text.scrollTop = text.scrollHeight;
  }
  function show(run) {
    shown = run; render();
    const first = run.state === 'bad' && text.querySelector('.line.bad:not(.head)');
    if (first) first.scrollIntoView({block: 'center'}); else text.scrollTop = 0;
  }
  function begin(title, command) {
    const run = {title, command, state: 'run', started: Date.now(), lines: [], progress: []};
    runs.unshift(run); runs.splice(10);
    shown = run; render();
    clearInterval(ticker); ticker = setInterval(() => { if (shown === run) get('build-output-time').textContent = seconds(run); }, 1000);
    return run;
  }
  function finish(run, state, lines, stderr) {
    clearInterval(ticker);
    Object.assign(run, {state, ended: Date.now(), lines: [...toolLines(stderr).filter(l => l.text.trim()).map(l => ({...l, kind: l.kind || 'muted'})), ...lines]});
    show(run);
  }
  get('build-output-counts').addEventListener('click', () => { onlyProblems = !onlyProblems; syncToggle(); render(); });
  const syncToggle = () => { get('build-output-problems').setAttribute('aria-pressed', String(onlyProblems)); };
  search.addEventListener('input', () => render());
  text.addEventListener('click', e => { const a = e.target.closest('[data-open]'); if (a) { e.preventDefault(); WS.openInEditor?.(a.dataset.open); } });
  get('build-output-tools').addEventListener('click', e => {
    const what = e.target.closest('[data-out]')?.dataset.out; if (!what || !shown) return;
    if (what === 'problems') { onlyProblems = !onlyProblems; syncToggle(); render(); }
    if (what === 'wrap') { const on = text.classList.toggle('nowrap'); e.target.closest('button').setAttribute('aria-pressed', String(!on)); }
    if (what === 'copy') ECO.copyText([shown.command, ...shown.lines.map(l => l.text)].join('\n'));
    if (what === 'max') { const on = pane.classList.toggle('max'); e.target.closest('button').setAttribute('aria-pressed', String(on)); }
    if (what === 'history') {
      const r = e.target.closest('button').getBoundingClientRect();
      ECO.menu(runs.map(run => [`${run === shown ? '✓ ' : '　'}${run.title}・${run.state === 'ok' ? '成功' : run.state === 'run' ? '実行中' : '失敗'}・${new Date(run.started).toLocaleTimeString()}`,
        () => show(run)]), r.right - 260, r.bottom + 4);
    }
  });
  // The height: dragged at the top edge, kept on this PC.
  try { const h = Number(localStorage.getItem(HEIGHT_KEY)); if (h) pane.style.height = h + 'px'; } catch (e) { /* storage blocked */ }
  get('build-output-resize').addEventListener('pointerdown', e => {
    e.preventDefault();
    const startY = e.clientY, startHeight = pane.getBoundingClientRect().height;
    pane.classList.remove('max'); get('build-output-tools').querySelector('[data-out=max]').setAttribute('aria-pressed', 'false');
    const move = m => { pane.style.height = Math.max(90, Math.min(window.innerHeight - 140, startHeight + startY - m.clientY)) + 'px'; };
    const up = () => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      try { localStorage.setItem(HEIGHT_KEY, String(Math.round(pane.getBoundingClientRect().height))); } catch (err) { /* storage blocked */ }
    };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  });
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
    const doc = await WS.cli(args, {onProgress: lines => { run.progress = lines; if (shown === run) render({follow: true}); }});
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
  get('build-output-close').addEventListener('click', () => { pane.hidden = true; });
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
  const showAgent = () => {
    const s = WS.status, ready = !!(s && s.task && !s.reviewing), command = agentCommand();
    get('agent-start').disabled = !ready;
    get('agent-start').title = ready ? `この作業空間のルートで、AIを新しい画面で起動します（${command || '既定のエージェント'}）`
      : !s ? '作業空間の状態を読み込んでいます' : 'エージェントはタスクブランチの作業空間でだけ起動できます（タスク管理で「作業を開始」してください）';
  };
  async function startAgent(command = agentCommand()) {
    const doc = await WS.cli(['agent', 'start', ...(command ? ['--agent', command] : [])]);
    if (!doc.ok) return ECO.showError(doc);
    say(`エージェントを起動しました：${doc.result.command.join(' ')}（新しい画面で動いています）`);
  }
  get('agent-start').addEventListener('click', () => startAgent());
  get('agent-more').addEventListener('click', () => {
    const r = get('agent-more').getBoundingClientRect(), ready = !get('agent-start').disabled;
    ECO.menu([
      ['起動するコマンドを指定…', () => ECO.form({title: 'エージェントを起動', intro: '起動するエージェントのコマンドです（引数は空白で区切る）。このPCで覚えておき、「エージェント」のボタンでも使います。', fields: [
        {name: 'command', label: 'コマンド（空欄なら既定のエージェント）', value: agentCommand(), placeholder: '例：claude', focus: true}], ok: ready ? '起動' : '保存',
        submit: async v => { setAgentCommand(v.command.trim()); showAgent(); if (ready) await startAgent(v.command.trim()); }})],
      ['AGENTS.md を作る', () => WS.run(['agent', 'init'], {success: 'AGENTS.md を作りました。コミットしてください。'}).then(doc => doc && WS.reloadFiles?.()), ready],
      ['AI向けの作業の手順を見る', async () => { const doc = await WS.cli(['agent', 'guide'], {quiet: true}); return doc.ok ? ECO.output('AI向けの作業の手順', doc.result.text) : ECO.showError(doc); }],
    ], r.right - 240, r.bottom + 4);
  });
  WS.onRefresh(showAgent);
  showAgent();

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
