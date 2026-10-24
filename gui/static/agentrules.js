'use strict';
// Module page エージェント: the module's agents, kept in the repository (.ecobuild/agents/, committed on a task branch and
// taken in by a PR): the text for every agent (ecobuild agent rules) on top, then the registrations (ecobuild agent
// registry: each role's document, tools, model, children), edited with AGENT_EDITOR. ECOBuild's presets (進行役・管理役・
// 作業役) are there as they are until saved for this module; new ones are made empty or from this PC's presets (the hub's
// settings). Anything can be edited from any place shown: saving asks for the task branch to commit on (a workspace
// of the module, or a new task made for it), then shows that place. The agents started get what the default branch has.
(() => {
  const {esc} = ECO;
  const $ = id => document.getElementById(id);
  const section = () => $('agents-content'), main = () => section().querySelector('.ar-main');
  let place = null, common = null, typedCommon = false;
  const here = () => place || MOD.root;
  const onTaskBranch = dir => !!MOD.states.get(MOD.keyOf(dir))?.task;

  // The place shown: the module's folder (the default branch: what the agents get) or a workspace.
  function placeSelect() {
    const places = [MOD.root, ...MOD.places.filter(p => MOD.keyOf(p) !== MOD.keyOf(MOD.root))];
    if (places.length < 2) return '';
    return `<label class="mi-place">表示<select id="ar-place">${places.map(p =>
      `<option value="${esc(p)}" ${MOD.keyOf(p) === MOD.keyOf(here()) ? 'selected' : ''}>${placeLabel(p)}</option>`).join('')}</select></label>`;
  }
  const placeLabel = p => MOD.keyOf(p) === MOD.keyOf(MOD.root) ? 'モジュールのフォルダ（既定のブランチ）'
    : esc(MOD.states.get(MOD.keyOf(p))?.branch || p) + '（' + esc(p.split(/[\\/]/).pop()) + '）';
  function showPlace() {
    const top = section().querySelector('.mi-place-slot');
    if (top && !top.contains(document.activeElement)) top.innerHTML = placeSelect();
  }
  const notice = () => onTaskBranch(here())
    ? `<p class="mi-note ar-where">表示：${placeLabel(here())}。保存するとこのタスクブランチでコミットします（提出して取り込まれると、起動するエージェントに効きます）。</p>`
    : '<p class="mi-note ar-where">表示：既定のブランチ（いま起動するエージェントに効いている内容）。直して保存するときに、コミットするタスクブランチを選びます。</p>';

  // Where a change is committed: the task branch shown, else one chosen (a workspace of the module, or a new task).
  const NEW = '#new';
  async function target(what) {
    if (onTaskBranch(here())) return here();
    const places = MOD.workspacePlaces();
    const v = await ECO.form({title: what, intro: 'エージェントの設定はリポジトリのファイルなので、タスクブランチでコミットします（提出して取り込まれると効きます）。どこで変えますか？',
      fields: [{name: 'place', label: 'コミットする場所', type: 'select', value: places[0] || NEW,
                options: [...places.map(p => [p, placeLabel(p)]), [NEW, '新しいタスクを作る']]},
               {name: 'title', label: '新しいタスクの題名', value: 'エージェントの設定を変える', showIf: x => x.place === NEW}],
      ok: '続ける'});
    if (!v) return undefined;
    if (v.place !== NEW) return v.place;
    const title = (v.title || '').trim() || 'エージェントの設定を変える';
    const doc = await ECO.run(MOD.root, ['task', 'new', title, '--start', '--name', ECO.branchLabel(title)],
                              {busy: 'タスクと作業空間を作っています…', success: r => `タスク #${(r.task || r).number} の作業空間を作りました。`});
    const dir = doc?.result?.task_branch?.workspace;
    if (!dir) return undefined;
    await MOD.syncPlaces?.(); await MOD.reloadPlace?.(dir);
    return dir;
  }
  // After a change: show the place it was made in (its task branch has it).
  async function changedIn(dir) {
    if (dir && MOD.keyOf(dir) !== MOD.keyOf(here())) { place = dir; showPlace(); }
    await MOD.reloadPlace?.(dir || here());
  }

  // The top of the list: the text for every agent (the common text).
  const top = {
    key: '#common', label: '全エージェント共通',
    render() {
      if (!common) return ECO.loading();
      return `<div class="ae-head"><div><h3>全エージェント共通</h3>
          <div class="ae-item-badges">${common.pending ? '<span class="ae-badge warn">まだ効いていない（取り込まれると効く）</span>' : ''}</div>
          <p class="mi-note">このモジュールで起動するどのエージェントにも、役の文書の後に渡します（基準・仕事の分け方の決まり 等）。効く版：${esc(common.in_force || '—')}</p></div>
        <div class="mi-actions"><button type="button" class="primary" data-ar-save>保存してコミット</button></div></div>
        <textarea class="ae-doc" data-ar-common rows="${Math.min(24, Math.max(8, common.common.split('\n').length + 2))}" placeholder="例：前後がつながった段階（調べる→設計→実装）は分けずに自分で進める。子に任せるのは、互いに独立した仕事と検証だけ。">${esc(common.common)}</textarea>`;
    },
    dirty: () => typedCommon,
    async click(e) {
      if (!e.target.closest('[data-ar-save]')) return;
      const text = main().querySelector('[data-ar-common]').value;
      const dir = await target('全エージェント共通の文を保存');
      if (dir === undefined) return;
      const doc = await ECO.run(dir, ['agent', 'rules', 'set', '-'], {stdin: text, success: r => r?.changed?.length
        ? `保存してコミットしました（${(r.committed || '').slice(0, 7)}。提出して取り込まれると効きます）。` : '変わったところはありません。'});
      if (doc) { typedCommon = false; await changedIn(dir); await read(); }
    },
  };
  const editor = AGENT_EDITOR.create(main(), {kind: 'module', dir: here, target, notice, top, onChanged: changedIn});
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
