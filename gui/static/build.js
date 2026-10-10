'use strict';
// Build / test / run toolbar of a place. Runs ecobuild build・test・run・rebuild・clean・check and shows the result.
WS.onRefresh(renderPrDetail);
(() => {
  const LABEL = {build: 'ビルド', rebuild: 'リビルド', clean: 'クリーン', test: 'テスト', run: '実行', check: '提出前の確認'};
  const CHECK = {generated: '生成ファイルが最新', conflict_markers: '衝突の印がない', build: 'ビルド', test: 'テスト'};
  let profiles = {}, selectedProfile = null, busy = false;

  async function loadOptions() {
    const [p, j] = await Promise.all([WS.cli(['profile', 'list'], {quiet: true}), WS.cli(['project', 'list'], {quiet: true})]);
    if (p.ok) {
      profiles = p.result.profiles; selectedProfile = p.result.selected;
      const names = Object.keys(profiles);
      get('build-profile').innerHTML = names.map(n => `<option value="${esc(n)}">${esc(n)}（${esc(profiles[n].configuration)}${profiles[n].shared ? '・共有' : ''}）</option>`).join('') + '<option value="none">使わない</option>';
      get('build-profile').value = selectedProfile || 'none';
      get('build-profile').disabled = !names.length; get('build-profile').title = names.length ? '' : 'ビルド設定はありません（モジュール画面の「ビルド設定」で追加できます）';
    }
    get('build-project-label').hidden = !j.ok;
    if (j.ok) get('build-project').innerHTML = '<option value="">すべてのProject</option>' + j.result.map(x => `<option value="${esc(x.name)}" data-kind="${esc(x.kind)}">${esc(x.name)}（${esc(x.kind)}）</option>`).join('');
  }

  const out = (title, state, html) => {
    get('build-output-title').textContent = title;
    get('build-output-state').textContent = state === 'ok' ? '成功' : state === 'run' ? '実行中…' : '失敗あり';
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
    const doc = await WS.run(['profile', 'use', e.target.value], {success: e.target.value === 'none' ? 'ビルド設定を使わないようにしました。' : `このPCでは ${e.target.value} を使います。`, refresh: false});
    if (!doc) e.target.value = selectedProfile || 'none'; else selectedProfile = e.target.value === 'none' ? null : e.target.value;
  });
  WS.ready.then(loadOptions);
  WS.reloadBuildOptions = loadOptions;
})();
