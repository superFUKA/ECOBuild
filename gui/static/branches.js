'use strict';
// ブランチ: the module's shared branches (main, develop, … — not the task branches) as tabs on the left, each with the
// submissions coming into it; the chosen one on the right: the branch (where it comes from, its own submission, the
// task branches made from it) and its submissions — looked at (status, CI, reviews, diff) and handled (checked here,
// approved, sent back, finished, withdrawn; a branch's submission is merged). Every command runs in the module's folder
// (a submission is the module's, not one workspace's); checking one here (task review) uses a workspace of it.
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {branches: null, submissions: [], selected: '', item: null, status: null, loaded: false, error: ''};
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

  // Reads: the branches and the submissions (cached: the kept answer shows at once, a newer one redraws). A submission
  // read from an older ecobuild has no base: its task's status (which has it) fills it in.
  async function load() {
    const [branches, tasks] = await Promise.all([
      ECO.query(MOD.root, ['branch', 'list'], fresh => { st.branches = fresh.ok ? fresh.result : st.branches; render(); }),
      ECO.query(MOD.root, ['task', 'list', '--submitted'], fresh => { if (fresh.ok) { st.submissions = fresh.result; fillBases().then(render); } }),
    ]);
    st.error = !branches.ok ? branches.error.message : !tasks.ok ? tasks.error.message : '';
    st.branches = branches.ok ? branches.result : [];
    st.submissions = tasks.ok ? tasks.result : [];
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
    const branches = shared(), names = new Set(branches.map(b => b.name)), side = el('br-side');
    const rows = [], walk = (b, depth) => { rows.push([b, depth]); for (const c of branches.filter(c => c.base === b.name && c !== b)) walk(c, depth + 1); };
    for (const b of branches.filter(b => !b.base || !names.has(b.base))) walk(b, 0);
    side.innerHTML = rows.map(([b, depth]) => {
      const n = incoming(b.name).length;
      return `<button type="button" role="tab" data-br="${esc(b.name)}" aria-selected="${b.name === st.selected}" tabindex="${b.name === st.selected ? 0 : -1}" style="--depth:${depth}"
        title="${esc(b.name)}${b.base ? `（作成元：${esc(b.base)}）` : ''}${n ? `　届いている提出 ${n} 件` : ''}">
        <span class="br-side-name">${esc(b.name)}</span><span class="br-count ${n ? '' : 'zero'}">${n}</span>
        ${open(b.submission) ? `<small class="br-side-sub">提出 → ${esc(b.submitted_to)}</small>` : ''}</button>`;
    }).join('') || '<p class="mi-note">共有ブランチはありません。</p>';
  }

  // Right: the branch, then what comes into it, then the one chosen.
  function renderMain() {
    const main = el('br-main'), b = shared().find(x => x.name === st.selected);
    if (!b) { main.innerHTML = st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : '<p class="mi-note">ブランチを選んでください。</p>'; return; }
    const where = [b.local && '手元', b.remote && 'GitHub'].filter(Boolean).join('・');
    const taskBranches = (st.branches || []).filter(t => t.is_task_branch && t.base === b.name);
    const items = incoming(b.name);
    if (st.item && !items.some(i => i.key === st.item)) { st.item = null; st.status = null; }
    if (!st.item && items.length) st.item = items[0].key;
    const branchActions = (open(b.submission) ? `<button type="button" class="primary" data-br-action="merge-own" title="${esc(ECO.submissionHelp.merge)}">取り込む</button>`
      : b.base ? '<button type="button" data-br-action="branch-submit" title="このブランチを、ほかのブランチへ取り込んでもらうように出します。">提出する</button>' : '')
      + (b.base ? '<button type="button" class="quiet-danger" data-br-action="branch-delete" title="このブランチを、手元と GitHub から削除します（取り込んでいない変更があれば止まります）。">削除</button>' : '');
    main.innerHTML = `${st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : ''}
      <div class="br-head"><div><h3>${esc(b.name)}</h3>
        <p class="mi-note">${pill('ブランチ')} ${esc(where)}${b.base ? `　作成元：${esc(b.base)}` : ''}${open(b.submission) ? `　${pill(`${b.submission.draft ? '下書きの' : ''}提出 → ${b.submitted_to}`, 'pr')}` : ''}</p></div>
        <div class="mi-actions">${branchActions}</div></div>
      <h4 class="br-section">このブランチへの提出 <span class="br-count ${items.length ? '' : 'zero'}">${items.length}</span></h4>
      <div class="br-list" role="listbox" aria-label="このブランチへの提出">${items.map(i => itemRow(i)).join('') ||
        '<p class="mi-note">届いている提出はありません。</p>'}</div>
      <div id="br-detail" class="br-detail"></div>
      ${taskBranches.length ? `<details class="br-task-branches"><summary>このブランチから作ったタスクブランチ（${taskBranches.length}）</summary>
        <ul>${taskBranches.map(t => { const n = /^task\/(\d+)$/.exec(t.name)?.[1];
          return `<li><span class="mi-branch-name">${esc(t.name)}</span> ${pill('タスクブランチ', 'ok')} <span class="mi-where">${esc([t.local && '手元', t.remote && 'GitHub'].filter(Boolean).join('・'))}</span>${open(t.submission) ? ' ' + pill('提出中', 'pr') : ''}${n ? ` <button type="button" data-open-ws="${n}">タスクブランチを開く</button>` : ''}</li>`; }).join('')}</ul></details>` : ''}`;
    renderDetail();
    if (st.item?.startsWith('task:') && (!st.status || 'task:' + st.status.number !== st.item)) loadStatus(Number(st.item.slice(5)));
  }
  function itemRow(i) {
    const selected = i.key === st.item;
    if (i.kind === 'branch') {
      const s = i.branch.submission;
      return `<button type="button" role="option" data-br-item="${esc(i.key)}" aria-selected="${selected}"><span>${pill('ブランチ')} ${esc(i.branch.name)}</span><span class="br-item-state">${esc(ECO.submissionText(s))}</span></button>`;
    }
    const t = i.task;
    return `<button type="button" role="option" data-br-item="${esc(i.key)}" aria-selected="${selected}"><span>#${t.number} ${esc(t.title)}</span>
      <span class="br-item-state">${esc(ECO.submissionText(t.submission))}${t.assignees.length ? ' · ' + esc(t.assignees.join(', ')) : ''}${mine(t) ? '（自分）' : ''}</span></button>`;
  }
  async function loadStatus(number) {
    const key = 'task:' + number;
    el('br-detail').innerHTML = ECO.loading();
    const doc = await ECO.query(MOD.root, ['task', 'status', String(number)], fresh => { if (st.item === key && fresh.ok) { st.status = fresh.result; renderDetail(); } });
    if (st.item !== key) return;
    st.status = doc.ok ? doc.result : null;
    if (!doc.ok) { el('br-detail').innerHTML = `<p class="mi-note">${esc(doc.error.message)}</p>`; return; }
    renderDetail();
  }
  // Where a submission is being checked (task review): the workspace of the module that shows it.
  const reviewingPlace = n => MOD.places.find(p => MOD.states.get(MOD.keyOf(p))?.reviewing_task === n) || null;
  function renderDetail() {
    const box = el('br-detail'); if (!box) return;
    if (st.item?.startsWith('branch:')) {
      const b = shared().find(x => 'branch:' + x.name === st.item); if (!b) { box.innerHTML = ''; return; }
      box.innerHTML = `<dl><dt>ブランチ</dt><dd><strong>${esc(b.name)}</strong> → ${esc(b.submitted_to)}</dd><dt>提出</dt><dd>${esc(ECO.submissionText(b.submission))}</dd><dt>URL</dt><dd>${esc(b.submission.url)}</dd></dl>`;
      const tools = document.createElement('div'); tools.className = 'br-tools';
      const act = document.createElement('div'); act.className = 'pr-act';
      act.append(ECO.submissionButton('merge', '取り込む', {kind: 'primary', enabled: !b.submission.draft, note: b.submission.draft ? '下書きの提出は取り込めません' : ''}));
      tools.append(document.createElement('div'), act); box.append(tools);
      return;
    }
    const t = st.status;
    if (!t || 'task:' + t.number !== st.item) { box.innerHTML = st.item ? ECO.loading() : ''; return; }
    const sub = t.pull_request, isOpen = open(sub), own = mine(t), draft = isOpen && sub.draft, reviewing = reviewingPlace(t.number);
    box.innerHTML = ECO.submissionDetail(t, {own});
    // Left: looking at it (small). Right: what can be done with it — someone else's is checked, approved or sent back;
    // one's own is finished or withdrawn (submitting and making a draft ready are done in its workspace).
    const tools = document.createElement('div'), look = document.createElement('div'), act = document.createElement('div');
    tools.className = 'br-tools'; look.className = 'pr-look'; act.className = 'pr-act';
    const b = ECO.submissionButton;
    look.append(b('diff', '差分'), b('comment', 'コメント'), b('task', 'タスク'), b('refresh', '更新'));
    if (reviewing) act.append(b('review-done', '判定せずに戻る'));
    if (isOpen && !own) {
      if (!reviewing) act.append(b('local-review', '手元で確認'));
      act.append(b('reject', '差し戻す'), b('approve', '承認して完了', {enabled: !draft, kind: 'primary', note: draft ? '下書きの提出は承認できません' : ''}));
    } else if (isOpen) {
      act.append(b('withdraw', '取り下げ', {kind: 'quiet-danger'}), b('finish', '完了', {enabled: !draft, kind: 'primary', note: draft ? '下書きの提出は完了できません。タスクブランチの作業空間で下書きを解除します' : ''}));
    }
    tools.append(look, act); box.append(tools);
  }
  function render() {
    if (el('branches-content').hidden) return;
    if (!st.loaded) { el('br-main').innerHTML = ECO.loading(); return; }
    renderSide(); renderMain();
  }

  // Doing things. After a change, the reads are read again (the server marks them stale) and the screen redrawn.
  const after = async doc => { if (doc) { st.status = null; await load(); } return doc; };
  async function taskAction(action) {
    const t = st.status; if (!t) return;
    const n = String(t.number);
    switch (action) {
      case 'refresh': st.status = null; return loadStatus(t.number);
      case 'diff': { const doc = await cli(['task', 'diff', n]); return doc.ok ? ECO.output(`#${n} の差分`, doc.result || '差分はありません。', {diff: true}) : ECO.showError(doc); }
      case 'comment': return ECO.form({title: `#${n} にコメント`, fields: [{name: 'message', label: '内容', type: 'textarea', required: true}], ok: 'コメントする',
        submit: async v => { if (!await after(await ECO.run(MOD.root, ['task', 'comment', n, '--message', v.message], {success: 'コメントしました。'}))) return 'コメントできませんでした。'; }});
      case 'task': showModulePage('tasks'); window.TASKS_SELECT?.(t.number); return;
      case 'approve': case 'reject': {
        const approve = action === 'approve';
        const v = await ECO.form(approve
          ? {title: `承認して完了：#${n}`, intro: '提出を承認し、そのまま完了します（CIを待って取り込み、タスクを閉じます）。', fields: [{name: 'message', label: 'コメント（任意）', type: 'textarea'}], ok: '承認して完了'}
          : {title: `差し戻す：#${n}`, intro: '直してほしいことを書いて差し戻します。タスクは作業中に戻ります。', fields: [{name: 'message', label: '直してほしいこと', type: 'textarea', required: true}], ok: '差し戻す', danger: true});
        if (!v) return;
        const place = reviewingPlace(t.number) || MOD.root;
        const doc = await ECO.run(place, ['task', action, n, ...(v.message ? ['--message', v.message] : [])], {success: approve ? `#${n} を承認して完了しました。` : `#${n} を差し戻しました。`});
        if (doc) MOD.reloadPlace(place);
        return after(doc);
      }
      case 'finish': {
        const v = await ECO.form({title: `完了：#${n}`, intro: 'CIを待って取り込み、タスクを閉じてタスクブランチを片付けます（中間提出なら、取り込んだ後にタスクブランチを作り直して続けます）。',
          fields: [{name: 'subject', label: '取り込むコミットの件名（空ならタスクの題名）'}, {name: 'ignore', label: 'CIが失敗していても完了する', type: 'checkbox'}], ok: '完了'});
        if (!v) return;
        const place = MOD.placeOfTask(t.number) || MOD.root;
        const doc = await ECO.run(place, ['task', 'finish', n, ...(v.subject ? ['--subject', v.subject] : []), ...(v.ignore ? ['--ignore-checks'] : [])], {success: r => r.partial ? '中間提出を取り込みました。' : `#${n} を完了しました。`});
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
  async function branchAction(action, name) {
    switch (action) {
      case 'merge': case 'merge-own': {
        const v = await ECO.form({title: `${name} の提出を取り込む`, intro: 'ブランチ同士の提出を、マージコミットで取り込みます。', fields: [{name: 'ignore', label: 'CIが失敗していても取り込む', type: 'checkbox'}], ok: '取り込む'});
        if (!v) return;
        return after(await ECO.run(MOD.root, ['branch', 'merge', name, ...(v.ignore ? ['--ignore-checks'] : [])], {success: `${name} の提出を取り込みました。`}));
      }
      case 'branch-submit': return ECO.form({title: `提出する：${name}`, fields: [
        {name: 'into', label: '取り込み先', type: 'select', options: shared().filter(b => b.name !== name).map(b => [b.name, b.name])},
        {name: 'title', label: '提出の題名'}], ok: '提出',
        submit: async v => { if (!v.into) return '取り込み先を選んでください。'; if (!await after(await ECO.run(MOD.root, ['branch', 'submit', name, '--into', v.into, ...(v.title ? ['--title', v.title] : [])], {success: `${name} を ${v.into} へ提出しました。`}))) return '提出できませんでした。'; }});
      case 'branch-delete': return after(await ECO.run(MOD.root, ['branch', 'delete', name], {success: `ブランチ ${name} を削除しました。`, confirm: `ブランチ ${name} を、手元と GitHub から削除します。`, title: 'ブランチを削除', danger: true}));
    }
  }

  const section = el('branches-content');
  section.addEventListener('click', e => {
    const tab = e.target.closest('[data-br]');
    if (tab) { st.selected = tab.dataset.br; st.item = null; st.status = null; render(); return; }
    const item = e.target.closest('[data-br-item]');
    if (item) { st.item = item.dataset.brItem; st.status = null; renderMain(); return; }
    const ws = e.target.closest('[data-open-ws]');
    if (ws) { MOD.openWorkspace(Number(ws.dataset.openWs)); return; }
    const own = e.target.closest('[data-br-action]');
    if (own) { branchAction(own.dataset.brAction, st.selected); return; }
    const pr = e.target.closest('[data-pr-action]');
    if (pr && !pr.disabled) {
      if (st.item?.startsWith('branch:')) branchAction(pr.dataset.prAction, st.item.slice(7)); else taskAction(pr.dataset.prAction);
    }
  });
  // ↑↓ between the branches (the tabs are vertical).
  el('br-side').addEventListener('keydown', e => {
    if (!['ArrowUp', 'ArrowDown'].includes(e.key)) return;
    const tabs = [...el('br-side').querySelectorAll('[data-br]')], i = tabs.findIndex(t => t.dataset.br === st.selected);
    const next = tabs[(i + (e.key === 'ArrowDown' ? 1 : tabs.length - 1)) % tabs.length]; if (!next) return;
    e.preventDefault(); st.selected = next.dataset.br; st.item = null; st.status = null; render(); el('br-side').querySelector(`[data-br="${CSS.escape(st.selected)}"]`)?.focus();
  });
  // Right-click a submission: the same actions as its buttons.
  section.addEventListener('contextmenu', e => {
    const item = e.target.closest('[data-br-item]'); if (!item) return;
    e.preventDefault();
    const x = e.clientX, y = e.clientY;
    if (st.item !== item.dataset.brItem) { st.item = item.dataset.brItem; st.status = null; renderMain(); }
    setTimeout(() => {
      const buttons = [...el('br-detail').querySelectorAll('[data-pr-action]')];
      if (buttons.length) ECO.menu(buttons.map(b => [b.textContent, () => b.click(), !b.disabled]), x, y);
    }, st.item?.startsWith('task:') && !st.status ? 800 : 0);
  });
  el('br-reload').addEventListener('click', () => { st.status = null; load(); });
  el('br-log').addEventListener('click', async () => { const doc = await cli(['log', '--all', '--gui']); if (!doc.ok) ECO.showError(doc); });
  el('br-create').addEventListener('click', () => ECO.form({title: 'ブランチを作成', intro: 'タスクブランチ以外のブランチ（develop・release など）を作成し、GitHubに反映します。', fields: [
    {name: 'name', label: 'ブランチ名（task/ で始まる名前はタスクブランチ専用）', required: true, placeholder: '例：develop'},
    {name: 'base', label: '作成元', type: 'select', value: st.selected, options: [['', '既定（default_base）'], ...shared().map(b => [b.name, b.name])]}], ok: '作成',
    submit: async v => {
      if (!await after(await ECO.run(MOD.root, ['branch', 'create', v.name, ...(v.base ? ['--base', v.base] : [])], {success: `ブランチ ${v.name} を作成しました。`}))) return '作成できませんでした。';
      st.selected = v.name; render();
    }}));

  pageHooks.branches = () => { if (!st.loaded) { render(); load(); } else render(); };
  ECO.onChange(() => { if (st.loaded) { st.status = null; if (!section.hidden) load(); else st.loaded = false; } });
})();
