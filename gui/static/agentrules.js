'use strict';
// Module page エージェント: the module's agents, kept in the repository (.ecobuild/agents/, committed on a task branch and
// taken in by a PR): the text for every agent (ecobuild agent rules) on top, then the registrations (ecobuild agent
// registry: each role's document, tools, model, children), edited with AGENT_EDITOR. New ones are copied from this PC's
// presets (the hub's settings) or ECOBuild's samples. The agents started get what the default branch has; a place on a
// task branch shows what will be taken in.
(() => {
  const {esc} = ECO;
  const $ = id => document.getElementById(id);
  const section = () => $('agents-content'), main = () => section().querySelector('.ar-main');
  let place = null, common = null, typedCommon = false;
  const here = () => place || MOD.root;
  const editable = () => !!MOD.states.get(MOD.keyOf(here()))?.task;

  // The place shown: the module's folder (the default branch: what the agents get) or a workspace.
  function placeSelect() {
    const places = [MOD.root, ...MOD.places.filter(p => MOD.keyOf(p) !== MOD.keyOf(MOD.root))];
    if (places.length < 2) return '';
    const label = p => MOD.keyOf(p) === MOD.keyOf(MOD.root) ? 'モジュールのフォルダ（既定のブランチ）'
      : esc(MOD.states.get(MOD.keyOf(p))?.branch || p) + '（' + esc(p.split(/[\\/]/).pop()) + '）';
    return `<label class="mi-place">表示<select id="ar-place">${places.map(p =>
      `<option value="${esc(p)}" ${MOD.keyOf(p) === MOD.keyOf(here()) ? 'selected' : ''}>${label(p)}</option>`).join('')}</select></label>`;
  }
  function showPlace() {
    const top = section().querySelector('.mi-place-slot');
    if (top && !top.contains(document.activeElement)) top.innerHTML = placeSelect();
  }
  const notEditable = () => `<div class="eco-banner mi-info"><span>変更はタスクブランチの作業空間で行います（コミットして提出し、取り込まれると起動するエージェントに効きます）。${MOD.workspacePlaces().length ? '上の「表示」でタスクブランチを選んでください。' : '作業空間がないので、今は見るだけです。'}</span>${MOD.workspacePlaces().length ? '' : '<button type="button" class="sm" data-ar-tasks>タスク管理を開く</button>'}</div>`;

  // The top of the list: the text for every agent (the common text).
  const top = {
    key: '#common', label: '全エージェント共通',
    render() {
      const off = editable() ? '' : ' disabled';
      if (!common) return ECO.loading();
      return `<div class="ae-head"><div><h3>全エージェント共通</h3>
          <div class="ae-item-badges">${common.pending ? '<span class="ae-badge warn">まだ効いていない（取り込まれると効く）</span>' : ''}</div>
          <p class="mi-note">このモジュールで起動するどのエージェントにも、役の文書の後に渡します（基準・仕事の分け方の決まり 等）。効く版：${esc(common.in_force || '—')}</p></div>
        <div class="mi-actions"><button type="button" class="primary" data-ar-save${off}>保存してコミット</button></div></div>
        <textarea class="ae-doc" data-ar-common rows="${Math.min(24, Math.max(8, common.common.split('\n').length + 2))}" placeholder="例：前後がつながった段階（調べる→設計→実装）は分けずに自分で進める。子に任せるのは、互いに独立した仕事と検証だけ。"${off}>${esc(common.common)}</textarea>`;
    },
    dirty: () => typedCommon,
    async click(e) {
      if (!e.target.closest('[data-ar-save]')) return;
      const text = main().querySelector('[data-ar-common]').value;
      const doc = await ECO.run(here(), ['agent', 'rules', 'set', '-'], {stdin: text, success: r => r?.changed?.length
        ? `保存してコミットしました（${(r.committed || '').slice(0, 7)}。提出して取り込まれると効きます）。` : '変わったところはありません。'});
      if (doc) { typedCommon = false; common = doc.result; editor.redraw(); MOD.reloadPlace?.(here()); }
    },
  };
  const editor = AGENT_EDITOR.create(main(), {kind: 'module', dir: here, editable, notEditable, top,
                                               onChanged: () => MOD.reloadPlace?.(here())});
  async function read() {
    showPlace(); typedCommon = false; common = null;
    const doc = await ECO.cli(here(), ['agent', 'rules', 'show'], {quiet: true});
    common = doc.ok ? doc.result : {common: '', pending: false, in_force: ''};
    await editor.load();
    stale = false;
  }

  section().addEventListener('click', e => { if (e.target.closest('[data-ar-tasks]')) showModulePage('tasks'); });
  section().addEventListener('input', e => { if (e.target.matches('[data-ar-common]')) typedCommon = true; });
  section().addEventListener('change', async e => {
    if (e.target.id !== 'ar-place') return;
    if (editor.dirty() && !await ECO.confirm({title: '保存していない変更', message: '保存していない変更を捨てて、表示する場所を変えますか？', ok: '捨てて変える', danger: true})) { e.target.value = here(); return; }
    place = e.target.value; read();
  });
  // Something typed and not saved is kept: a change made elsewhere is read when the page is shown next (or 更新).
  let stale = true;
  $('agents-reload').addEventListener('click', read);
  pageHooks.agents = () => { if (stale && !editor.dirty()) MOD.ready.then(read); };
  const changed = pageHooks.changed;   // tasks.js's (this script comes after it)
  pageHooks.changed = () => { changed?.(); stale = true; if (!section().hidden && !editor.dirty()) read(); };
})();
