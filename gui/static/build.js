'use strict';
// Build / test / run toolbar of a place. Runs ecobuild build・test・run・rebuild・clean・check and shows the result.
// What it offers follows the module's type (the configurations; Visual Studio only for types that make a solution).
// It also starts the AI (coding agent) in the workspace: ecobuild agent start.
WS.onRefresh(renderPrDetail);
(() => {
  const LABEL = {build: 'ビルド', rebuild: 'リビルド', clean: 'クリーン', test: 'テスト', run: '実行', check: '提出前の確認'};
  const CHECK = {generated: '生成ファイルが最新', conflict_markers: '衝突マーカーがない', build: 'ビルド', test: 'テスト'};
  let profiles = {}, selectedProfile = null, busy = false;

  async function loadOptions() {
    const [p, j, type] = await Promise.all([WS.cli(['profile', 'list'], {quiet: true}), WS.cli(['project', 'list'], {quiet: true}), ECO.moduleType(WS.dir)]);
    const features = ECO.typeFeatures(type), config = get('build-config'), chosen = config.value;
    config.innerHTML = '<option value="">ビルド設定のまま</option>' + features.configurations.map(c => `<option>${esc(c)}</option>`).join('');
    config.value = features.configurations.includes(chosen) ? chosen : '';
    get('vs-group').hidden = !features.solution;
    if (p.ok) {
      profiles = p.result.profiles; selectedProfile = p.result.selected;
      const names = Object.keys(profiles);
      get('build-profile').innerHTML = names.map(n => `<option value="${esc(n)}">${esc(n)}（${esc(profiles[n].configuration)}${profiles[n].shared ? '・共有' : ''}）</option>`).join('') + '<option value="none">使わない</option>';
      get('build-profile').value = selectedProfile || 'none';
      get('build-profile').disabled = !names.length; get('build-profile').title = names.length ? '' : 'ビルド設定はありません（モジュールの「ビルド設定」タブで追加できます）';
    }
    get('build-project-label').hidden = !j.ok;
    if (j.ok) get('build-project').innerHTML = '<option value="">すべてのProject</option>' + j.result.map(x => `<option value="${esc(x.name)}" data-kind="${esc(x.kind)}">${esc(x.name)}（${esc(x.kind)}）</option>`).join('');
  }

  const out = (title, state, html) => {
    get('build-output-title').textContent = title;
    get('build-output-state').textContent = state === 'ok' ? '成功' : state === 'run' ? '実行中…' : '失敗';
    get('build-output-state').className = 'build-state ' + (state === 'run' ? '' : state);
    get('build-output-text').innerHTML = html; get('build-output').hidden = false;
  };
  function resultText(action, r) {
    if (action === 'test') return `${esc(r.project || '全体')}（${esc(r.configuration)}）：成功 ${r.passed}・失敗 ${r.failed}・スキップ ${r.skipped}\n` + r.cases.map(c => `<span class="${c.status === 'passed' ? 'ok' : c.status === 'failed' ? 'bad' : ''}">${c.status === 'passed' ? '✓' : c.status === 'failed' ? '✗' : '-'} ${esc(c.name)}</span>`).join('\n');
    if (action === 'run') return `${esc(r.project || '')}（${esc(r.configuration)}）終了コード ${r.returncode}\n\n${esc(r.output || '（出力なし）')}`;
    if (action === 'check') return r.items.map(i => `<span class="${i.ok ? 'ok' : 'bad'}">${i.ok ? '✓' : '✗'} ${esc(CHECK[i.name] || i.name)}</span>${i.detail ? '\n  ' + esc(i.detail) : ''}`).join('\n');
    const done = {build: 'ビルドしました', rebuild: 'リビルドしました', clean: 'クリーンしました'}[action];
    return `${done}：${esc(r.project || '全体')}（${esc(r.configuration)}${r.profile ? '、' + esc(r.profile) : ''}）` + (r.artifacts?.length ? '\n\n成果物：\n' + r.artifacts.map(a => '  ' + esc(a)).join('\n') : '');
  }

  async function runAction(action) {
    if (busy) return;
    get('build-more').removeAttribute('open');
    const project = get('build-project').value, configuration = get('build-config').value;
    const args = action === 'check' ? ['check'] : [action, ...(project ? ['--project', project] : []), ...(configuration ? ['--configuration', configuration] : [])];
    if (action === 'run' && get('build-run-args').value.trim()) args.push('--arguments', get('build-run-args').value.trim());
    busy = true; document.querySelectorAll('[data-build]').forEach(b => { b.disabled = true; });
    out(LABEL[action], 'run', esc('ecobuild ' + args.join(' ')));
    const doc = await WS.cli(args);
    busy = false; document.querySelectorAll('[data-build]').forEach(b => { b.disabled = false; });
    if (!doc.ok) {
      const e = doc.error, detail = ECO.detailText(e.details);
      out(LABEL[action], 'bad', `<span class="bad">${esc(e.message)}</span>${e.hint ? '\n' + esc(e.hint) : ''}${detail ? '\n\n' + esc(detail) : ''}`);
    } else {
      const r = doc.result, failed = (action === 'test' && r.failed) || (action === 'run' && r.returncode) || (action === 'check' && r.items.some(i => !i.ok));
      out(LABEL[action], failed ? 'bad' : 'ok', resultText(action, r));
    }
    get('build-output-text').scrollTop = 0;
    if (['build', 'rebuild', 'clean', 'check'].includes(action)) WS.refresh();
  }
  document.querySelector('.build-bar').addEventListener('click', e => { const b = e.target.closest('[data-build]'); if (b) runAction(b.dataset.build); });
  get('build-output-close').addEventListener('click', () => { get('build-output').hidden = true; });
  get('build-profile').addEventListener('change', async e => {
    const doc = await WS.run(['profile', 'use', e.target.value], {success: e.target.value === 'none' ? 'ビルド設定の使用をやめました。' : `このPCではビルド設定 ${e.target.value} を使います。`, refresh: false});
    if (!doc) e.target.value = selectedProfile || 'none'; else selectedProfile = e.target.value === 'none' ? null : e.target.value;
  });
  // "Open in editor" split button: the button opens with the chosen editor; ▾ only chooses which one (it does not open).
  // The choice is kept per PC; Visual Studio 2026 by default.
  const EDITORS = [['2026', 'Visual Studio 2026'], ['2022', 'Visual Studio 2022']];
  let installed = null;
  const showVs = () => { get('open-vs').textContent = `VS${ECO.vsVersion()} で開く`; };
  const openVs = version => ECO.openInVisualStudio(WS.dir, {version, build: async () => { await runAction('build'); return get('build-output-state').classList.contains('ok') ? {} : null; }});
  showVs();
  get('open-vs').addEventListener('click', () => openVs(ECO.vsVersion()));
  get('choose-vs').addEventListener('click', async () => {
    installed ??= await ECO.call('vs-versions').catch(() => EDITORS.map(([v]) => v));
    const r = get('choose-vs').getBoundingClientRect(), current = ECO.vsVersion();
    ECO.menu(EDITORS.map(([version, name]) => [`${version === current ? '✓ ' : '　'}${name}${installed.includes(version) ? '' : '（このPCにありません）'}`,
      () => { ECO.setVsVersion(version); showVs(); }, installed.includes(version)]), r.right - 220, r.bottom + 4);
  });
  // AI (coding agent): ecobuild agent start opens it in a new window at the workspace's root and returns at once.
  // The command to start (--agent) is kept per PC; empty means ECOBuild's default.
  const AGENT_KEY = 'ecobuild-gui-agent';
  const agentCommand = () => { try { return localStorage.getItem(AGENT_KEY) || ''; } catch (e) { return ''; } };
  const setAgentCommand = command => { try { localStorage.setItem(AGENT_KEY, command); } catch (e) { /* storage blocked */ } };
  const showAgent = () => {
    const s = WS.status, ready = !!(s && s.workspace && !s.reviewing), command = agentCommand();
    get('agent-start').disabled = !ready;
    get('agent-start').title = ready ? `この作業空間のルートで、AIを新しい画面で起動します（${command || '既定のエージェント'}）` : 'AIは作業空間で起動します（タスク管理で「作業を開始」してください）';
  };
  async function startAgent(command = agentCommand()) {
    const doc = await WS.cli(['agent', 'start', ...(command ? ['--agent', command] : [])]);
    if (!doc.ok) return ECO.showError(doc);
    say(`AIを起動しました：${doc.result.command.join(' ')}（新しい画面で動いています）`);
  }
  get('agent-start').addEventListener('click', () => startAgent());
  get('agent-more').addEventListener('click', () => {
    const r = get('agent-more').getBoundingClientRect(), ready = !get('agent-start').disabled;
    ECO.menu([
      ['起動するコマンドを指定…', () => ECO.form({title: 'AIを起動', intro: '起動するエージェントのコマンドです（引数は空白で区切る）。このPCで覚えておき、「AIを起動」でも使います。', fields: [
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
})();
