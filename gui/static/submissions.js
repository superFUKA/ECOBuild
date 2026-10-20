'use strict';
// 提出: the submissions coming into the module's shared branches (main, develop, …), by the branch they go into (the
// tabs on the left, with their counts), the chosen one's on the right — looked at (status, CI, reviews, diff) and
// handled (checked here, approved, sent back, taken in, withdrawn; a branch's submission is merged). Handling one is
// for whoever made the branch it goes into, and admins (the default branch: admins) — the others' buttons are grey
// (ECO.canTakeIn). Every command runs in the module's folder (a submission is the module's, not one workspace's);
// checking one here (task review) uses a workspace of it.
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {branches: null, submissions: [], access: null, selected: '', item: null, status: null, loaded: false, error: ''};
  const cli = args => ECO.cli(MOD.root, args, {quiet: true});
  const pill = (text, cls = '') => `<span class="mi-pill ${cls}">${esc(text)}</span>`;
  const shared = () => (Array.isArray(st.branches) ? st.branches : []).filter(b => !b.is_task_branch);
  const open = s => s?.state === 'open';
  // What comes into a branch: the open submissions of tasks (their base) and of other branches (submitted_to).
  const incoming = name => [
    ...st.submissions.filter(t => open(t.submission) && t.submission.base === name).map(t => ({kind: 'task', key: 'task:' + t.number, task: t})),
    ...shared().filter(b => open(b.submission) && b.submitted_to === name).map(b => ({kind: 'branch', key: 'branch:' + b.name, branch: b})),
  ];
  const mine = t => MOD.me && t.assignees.includes(MOD.me);

  // Reads: the branches, the submissions and the account (cached: the kept answer shows at once, a newer one redraws).
  // A submission read from an older ecobuild has no base: its task's status (which has it) fills it in.
  async function load() {
    const [branches, tasks, access] = await Promise.all([
      ECO.query(MOD.root, ['branch', 'list'], fresh => { st.branches = fresh.ok ? fresh.result : st.branches; render(); }),
      ECO.query(MOD.root, ['task', 'list', '--submitted'], fresh => { if (fresh.ok) { st.submissions = fresh.result; fillBases().then(render); } }),
      ECO.access(MOD.root),
    ]);
    st.error = !branches.ok ? branches.error.message : !tasks.ok ? tasks.error.message : '';
    st.branches = branches.ok ? branches.result : [];
    st.submissions = tasks.ok ? tasks.result : [];
    st.access = access;
    await fillBases();
    st.loaded = true;
    if (!shared().some(b => b.name === st.selected)) {
      const busy = shared().find(b => incoming(b.name).length);
      st.selected = (busy || shared().find(b => b.name === 'main') || shared()[0] || {}).name || '';
    }
    render();
  }
  async function fillBases() {
    await Promise.all(st.submissions.filter(t => t.submission && !t.submission.base).map(async t => {
      const doc = await ECO.query(MOD.root, ['task', 'status', String(t.number)]);
      if (doc.ok && doc.result.base) t.submission = {...t.submission, base: doc.result.base};
    }));
  }

  // Left: the shared branches, by where they come from (a branch made from another under it), with the count coming in.
  function renderSide() {
    const branches = shared(), names = new Set(branches.map(b => b.name)), side = el('sub-side');
    const rows = [], walk = (b, depth) => { rows.push([b, depth]); for (const c of branches.filter(c => c.base === b.name && c !== b)) walk(c, depth + 1); };
    for (const b of branches.filter(b => !b.base || !names.has(b.base))) walk(b, 0);
    side.innerHTML = rows.map(([b, depth]) => {
      const n = incoming(b.name).length;
      return `<button type="button" role="tab" data-sub-branch="${esc(b.name)}" aria-selected="${b.name === st.selected}" tabindex="${b.name === st.selected ? 0 : -1}" style="--depth:${depth}"
        title="${esc(b.name)} への提出${n ? ` ${n} 件` : 'はありません'}">
        <span class="br-side-name">${esc(b.name)}</span><span class="br-count ${n ? '' : 'zero'}">${n}</span></button>`;
    }).join('') || '<p class="mi-note">共有ブランチはありません。</p>';
  }

  // Right: what comes into the chosen branch (and who handles it), then the one chosen.
  function renderMain() {
    const main = el('sub-main'), name = st.selected;
    if (!shared().some(b => b.name === name)) { main.innerHTML = st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : '<p class="mi-note">ブランチを選んでください。</p>'; return; }
    const items = incoming(name), handles = ECO.canTakeIn(st.access, name);
    if (st.item && !items.some(i => i.key === st.item)) { st.item = null; st.status = null; }
    if (!st.item && items.length) st.item = items[0].key;
    main.innerHTML = `${st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : ''}
      <h3 class="br-section sub-title">${esc(name)} への提出 <span class="br-count ${items.length ? '' : 'zero'}">${items.length}</span></h3>
      ${st.access && !handles ? `<p class="mi-note">${esc(ECO.takeInNote(st.access, name))}（見る・手元で確認・コメントはできます）。</p>` : ''}
      <div class="br-list" role="listbox" aria-label="${esc(name)} への提出">${items.map(i => itemRow(i)).join('') ||
        '<p class="mi-note">届いている提出はありません。</p>'}</div>
      <div id="sub-detail" class="br-detail"></div>`;
    renderDetail();
    if (st.item?.startsWith('task:') && (!st.status || 'task:' + st.status.number !== st.item)) loadStatus(Number(st.item.slice(5)));
  }
  function itemRow(i) {
    const selected = i.key === st.item;
    if (i.kind === 'branch') {
      const s = i.branch.submission;
      return `<button type="button" role="option" data-sub-item="${esc(i.key)}" aria-selected="${selected}"><span>${pill('ブランチ')} ${esc(i.branch.name)}</span><span class="br-item-state">${esc(ECO.submissionText(s))}</span></button>`;
    }
    const t = i.task;
    return `<button type="button" role="option" data-sub-item="${esc(i.key)}" aria-selected="${selected}"><span>#${t.number} ${esc(t.title)}</span>
      <span class="br-item-state">${esc(ECO.submissionText(t.submission))}${t.assignees.length ? ' · ' + esc(t.assignees.join(', ')) : ''}${mine(t) ? '（自分）' : ''}</span></button>`;
  }
  async function loadStatus(number) {
    const key = 'task:' + number;
    el('sub-detail').innerHTML = ECO.loading();
    const doc = await ECO.query(MOD.root, ['task', 'status', String(number)], fresh => { if (st.item === key && fresh.ok) { st.status = fresh.result; renderDetail(); } });
    if (st.item !== key) return;
    st.status = doc.ok ? doc.result : null;
    if (!doc.ok) { el('sub-detail').innerHTML = `<p class="mi-note">${esc(doc.error.message)}</p>`; return; }
    renderDetail();
  }
  // Where a submission is being checked (task review): the workspace of the module that shows it.
  const reviewingPlace = n => MOD.places.find(p => MOD.states.get(MOD.keyOf(p))?.reviewing_task === n) || null;
  function renderDetail() {
    const box = el('sub-detail'); if (!box) return;
    const handles = ECO.canTakeIn(st.access, st.selected), why = handles ? '' : ECO.takeInNote(st.access, st.selected);
    if (st.item?.startsWith('branch:')) {
      const b = shared().find(x => 'branch:' + x.name === st.item); if (!b) { box.innerHTML = ''; return; }
      box.innerHTML = `<dl><dt>ブランチ</dt><dd><strong>${esc(b.name)}</strong> → ${esc(b.submitted_to)}</dd><dt>提出</dt><dd>${esc(ECO.submissionText(b.submission))}</dd><dt>URL</dt><dd>${esc(b.submission.url)}</dd></dl>`;
      const tools = document.createElement('div'); tools.className = 'br-tools';
      const act = document.createElement('div'); act.className = 'pr-act';
      act.append(ECO.submissionButton('merge', '取り込む', {kind: 'primary', enabled: !b.submission.draft && handles, note: b.submission.draft ? '下書きの提出は取り込めません' : why}));
      tools.append(document.createElement('div'), act); box.append(tools);
      return;
    }
    const t = st.status;
    if (!t || 'task:' + t.number !== st.item) { box.innerHTML = st.item ? ECO.loading() : ''; return; }
    const sub = t.pull_request, isOpen = open(sub), own = mine(t), draft = isOpen && sub.draft, reviewing = reviewingPlace(t.number);
    box.innerHTML = ECO.submissionDetail(t, {own});
    // Left: looking at it (small). Right: what can be done with it — someone else's is checked, approved or sent back;
    // one's own is taken in or withdrawn (submitting and making a draft ready are done in its workspace). Approving,
    // sending back and taking in are greyed for those who do not handle this branch's submissions.
    const tools = document.createElement('div'), look = document.createElement('div'), act = document.createElement('div');
    tools.className = 'br-tools'; look.className = 'pr-look'; act.className = 'pr-act';
    const b = ECO.submissionButton;
    look.append(b('diff', '差分'), b('comment', 'コメント'), b('task', 'タスク'), b('refresh', '更新'));
    if (reviewing) act.append(b('review-done', '判定せずに戻る'));
    if (isOpen && !own) {
      if (!reviewing) act.append(b('local-review', '手元で確認'));
      act.append(b('reject', '差し戻す', {enabled: handles, note: why}),
        b('approve', '承認して取り込む', {enabled: !draft && handles, kind: 'primary', note: draft ? '下書きの提出は承認できません' : why}));
    } else if (isOpen) {
      act.append(b('withdraw', '取り下げ', {kind: 'quiet-danger'}),
        b('finish', '取り込む', {enabled: !draft && handles, kind: 'primary', note: draft ? '下書きの提出は取り込めません。タスクブランチの作業空間で下書きを解除します' : why}));
    }
    tools.append(look, act); box.append(tools);
  }
  function render() {
    if (el('submissions-content').hidden) return;
    if (!st.loaded) { el('sub-main').innerHTML = ECO.loading(); return; }
    renderSide(); renderMain();
  }

  // Doing things. After a change, the reads are read again (the server marks them stale) and the screen redrawn.
  const after = async doc => { if (doc) { st.status = null; await load(); } return doc; };
  async function taskAction(action) {
    const t = st.status; if (!t) return;
    const n = String(t.number);
    switch (action) {
      case 'refresh': st.status = null; return loadStatus(t.number);
      case 'diff': return ECO.inTortoiseGit(MOD.root, ['task', 'diff', n], async () => { const doc = await cli(['task', 'diff', n]); return doc.ok ? ECO.output(`#${n} の差分`, doc.result || '差分はありません。', {diff: true}) : ECO.showError(doc); });
      case 'comment': return ECO.form({title: `#${n} にコメント`, fields: [{name: 'message', label: '内容', type: 'textarea', required: true}], ok: 'コメントする',
        submit: async v => { if (!await after(await ECO.run(MOD.root, ['task', 'comment', n, '--message', v.message], {success: 'コメントしました。'}))) return 'コメントできませんでした。'; }});
      case 'task': showModulePage('tasks'); window.TASKS_SELECT?.(t.number); return;
      case 'approve': case 'reject': {
        const approve = action === 'approve';
        const v = await ECO.form(approve
          ? {title: `承認して取り込む：#${n}`, intro: '提出を承認し、CIを待って取り込みます。タスクは提出のとおり、閉じるか続けます。', fields: [{name: 'message', label: 'コメント（任意）', type: 'textarea'}], ok: '承認して取り込む'}
          : {title: `差し戻す：#${n}`, intro: '直してほしいことを書いて差し戻します。タスクは作業中に戻ります。', fields: [{name: 'message', label: '直してほしいこと', type: 'textarea', required: true}], ok: '差し戻す', danger: true});
        if (!v) return;
        const place = reviewingPlace(t.number) || MOD.root;
        const doc = await ECO.run(place, ['task', action, n, ...(v.message ? ['--message', v.message] : [])], {success: approve ? r => `#${n} を承認して取り込みました。` + (r.partial ? 'タスクは続きます。' : 'タスクを完了しました。') : `#${n} を差し戻しました。`});
        if (doc) MOD.reloadPlace(place);
        return after(doc);
      }
      case 'finish': {
        const options = await ECO.finishForm({number: n, base: t.base, partial: !!t.pull_request?.partial});
        if (!options) return;
        const place = MOD.placeOfTask(t.number) || MOD.root;
        const doc = await ECO.run(place, ['task', 'finish', n, ...options], {success: r => r.partial ? `#${n} を取り込みました（タスクは続きます）。` : `#${n} を取り込み、完了しました。`});
        if (doc) MOD.reloadPlace(place);
        return after(doc);
      }
      case 'withdraw': return after(await ECO.run(MOD.root, ['task', 'withdraw', n], {success: '提出を取り下げました。', confirm: `#${n} の提出を取り下げて作業中に戻します（タスクブランチはそのまま。もう一度提出できます）。`, title: '提出を取り下げる'}));
      case 'local-review': {
        // Checking it here takes the submission into a workspace (the module's folder, or where it is checked already).
        const place = reviewingPlace(t.number);
        if (place) { const doc = await ECO.run(place, ['task', 'review', '--done'], {success: '確認を終えて戻りました。'}); if (doc) MOD.reloadPlace(place); return after(doc); }
        const doc = await ECO.run(MOD.root, ['task', 'review', n], {success: `#${n} の提出を手元に取り出しました。作業空間でビルド・テスト・実行して確かめ、ここで承認か差し戻しをします。`});
        if (doc) { await MOD.reloadPlace(MOD.root); MOD.activate(MOD.root); showModulePage('workspace'); }
        return after(doc);
      }
    }
  }
  // A branch's submission (branch submit) is taken in with a merge commit.
  async function mergeBranch(name) {
    const v = await ECO.form({title: `${name} の提出を取り込む`, intro: 'ブランチ同士の提出を、マージコミットで取り込みます。', fields: [{name: 'ignore', label: 'CIが失敗していても取り込む', type: 'checkbox'}], ok: '取り込む'});
    if (!v) return;
    return after(await ECO.run(MOD.root, ['branch', 'merge', name, ...(v.ignore ? ['--ignore-checks'] : [])], {success: `${name} の提出を取り込みました。`}));
  }

  const section = el('submissions-content');
  section.addEventListener('click', e => {
    const tab = e.target.closest('[data-sub-branch]');
    if (tab) { st.selected = tab.dataset.subBranch; st.item = null; st.status = null; render(); return; }
    const item = e.target.closest('[data-sub-item]');
    if (item) { st.item = item.dataset.subItem; st.status = null; renderMain(); return; }
    const pr = e.target.closest('[data-pr-action]');
    if (pr && !pr.disabled) {
      if (st.item?.startsWith('branch:')) mergeBranch(st.item.slice(7)); else taskAction(pr.dataset.prAction);
    }
  });
  // ↑↓ between the branches (the tabs are vertical).
  el('sub-side').addEventListener('keydown', e => {
    if (!['ArrowUp', 'ArrowDown'].includes(e.key)) return;
    const tabs = [...el('sub-side').querySelectorAll('[data-sub-branch]')], i = tabs.findIndex(t => t.dataset.subBranch === st.selected);
    const next = tabs[(i + (e.key === 'ArrowDown' ? 1 : tabs.length - 1)) % tabs.length]; if (!next) return;
    e.preventDefault(); st.selected = next.dataset.subBranch; st.item = null; st.status = null; render(); el('sub-side').querySelector(`[data-sub-branch="${CSS.escape(st.selected)}"]`)?.focus();
  });
  // Right-click a submission: the same actions as its buttons.
  section.addEventListener('contextmenu', e => {
    const item = e.target.closest('[data-sub-item]'); if (!item) return;
    e.preventDefault();
    const x = e.clientX, y = e.clientY;
    if (st.item !== item.dataset.subItem) { st.item = item.dataset.subItem; st.status = null; renderMain(); }
    setTimeout(() => {
      const buttons = [...el('sub-detail').querySelectorAll('[data-pr-action]')];
      if (buttons.length) ECO.menu(buttons.map(b => [b.textContent, () => b.click(), !b.disabled]), x, y);
    }, st.item?.startsWith('task:') && !st.status ? 800 : 0);
  });
  el('sub-reload').addEventListener('click', () => { st.status = null; load(); });

  // Another page (管理 › ブランチ) leads here to a branch's submissions.
  window.SUBMISSIONS_SHOW = name => { if (name) { st.selected = name; st.item = null; st.status = null; } showModulePage('submissions'); };
  pageHooks.submissions = () => { if (!st.loaded) { render(); load(); } else render(); };
  ECO.onChange(() => { if (st.loaded) { st.status = null; if (!section.hidden) load(); else st.loaded = false; } });
})();
