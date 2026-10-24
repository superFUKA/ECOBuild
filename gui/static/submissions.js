'use strict';
// The submissions coming into a shared branch, under it on the page ブランチ (branches.js reads the branches, the
// submissions and the account and hands them here): listed, the chosen one looked at (status, CI, reviews, diff) and
// handled (checked here, approved, sent back, taken in, withdrawn; a branch's submission is merged). Handling one is
// for whoever made the branch it goes into, and admins (the default branch: admins) — the others' buttons are grey
// (ECO.canTakeIn). Every command runs in the module's folder (a submission is the module's, not one workspace's);
// checking one here (task review) uses a workspace of it.
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {branches: [], submissions: [], access: null, selected: '', item: null, status: null};
  const cli = args => ECO.cli(MOD.root, args, {quiet: true});
  const pill = (text, cls = '') => `<span class="mi-pill ${cls}">${esc(text)}</span>`;
  const shared = () => st.branches;
  const open = s => s?.state === 'open';
  // What comes into a branch: the open submissions of tasks (their base) and of other branches (submitted_to).
  const incoming = name => [
    ...st.submissions.filter(t => open(t.submission) && t.submission.base === name).map(t => ({kind: 'task', key: 'task:' + t.number, task: t})),
    ...shared().filter(b => open(b.submission) && b.submitted_to === name).map(b => ({kind: 'branch', key: 'branch:' + b.name, branch: b})),
  ];
  const mine = t => MOD.me && t.assignees.includes(MOD.me);

  // What comes into the chosen branch (and who handles it), then the one chosen.
  function renderMain() {
    const main = el('sub-main'), name = st.selected; if (!main) return;
    const items = incoming(name), handles = ECO.canTakeIn(st.access, name);
    if (st.item && !items.some(i => i.key === st.item)) { st.item = null; st.status = null; }
    if (!st.item && items.length) st.item = items[0].key;
    main.innerHTML = `<h3 class="br-section">届いている提出 ${items.length ? `<span class="br-count">${items.length}</span>` : ''}</h3>
      ${items.length && st.access && !handles ? `<p class="mi-note">${esc(ECO.takeInNote(st.access, name))}（見る・手元で確認・コメントはできます）。</p>` : ''}
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
  // Where a submission is being checked (task review): its workspace in the module (.ecobuild/w/r<PR number>).
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
    if (reviewing) act.append(b('review-done', '判定せずに終える'));
    if (isOpen && !own) {
      if (!reviewing) act.append(b('local-review', '手元で確認'));
      act.append(b('reject', '差し戻す', {enabled: handles, note: why}),
        b('approve', '承認して取り込む', {enabled: !draft && handles, kind: 'primary', note: draft ? '下書きの提出は承認できません' : why}));
    } else if (isOpen) {
      act.append(b('withdraw', '提出を取り下げる', {kind: 'danger-text'}),
        b('finish', '取り込む', {enabled: !draft && handles, kind: 'primary', note: draft ? '下書きの提出は取り込めません。タスクブランチの作業空間で下書きを解除します' : why}));
    }
    tools.append(look, act); box.append(tools);
  }
  // Doing things. After a change, the reads are read again (the server marks them stale) and the screen redrawn.
  const after = async doc => { if (doc) { st.status = null; await window.BRANCHES_RELOAD?.(); } return doc; };
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
          ? {title: `承認して取り込む：#${n}`, intro: 'CIが終わるのを待ちます。タスクは提出のとおり閉じるか続けます。', fields: [{name: 'message', label: 'コメント（任意）', type: 'textarea'}], ok: '承認して取り込む'}
          : {title: `差し戻す：#${n}`, intro: 'タスクは作業中に戻ります。', fields: [{name: 'message', label: '直してほしいこと', type: 'textarea', required: true}], ok: '差し戻す', danger: true});
        if (!v) return;
        // Run in the module's own clone: the workspace it was checked in (if any) is removed by approve・reject.
        const doc = await ECO.run(MOD.root, ['task', action, n, ...(v.message ? ['--message', v.message] : [])], {success: approve ? r => `#${n} を承認して取り込みました。` + (r.partial ? 'タスクは続きます。' : 'タスクを完了しました。') : `#${n} を差し戻しました。`});
        if (doc) { if (approve) ECO.workspaceKept(doc.result, n); await MOD.syncPlaces(); }
        return after(doc);
      }
      case 'finish': {
        const options = await ECO.finishForm({number: n, base: t.base, partial: !!t.pull_request?.partial});
        if (!options) return;
        const place = MOD.placeOfTask(t.number) || MOD.root;
        const doc = await ECO.run(place, ['task', 'finish', n, ...options], {success: r => r.partial ? `#${n} を取り込みました（タスクは続きます）。` : `#${n} を取り込み、完了しました。`});
        if (doc) { ECO.workspaceKept(doc.result, n); await MOD.reloadPlace(place); }
        return after(doc);
      }
      case 'withdraw': return after(await ECO.run(MOD.root, ['task', 'withdraw', n], {success: '提出を取り下げました。', confirm: `#${n} の提出を取り下げて作業中に戻します（タスクブランチはそのまま。もう一度提出できます）。`, title: '提出を取り下げる'}));
      case 'local-review': {
        // Checking it here takes the submission into a workspace of its own (task review: .ecobuild/w/r<PR number>; the
        // module's own clone stays as it is). Ending it (task review --done) removes that workspace.
        const place = reviewingPlace(t.number);
        if (place) { const doc = await ECO.run(place, ['task', 'review', '--done'], {success: '確認を終え、確認用の作業空間を消しました。'}); if (doc) await MOD.syncPlaces(); return after(doc); }
        const doc = await ECO.run(MOD.root, ['task', 'review', n], {success: r => `#${n} の提出を確認用の作業空間に取り出しました（${r.workspace}）。そこでビルド・テスト・実行して確かめ、ここで承認か差し戻しをします。`});
        if (doc) await MOD.showPlace(doc.result.workspace);
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

  const section = el('branches-content');
  section.addEventListener('click', e => {
    const item = e.target.closest('[data-sub-item]');
    if (item) { st.item = item.dataset.subItem; st.status = null; renderMain(); return; }
    const pr = e.target.closest('#sub-detail [data-pr-action]');
    if (pr && !pr.disabled) {
      if (st.item?.startsWith('branch:')) mergeBranch(st.item.slice(7)); else taskAction(pr.dataset.prAction);
    }
  });
  // ↑↓ between the submissions.
  section.addEventListener('keydown', e => {
    if (!['ArrowUp', 'ArrowDown'].includes(e.key) || !e.target.closest('[data-sub-item]')) return;
    const items = [...section.querySelectorAll('[data-sub-item]')], i = items.findIndex(x => x.dataset.subItem === st.item);
    const next = items[(i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]; if (!next) return;
    e.preventDefault(); st.item = next.dataset.subItem; st.status = null; renderMain(); section.querySelector(`[data-sub-item="${CSS.escape(st.item)}"]`)?.focus();
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
  // branches.js draws the branch and calls this with what it read (a newly chosen branch starts from its first one).
  window.BRANCH_SUBMISSIONS = {render(name, data) {
    if (name !== st.selected) { st.item = null; st.status = null; }
    Object.assign(st, data, {selected: name});
    renderMain();
  }};
})();
