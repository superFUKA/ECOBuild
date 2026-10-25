'use strict';
// モジュール › パイプライン: named lists of checks (pipeline add/remove: [pipelines] in ecobuild.toml), run one now
// (pipeline run), and which of them run at each timing of ECOBuild's operations (pipeline on: [triggers]; before an
// operation a failure stops it, after one it is only told). What the module shares is changed on a task branch (then
// committed and submitted, like the CI's workflow); what only this PC adds (pipeline on --local, ecobuild.local.toml)
// is changed anywhere, in every place of the module here. None by default. Shown and changed in the place chosen at
// the top of モジュール (a workspace with a task branch to change, else what the base branch has).
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {data: null, error: '', place: '', loaded: false};   // place: the one read
  const pill = (text, cls = '') => `<span class="mi-pill ${cls}">${esc(text)}</span>`;
  const STEPS = [['generated', '生成ファイルが最新か'], ['conflict_markers', '衝突の印（<<<<<<< 等）がないか'], ['build', 'ビルド'], ['test', 'テスト']];
  const STEP_NAMES = {generated: '生成ファイル', conflict_markers: '衝突の印', build: 'ビルド', test: 'テスト'};
  // The timings, by operation: [operation, [timing, label]…]. before-* stops the operation when it fails.
  const TIMINGS = [
    ['コミット', [['before-commit', '前'], ['after-commit', '後']]],
    ['Push', [['before-push', '前'], ['after-push', '後']]],
    ['提出', [['before-submit', '前'], ['after-submit', '後']]],
    ['取り込み（完了）', [['before-finish', '前']]],
    ['最新の取り込み（同期）', [['after-sync', '後']]],
    ['タスクの開始', [['after-start', '後']]],
  ];
  const TIMING_NAMES = Object.fromEntries(TIMINGS.flatMap(([op, ts]) => ts.map(([t, when]) => [t, `${op}の${when}`])));

  const stateOf = p => MOD.states.get(MOD.keyOf(p));
  const editable = p => { const s = stateOf(p); return !!s?.task && !s.reviewing; };
  const places = () => [MOD.root, ...MOD.places.filter(p => MOD.keyOf(p) !== MOD.keyOf(MOD.root))];
  const here = () => MOD.shownPlace?.() || MOD.root;

  async function load() {
    const place = st.place = here();
    const doc = await ECO.query(place, ['pipeline', 'list'], fresh => { if (fresh.ok && place === here()) { st.data = fresh.result; render(); } });
    if (place !== here()) return;
    st.data = doc.ok ? doc.result : null;
    st.error = doc.ok ? '' : doc.error.message;
    st.loaded = true;
    render();
  }

  const usedAt = name => Object.keys(TIMING_NAMES).filter(t => st.data.triggers[t]?.includes(name) || st.data.local[t]?.includes(name));
  function pipelinesHtml() {
    const d = st.data;
    if (!d.pipelines.length) return '<p class="mi-note">パイプラインはありません。「＋ パイプライン」で、確かめる手順の並びに名前を付けて作ります。</p>';
    return `<div class="pl-list">${d.pipelines.map(p => {
      const used = usedAt(p.name);
      return `<div class="ci-card pl-card" data-pl="${esc(p.name)}"><div class="ci-card-head"><div><strong>${esc(p.name)}</strong>
          <span class="pl-steps">${p.steps.map((s, i) => `${i ? '<span class="pl-arrow" aria-hidden="true">→</span>' : ''}${pill(STEP_NAMES[s] || s)}`).join('')}</span></div>
          <div class="mi-actions"><button type="button" class="primary" data-pl-action="run">▶ 実行</button><button type="button" data-pl-action="edit">編集…</button><button type="button" class="danger-text" data-pl-action="remove">削除…</button></div></div>
        <dl class="ci-settings">${p.tests.length ? `<dt>流す試験</dt><dd>${esc(p.tests.join('、'))}</dd>` : ''}
          <dt>当てているタイミング</dt><dd>${used.length ? used.map(t => esc(TIMING_NAMES[t])).join('、') : '<span class="mi-sub">なし（「▶ 実行」で単体で走らせます）</span>'}</dd></dl></div>`;
    }).join('')}</div>`;
  }
  function timingsHtml() {
    const d = st.data, none = !d.pipelines.length;
    const chips = t => {
      const shared = d.triggers[t] || [], local = (d.local[t] || []).filter(n => !shared.includes(n));
      return shared.map(n => pill(n, 'ok')).join(' ') + (local.length ? ' ' + local.map(n => pill(`${n}（このPCだけ）`)).join(' ') : '') || '<span class="mi-sub">なし</span>';
    };
    return `<table class="mi-table pl-timings"><thead><tr><th>操作</th><th>いつ</th><th>走らせるパイプライン</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>${TIMINGS.map(([op, ts]) => ts.map(([t, when], i) => `<tr data-pl-timing="${t}">
        ${i ? '' : `<td rowspan="${ts.length}">${esc(op)}</td>`}<td>${when === '前' ? '前<small class="mi-sub">（失敗したら止める）</small>' : '後<small class="mi-sub">（知らせるだけ）</small>'}</td>
        <td>${chips(t)}</td><td class="ci-row-actions"><button type="button" data-pl-action="trigger"${none ? ' disabled title="先にパイプラインを作ってください"' : ''}>変える…</button><button type="button" data-pl-action="local"${none ? ' disabled title="先にパイプラインを作ってください"' : ''}>このPCで足す…</button></td></tr>`).join('')).join('')}</tbody></table>`;
  }
  function render() {
    if (el('modinfo-content').hidden || el('pipelines-main').hidden) return;
    const main = el('pipelines-main');
    if (!st.loaded) { main.innerHTML = ECO.loading(); return; }
    const place = here(), canEdit = editable(place);
    const note = canEdit ? 'ここで変えたものは、コミットして提出し、取り込まれるとモジュールで共有されます。'
      : 'パイプラインと当て方は、タスクブランチ（作業空間）で変えます。右上の「表示」で作業空間を選んでください。「このPCで足す」はどこでも使えます。';
    main.innerHTML = `${st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : ''}
      <p class="mi-note pl-place">${esc(note)}</p>
      ${st.data ? `<div class="ci-section-row"><h4 class="br-section">パイプライン</h4><span class="ci-section-end"><button type="button" data-pl-action="add">＋ パイプライン</button></span></div>${pipelinesHtml()}
      <div class="ci-section-row"><h4 class="br-section">タイミング</h4></div>${timingsHtml()}
      <p class="mi-note">走らせずに進めたいときは、コマンドに --no-pipelines（提出は --no-check）を付けます。GitHub の CI は「CI」のタブです。</p>` : ''}`;
    if (!canEdit) for (const b of main.querySelectorAll('[data-pl-action=add], [data-pl-action=edit], [data-pl-action=remove], [data-pl-action=trigger]')) {
      b.disabled = true; b.title = 'タスクブランチ（作業空間）で変えます';
    }
  }

  async function changed(doc) { if (doc) { MOD.reloadPlace(here()); await load(); } }
  function editPipeline(p) {
    const fresh = !p;
    return ECO.form({title: fresh ? 'パイプラインを作る' : `パイプライン ${p.name} を変える`, wide: true,
      intro: '選んだ手順を、上から順に行います。作っただけでは走りません（「▶ 実行」か、タイミングに当てて走らせます）。',
      fields: [
        ...(fresh ? [{name: 'name', label: '名前（例：quick、full）', required: true, focus: true}] : []),
        {name: 'steps', label: '手順', type: 'checks', value: p?.steps || [], options: STEPS},
        {name: 'tests', label: 'テストで流す試験（カンマ区切り。空なら全部。型が絞れるとき）', value: (p?.tests || []).join(','), placeholder: '例：tests/unit,gui/tests'},
      ], ok: fresh ? '作る' : '変える',
      submit: async v => {
        const name = fresh ? v.name.trim() : p.name;
        if (fresh && st.data.pipelines.some(x => x.name === name)) return `${name} はもうあります。`;
        if (!v.steps.length) return '手順を1つ以上選んでください。';
        if (v.tests && !v.steps.includes('test')) return '流す試験を書くときは「テスト」も選んでください。';
        const doc = await ECO.run(here(), ['pipeline', 'add', name, '--steps', v.steps.join(','), ...(v.tests ? ['--tests', v.tests] : [])],
          {success: fresh ? `パイプライン ${name} を作りました。` : `パイプライン ${name} を変えました。`});
        if (!doc) return fresh ? '作れませんでした。' : '変えられませんでした。';
        await changed(doc);
      }});
  }
  function removePipeline(p) {
    const used = usedAt(p.name);
    return ECO.run(here(), ['pipeline', 'remove', p.name], {success: `パイプライン ${p.name} を消しました。`, title: 'パイプラインを削除', ok: '削除する', danger: true,
      confirm: `パイプライン ${p.name} を消します。` + (used.length ? `当てているタイミング（${used.map(t => TIMING_NAMES[t]).join('、')}）からも外れます。` : '')}).then(changed);
  }
  function runPipeline(p) {
    return ECO.run(here(), ['pipeline', 'run', p.name], {busy: `パイプライン ${p.name} を実行しています…`, success: `パイプライン ${p.name} が通りました。`});
  }
  // The pipelines of a timing: the module's (on the task branch here), or what this PC adds (in every place here,
  // so the workspaces made later get it from the original clone too).
  async function setTiming(timing, local) {
    const d = st.data, current = (local ? d.local[timing] : d.triggers[timing]) || [];
    const shared = d.triggers[timing] || [];
    await ECO.form({title: `${TIMING_NAMES[timing]}に走らせるパイプライン${local ? '（このPCだけ）' : ''}`,
      intro: (timing.startsWith('before-') ? '選んだ順に走らせ、どれかが失敗したら、その操作を止めます。' : '選んだ順に走らせます。失敗しても操作は止めず、知らせるだけです。')
        + (local ? `モジュールの当て方（${shared.length ? shared.join('、') : 'なし'}）に足すだけで、外せません。コミットせず、このPCのこのモジュールのすべての場所に入れます。` : ''),
      fields: [{name: 'names', label: 'パイプライン', type: 'checks', value: current, options: d.pipelines.filter(p => !local || !shared.includes(p.name)).map(p => [p.name, `${p.name}（${p.steps.map(s => STEP_NAMES[s] || s).join('→')}）`])}],
      ok: '決める',
      submit: async v => {
        const names = v.names.length ? v.names.join(',') : 'none';
        const targets = local ? places() : [here()];
        for (const place of targets) {
          const doc = await ECO.run(place, ['pipeline', 'on', timing, names, ...(local ? ['--local'] : [])]);
          if (!doc) return '変えられませんでした。';
        }
        ECO.toast(local ? `${TIMING_NAMES[timing]}に、このPCだけで足しました。` : `${TIMING_NAMES[timing]}の当て方を変えました。コミットして提出すると共有されます。`, 'ok');
        await changed(true);
      }});
  }

  const main = el('pipelines-main');
  main.addEventListener('click', e => {
    const b = e.target.closest('[data-pl-action]'); if (!b || b.disabled) return;
    const p = st.data?.pipelines.find(x => x.name === b.closest('[data-pl]')?.dataset.pl);
    const timing = b.closest('[data-pl-timing]')?.dataset.plTiming;
    switch (b.dataset.plAction) {
      case 'add': return editPipeline(null);
      case 'edit': return p && editPipeline(p);
      case 'remove': return p && removePipeline(p);
      case 'run': return p && runPipeline(p);
      case 'trigger': return timing && setTiming(timing, false);
      case 'local': return timing && setTiming(timing, true);
    }
  });

  // Shown again: read when not yet, or when another place was chosen meanwhile.
  const fresh = () => st.loaded && MOD.keyOf(st.place) === MOD.keyOf(here());
  window.MANAGE_PIPELINES = {show: () => { if (!fresh()) { st.loaded = false; render(); MOD.ready.then(load); } else render(); },
                             reload: () => { if (!fresh()) { st.loaded = false; render(); } return load(); }};
  ECO.onChange(() => { if (st.loaded) { if (!main.hidden && !el('modinfo-content').hidden) load(); else st.loaded = false; } });
})();
