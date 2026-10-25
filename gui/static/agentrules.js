'use strict';
// モジュール › エージェント: the module's agents, kept in the repository (.ecobuild/agents/, committed on a task branch and
// taken in by a PR): the text for every agent (ecobuild agent rules) on top, then the registrations (ecobuild agent
// registry: each role's document, tools, model, children), edited with AGENT_EDITOR. ECOBuild's presets (進行役・管理役・
// 作業役) are there as they are until saved for this module; new ones are made empty or from this PC's presets (the hub's
// settings). Anything can be edited from any place shown (chosen at the top of モジュール): saving asks for the task branch
// to commit on (a workspace of the module, or a new task made for it), then shows that place. The agents started get
// what the default branch has.
(() => {
  const {esc} = ECO;
  const $ = id => document.getElementById(id);
  const main = () => $('module-agents'), shownNow = () => !main().hidden && !$('modinfo-content').hidden;
  let readAt = null, common = null, typedCommon = false;   // readAt: the place read
  const here = () => MOD.shownPlace?.() || MOD.root;
  const onTaskBranch = dir => !!MOD.states.get(MOD.keyOf(dir))?.task;

  const placeLabel = p => MOD.keyOf(p) === MOD.keyOf(MOD.root) ? 'モジュールのフォルダ（既定のブランチ）'
    : esc(MOD.states.get(MOD.keyOf(p))?.branch || p) + '（' + esc(p.split(/[\\/]/).pop()) + '）';
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
    if (dir && MOD.keyOf(dir) !== MOD.keyOf(here())) MOD.showPlaceOf?.(dir);
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
    readAt = here(); typedCommon = false; common = null;
    const doc = await ECO.cli(here(), ['agent', 'rules', 'show'], {quiet: true});
    common = doc.ok ? doc.result : {common: '', pending: false, in_force: ''};
    await editor.load();
    stale = false;
  }

  main().addEventListener('click', e => { if (e.target.closest('[data-ar-tasks]')) showModulePage('tasks'); });
  main().addEventListener('input', e => { if (e.target.matches('[data-ar-common]')) typedCommon = true; });
  // Something typed and not saved is kept: a change made elsewhere is read when the tab is shown next (or 更新). Another
  // place chosen at the top (モジュール's) asks first (leave) and is read when shown.
  let stale = true;
  const moved = () => !readAt || MOD.keyOf(readAt) !== MOD.keyOf(here());
  window.MODULE_AGENTS = {
    show: () => { if ((stale || moved()) && !editor.dirty()) MOD.ready.then(read); },
    reload: () => MOD.ready.then(read),
    leave: async () => !editor.dirty() || ECO.confirm({title: '保存していない変更', message: '保存していない変更を捨てて、表示する場所を変えますか？', ok: '捨てて変える', danger: true}),
  };
  const changed = pageHooks.changed;   // tasks.js's (this script comes after it)
  pageHooks.changed = () => { changed?.(); stale = true; if (shownNow() && !editor.dirty()) read(); };
})();
