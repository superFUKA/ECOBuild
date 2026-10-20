'use strict';
// ブランチ: the module's shared branches (main, develop, … — not the task branches) as tabs on the left, by where they
// come from, with the count of submissions coming in; the chosen one on the right: where it is, who made it, its own
// submission, the protection of the default branch, what can be done with it (made, submitted, taken in, deleted,
// protected), the submissions coming into it (looked at and handled: submissions.js) and the task branches made from it.
// Managing a branch is for admins (GitHub's permission, account show): the others see it with the buttons grey.
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {branches: null, submissions: [], access: null, protection: undefined, selected: '', loaded: false, error: ''};
  const cli = args => ECO.cli(MOD.root, args, {quiet: true});
  const pill = (text, cls = '') => `<span class="mi-pill ${cls}">${esc(text)}</span>`;
  const shared = () => (Array.isArray(st.branches) ? st.branches : []).filter(b => !b.is_task_branch);
  const open = s => s?.state === 'open';
  // What comes into a branch: the open submissions of tasks (their base) and of other branches (submitted_to).
  const incoming = name => [
    ...st.submissions.filter(t => open(t.submission) && t.submission.base === name).map(t => ({kind: 'task', key: 'task:' + t.number, task: t})),
    ...shared().filter(b => open(b.submission) && b.submitted_to === name).map(b => ({kind: 'branch', key: 'branch:' + b.name, branch: b})),
  ];
  const admin = () => ECO.isAdmin(st.access);
  // A branch is submitted by an admin or by whoever made it (the same as the CLI).
  const canSubmit = name => admin() || (st.access?.creators?.[name] || '').toLowerCase() === (st.access?.login || '').toLowerCase();

  // Reads: the branches, the submissions (for the counts) and the account (cached: the kept answer shows at once, a newer
  // one redraws). A submission read from an older ecobuild has no base: its task's status (which has it) fills it in.
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
      st.selected = (shared().find(b => b.name === (st.access?.default_base || 'main')) || shared()[0] || {}).name || '';
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

  // Right: the branch and what can be done with it. Managing it is for admins (the others' buttons are grey with the
  // reason); a branch's own submission is taken in by those who handle the branch it goes into.
  function renderMain() {
    const main = el('br-main'), b = shared().find(x => x.name === st.selected);
    if (!b) { main.innerHTML = st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : '<p class="mi-note">ブランチを選んでください。</p>'; return; }
    const where = [b.local && '手元', b.remote && 'GitHub'].filter(Boolean).join('・');
    const taskBranches = (st.branches || []).filter(t => t.is_task_branch && t.base === b.name);
    const creator = st.access?.creators?.[b.name] || '';
    const isDefault = b.name === (st.access?.default_base || 'main');
    const button = (action, label, {enabled = true, why = '', kind = '', help = ''} = {}) =>
      `<button type="button" ${kind ? `class="${kind}"` : ''} data-br-action="${action}" ${enabled ? '' : 'disabled'} title="${esc(help + (enabled || !why ? '' : `\n（${why}）`))}">${label}</button>`;
    const takes = ECO.canTakeIn(st.access, b.submitted_to);
    const branchActions = (open(b.submission)
      ? button('merge-own', '取り込む', {kind: 'primary', enabled: takes && !b.submission.draft, why: b.submission.draft ? '下書きの提出は取り込めません' : ECO.takeInNote(st.access, b.submitted_to), help: ECO.submissionHelp.merge})
      : !isDefault ? button('branch-submit', '提出する', {enabled: canSubmit(b.name), why: `${ECO.adminNote}（このブランチを作った人も）`, help: 'このブランチを、ほかのブランチへ取り込んでもらうように出します。'}) : '')
      + (!isDefault ? button('branch-delete', '削除', {kind: 'quiet-danger', enabled: admin(), why: ECO.adminNote, help: 'このブランチを、手元と GitHub から削除します（タスクブランチの作成元・今いるブランチは消せません）。'}) : '');
    main.innerHTML = `${st.error ? `<div class="eco-banner bad">${esc(st.error)}</div>` : ''}
      <div class="br-head"><div><h3>${esc(b.name)}</h3>
        <p class="mi-note">${pill('ブランチ')} ${esc(where)}${b.base ? `　作成元：${esc(b.base)}` : ''}${creator && !isDefault ? `　作った人：${esc(creator)}` : ''}${open(b.submission) ? `　${pill(`${b.submission.draft ? '下書きの' : ''}提出 → ${b.submitted_to}`, 'pr')}` : ''}</p></div>
        <div class="mi-actions">${branchActions}</div></div>
      <dl class="br-facts">
        <dt>提出を処理できる人</dt><dd>${esc(isDefault ? '管理者' : creator ? `${creator}（作った人）と管理者` : '管理者')}</dd>
        ${isDefault ? `<dt>保護</dt><dd id="br-protection">${protectionText()}</dd>` : ''}
      </dl>
      <div id="sub-main"></div>
      ${taskBranches.length ? `<details class="br-task-branches"><summary>このブランチから作ったタスクブランチ（${taskBranches.length}）</summary>
        <ul>${taskBranches.map(t => { const n = /^task\/(\d+)/.exec(t.name)?.[1];
          return `<li><span class="mi-branch-name">${esc(t.name)}</span> ${pill('タスクブランチ', 'ok')} <span class="mi-where">${esc([t.local && '手元', t.remote && 'GitHub'].filter(Boolean).join('・'))}</span>${open(t.submission) ? ' ' + pill('提出中', 'pr') : ''}${n ? ` <button type="button" data-open-ws="${n}">タスクブランチを開く</button>` : ''}</li>`; }).join('')}</ul></details>` : ''}`;
    window.BRANCH_SUBMISSIONS?.render(b.name, {branches: shared(), submissions: st.submissions, access: st.access});
    if (isDefault && st.protection === undefined) loadProtection();
  }
  // The protection of the default branch (module protect): GitHub shows it to admins only.
  function protectionText() {
    if (!admin()) return '<span class="mi-sub">管理者だけが見られます</span>';
    const p = st.protection, set = ' <button type="button" class="mi-link" data-br-action="protect">設定…</button>';
    if (!p && p !== false) return p === null && st.protectionRead ? `なし（提出以外でも変更できます）${set}` : '…';
    if (p.error) return `<span class="mi-sub">${esc(p.error)}</span>`;
    return `${esc(`取り込みは提出だけ・承認 ${p.approvals ? `${p.approvals} 人` : 'は不要'}${p.checks?.length ? `・CI（${p.checks.join(', ')}）` : ''}`)}${set} <button type="button" class="mi-link" data-br-action="unprotect">外す</button>`;
  }
  async function loadProtection() {
    if (!admin()) return;
    st.protection = null; st.protectionRead = false;
    const doc = await cli(['module', 'protect', '--show']);
    st.protection = doc.ok ? doc.result : {error: doc.error.message}; st.protectionRead = true;
    const box = el('br-protection'); if (box) box.innerHTML = protectionText();
  }
  function render() {
    if (el('branches-content').hidden) return;
    if (!st.loaded) { el('br-main').innerHTML = ECO.loading(); return; }
    el('br-create').disabled = !admin(); el('br-create').title = admin() ? 'タスクブランチ以外のブランチを作成します' : ECO.adminNote;
    renderSide(); renderMain();
  }

  // Doing things. After a change, the reads are read again (the server marks them stale) and the screen redrawn.
  const after = async doc => { if (doc) { st.protection = undefined; await load(); } return doc; };
  async function branchAction(action, name) {
    switch (action) {
      case 'merge-own': {
        const v = await ECO.form({title: `${name} の提出を取り込む`, intro: 'ブランチ同士の提出を、マージコミットで取り込みます。', fields: [{name: 'ignore', label: 'CIが失敗していても取り込む', type: 'checkbox'}], ok: '取り込む'});
        if (!v) return;
        return after(await ECO.run(MOD.root, ['branch', 'merge', name, ...(v.ignore ? ['--ignore-checks'] : [])], {success: `${name} の提出を取り込みました。`}));
      }
      case 'branch-submit': return ECO.form({title: `提出する：${name}`, fields: [
        {name: 'into', label: '取り込み先', type: 'select', options: shared().filter(b => b.name !== name).map(b => [b.name, b.name])},
        {name: 'title', label: '提出の題名'}], ok: '提出',
        submit: async v => { if (!v.into) return '取り込み先を選んでください。'; if (!await after(await ECO.run(MOD.root, ['branch', 'submit', name, '--into', v.into, ...(v.title ? ['--title', v.title] : [])], {success: `${name} を ${v.into} へ提出しました。`}))) return '提出できませんでした。'; }});
      case 'branch-delete': return after(await ECO.run(MOD.root, ['branch', 'delete', name], {success: `ブランチ ${name} を削除しました。`, confirm: `ブランチ ${name} を、手元と GitHub から削除します。`, title: 'ブランチを削除', danger: true}));
      case 'protect': {
        const p = st.protection && !st.protection.error ? st.protection : null;
        const v = await ECO.form({title: `${name} を保護する`, intro: 'GitHub のブランチの保護で、提出（PR）以外での変更・強制 push・削除を止めます。管理者は保護を越えられます。GitHub の無料プランの非公開リポジトリでは使えません。', fields: [
          {name: 'approvals', label: '取り込みに要る承認の数（0〜6）', value: String(p?.approvals ?? 0)},
          {name: 'ci', label: '最新のコミットの CI が通っていることも必須にする', type: 'checkbox', value: !!p?.checks?.length}], ok: '保護する'});
        if (!v) return;
        return after(await ECO.run(MOD.root, ['module', 'protect', '--approvals', String(Number(v.approvals) || 0), ...(v.ci ? ['--require-ci'] : [])], {success: `${name} を保護しました。`}));
      }
      case 'unprotect': return after(await ECO.run(MOD.root, ['module', 'protect', '--off'], {success: `${name} の保護を外しました。`, confirm: `${name} のブランチの保護を外します（提出以外でも変更できるようになります）。`, title: '保護を外す', danger: true}));
    }
  }

  const section = el('branches-content');
  section.addEventListener('click', e => {
    const tab = e.target.closest('[data-br]');
    if (tab) { st.selected = tab.dataset.br; render(); return; }
    const ws = e.target.closest('[data-open-ws]');
    if (ws) { MOD.openWorkspace(Number(ws.dataset.openWs)); return; }
    const own = e.target.closest('[data-br-action]');
    if (own && !own.disabled) branchAction(own.dataset.brAction, st.selected);
  });
  // ↑↓ between the branches (the tabs are vertical).
  el('br-side').addEventListener('keydown', e => {
    if (!['ArrowUp', 'ArrowDown'].includes(e.key)) return;
    const tabs = [...el('br-side').querySelectorAll('[data-br]')], i = tabs.findIndex(t => t.dataset.br === st.selected);
    const next = tabs[(i + (e.key === 'ArrowDown' ? 1 : tabs.length - 1)) % tabs.length]; if (!next) return;
    e.preventDefault(); st.selected = next.dataset.br; render(); el('br-side').querySelector(`[data-br="${CSS.escape(st.selected)}"]`)?.focus();
  });
  const reload = () => { st.protection = undefined; return load(); };
  el('br-reload').addEventListener('click', reload);
  window.BRANCHES_RELOAD = reload;   // after handling a submission (submissions.js)
  el('br-log').addEventListener('click', async () => { const doc = await cli(['log', '--all', '--gui']); if (!doc.ok) ECO.showError(doc); });
  el('br-create').addEventListener('click', () => ECO.form({title: 'ブランチを作成', intro: 'タスクブランチ以外のブランチ（develop・release など）を作成し、GitHubに反映します。', fields: [
    {name: 'name', label: 'ブランチ名（task/ で始まる名前はタスクブランチ専用）', required: true, placeholder: '例：develop'},
    {name: 'base', label: '作成元', type: 'select', value: st.selected, options: [['', '既定（default_base）'], ...shared().map(b => [b.name, b.name])]}], ok: '作成',
    submit: async v => {
      if (!await after(await ECO.run(MOD.root, ['branch', 'create', v.name, ...(v.base ? ['--base', v.base] : [])], {success: `ブランチ ${v.name} を作成しました。`}))) return '作成できませんでした。';
      st.selected = v.name; render();
    }}));

  pageHooks.branches = () => { if (!st.loaded) { render(); load(); } else render(); };
  ECO.onChange(() => { if (st.loaded) { st.protection = undefined; if (!section.hidden) load(); else st.loaded = false; } });
})();
