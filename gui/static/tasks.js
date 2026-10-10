'use strict';
// Task management: task list / status / new / edit / plan / comment / close / reopen / start / remove / drop / clean,
// task workload, milestone list, pr list. Every change runs ecobuild. Where ecobuild keeps the stages and plans on
// GitHub is ecobuild's business: the screen only deals with tasks.
(() => {
  const tkEl = id => document.getElementById(id);
  const {esc} = ECO;
  const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const STAGES = [['planned', '計画中', 'backlog'], ['todo', '未着手', 'todo'], ['in_progress', '作業中', 'in_progress'], ['in_review', 'レビュー待ち', 'in_review'], ['done', '完了', 'done']];
  const PRIORITIES = ['High', 'Middle', 'Low'];   // task plan --priority（高い順）
  const STAGE = Object.fromEntries(STAGES.map(s => [s[0], s]));
  const st = {tasks: [], milestones: [], loaded: false, loading: false, view: 'list', selected: 0, details: new Map(), assignee: '', sort: {key: 'number', dir: 1}, person: ''};
  const me = () => MOD.me;
  const root = () => MOD.root;

  // A task's stage on screen: closed = done; not recorded yet = in progress when it has a workspace, else todo.
  const stageOf = t => t.state !== 'open' ? 'done' : t.stage || (t.workspace || t.remote || t.current ? 'in_progress' : 'todo');
  const byNumber = n => st.tasks.find(t => t.number === n);
  const md = d => d ? Number(d.slice(5, 7)) + '/' + Number(d.slice(8)) : '';
  const stageBadge = t => t.state !== 'open' ? `<span class="tk-stage ${t.closed_reason === 'not_planned' ? 'not_planned' : 'done'}">${t.closed_reason === 'not_planned' ? '対応しない' : '完了'}</span>` : `<span class="tk-stage ${STAGE[stageOf(t)][2]}">${STAGE[stageOf(t)][1]}</span>`;
  const prio = t => t.priority ? `<span class="tk-prio ${esc(t.priority)}">${esc(t.priority)}</span>` : '';
  const due = t => t.due ? `<span class="tk-due ${t.state === 'open' && t.due < today() ? 'overdue' : ''}">${md(t.due)}</span>` : '';
  const isAgent = who => /agent|bot/i.test(who);
  const avatarMark = who => !who ? '<span class="tk-avatar none" title="担当なし"></span>' : `<span class="tk-avatar ${isAgent(who) ? 'agent' : ''}" title="${esc(who)}">${isAgent(who) ? 'AI' : esc(who[0].toUpperCase())}</span>`;
  const avatar = who => !who ? avatarMark('') : `<button type="button" class="tk-person-link" data-person="${esc(who)}" title="${esc(who)} の画面">${avatarMark(who)}</button>`;
  const avatars = t => t.assignees.length ? t.assignees.map(avatar).join('') : avatar('');
  const flags = t => (t.blocked_by && t.state === 'open' ? `<span class="tk-flag blocked">待ち ${t.blocked_by}</span>` : '') + (t.subtasks ? `<span class="tk-flag">子 ${t.subtasks_done}/${t.subtasks}</span>` : '') + (t.current || t.workspace ? '<span class="tk-flag">作業空間</span>' : t.remote ? '<span class="tk-flag">GitHubに作業空間</span>' : '');
  const sel = t => `aria-selected="${t.number === st.selected}" data-task="${t.number}"`;

  // Loading ---------------------------------------------------------------------------------------
  async function load({full = false} = {}) {
    if (st.loading) return; st.loading = true;
    if (!st.loaded) tkEl('tk-main').innerHTML = ECO.loading('タスクを読み込んでいます…');
    const args = ['task', 'list', ...(tkEl('tk-closed').checked ? ['--all'] : []), ...(tkEl('tk-ready').checked ? ['--ready'] : [])];
    const jobs = [ECO.cli(root(), args, {quiet: true})];
    if (full || !st.loaded) jobs.push(ECO.cli(root(), ['milestone', 'list'], {quiet: true}));
    const [list, milestones] = await Promise.all(jobs);
    st.loading = false;
    if (milestones?.ok) st.milestones = milestones.result;
    if (!list.ok) { tkEl('tk-main').innerHTML = `<div class="eco-banner bad">${esc(list.error.message)}${list.error.hint ? '<br>' + esc(list.error.hint) : ''}</div>`; return; }
    st.tasks = list.result; st.loaded = true;
    renderAssigneeOptions(); render();
  }
  async function reloadAfter(n) { if (n) st.details.delete(n); await load(); if (n && st.selected === n) loadDetail(n); }

  function renderAssigneeOptions() {
    const accounts = [...new Set(st.tasks.flatMap(t => t.assignees))].sort();
    const current = st.assignee;
    tkEl('tk-assignee').innerHTML = [['', '担当者：すべて'], ['@me', '自分'], ...accounts.filter(a => a !== me()).map(a => [a, a]), ['-', '担当なし']].map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
    tkEl('tk-assignee').value = current;
  }

  // Views -----------------------------------------------------------------------------------------
  const assignedTo = (t, who) => who === '' ? true : who === '-' ? !t.assignees.length : t.assignees.includes(who === '@me' ? me() : who);
  const search = () => tkEl('tk-search').value.trim().toLowerCase();
  const visible = () => st.tasks.filter(t => assignedTo(t, st.assignee) && (!search() || t.title.toLowerCase().includes(search()) || ('#' + t.number) === search()));
  const PRIO_RANK = t => t.priority ? PRIORITIES.indexOf(t.priority) : 99;
  const SORT_KEYS = {number: t => t.number, title: t => t.title, stage: t => STAGES.findIndex(s => s[0] === stageOf(t)), priority: PRIO_RANK, due: t => t.due || '9999', assignee: t => t.assignees[0] || '￿'};
  const sorted = ts => [...ts].sort((a, b) => { const f = SORT_KEYS[st.sort.key], x = f(a), y = f(b); return (x < y ? -1 : x > y ? 1 : a.number - b.number) * st.sort.dir; });
  const sortHead = (key, label) => `<th><button type="button" class="tk-sort ${st.sort.key === key ? 'on' : ''}" data-sort="${key}">${label}<span aria-hidden="true">${st.sort.key === key ? (st.sort.dir > 0 ? '▲' : '▼') : ''}</span></button></th>`;
  const taskTable = (ts, withAssignee = true) => `<table class="tk-table"><thead><tr>${sortHead('number', '#')}${sortHead('title', '題名')}${sortHead('stage', '状態')}${sortHead('priority', '優先度')}${sortHead('due', '期限')}${withAssignee ? sortHead('assignee', '担当') : ''}</tr></thead><tbody>
    ${sorted(ts).map(t => `<tr ${sel(t)} class="${t.state === 'open' ? '' : 'closed'}"><td class="tk-num-cell"><span class="tk-num">#${t.number}</span></td><td class="tk-title-cell">${esc(t.title)} ${flags(t)}</td><td>${stageBadge(t)}</td><td>${prio(t)}</td><td>${due(t)}</td>${withAssignee ? `<td>${avatars(t)}</td>` : ''}</tr>`).join('')}</tbody></table>`;
  function renderList() {
    const ts = visible();
    return (ts.length ? taskTable(ts) : `<p class="tk-empty">${st.tasks.length ? '条件に合うタスクはありません。' : 'タスクはまだありません。「＋ 新しいタスク」で作れます。'}</p>`) + '<div class="tk-list-foot"><button type="button" data-tk="clean">完了した作業空間を片付ける</button></div>';
  }
  function renderStages() {
    return `<div class="tk-kanban">${STAGES.map(([key, ja, cls]) => {
      const cards = visible().filter(t => stageOf(t) === key);
      return `<section class="tk-column" data-stage="${key}"><div class="tk-column-head"><span><span class="tk-stage ${cls}">${ja}</span></span><small>${cards.length}</small></div><div class="tk-column-cards">
      ${cards.map(t => `<article class="tk-kcard" draggable="true" ${sel(t)}><div class="tk-kcard-meta"><span class="tk-num">#${t.number}</span>${prio(t)}</div><div class="tk-kcard-title">${esc(t.title)}</div><div class="tk-kcard-meta">${due(t)}${flags(t)}${avatar(t.assignees[0])}</div></article>`).join('')}
      </div></section>`;
    }).join('')}</div>`;
  }
  const DAY = 86400000, WEEK = ['日', '月', '火', '水', '木', '金', '土'];
  const dayOf = d => Date.parse(d + 'T00:00:00Z') / DAY, weekday = n => new Date(n * DAY).getUTCDay();
  function renderTimeline() {
    const dated = visible().filter(t => t.planned_start && t.planned_end).sort((a, b) => a.planned_start.localeCompare(b.planned_start) || a.number - b.number);
    const undated = visible().filter(t => !t.planned_start || !t.planned_end), now = dayOf(today());
    const all = dated.flatMap(t => [t.planned_start, t.planned_end, t.due].filter(Boolean)).map(dayOf).concat(now);
    let first = Math.min(...all), last = Math.max(...all, now + 13);
    first -= (weekday(first) + 6) % 7; last += 6 - (weekday(last) + 6) % 7;
    const days = Array.from({length: last - first + 1}, (_, i) => first + i), col = n => n - first + 2, off = n => weekday(n) === 0 || weekday(n) === 6;
    const head = days.map(n => { const d = new Date(n * DAY); return `<div class="tl-day ${off(n) ? 'off' : ''} ${n === now ? 'today' : ''}" style="grid-column:${col(n)}">${d.getUTCDate() === 1 || n === first ? `<b>${d.getUTCMonth() + 1}月</b>` : ''}<span>${d.getUTCDate()}</span><small>${WEEK[weekday(n)]}</small></div>`; }).join('');
    const shade = dated.length ? days.filter(off).map(n => `<div class="tl-off" style="grid-column:${col(n)};grid-row:2 / span ${dated.length}"></div>`).join('') : '';
    const rows = dated.map((t, i) => { const r = i + 2, late = t.state === 'open' && dayOf(t.planned_end) < now, s = STAGE[stageOf(t)];
      return `<div class="tl-label" style="grid-row:${r}" ${sel(t)}><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span></div>
      <div class="tl-bar ${s[2]} ${late ? 'late' : ''} ${t.number === st.selected ? 'sel' : ''} ${t.state === 'open' ? 'movable' : ''}" style="grid-row:${r};grid-column:${col(dayOf(t.planned_start))} / ${col(dayOf(t.planned_end)) + 1}" data-task="${t.number}" title="${md(t.planned_start)}〜${md(t.planned_end)}${t.state === 'open' ? '（ドラッグで移動、右端で終了予定を変える）' : ''}">${s[1]}<span class="tl-grip" aria-hidden="true"></span></div>
      ${t.due ? `<div class="tl-due ${t.state === 'open' && t.due < today() ? 'overdue' : ''}" style="grid-row:${r};grid-column:${col(dayOf(t.due))}" title="期限 ${md(t.due)}">◆</div>` : ''}`; }).join('');
    return `<div class="tl-wrap"><div class="tl-grid" style="grid-template-columns:220px repeat(${days.length}, 28px);grid-template-rows:54px repeat(${dated.length}, 34px)">
      <div class="tl-corner">タスク</div>${head}${shade}<div class="tl-now" style="grid-column:${col(now)};grid-row:1 / span ${dated.length + 1}"></div>${rows}</div></div>
      <div class="tl-legend"><span><i class="tl-key bar"></i>開始予定〜終了予定</span><span><i class="tl-key due">◆</i>期限</span><span><i class="tl-key now"></i>今日</span><span><i class="tl-key late"></i>終了予定を過ぎている</span></div>
      ${undated.length ? `<p class="tk-note">日程のないタスク：${undated.map(t => `<span class="tk-label" data-task="${t.number}" style="cursor:pointer">#${t.number} ${esc(t.title)}</span>`).join('')}</p>` : ''}`;
  }
  function scrollToToday() { const wrap = document.querySelector('.tl-wrap'), nowLine = document.querySelector('.tl-now'); if (wrap && nowLine) wrap.scrollLeft = Math.max(0, nowLine.offsetLeft - 220 - 7 * 28); }

  const VIEWS = {list: renderList, stages: renderStages, timeline: renderTimeline};
  function render() {
    for (const b of document.querySelectorAll('.tk-views [data-view]')) b.setAttribute('aria-selected', String(b.dataset.view === st.view));
    if (st.loaded) tkEl('tk-main').innerHTML = VIEWS[st.view]();
    if (st.view === 'timeline') scrollToToday();
    tkEl('tk-detail').hidden = !st.selected; document.querySelector('.tk-body').classList.toggle('no-detail', !st.selected);
    if (st.selected) renderDetail();
  }

  // Detail ----------------------------------------------------------------------------------------
  async function loadDetail(n) {
    const doc = await ECO.cli(root(), ['task', 'status', String(n)], {quiet: true});
    st.details.set(n, doc.ok ? doc.result : {error: doc.error});
    if (st.selected === n) renderDetail();
  }
  function select(n) { st.selected = n; render(); if (!st.details.has(n)) loadDetail(n); }
  window.TASKS_SELECT = n => { if (!st.loaded) load().then(() => select(n)); else select(n); };

  function renderDetail() {
    const n = st.selected, summary = byNumber(n), d = st.details.get(n);
    const close = '<button type="button" class="tk-d-close" data-close-detail title="詳細を閉じる" aria-label="詳細を閉じる">×</button>';
    if (!d) { tkEl('tk-detail').innerHTML = `<div class="tk-d-head"><span class="tk-num">#${n}</span>${close}</div>${summary ? `<h3 class="tk-d-title">${esc(summary.title)}</h3>` : ''}${ECO.loading()}`; return; }
    if (d.error) { tkEl('tk-detail').innerHTML = `<div class="tk-d-head"><span class="tk-num">#${n}</span>${close}</div><p class="tk-empty">${esc(d.error.message)}</p>`; return; }
    const t = d.task || {}, open = d.state === 'open', place = MOD.placeOfTask(n);
    const view = {...(summary || {}), ...t, state: d.state, workspace: d.workspace, remote: d.remote};
    const hasWorkspace = !!place || d.workspace;
    const primary = !open ? '<button type="button" data-tk="reopen">開き直す</button>'
      : hasWorkspace ? '<button type="button" class="primary" data-tk="open-ws">作業空間を開く</button>'
      : `<button type="button" class="primary" data-tk="start">${d.remote ? '作業を再開' : '作業を開始'}</button>`;
    const dis = open ? '' : 'disabled';
    const rel = x => `<div class="tk-rel" data-task="${x.number}"><span class="tk-num">#${x.number}</span><span class="tk-grow">${esc(x.title)}</span>${x.state === 'open' ? '' : '<span class="tk-stage done">完了</span>'}</div>`;
    const relations = [d.parent && ['親タスク', [d.parent]], d.subtasks.length && ['子タスク', d.subtasks], d.blocked_by.length && ['先に終わるべき', d.blocked_by], d.blocking.length && ['待っているタスク', d.blocking]].filter(Boolean);
    const pr = d.pull_request;
    tkEl('tk-detail').innerHTML = `
    <div class="tk-d-head"><span class="tk-num">#${n}</span>${stageBadge(view)}${close}</div>
    <h3 class="tk-d-title">${esc(d.title)}</h3>
    <div class="tk-d-actions">${primary}${open ? '<button type="button" data-tk="close">閉じる</button>' : ''}<button type="button" data-tk="edit">編集</button>
      <details class="tk-menu"><summary aria-label="その他の操作">⋯</summary><div>
        ${open && !hasWorkspace && !d.remote ? '<button type="button" data-tk="start">作業を開始…</button>' : ''}
        ${hasWorkspace ? '<button type="button" data-tk="remove">手元の作業空間を消す</button>' : ''}
        ${hasWorkspace || d.remote ? '<button type="button" class="danger-text" data-tk="drop">作業をやめる</button>' : ''}
        <button type="button" data-tk="github">GitHubで開く</button></div></details></div>
    <section class="tk-d-section"><dl class="tk-kv">
      <dt>優先度</dt><dd><select data-plan="priority" ${dis}><option value="">なし</option>${PRIORITIES.map(p => `<option ${p === t.priority ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select></dd>
      <dt>開始予定</dt><dd><input type="date" data-plan="planned_start" value="${esc(t.planned_start || '')}" ${dis}></dd>
      <dt>終了予定</dt><dd><input type="date" data-plan="planned_end" value="${esc(t.planned_end || '')}" ${dis}></dd>
      <dt>期限</dt><dd><input type="date" data-plan="due" value="${esc(t.due || '')}" ${dis}></dd>
      <dt>担当者</dt><dd class="tk-chips">${d.assignees.map(a => `<span class="tk-chip"><button type="button" class="tk-person-name" data-person="${esc(a)}" title="${esc(a)} の画面">${esc(a)}${a === me() ? '（自分）' : ''}</button><button type="button" class="x" data-remove-assignee="${esc(a)}" title="外す">×</button></span>`).join('')}<button type="button" class="tk-add" data-tk="add-assignee" title="担当者を加える">＋</button></dd>
      <dt>ラベル</dt><dd class="tk-chips">${d.labels.map(l => `<span class="tk-chip">${esc(l)}<button type="button" class="x" data-remove-label="${esc(l)}" title="外す">×</button></span>`).join('')}<button type="button" class="tk-add" data-tk="add-label" title="ラベルを付ける">＋</button></dd>
      <dt>マイルストーン</dt><dd><select data-milestone><option value="">なし</option>${st.milestones.map(m => `<option ${m.title === d.milestone ? 'selected' : ''}>${esc(m.title)}</option>`).join('')}${d.milestone && !st.milestones.some(m => m.title === d.milestone) ? `<option selected>${esc(d.milestone)}</option>` : ''}</select></dd>
      <dt>作業空間</dt><dd>${hasWorkspace ? `task/${n}${place && MOD.keyOf(place) !== MOD.keyOf(MOD.root) ? `<div class="tk-muted">${esc(place)}</div>` : ''}` : d.remote ? `<span class="tk-muted">GitHubにだけあります（作業を再開で手元へ）</span>` : '<span class="tk-muted">なし</span>'}${d.base ? `<div class="tk-muted">作成元 ${esc(d.base)}</div>` : ''}</dd>
      <dt>PR</dt><dd>${pr ? `#${pr.number}（${esc(pr.state)}）` : '<span class="tk-muted">なし</span>'}</dd>
      <dt>日付</dt><dd class="tk-muted">追加 ${esc(t.created || '-')}${t.started ? ' · 開始 ' + esc(t.started) : ''}${t.finished ? ' · 終了 ' + esc(t.finished) : ''}</dd>
    </dl></section>
    ${relations.length ? `<section class="tk-d-section"><dl class="tk-kv">${relations.map(([label, xs]) => `<dt>${label}</dt><dd>${xs.map(rel).join('')}</dd>`).join('')}</dl></section>` : ''}
    <section class="tk-d-section"><p class="tk-d-body">${esc(d.body) || '<span class="tk-muted">本文はありません</span>'}</p></section>
    <section class="tk-d-section"><h4>コメント ${d.comments.length}</h4>${d.comments.map(c => `<article class="tk-comment"><header>${esc(c.author)}</header><p>${esc(c.body)}</p></article>`).join('')}
      <div class="tk-comment-box"><textarea id="tk-comment-text" placeholder="コメントを書く（作業の記録・申し送り）" aria-label="コメント"></textarea><div><button type="button" data-tk="comment">コメント</button></div></div></section>`;
  }

  // Operations ------------------------------------------------------------------------------------
  const run = (args, options = {}) => ECO.run(options.dir || root(), args, options);
  const placeFor = n => MOD.placeOfTask(n) || root();

  // Choices for dialogs. ecobuild has no command for "members who can be assigned", so the candidates are
  // what its commands return: yourself, the assignees of the tasks (task list --all) and the PR authors (pr list --all).
  async function members() {
    if (!st.members) {
      const [tasks, prs] = await Promise.all([ECO.cli(root(), ['task', 'list', '--all'], {quiet: true}), ECO.cli(root(), ['pr', 'list', '--all'], {quiet: true})]);
      const names = new Set([...(tasks.ok ? tasks.result.flatMap(t => t.assignees) : []), ...(prs.ok ? prs.result.map(p => p.author).filter(Boolean) : [])]);
      if (me()) names.delete(me());
      st.members = [...(me() ? [me()] : []), ...[...names].sort((a, b) => a.localeCompare(b))];
    }
    return st.members;
  }
  const memberOptions = list => list.map(m => [m, m === me() ? `${m}（自分）` : m]);
  const parentOptions = (self, current) => [['', 'なし'], ...st.tasks.filter(t => t.number !== self && (t.state === 'open' || t.number === current))
    .sort((a, b) => a.number - b.number).map(t => [String(t.number), `#${t.number} ${t.title}`]),
    ...(current && !st.tasks.some(t => t.number === current) ? [[String(current), `#${current}`]] : [])];
  // Defaults the module sets (ecobuild.toml), to put into the fields from the start.
  async function moduleDefaults() {
    if (!st.defaults) st.defaults = await ECO.call('module-defaults', {dir: root()}).catch(() => ({}));
    return st.defaults;
  }

  async function startDialog(n) {
    const t = byNumber(n) || {}, d = st.details.get(n) || {}, defaults = await moduleDefaults();
    const parent = d.parent?.number || t.parent || 0;
    // The default base: a child task starts from its parent's workspace; otherwise default_base (ecobuild.toml).
    const base = parent ? `task/${parent}` : d.remote && d.base ? d.base : defaults.default_base || '';
    const suggested = root().replace(/[\\/]+$/, '') + '-' + n;
    await ECO.form({title: (d.remote ? '作業を再開' : '作業を開始') + `：#${n}`, intro: esc(t.title || d.title || ''), busy: `#${n} の作業空間を用意しています…`, fields: [
      {name: 'place', label: '作業の場所', type: 'radio', value: 'here', options: [
        ['here', 'このモジュールのcloneに作業空間を作る', `task/${n} のブランチを作って切り替えます（${root()}）`],
        ['dir', '専用のcloneを作る', '並行作業用。別のフォルダにcloneして、新しいタブで開きます'],
        ['none', '作業空間を作らない', '調査・設計など、コードを変えないタスク（作業中にするだけ）']]},
      {name: 'dir', label: '専用のcloneの場所', value: suggested},
      {name: 'base', label: '作成元のブランチ', value: base,
        help: parent ? `子タスクは親タスクの作業空間（task/${parent}）から作ります。` : d.remote ? 'GitHubにある作業空間から再開します（作成元は記録されたもの）。' : '既定は ecobuild.toml の default_base です。'},
      {name: 'ignoreBlocked', label: '先に終わるべきタスクが開いていても始める', type: 'checkbox'}], ok: '開始',
      submit: async v => {
        // Pass --base only when it was changed from the default (the CLI decides the default the same way).
        const args = ['task', 'start', String(n), ...(v.base && v.base !== base && v.place !== 'none' ? ['--base', v.base] : []), ...(v.ignoreBlocked ? ['--ignore-blocked'] : [])];
        if (v.place === 'none') args.push('--no-workspace');
        if (v.place === 'dir') { if (!v.dir) return '専用のcloneの場所を入力してください。'; args.push('--dir', v.dir); }
        const doc = await run(args, {success: v.place === 'none' ? `#${n} を作業中にしました。` : `作業空間 task/${n} を用意しました。`, quietErrors: true});
        if (!doc) return '開始できませんでした。';
        if (v.place === 'here') { await MOD.reloadPlace(root()); MOD.openWorkspace(n); }
        if (v.place === 'dir') { const place = await MOD.addPlace(doc.module || v.dir); await MOD.reloadPlace(place); showModulePage('workspace'); MOD.activate(place, true); }
        reloadAfter(n);
      }});
  }
  async function newTaskDialog(preset = {}) {
    const people = await members();
    await ECO.form({title: '新しいタスク', busy: 'タスクを作っています…', fields: [
      {name: 'title', label: '題名', required: true, placeholder: '何をするか'},
      {name: 'body', label: '本文', type: 'textarea', placeholder: '背景・完了の条件など'},
      {name: 'assignees', label: '担当者', type: 'checks', value: preset.assignees || [], options: memberOptions(people), empty: 'まだ候補がありません（下の欄に入力できます）'},
      {name: 'otherAssignees', label: '候補にいない担当者（GitHubのアカウント、カンマ区切り。任意）'},
      {name: 'label', label: 'ラベル（カンマ区切り。なければ作ります）'},
      {name: 'parent', label: '親タスク', type: 'select', value: preset.parent ? String(preset.parent) : '', options: parentOptions(0, 0)},
      {name: 'blockedBy', label: '先に終わるべきタスクの番号（カンマ区切り）'},
      {name: 'milestone', label: 'マイルストーン', type: 'select', options: [['', 'なし'], ...st.milestones.map(m => [m.title, m.title + (m.due ? `（${m.due}）` : '')])]},
      {name: 'due', label: '期限', type: 'date'}, {name: 'plannedStart', label: '開始予定日', type: 'date'}, {name: 'plannedEnd', label: '終了予定日', type: 'date'},
      {name: 'start', label: '作成したら、このモジュールのcloneで作業を開始する（担当者を選ばなければ自分になります）', type: 'checkbox'}], ok: '作成',
      submit: async v => {
        const args = ['task', 'new', v.title];
        const assignees = [...v.assignees, ...ECO.commaList(v.otherAssignees)];
        if (assignees.length) args.push('--assignee', [...new Set(assignees)].join(','));
        for (const [key, option] of [['body', '--body'], ['label', '--label'], ['parent', '--parent'], ['blockedBy', '--blocked-by'], ['milestone', '--milestone'], ['due', '--due'], ['plannedStart', '--planned-start'], ['plannedEnd', '--planned-end']]) if (v[key]) args.push(option, v[key]);
        if (v.start) args.push('--start');
        const doc = await run(args, {success: r => `タスク #${(r.task || r).number} を作りました。`, quietErrors: true});
        if (!doc) return '作成できませんでした。';
        const n = (doc.result.task || doc.result).number;
        st.members = null;
        if (v.start) { await MOD.reloadPlace(root()); }
        await reloadAfter(); select(n);
      }});
  }
  async function editDialog(n) {
    const d = st.details.get(n); if (!d || d.error) return;
    const current = d.parent?.number || 0;
    await ECO.form({title: `タスク #${n} を編集`, busy: `#${n} を保存しています…`, fields: [
      {name: 'title', label: '題名', value: d.title, required: true}, {name: 'body', label: '本文', type: 'textarea', value: d.body, rows: 6},
      {name: 'parent', label: '親タスク', type: 'select', value: current ? String(current) : '', options: parentOptions(n, current)},
      {name: 'addBlocked', label: '先に終わるべきタスクを加える（番号、カンマ区切り）'},
      {name: 'removeBlocked', label: '先に終わるべきタスクから外す（番号、カンマ区切り）', placeholder: d.blocked_by.map(b => b.number).join(',')}], ok: '保存',
      submit: async v => {
        const args = ['task', 'edit', String(n)], parent = Number(v.parent) || 0;
        if (v.title !== d.title) args.push('--title', v.title);
        if (v.body !== d.body) args.push('--body', v.body);
        if (parent !== current && !parent) args.push('--clear-parent');
        if (parent !== current && parent && !current) args.push('--parent', String(parent));
        if (v.addBlocked) args.push('--add-blocked-by', v.addBlocked);
        if (v.removeBlocked) args.push('--remove-blocked-by', v.removeBlocked);
        // Moving to another parent: ecobuild does not re-parent implicitly, so remove the old parent first, then set the new one.
        const reparent = parent && current && parent !== current;
        if (args.length === 3 && !reparent) return '変える内容がありません。';
        if (args.length > 3 && !await run(args, {success: '保存しました。', quietErrors: true})) return '保存できませんでした。';
        if (reparent) {
          if (!await run(['task', 'edit', String(n), '--clear-parent'], {quietErrors: true})) return `親タスク #${current} から外せませんでした。`;
          if (!await run(['task', 'edit', String(n), '--parent', String(parent)], {success: `親タスクを #${parent} にしました。`, quietErrors: true})) return `親タスクを #${parent} にできませんでした（#${current} からは外れています）。`;
        }
        reloadAfter(n);
      }});
  }
  async function addAssigneeDialog(n) {
    const already = st.details.get(n)?.assignees || byNumber(n)?.assignees || [], people = (await members()).filter(m => !already.includes(m));
    const v = await ECO.form({title: `担当者を加える：#${n}`, fields: [
      {name: 'who', label: '担当者', type: 'checks', options: memberOptions(people), empty: '候補はすべて担当者です（下の欄に入力できます）'},
      {name: 'other', label: '候補にいない担当者（GitHubのアカウント、カンマ区切り。任意）'}], ok: '加える'});
    const who = v ? [...new Set([...v.who, ...ECO.commaList(v.other)])] : [];
    if (who.length) editList(n, '--add-assignee', who.join(','), '担当者を加えました。');
  }
  async function closeDialog(n) {
    const v = await ECO.form({title: `タスク #${n} を閉じる`, fields: [{name: 'reason', label: '閉じる理由', type: 'radio', value: 'completed', options: [['completed', '完了', 'やり終えた'], ['not_planned', '対応しない', 'やらないと決めた']]}],
      extra: '<p class="eco-intro">作業空間は残ります。片付けは「作業をやめる」か「完了した作業空間を片付ける」で行います。</p>', ok: '閉じる'});
    if (v && await run(['task', 'close', String(n), ...(v.reason === 'not_planned' ? ['--not-planned'] : [])], {success: `#${n} を閉じました。`})) reloadAfter(n);
  }
  async function dropDialog(n) {
    const v = await ECO.form({title: `作業をやめる：#${n}`, intro: 'PRを出さずに作業をやめます。開いているPRを閉じ、作業空間を手元とGitHubから消して、作成元へ戻ります。', fields: [{name: 'close', label: 'タスクも「対応しない」として閉じる', type: 'checkbox'}], ok: 'やめる', danger: true});
    if (!v) return;
    const place = placeFor(n), doc = await run(['task', 'drop', String(n), ...(v.close ? ['--close'] : [])], {dir: place, success: r => `作業空間 ${r.branch} をやめました。` + (r.switched_to ? `${r.switched_to} に戻りました。` : '')});
    if (doc) { await MOD.reloadPlace(place); reloadAfter(n); }
  }
  async function removeWorkspace(n) {
    const place = placeFor(n);
    const ok = await ECO.confirm({title: `手元の作業空間を消す：#${n}`, message: '手元の作業空間だけを消します。GitHubのブランチ・PR・タスクはそのままで、「作業を再開」でPush済みの所から再開できます。（未コミット・未Pushの変更があれば止まります）', ok: '消す', danger: true});
    if (!ok) return;
    const doc = await run(['task', 'remove', String(n)], {dir: place, success: r => `手元の作業空間 ${r.branch} を消しました。` + (r.switched_to ? `${r.switched_to} に戻りました。` : '')});
    if (doc) { await MOD.reloadPlace(place); reloadAfter(n); }
  }
  async function cleanDialog() {
    const results = [];
    for (const place of MOD.places) { const doc = await ECO.cli(place, ['task', 'clean', '--dry-run']); if (doc.ok) results.push([place, doc.result]); else return ECO.showError(doc); }
    const removable = results.filter(([, r]) => r.removed.length), skipped = results.flatMap(([, r]) => r.skipped);
    const body = (removable.length ? '<p>片付ける作業空間：</p><ul class="eco-list">' + removable.flatMap(([p, r]) => r.removed.map(b => `<li>${esc(b)}${MOD.keyOf(p) === MOD.keyOf(root()) ? '' : `<span class="eco-help">（${esc(p)}）</span>`}</li>`)).join('') + '</ul>' : '<p>片付ける作業空間はありません。</p>')
      + (skipped.length ? '<p>残すもの：</p><ul class="eco-list">' + skipped.map(s => `<li>${esc(s.branch)}：${esc(s.reason)}</li>`).join('') + '</ul>' : '');
    const ok = await ECO.dialog({title: '完了した作業空間を片付ける', body: '<p class="eco-intro">タスクが閉じた作業空間を片付けます。マージしていないコミットがある作業空間は残します。</p>' + body,
      buttons: removable.length ? [['キャンセル', '', false], ['片付ける', 'primary', true]] : [['閉じる', 'primary', false]]});
    if (!ok) return;
    for (const [place] of removable) {
      const doc = await run(['task', 'clean', '--yes'], {dir: place, success: r => (r.removed.length ? `片付けました：${r.removed.join('、')}` : '片付けたものはありません。') + (r.switched_to ? `（${r.switched_to} に移りました）` : '')});
      if (!doc) continue;
      for (const s of doc.result.skipped) ECO.toast(`${s.branch} は残しました：${s.reason}`, 'info', 9000);
      await MOD.reloadPlace(place);
    }
    reloadAfter();
  }
  async function plan(n, key, value) {
    const option = {priority: '--priority', due: '--due', planned_start: '--planned-start', planned_end: '--planned-end'}[key];
    const args = ['task', 'plan', String(n), ...(value ? [option, value] : ['--clear', key])];
    if (await run(args, {success: '計画を保存しました。'})) reloadAfter(n); else renderDetail();
  }
  async function editList(n, option, value, message) { if (await run(['task', 'edit', String(n), option, value], {success: message})) reloadAfter(n); }

  // Account popup: assigned tasks (task list), counts (task workload), PRs (pr list), review requests (pr list --review-requested).
  async function showPerson(who) {
    st.person = who;
    const body = tkEl('tk-person-body'); body.innerHTML = ECO.loading(); if (!tkEl('tk-person-dialog').open) tkEl('tk-person-dialog').showModal();
    const [workload, prs, reviews] = await Promise.all([ECO.cli(root(), ['task', 'workload'], {quiet: true}), ECO.cli(root(), ['pr', 'list'], {quiet: true}), who === me() ? ECO.cli(root(), ['pr', 'list', '--review-requested'], {quiet: true}) : null]);
    if (st.person !== who) return;
    const w = workload.ok ? workload.result.find(x => x.assignee === who) : null;
    const ts = st.tasks.filter(t => t.state === 'open' && t.assignees.includes(who)), doing = ts.filter(t => ['in_progress', 'in_review'].includes(stageOf(t)));
    const own = prs.ok ? prs.result.filter(p => p.author === who) : [], asked = reviews?.ok ? reviews.result : [];
    const stat = (label, value, cls = '') => `<div class="tk-pf-stat ${cls}"><b>${value}</b><span>${label}</span></div>`;
    const taskRow = t => `<div class="tk-row" data-task="${t.number}"><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span>${stageBadge(t)}${due(t)}</div>`;
    const taskOfPr = p => /^task\/(\d+)$/.exec(p.head)?.[1] || '';
    const prRow = p => `<div class="tk-row" data-task="${taskOfPr(p)}"><span class="tk-num">PR #${p.number}</span><span class="tk-grow">${esc(p.title)}</span><span class="tk-pill">${p.draft ? '下書き' : 'レビュー待ち'}</span>${p.author !== who ? `<span class="tk-muted">${esc(p.author)}</span>` : ''}</div>`;
    const section = (title, html, extra = '') => `<section class="tk-pf-section ${extra}"><h4>${title}</h4>${html || '<p class="tk-muted">ありません</p>'}</section>`;
    body.innerHTML = `<div class="tk-pf"><header class="tk-pf-head">${avatarMark(who)}<div><div class="tk-pf-name">${esc(who)}${who === me() ? '<span class="tk-pill ok">自分</span>' : ''}</div><div class="tk-muted">GitHub アカウント</div></div>
      <button type="button" class="tk-d-close" data-close-person title="閉じる" aria-label="閉じる">×</button></header>
      <div class="tk-pf-stats">${stat('担当（親を除く）', w ? w.open : ts.length)}${stat('作業中', w ? w.in_progress : doing.length)}${stat('期限切れ', w ? w.overdue : 0, w?.overdue ? 'bad' : '')}${stat('開いているPR', own.length)}</div>
      <div class="tk-pf-grid">${section('作業中', doing.map(taskRow).join(''))}${section('プルリクエスト', own.map(prRow).join(''))}${who === me() ? section('レビューを頼まれているPR', asked.map(prRow).join('')) : ''}
      ${section('担当タスク', ts.length ? taskTable(ts, false) : '', 'wide')}</div></div>`;
  }

  // Right-click menu on a task (list rows, stage cards, timeline, relations, the account popup) --------------
  async function detailOf(n) { if (!st.details.has(n) || st.details.get(n).error) await loadDetail(n); return st.details.get(n); }
  function taskMenu(n, x, y) {
    const t = byNumber(n); if (!t) return;
    const open = t.state === 'open', hasWorkspace = !!MOD.placeOfTask(n) || t.workspace || t.current, mine = me() && t.assignees.includes(me());
    ECO.menu([
      ['詳細を見る', () => select(n)],
      ...(open ? [hasWorkspace ? ['作業空間を開く', () => MOD.openWorkspace(n)] : [t.remote ? '作業を再開…' : '作業を開始…', async () => { await detailOf(n); startDialog(n); }]] : []),
      '-',
      ['担当者を加える…', async () => { await detailOf(n); addAssigneeDialog(n); }],
      ...(me() ? [mine ? ['自分を担当から外す', () => editList(n, '--remove-assignee', '@me', '担当から外れました。')] : ['自分を担当にする', () => editList(n, '--add-assignee', '@me', '担当にしました。')]] : []),
      ...(open ? PRIORITIES.map(p => [`優先度：${p}${t.priority === p ? '（今）' : ''}`, () => plan(n, 'priority', p), t.priority !== p]).concat(t.priority ? [['優先度を消す', () => plan(n, 'priority', '')]] : []) : []),
      '-',
      ['子タスクを作る…', () => newTaskDialog({parent: n}), open],
      ['編集…', async () => { await detailOf(n); select(n); editDialog(n); }],
      open ? ['閉じる…', () => closeDialog(n)] : ['開き直す', async () => { if (await run(['task', 'reopen', String(n)], {success: `#${n} を開き直しました。`})) reloadAfter(n); }],
      ...(hasWorkspace || t.remote ? ['-', ...(hasWorkspace ? [['手元の作業空間を消す…', () => removeWorkspace(n)]] : []), ['作業をやめる…', () => dropDialog(n)]] : []),
      '-',
      ['GitHubで開く', () => window.open(t.url, '_blank', 'noopener')],
    ], x, y);
  }
  document.addEventListener('contextmenu', e => {
    const target = e.target.closest('#tasks-content [data-task], #tk-person-dialog [data-task]');
    if (!target || !target.dataset.task) return;
    e.preventDefault(); taskMenu(Number(target.dataset.task), e.clientX, e.clientY);
  });

  // Drag a card to another column. The stages before the work (計画中・未着手) are set with task plan --stage; the work
  // stages follow the work itself, so dropping there starts the work (作業中) or closes the task (完了) through the dialogs.
  let draggedCard = 0;
  document.addEventListener('dragstart', e => {
    const card = e.target.closest?.('#tasks-content .tk-kcard'); if (!card) return;
    draggedCard = Number(card.dataset.task); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', '#' + draggedCard); card.classList.add('dragging');
  });
  document.addEventListener('dragend', e => { e.target.closest?.('.tk-kcard')?.classList.remove('dragging'); draggedCard = 0; document.querySelectorAll('.tk-column.drop').forEach(c => c.classList.remove('drop')); });
  document.addEventListener('dragover', e => {
    const column = draggedCard && e.target.closest?.('#tasks-content .tk-column'); if (!column) return;
    e.preventDefault(); document.querySelectorAll('.tk-column.drop').forEach(c => { if (c !== column) c.classList.remove('drop'); }); column.classList.add('drop');
  });
  document.addEventListener('drop', async e => {
    const column = draggedCard && e.target.closest?.('#tasks-content .tk-column'); if (!column) return;
    e.preventDefault(); column.classList.remove('drop');
    const n = draggedCard, t = byNumber(n), stage = column.dataset.stage; draggedCard = 0;
    if (!t || stageOf(t) === stage) return;
    if (stage === 'done') return closeDialog(n);
    if (t.state !== 'open') return ECO.toast('閉じたタスクです。先に開き直してください。', 'info');
    if (stage === 'in_progress') {
      if (MOD.placeOfTask(n) || t.workspace) return ECO.toast('作業空間があるタスクは、もう作業中です。', 'info');
      await detailOf(n); return startDialog(n);
    }
    if (stage === 'in_review') return ECO.toast('レビュー待ちには、作業空間でプルリクエストを提出すると移ります。', 'info', 6000);
    if (MOD.placeOfTask(n) || t.workspace || t.remote) return ECO.toast('作業空間があるタスクです。作業をやめると未着手に戻ります。', 'info', 6000);
    if (await run(['task', 'plan', String(n), '--stage', stage], {success: `#${n} を${STAGE[stage][1]}にしました。`})) reloadAfter(n);
  });

  // Drag a timeline bar to move its planned dates; drag its right edge to change the planned end.
  let barDrag = null;
  const DAY_PX = 28, shiftDate = (d, days) => new Date(Date.parse(d + 'T00:00:00Z') + days * 86400000).toISOString().slice(0, 10);
  document.addEventListener('pointerdown', e => {
    const bar = e.target.closest?.('#tasks-content .tl-bar.movable'); if (!bar || e.button !== 0) return;
    const t = byNumber(Number(bar.dataset.task)); if (!t) return;
    const resize = e.target.classList.contains('tl-grip');
    barDrag = {bar, t, resize, x: e.clientX, days: 0, column: bar.style.gridColumn};
    try { bar.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer */ } bar.classList.add('dragging');
  });
  document.addEventListener('pointermove', e => {
    if (!barDrag) return;
    const days = Math.round((e.clientX - barDrag.x) / DAY_PX); if (days === barDrag.days) return;
    barDrag.days = days;
    const [a, b] = barDrag.column.split('/').map(x => Number(x.trim()));
    const start = barDrag.resize ? a : a + days, end = Math.max(start + 1, b + days);
    barDrag.bar.style.gridColumn = `${start} / ${end}`;
    const newStart = barDrag.resize ? barDrag.t.planned_start : shiftDate(barDrag.t.planned_start, days);
    const newEnd = shiftDate(barDrag.t.planned_end, days);
    barDrag.bar.title = `${md(newStart)}〜${md(newEnd < newStart ? newStart : newEnd)}`;
  });
  document.addEventListener('pointerup', async () => {
    if (!barDrag) return;
    const {bar, t, resize, days} = barDrag; barDrag = null; bar.classList.remove('dragging');
    if (!days) return;
    const start = resize ? t.planned_start : shiftDate(t.planned_start, days);
    let end = shiftDate(t.planned_end, days); if (end < start) end = start;
    const doc = await run(['task', 'plan', String(t.number), '--planned-start', start, '--planned-end', end], {success: `#${t.number} の予定を ${md(start)}〜${md(end)} にしました。`});
    if (doc) reloadAfter(t.number); else render();
  });

  // Events ----------------------------------------------------------------------------------------
  document.querySelector('.tk-views').addEventListener('click', e => { const b = e.target.closest('[data-view]'); if (b) { st.view = b.dataset.view; render(); } });
  tkEl('tk-search').addEventListener('input', render);
  tkEl('tk-assignee').addEventListener('change', e => { st.assignee = e.target.value; render(); });
  tkEl('tk-ready').addEventListener('change', () => load());
  tkEl('tk-closed').addEventListener('change', () => load());
  tkEl('tk-reload').addEventListener('click', () => { st.details.clear(); load({full: true}).then(() => st.selected && loadDetail(st.selected)); });
  tkEl('tk-new').addEventListener('click', newTaskDialog);
  tkEl('tk-person-dialog').addEventListener('close', () => { st.person = ''; });

  document.addEventListener('click', async e => {
    const inTasks = e.target.closest('#tasks-content, #tk-person-dialog'); if (!inTasks) return;
    const action = e.target.closest('[data-tk]');
    if (action) {
      action.closest('details.tk-menu')?.removeAttribute('open');
      const n = st.selected;
      switch (action.dataset.tk) {
        case 'clean': return cleanDialog();
        case 'start': return startDialog(n);
        case 'open-ws': return MOD.openWorkspace(n);
        case 'reopen': if (await run(['task', 'reopen', String(n)], {success: `#${n} を開き直しました。`})) reloadAfter(n); return;
        case 'close': return closeDialog(n);
        case 'edit': return editDialog(n);
        case 'drop': return dropDialog(n);
        case 'remove': return removeWorkspace(n);
        case 'github': { const d = st.details.get(n); if (d?.url) window.open(d.url, '_blank', 'noopener'); return; }
        case 'comment': { const text = tkEl('tk-comment-text').value.trim(); if (!text) return; if (await run(['task', 'comment', String(n), '--message', text], {success: 'コメントしました。'})) reloadAfter(n); return; }
        case 'add-assignee': return addAssigneeDialog(n);
        case 'add-label': { const v = await ECO.form({title: 'ラベルを付ける', fields: [{name: 'label', label: 'ラベル（カンマ区切り。なければ作ります）', required: true}], ok: '付ける'}); if (v) editList(n, '--add-label', v.label, 'ラベルを付けました。'); return; }
      }
      return;
    }
    const removeAssignee = e.target.closest('[data-remove-assignee]'); if (removeAssignee) return editList(st.selected, '--remove-assignee', removeAssignee.dataset.removeAssignee, '担当者を外しました。');
    const removeLabel = e.target.closest('[data-remove-label]'); if (removeLabel) return editList(st.selected, '--remove-label', removeLabel.dataset.removeLabel, 'ラベルを外しました。');
    const person = e.target.closest('[data-person]'); if (person) return showPerson(person.dataset.person);
    if (e.target.closest('[data-close-person]')) return tkEl('tk-person-dialog').close();
    const sortButton = e.target.closest('[data-sort]');
    if (sortButton) { const key = sortButton.dataset.sort; st.sort = {key, dir: st.sort.key === key ? -st.sort.dir : 1}; render(); if (st.person) showPerson(st.person); return; }
    const picked = e.target.closest('#tk-person-dialog [data-task]');
    if (picked && !e.target.closest('button')) { if (picked.dataset.task) { tkEl('tk-person-dialog').close(); select(Number(picked.dataset.task)); } return; }
    if (e.target.closest('[data-close-detail]')) { st.selected = 0; render(); return; }
    const task = e.target.closest('#tasks-content [data-task]');
    if (task && !e.target.closest('button, select, input, textarea')) select(Number(task.dataset.task));
  });
  document.addEventListener('change', e => {
    if (!e.target.closest('#tk-detail')) return;
    if (e.target.dataset.plan) plan(st.selected, e.target.dataset.plan, e.target.value);
    if (e.target.matches('[data-milestone]')) {
      const n = st.selected, args = ['task', 'edit', String(n), ...(e.target.value ? ['--milestone', e.target.value] : ['--clear-milestone'])];
      run(args, {success: 'マイルストーンを変えました。'}).then(doc => doc ? reloadAfter(n) : renderDetail());
    }
  });

  pageHooks.tasks = () => { if (!st.loaded) load(); else render(); };
  pageHooks.changed = () => { if (st.loaded && !mEl('tasks-content').hidden) load(); };
})();
