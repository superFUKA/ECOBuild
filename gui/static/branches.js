'use strict';
// ブランチ: the module's shared branches (main, develop, … — not the task branches) as tabs on the left, in a tree of
// their names, with the count of submissions coming in; the chosen one on the right. First the chosen branch: where it is,
// who made it, its own submission, the protection of the default branch, what can be done with it (made, submitted,
// taken in, deleted, protected) and the submissions coming into it (looked at and handled: submissions.js). Then, in a
// card that folds (open when there is something to do), taking one shared branch into another directly (branch merge
// <from> --into <to>, no submission): the two branches and, before doing it, what it does (branch merge --dry-run: the
// commits coming in, the files, fast-forward / merge commit / conflict, who may). Last, the task branches made from it.
// Managing a branch is for admins (GitHub's permission, account show): the others see it with the buttons grey.
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {branches: null, submissions: [], access: null, protection: undefined, selected: '', loaded: false, error: '',
    merge: {from: '', into: '', plan: null, error: '', reading: false, read: 0, all: false}};
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
      reveal(st.selected);
    }
    render();
  }
  async function fillBases() {
    await Promise.all(st.submissions.filter(t => t.submission && !t.submission.base).map(async t => {
      const doc = await ECO.query(MOD.root, ['task', 'status', String(t.number)]);
      if (doc.ok && doc.result.base) t.submission = {...t.submission, base: doc.result.base};
    }));
  }

  // Left: the shared branches as a tree of their names (feature/x under a folder feature, as in Explorer), the branches
  // before the folders, each by name. A folder stays open or closed as left (kept for the module); a
  // closed one shows the count coming into the branches inside. Each branch: the count coming in,
  // dim when not an ECOBuild module, a mark when only here (not on GitHub; dimmer when already in the default base) or
  // only on GitHub.
  const FOLDERS_KEY = `ecobuild-branch-folders:${MOD.root}`;
  const openFolders = (() => { try { return new Set(JSON.parse(localStorage.getItem(FOLDERS_KEY) || '[]')); } catch (e) { return new Set(); } })();
  const saveFolders = () => { try { localStorage.setItem(FOLDERS_KEY, JSON.stringify([...openFolders])); } catch (e) { /* storage blocked */ } };
  const parents = name => name.split('/').slice(0, -1).map((_, i, parts) => parts.slice(0, i + 1).join('/'));
  const isOpen = path => openFolders.has(path);
  // Choosing a branch opens the folders it is in (they can be closed again: the folder then marks it).
  const reveal = name => { if (parents(name).some(p => !openFolders.has(p))) { parents(name).forEach(p => openFolders.add(p)); saveFolders(); } };
  const ICON = {
    local: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 12.5h7a3 3 0 0 0 .4-6 4 4 0 0 0-7.6-1A3.3 3.3 0 0 0 4.5 12.5z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M2 2l12 12" stroke="currentColor" stroke-width="1.3"/></svg>',
    remote: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 12.5h7a3 3 0 0 0 .4-6 4 4 0 0 0-7.6-1A3.3 3.3 0 0 0 4.5 12.5z" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>',
  };
  const whereOf = b => !b.remote ? `GitHub にない（手元だけ${b.merged ? '・既定の作成元に取り込み済み' : ''}）` : !b.local ? 'GitHub だけ（手元にない）' : '';
  function tree(branches) {
    const root = {folders: new Map(), branches: []};
    for (const b of branches) {
      let node = root;
      for (const path of parents(b.name)) {
        if (!node.folders.has(path)) node.folders.set(path, {path, folders: new Map(), branches: []});
        node = node.folders.get(path);
      }
      node.branches.push(b);
    }
    return root;
  }
  const inside = node => [...node.branches, ...[...node.folders.values()].flatMap(inside)];
  function renderSide() {
    const side = el('br-side'), def = st.access?.default_base || 'main', rows = [];
    const byName = (a, b) => a.localeCompare(b, 'ja');
    const walk = (node, depth) => {
      for (const b of [...node.branches].sort((x, y) => byName(x.name, y.name))) {
        const n = incoming(b.name).length, where = whereOf(b), leaf = b.name.split('/').pop();
        const cls = ['br-branch', b.unusable && 'other', !b.remote && b.merged && 'done'].filter(Boolean).join(' ');
        const tip = [b.name, b.unusable && 'ECOBuild のモジュールではない', where, n && `届いている提出 ${n} 件`].filter(Boolean).join('\n');
        rows.push(`<button type="button" role="tab" class="${cls}" data-br="${esc(b.name)}" aria-selected="${b.name === st.selected}" tabindex="${b.name === st.selected ? 0 : -1}" style="--depth:${depth}" title="${esc(tip)}">
          <span class="br-side-name">${esc(leaf)}</span>${b.name === def ? pill('既定', 'ok') : ''}${where ? `<span class="br-where" aria-label="${esc(where)}">${ICON[b.remote ? 'remote' : 'local']}</span>` : ''}${n ? `<span class="br-count">${n}</span>` : ''}
          ${open(b.submission) ? `<small class="br-side-sub">提出 → ${esc(b.submitted_to)}</small>` : ''}</button>`);
      }
      for (const f of [...node.folders.values()].sort((x, y) => byName(x.path, y.path))) {
        const shown = isOpen(f.path), all = inside(f), n = shown ? 0 : all.reduce((sum, b) => sum + incoming(b.name).length, 0);
        const holds = !shown && parents(st.selected).includes(f.path);
        rows.push(`<button type="button" class="br-folder${holds ? ' holds' : ''}" data-br-folder="${esc(f.path)}" aria-expanded="${shown}" tabindex="-1" style="--depth:${depth}" title="${esc(f.path)}/">
          <span class="br-side-name"><span class="br-caret" aria-hidden="true">${shown ? '▾' : '▸'}</span>${esc(f.path.split('/').pop())}</span><span class="br-folder-count">${all.length}</span>${n ? `<span class="br-count">${n}</span>` : ''}</button>`);
        if (shown) walk(f, depth + 1);
      }
    };
    walk(tree(shared()), 0);
    side.innerHTML = rows.join('') || '<p class="mi-note">共有ブランチはありません。</p>';
  }
  function toggleFolder(path, show = !isOpen(path)) {
    if (show) openFolders.add(path); else openFolders.delete(path);
    saveFolders(); renderSide();
    el('br-side').querySelector(`[data-br-folder="${CSS.escape(path)}"]`)?.focus();
  }

  // Taking a branch into another. The chosen branch is one side, fixed (shown, not chosen): at first where it goes (the arrow, a button, puts
  // it on the other side); the other is chosen: at first a branch made from it (its work), else the branch it was made
  // from (its latest), else another. Only branches on GitHub can be merged.
  function chooseMerge(into) {
    const others = shared().filter(b => b.remote && b.name !== into), base = shared().find(b => b.name === into)?.base;
    const from = (others.find(b => b.base === into) || others.find(b => b.name === base) || others[0] || {}).name || '';
    st.merge = {...st.merge, from, into, chosenFor: into, plan: null, error: '', all: false};
  }
  const fixedSide = () => st.merge.into === st.selected ? 'into' : 'from';
  // What the merge would do (branch merge --dry-run: changes nothing). An older answer arriving late is dropped.
  async function readPlan() {
    const m = st.merge, read = ++m.read;
    m.plan = null; m.error = '';
    if (!m.from || !m.into || m.from === m.into || !shared().find(b => b.name === st.selected)?.remote) { m.reading = false; renderMerge(); return; }
    m.reading = true; renderMerge();
    const doc = await cli(['branch', 'merge', m.from, '--into', m.into, '--dry-run']);
    if (read !== st.merge.read) return;
    m.reading = false;
    if (doc.ok) m.plan = doc.result; else m.error = [doc.error.message, doc.error.hint].filter(Boolean).join('\n');
    // Something to do (to take in, or a conflict): the card opens, once for the branch chosen.
    if (m.plan && m.plan.method !== 'up-to-date' && st.mergeOpenFor !== m.chosenFor) { st.mergeOpenFor = m.chosenFor; st.mergeOpen = true; el('br-merge-card')?.setAttribute('open', ''); }
    renderMerge();
  }
  const METHODS = {
    'fast-forward': ['早送り', 'ok', ''],
    merge: ['マージコミット', 'ok', ''],
    conflict: ['衝突する', 'bad', '同じところが両方で変わっているので、このままでは取り込めません。'],
    'up-to-date': ['取り込み済み', '', ''],
  };
  function renderMerge() {
    const box = el('br-merge'); if (!box) return;
    const m = st.merge, p = m.plan;
    const option = (b, chosen) => `<option value="${esc(b.name)}" ${b.name === chosen ? 'selected' : ''} ${b.remote ? '' : 'disabled'}>${esc(b.name)}${b.remote ? '' : '（GitHub にない）'}</option>`;
    const fixed = fixedSide(), chosen = shared().find(b => b.name === st.selected);
    const side = (key, label) => key === fixed
      ? `<div class="br-merge-pick"><span>${label}</span><span class="br-merge-fixed" title="${esc(st.selected)}">${esc(st.selected)}</span></div>`
      : `<label class="br-merge-pick"><span>${label}</span><select id="br-merge-other">${shared().filter(b => b.name !== st.selected).map(b => option(b, m[key])).join('')}</select></label>`;
    let result = '';
    if (chosen && !chosen.remote) result = `<p class="mi-note">${esc(st.selected)} は GitHub にないので、取り込みには使えません。</p>`;
    else if (m.reading) result = ECO.loading();
    else if (m.error) result = `<div class="eco-banner bad">${esc(m.error)}</div>`;
    else if (p) {
      const [label, cls, why] = METHODS[p.method] || [p.method, '', ''];
      const shown = m.all ? p.commits : p.commits.slice(0, 8), more = p.commit_count - shown.length;
      const commits = shown.length ? `<ol class="br-merge-commits">${shown.map(c => `<li><code>${esc(c.sha.slice(0, 7))}</code><span class="br-merge-subject" title="${esc(c.subject)}">${esc(c.subject)}</span><span class="mi-sub">${esc(c.author)}・${esc(ECO.localTime(c.date))}</span></li>`).join('')}</ol>
        ${more <= 0 ? '' : shown.length < p.commits.length ? `<button type="button" class="mi-link" data-br-merge="all">すべて表示（${p.commit_count} 件）</button>` : `<p class="mi-note">ほか ${more} 件（ログで見られます）</p>`}` : '';
      const files = p.file_count ? `<details class="br-merge-files"><summary>変わるファイル ${p.file_count} 件</summary><ul>${p.files.map(f => `<li>${esc(f)}</li>`).join('')}${p.file_count > p.files.length ? `<li class="mi-sub">ほか ${p.file_count - p.files.length} 件</li>` : ''}</ul></details>` : '';
      const conflicts = p.method !== 'conflict' ? '' : `<div class="eco-banner bad">衝突するファイル（${p.conflicts.length}）<ul class="br-conflicts">${p.conflicts.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
        衝突は「衝突を直すタスク」で直します：${esc(p.into)} を ${esc(p.name)} へ取り込むタスクの作業空間で直して ${esc(p.name)} へ入れると、${esc(p.name)} → ${esc(p.into)} が取り込めるようになります。
        <div class="br-merge-go"><button type="button" class="primary" data-br-merge="resolve">衝突を直す…</button></div></div>`;
      // Conflicts only in the files the type makes: made again from the merged sources when taken in (no submission needed).
      const resolved = p.resolved?.length ? `<p class="mi-note">自動で作るファイル ${p.resolved.length} 件が衝突しますが、取り込むときに、合わさった設定から作り直します（${p.resolved.map(esc).join('、')}）。</p>` : '';
      // The button only when it can be merged: grey (with who may) for the others, none when in already or conflicting.
      const mergeable = ['fast-forward', 'merge'].includes(p.method), note = p.allowed ? '' : `取り込めるのは ${p.owners} です。`;
      result = `<p class="br-merge-what"><span class="mi-pill ${cls}">${esc(label)}</span>${p.commit_count ? ` 入るコミット <b>${p.commit_count}</b> 件・変わるファイル <b>${p.file_count}</b> 件` : ''}${why ? `<span class="mi-sub">　${esc(why)}</span>` : ''}</p>
        ${conflicts}${resolved}${commits}${files}
        ${mergeable ? `<div class="br-merge-go">${note ? `<span class="mi-sub">${esc(note)}</span>` : ''}
          <button type="button" class="primary" data-br-merge="go" ${p.allowed ? '' : `disabled title="${esc(note)}"`}>${esc(p.name)} を ${esc(p.into)} へ取り込む</button></div>` : ''}`;
    }
    const sum = el('br-merge-sum');
    if (sum) sum.innerHTML = m.reading ? '<span class="eco-spinner"></span>' : p ? `<span class="mi-pill ${(METHODS[p.method] || [])[1] || ''}">${esc((METHODS[p.method] || [p.method])[0])}</span>${p.commit_count ? ` <span class="mi-sub">${esc(p.name)} → ${esc(p.into)}・${p.commit_count} 件</span>` : ''}` : '';
    box.innerHTML = `<div class="br-merge-row">${side('from', '取り込むブランチ')}<button type="button" class="br-merge-arrow" data-br-merge="swap" title="取り込む向きを入れ替える" aria-label="取り込む向きを入れ替える">→</button>${side('into', '取り込み先')}
      <button type="button" class="mi-link" data-br-merge="reload">確かめ直す</button></div>
      <div class="br-merge-result" aria-live="polite">${result}</div>`;
  }
  async function mergeAction(action) {
    const m = st.merge;
    switch (action) {
      case 'swap': st.merge = {...m, from: m.into, into: m.from, all: false}; return readPlan();
      case 'reload': return readPlan();
      case 'all': m.all = true; return renderMerge();
      case 'submit': return branchAction('branch-submit', m.from, m.into);
      case 'resolve': {   // branch resolve: a task (from the branch) taking in the other; its workspace opens stopped at the conflicts
        const p = m.plan; if (!p) return;
        if (!await ECO.confirm({title: '衝突を直す', ok: '作って開く', message: `${p.into} を ${p.name} へ取り込むタスクを作り、作業空間に取り出して ${p.into} を取り込みます（衝突したところで止まります）。\n`
          + `作業空間で衝突したファイルを直して「続ける」、提出のタブで ${p.name} へ入れる（このタスクはスカッシュせずに履歴ごと入ります）と、${p.name} → ${p.into} が取り込めるようになります。`})) return;
        const doc = await ECO.run(MOD.root, ['branch', 'resolve', p.name, '--into', p.into], {success: r => `衝突を直すタスク #${r.task} を作りました。` + (r.conflicts.length ? `衝突したファイル ${r.conflicts.length} 件を作業空間で直してください。` : '')});
        if (doc) await MOD.showPlace(doc.result.workspace);
        return readPlan();
      }
      case 'go': {
        const p = m.plan; if (!p) return;
        const how = p.method === 'fast-forward' ? '早送りで' : 'マージコミットで';
        return after(await ECO.run(MOD.root, ['branch', 'merge', p.name, '--into', p.into], {
          title: 'ブランチを取り込む', ok: '取り込む', success: `${p.name} を ${p.into} へ取り込みました。`,
          confirm: `${p.name} の ${p.commit_count} 件のコミットを、${p.into} へ${how}取り込みます（GitHub の ${p.into} が変わります。提出〔PR〕は作りません）。` + (p.resolved?.length ? `衝突する自動で作るファイル（${p.resolved.length} 件）は作り直します。` : '')}));
      }
    }
  }

  // Right: the branch and what can be done with it. Managing it is for admins (the others' buttons are grey with the
  // reason); a branch's own submission is taken in by those who handle the branch it goes into.
  function renderMain() {
    const main = el('br-main'), b = shared().find(x => x.name === st.selected);
    if (!b) { main.innerHTML = st.error ? `<div class="eco-banner bad">${esc(st.error)}<button type="button" class="sm" data-br-retry>読み直す</button></div>` : '<p class="mi-note">ブランチを選んでください。</p>'; return; }
    const where = [b.local && '手元', b.remote && 'GitHub'].filter(Boolean).join('・') + (b.remote ? '' : b.merged ? '（既定の作成元に取り込み済み）' : b.merged === false ? '（既定の作成元に取り込んでいない）' : '');
    const taskBranches = (st.branches || []).filter(t => t.is_task_branch && t.base === b.name);
    const creator = st.access?.creators?.[b.name] || '';
    const isDefault = b.name === (st.access?.default_base || 'main');
    const button = (action, label, {enabled = true, why = '', kind = '', help = ''} = {}) =>
      `<button type="button" ${kind ? `class="${kind}"` : ''} data-br-action="${action}" ${enabled ? '' : 'disabled'}${((t) => t ? ` title="${esc(t)}"` : '')([help, enabled || !why ? '' : `（${why}）`].filter(Boolean).join('\n'))}>${label}</button>`;
    const takes = ECO.canTakeIn(st.access, b.submitted_to);
    // A shared branch of an older ECOBuild format: brought up to date here (it is not opened as a workspace).
    const outdated = b.format != null && b.format < b.latest_format;
    const upgrade = outdated ? button('upgrade', '最新の仕様にする…', {enabled: b.remote && ECO.canTakeIn(st.access, b.name), why: b.remote ? ECO.takeInNote(st.access, b.name) : 'GitHub にないブランチです', help: 'GitHub のこのブランチを今の ECOBuild の仕様に合わせ、「ECOBuild の更新」としてコミットして push します（手元の作業ツリーには触れません）。'}) : '';
    const branchActions = (open(b.submission)
      ? button('merge-own', '取り込む', {kind: 'primary', enabled: takes && !b.submission.draft, why: b.submission.draft ? '下書きの提出は取り込めません' : ECO.takeInNote(st.access, b.submitted_to), help: ECO.submissionHelp.merge})
      : !isDefault ? button('branch-submit', '提出する', {enabled: canSubmit(b.name), why: `${ECO.adminNote}（このブランチを作った人も）`}) : '')
      + (!isDefault ? button('branch-delete', '削除…', {kind: 'danger-text', enabled: admin(), why: ECO.adminNote, help: 'このブランチを、手元と GitHub から削除します（タスクブランチの作成元・今いるブランチは消せません）。'}) : '');
    main.innerHTML = `${st.error ? `<div class="eco-banner bad">${esc(st.error)}<button type="button" class="sm" data-br-retry>読み直す</button></div>` : ''}
      <div class="br-head"><div><h3>${esc(b.name)}</h3>
        <p class="mi-note">${b.unusable ? pill('モジュールではない') + ' ' : ''}${esc(where)}${b.base ? `　作成元：${esc(b.base)}` : ''}${creator && !isDefault ? `　作った人：${esc(creator)}` : ''}${open(b.submission) ? `　${pill(`${b.submission.draft ? '下書きの' : ''}提出 → ${b.submitted_to}`, 'pr')}` : ''}</p></div>
        <div class="mi-actions">${branchActions}</div></div>
      <dl class="br-facts">
        ${b.unusable ? `<dt>作業</dt><dd>${esc(b.unusable)}。タスクブランチの作成元にはできません</dd>` : ''}
        ${outdated ? `<dt>仕様</dt><dd>以前の ECOBuild の仕様（版 ${b.format}。今の版は ${b.latest_format}）　${upgrade}</dd>` : ''}
        <dt>提出を処理できる人</dt><dd>${esc(isDefault ? '管理者' : creator ? `${creator}（作った人）と管理者` : '管理者')}</dd>
        ${isDefault ? `<dt>保護</dt><dd id="br-protection">${protectionText()}</dd>` : ''}
      </dl>
      <div id="sub-main"></div>
      <details class="br-merge" id="br-merge-card"${st.mergeOpen ? ' open' : ''}><summary><h4>ブランチ同士の取り込み <span class="mi-sub">提出（PR）なしで直接</span></h4><span class="br-merge-sum" id="br-merge-sum"></span></summary><div id="br-merge"></div></details>
      ${taskBranches.length ? `<details class="br-task-branches"><summary>このブランチから作ったタスクブランチ（${taskBranches.length}）</summary>
        <ul>${taskBranches.map(t => { const n = /^task\/(\d+)/.exec(t.name)?.[1];
          return `<li><span class="mi-branch-name">${esc(t.name)}</span> ${pill('タスクブランチ', 'ok')} <span class="mi-where">${esc([t.local && '手元', t.remote && 'GitHub'].filter(Boolean).join('・'))}</span>${open(t.submission) ? ' ' + pill('提出中', 'pr') : ''}${n ? ` <button type="button" data-open-ws="${n}">タスクブランチを開く</button>` : ''}</li>`; }).join('')}</ul></details>` : ''}`;
    window.BRANCH_SUBMISSIONS?.render(b.name, {branches: shared(), submissions: st.submissions, access: st.access});
    renderMerge();
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
    el('br-create').disabled = !admin(); el('br-create').title = admin() ? '' : ECO.adminNote;
    const choose = st.merge.chosenFor !== st.selected;
    if (choose) chooseMerge(st.selected);
    renderSide(); renderMain();
    if (choose) readPlan();
  }

  // Doing things. After a change, the reads are read again (the server marks them stale) and the screen redrawn.
  const after = async doc => { if (doc) { st.protection = undefined; await load(); readPlan(); } return doc; };
  async function branchAction(action, name, into = '') {
    switch (action) {
      case 'merge-own': {
        const v = await ECO.form({title: `${name} の提出を取り込む`, intro: 'ブランチ同士の提出を、マージコミットで取り込みます。', fields: [{name: 'ignore', label: 'CIが失敗していても取り込む', type: 'checkbox'}], ok: '取り込む'});
        if (!v) return;
        return after(await ECO.run(MOD.root, ['branch', 'merge', name, ...(v.ignore ? ['--ignore-checks'] : [])], {success: `${name} の提出を取り込みました。`}));
      }
      case 'branch-submit': return ECO.form({title: `提出する：${name}`, fields: [
        {name: 'into', label: '取り込み先', type: 'select', value: into, options: shared().filter(b => b.name !== name).map(b => [b.name, b.name])},
        {name: 'title', label: '提出の題名'}], ok: '提出',
        submit: async v => { if (!v.into) return '取り込み先を選んでください。'; if (!await after(await ECO.run(MOD.root, ['branch', 'submit', name, '--into', v.into, ...(v.title ? ['--title', v.title] : [])], {success: `${name} を ${v.into} へ提出しました。`}))) return '提出できませんでした。'; }});
      case 'upgrade': {
        const plan = await ECO.run(MOD.root, ['module', 'upgrade', '--branch', name, '--dry-run'], {busy: '変えるファイルを確かめています…'});
        if (!plan) return;
        const r = plan.result;
        if (!await ECO.confirm({title: '最新の仕様にする', message: `GitHub の ${name} を ECOBuild の仕様（版 ${r.format} → ${r.latest_format}）に合わせて、次のファイルを変えます（生成ファイルも作り直します）。変えたファイルは「ECOBuild の更新」として ${name} にコミットし、GitHub へ push します。手元の作業ツリーには触れません。`, detail: r.paths.join('\n'), ok: '最新の仕様にする'})) return;
        return after(await ECO.run(MOD.root, ['module', 'upgrade', '--branch', name], {busy: `${name} を最新の仕様にしています…`,
          success: x => x.commit ? `${name} を最新の仕様にしました（${x.paths.length}件のファイル）。「ECOBuild の更新」としてコミットし、push しました。` + (x.skipped.length ? `手で編集してあるため作り直していません：${x.skipped.join('、')}` : '') : `${name} は今の仕様です（変えるファイルはありませんでした）。`}));
      }
      case 'branch-delete': return after(await ECO.run(MOD.root, ['branch', 'delete', name], {success: `ブランチ ${name} を削除しました。`, confirm: `ブランチ ${name} を、手元と GitHub から削除します。`, title: 'ブランチを削除', ok: '削除する', danger: true}));
      case 'protect': {
        const p = st.protection && !st.protection.error ? st.protection : null;
        const v = await ECO.form({title: `${name} を保護する`, intro: 'GitHub のブランチの保護で、提出（PR）以外での変更・強制 push・削除を止めます。管理者は保護を越えられます。GitHub の無料プランの非公開リポジトリでは使えません。', fields: [
          {name: 'approvals', label: '取り込みに要る承認の数（0〜6）', value: String(p?.approvals ?? 0)},
          {name: 'ci', label: '最新のコミットの CI が通っていることも必須にする', type: 'checkbox', value: !!p?.checks?.length}], ok: '保護する'});
        if (!v) return;
        return after(await ECO.run(MOD.root, ['module', 'protect', '--approvals', String(Number(v.approvals) || 0), ...(v.ci ? ['--require-ci'] : [])], {success: `${name} を保護しました。`}));
      }
      case 'unprotect': return after(await ECO.run(MOD.root, ['module', 'protect', '--off'], {success: `${name} の保護を外しました。`, confirm: `${name} のブランチの保護を外します（提出以外でも変更できるようになります）。`, title: '保護を外す', ok: '保護を外す', danger: true}));
    }
  }

  const section = el('branches-content');
  section.addEventListener('click', e => {
    if (e.target.closest('[data-br-retry]')) { reload(); return; }
    const folder = e.target.closest('[data-br-folder]');
    if (folder) { toggleFolder(folder.dataset.brFolder); return; }
    const tab = e.target.closest('[data-br]');
    if (tab) { st.selected = tab.dataset.br; render(); return; }
    const ws = e.target.closest('[data-open-ws]');
    if (ws) { MOD.openWorkspace(Number(ws.dataset.openWs)); return; }
    const own = e.target.closest('[data-br-action]');
    if (own && !own.disabled) { branchAction(own.dataset.brAction, st.selected); return; }
    const merge = e.target.closest('[data-br-merge]');
    if (merge && !merge.disabled) mergeAction(merge.dataset.brMerge);
  });
  // The card of the merge folded or opened by hand stays so for the other branches.
  section.addEventListener('toggle', e => { if (e.target.id === 'br-merge-card') st.mergeOpen = e.target.open; }, true);
  section.addEventListener('change', e => {
    if (e.target.id !== 'br-merge-other') return;
    st.merge = {...st.merge, [fixedSide() === 'into' ? 'from' : 'into']: e.target.value, all: false};
    readPlan();
  });
  // The keys of a tree (as in Explorer): ↑↓ through the rows (a branch is chosen as it is reached), → opens a folder,
  // ← closes it or goes up to the folder of a branch.
  el('br-side').addEventListener('keydown', e => {
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    const side = el('br-side'), rows = [...side.querySelectorAll('[data-br], [data-br-folder]')];
    const row = e.target.closest('[data-br], [data-br-folder]') || side.querySelector('[aria-selected=true]'); if (!row) return;
    e.preventDefault();
    const folder = row.dataset.brFolder;
    if (e.key === 'ArrowRight') { if (folder !== undefined && !isOpen(folder)) toggleFolder(folder, true); return; }
    if (e.key === 'ArrowLeft') {
      if (folder !== undefined && isOpen(folder)) { toggleFolder(folder, false); return; }
      const up = parents(folder ?? row.dataset.br).pop();
      if (up) side.querySelector(`[data-br-folder="${CSS.escape(up)}"]`)?.focus();
      return;
    }
    const next = rows[rows.indexOf(row) + (e.key === 'ArrowDown' ? 1 : -1)]; if (!next) return;
    if (next.dataset.brFolder !== undefined) { next.focus(); return; }
    st.selected = next.dataset.br; render(); side.querySelector(`[data-br="${CSS.escape(st.selected)}"]`)?.focus();
  });
  const reload = async () => { st.protection = undefined; await load(); readPlan(); };
  el('br-reload').addEventListener('click', reload);
  window.BRANCHES_RELOAD = reload;   // after handling a submission (submissions.js)
  el('br-log').addEventListener('click', async () => { const doc = await cli(['log', '--all', '--gui']); if (!doc.ok) ECO.showError(doc); });
  el('br-create').addEventListener('click', () => ECO.form({title: 'ブランチを作成', fields: [
    {name: 'name', label: 'ブランチ名（task/ で始まる名前はタスクブランチ専用）', required: true, placeholder: '例：develop'},
    {name: 'base', label: '作成元', type: 'select', value: st.selected, options: [['', '既定（default_base）'], ...shared().map(b => [b.name, b.name])]}], ok: '作成',
    submit: async v => {
      if (!await after(await ECO.run(MOD.root, ['branch', 'create', v.name, ...(v.base ? ['--base', v.base] : [])], {success: `ブランチ ${v.name} を作成しました。`}))) return '作成できませんでした。';
      st.selected = v.name; reveal(v.name); render();
    }}));

  pageHooks.branches = () => { if (!st.loaded) { render(); load(); } else render(); };
  ECO.onChange(() => { if (st.loaded) { st.protection = undefined; if (!section.hidden) load().then(readPlan); else { st.loaded = false; st.merge.chosenFor = ''; } } });
})();
