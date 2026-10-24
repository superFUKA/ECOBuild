'use strict';
// Task management: task list / status / new / edit / comment / close / reopen / start / finish / approve / reject / withdraw / drop / clean,
// task next / overdue / workload, sprint list / status, milestone list / status.
// The board (view stages) is the tasks by stage (drag a card to change its stage); the summary (view summary) is made from these commands' own totals (ecobuild has no board commands for the user). Every change runs ecobuild. Where ecobuild keeps the stages and plans on
// GitHub is ecobuild's business: the screen only deals with tasks.
(() => {
  const tkEl = id => document.getElementById(id);
  const {esc} = ECO;
  const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const STAGES = [['planned', '計画中', 'backlog'], ['todo', '未着手', 'todo'], ['in_progress', '作業中', 'in_progress'], ['in_review', 'レビュー待ち', 'in_review'], ['done', '完了', 'done']];
  const PRIORITIES = ['High', 'Middle', 'Low'];   // task edit --priority（高い順）
  const STAGE = Object.fromEntries(STAGES.map(s => [s[0], s]));
  const st = {tasks: [], milestones: [], sprints: [], loaded: false, loading: false, view: 'stages', selected: 0, details: new Map(), assignee: '', sprint: '', milestone: '', sort: {key: 'number', dir: 1}, person: '',
    extra: {}, sprintShown: ''};   // extra: what the 次にやる / スプリント views read (cleared when the tasks are read again)
  const me = () => MOD.me;
  const root = () => MOD.root;

  // A deleted task is one closed as "not planned" (GitHub keeps it): not done, kept apart and hidden unless asked for.
  const deleted = t => t.state !== 'open' && t.closed_reason === 'not_planned';
  const showDeleted = () => tkEl('tk-deleted').checked;
  // A task's stage on screen: closed = done (or deleted); not recorded yet = in progress when it has a task branch, else todo.
  const stageOf = t => deleted(t) ? 'deleted' : t.state !== 'open' ? 'done' : t.stage || (t.task_branch || t.remote || t.current ? 'in_progress' : 'todo');
  // Also the recently closed tasks the board's 完了 column shows (read with task list --all).
  const byNumber = n => st.tasks.find(t => t.number === n) || ((st.extra.closed?.ok ? st.extra.closed : st.lastClosed)?.result || []).find(t => t.number === n);
  const md = d => d ? Number(d.slice(5, 7)) + '/' + Number(d.slice(8)) : '';
  const stageBadge = t => t.state !== 'open' ? `<span class="tk-stage ${deleted(t) ? 'not_planned' : 'done'}">${deleted(t) ? '削除済み' : '完了'}</span>` : `<span class="tk-stage ${STAGE[stageOf(t)][2]}">${STAGE[stageOf(t)][1]}</span>`;
  const prio = t => t.priority ? `<span class="tk-prio ${esc(t.priority)}">${esc(t.priority)}</span>` : '';
  const due = t => t.due ? `<span class="tk-due ${t.state === 'open' && t.due < today() ? 'overdue' : ''}">${md(t.due)}</span>` : '';
  const isAgent = who => /agent|bot/i.test(who);
  const avatarMark = who => !who ? '<span class="tk-avatar none" title="担当なし"></span>' : `<span class="tk-avatar ${isAgent(who) ? 'agent' : ''}" title="${esc(who)}">${isAgent(who) ? 'AI' : esc(who[0].toUpperCase())}</span>`;
  const avatar = who => !who ? avatarMark('') : `<button type="button" class="tk-person-link" data-person="${esc(who)}" title="${esc(who)} の画面">${avatarMark(who)}</button>`;
  const avatars = t => t.assignees.length ? t.assignees.map(avatar).join('') : avatar('');
  const flags = t => (t.blocked_by && t.state === 'open' ? `<span class="tk-flag blocked">待ち ${t.blocked_by}</span>` : '') + (t.subtasks ? `<span class="tk-flag">子 ${t.subtasks_done}/${t.subtasks}</span>` : '') + (t.current || t.task_branch ? '<span class="tk-flag">タスクブランチ</span>' : t.remote ? '<span class="tk-flag">GitHubにタスクブランチ</span>' : '');
  const sel = t => `aria-selected="${t.number === st.selected}" data-task="${t.number}"`;
  const focusable = 'tabindex="0"';   // rows and cards: Enter / Space opens the detail (see the keydown handler)
  // Sprints: task list gives the name, sprint status the whole sprint. A sprint runs from start to the day before end.
  const sprintName = t => typeof t.sprint === 'string' ? t.sprint : t.sprint?.name || '';
  const currentSprint = () => st.sprints.find(s => s.start <= today() && today() < s.end)?.name || '';
  const est = t => t.estimate != null ? `<span class="tk-est" title="見積もり">${t.estimate}</span>` : '';
  const sprintTag = t => sprintName(t) ? `<span class="tk-sprint ${sprintName(t) === currentSprint() ? 'now' : ''}" title="スプリント">${esc(sprintName(t))}</span>` : '';

  // Loading ---------------------------------------------------------------------------------------
  // The reads are cached (ECO.query): what was read before shows at once, and a newer answer replaces it when it comes
  // (refresh). Not while something is being typed here (the screen would be drawn again under it).
  const typing = () => !!document.activeElement?.closest?.('#tasks-content') && document.activeElement.matches('textarea, input:not([type=checkbox]):not([type=radio]), select');
  function refresh() { if (!st.loaded || typing()) return; renderAssigneeOptions(); renderFilterOptions(); render(); }
  const listArgs = () => ['task', 'list', ...(tkEl('tk-closed').checked || showDeleted() ? ['--all'] : []),...(tkEl('tk-ready').checked ? ['--ready'] : [])];
  const query = (args, apply) => ECO.query(root(), args, doc => { apply(doc); refresh(); });
  async function load({full = false} = {}) {
    if (st.loading) return; st.loading = true;
    if (!st.loaded) tkEl('tk-main').innerHTML = ECO.loading('タスクを読み込んでいます…');
    const args = listArgs(), same = () => listArgs().join(' ') === args.join(' ');
    const jobs = [query(args, d => { if (same()) st.tasks = d.result; })];
    if (full || !st.loaded) jobs.push(query(['milestone', 'list'], d => { st.milestones = d.result; }), query(['sprint', 'list'], d => { st.sprints = d.result; }));
    const [list, milestones, sprints] = await Promise.all(jobs);
    if (full || !st.loaded) st.access = await ECO.access(root());
    st.loading = false; st.lastClosed = st.extra.closed?.ok ? st.extra.closed : st.lastClosed; st.extra = {};
    if (milestones?.ok) st.milestones = milestones.result;
    if (sprints?.ok) st.sprints = sprints.result;
    if (!list.ok) { tkEl('tk-main').innerHTML = `<div class="eco-banner bad">${esc(list.error.message)}${list.error.hint ? '<br>' + esc(list.error.hint) : ''}</div>`; return; }
    st.tasks = list.result; st.loaded = true;
    renderAssigneeOptions(); renderFilterOptions(); render();
  }
  // The views are drawn from task list alone (it has the stage, submission, branch, workspace and worker of each task):
  // task status (several seconds each, it asks GitHub a lot) is read only for the task opened in the detail pane.
  // It used to be read ahead for a dozen likely tasks, one after another, on every load.
  async function reloadAfter(n) { if (n) st.details.delete(n); await load(); if (n && st.selected === n) loadDetail(n); }

  function renderAssigneeOptions() {
    const accounts = [...new Set(st.tasks.flatMap(t => t.assignees))].sort();
    const current = st.assignee;
    tkEl('tk-assignee').innerHTML = [['', '担当者：すべて'], ['@me', '自分'], ...accounts.filter(a => a !== me()).map(a => [a, a]), ['-', '担当なし']].map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
    tkEl('tk-assignee').value = current;
  }
  function renderFilterOptions() {
    const now = currentSprint(), option = ([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`;
    tkEl('tk-sprint').innerHTML = [['', 'スプリント：すべて'], ...(now ? [['current', `今のスプリント（${now}）`]] : []), ...st.sprints.map(s => [s.name, `${s.name}（${md(s.start)}〜）`]), ['-', 'スプリントなし']].map(option).join('');
    tkEl('tk-sprint').value = [...tkEl('tk-sprint').options].some(o => o.value === st.sprint) ? st.sprint : '';
    const names = [...new Set([...st.milestones.map(m => m.title), ...st.tasks.map(t => t.milestone).filter(Boolean)])];
    tkEl('tk-milestone').innerHTML = [['', 'マイルストーン：すべて'], ...names.map(m => [m, m]), ['-', 'マイルストーンなし']].map(option).join('');
    tkEl('tk-milestone').value = [...tkEl('tk-milestone').options].some(o => o.value === st.milestone) ? st.milestone : '';
  }

  // Views -----------------------------------------------------------------------------------------
  const assignedTo = (t, who) => who === '' ? true : who === '-' ? !t.assignees.length : t.assignees.includes(who === '@me' ? me() : who);
  const search = () => tkEl('tk-search').value.trim().toLowerCase();
  const inSprint = (t, s) => s === '' ? true : s === '-' ? !sprintName(t) : sprintName(t) === (s === 'current' ? currentSprint() : s);
  const inMilestone = (t, m) => m === '' ? true : m === '-' ? !t.milestone : t.milestone === m;
  const shown = t => t.state === 'open' || (deleted(t) ? showDeleted() : tkEl('tk-closed').checked);
  const visible = () => st.tasks.filter(t => shown(t) && assignedTo(t, st.assignee) && inSprint(t, st.sprint) && inMilestone(t, st.milestone)
    && (!search() || t.title.toLowerCase().includes(search()) || ('#' + t.number) === search()));
  const PRIO_RANK = t => t.priority ? PRIORITIES.indexOf(t.priority) : 99;
  const SPRINT_RANK = t => { const i = st.sprints.findIndex(s => s.name === sprintName(t)); return i < 0 ? 9999 : i; };
  const SORT_KEYS = {number: t => t.number, title: t => t.title, stage: t => deleted(t) ? STAGES.length : STAGES.findIndex(s => s[0] === stageOf(t)), priority: PRIO_RANK, due: t => t.due || '9999',
    estimate: t => t.estimate ?? 1e9, sprint: SPRINT_RANK, assignee: t => t.assignees[0] || '￿'};
  const sorted = ts => [...ts].sort((a, b) => { const f = SORT_KEYS[st.sort.key], x = f(a), y = f(b); return (x < y ? -1 : x > y ? 1 : a.number - b.number) * st.sort.dir; });
  const sortHead = (key, label) => `<th><button type="button" class="tk-sort ${st.sort.key === key ? 'on' : ''}" data-sort="${key}">${label}<span aria-hidden="true">${st.sort.key === key ? (st.sort.dir > 0 ? '▲' : '▼') : ''}</span></button></th>`;
  const taskTable = (ts, withAssignee = true) => `<table class="tk-table"><thead><tr>${sortHead('number', '#')}${sortHead('title', '題名')}${sortHead('stage', '状態')}${sortHead('priority', '優先度')}${sortHead('due', '期限')}${sortHead('estimate', '見積')}${sortHead('sprint', 'スプリント')}${withAssignee ? sortHead('assignee', '担当') : ''}</tr></thead><tbody>
    ${sorted(ts).map(t => `<tr ${sel(t)} ${focusable} class="${t.state === 'open' ? '' : 'closed'}"><td class="tk-num-cell"><span class="tk-num">#${t.number}</span></td><td class="tk-title-cell">${esc(t.title)} ${flags(t)}</td><td>${stageBadge(t)}</td><td>${prio(t)}</td><td>${due(t)}</td><td>${est(t)}</td><td>${sprintTag(t)}</td>${withAssignee ? `<td>${avatars(t)}</td>` : ''}</tr>`).join('')}</tbody></table>`;
  function renderList() {
    const ts = visible();
    // Cleaning up is seldom done: a quiet link under the list, not a main button.
    return (ts.length ? taskTable(ts) : `<p class="tk-empty">${st.tasks.length ? '条件に合うタスクはありません。' : 'タスクはまだありません。「＋ 新しいタスク」で作れます。'}</p>`) + '<div class="tk-list-foot"><button type="button" class="tk-link" data-tk="clean">完了したタスクブランチを片付ける…</button></div>';
  }
  // The board: tasks by stage. Drag a card to another column to change its stage (see the drop handler below).
  // 完了 shows the recently completed tasks (task list --all) even when 「完了したタスクも表示」 is off. Deleted tasks are
  // not done: they have their own column, shown with 「削除したタスクも表示」.
  const RECENT_DONE = 15;
  const DELETED_COLUMN = ['deleted', '削除済み', 'not_planned'];
  const newestDone = (a, b) => (b.finished || '').localeCompare(a.finished || '') || b.number - a.number;   // 完了: the newest first
  // A card: the title on top, the rest under it (the assignee on the right, kept on the line).
  const kanbanCard = t => `<article class="tk-kcard" draggable="true" ${focusable} ${sel(t)}><div class="tk-kcard-title">${esc(t.title)}</div>
    <div class="tk-kcard-foot"><div class="tk-kcard-meta"><span class="tk-num">#${t.number}</span>${prio(t)}${est(t)}${sprintTag(t)}${due(t)}${flags(t)}</div>${avatar(t.assignees[0])}</div></article>`;
  function renderStages() {
    let closed = null;
    if (!tkEl('tk-closed').checked) {
      // With 「削除したタスクも表示」 the list itself was read with --all.
      if (!showDeleted() && st.extra.closed === undefined) fetchExtra('closed', () => extra('closed', null, ['task', 'list', '--all']));
      const source = showDeleted() ? {ok: true, result: st.tasks} : st.extra.closed?.ok ? st.extra.closed : st.lastClosed;   // the previous one while it is read again
      const all = source?.ok ? source.result : [];
      closed = all.filter(t => t.state !== 'open' && !deleted(t))
        .filter(t => assignedTo(t, st.assignee) && inSprint(t, st.sprint) && inMilestone(t, st.milestone) && (!search() || t.title.toLowerCase().includes(search()) || ('#' + t.number) === search()))
        .sort(newestDone).slice(0, RECENT_DONE);
    }
    return `<div class="tk-kanban ${showDeleted() ? 'with-deleted' : ''}">${[...STAGES, ...(showDeleted() ? [DELETED_COLUMN] : [])].map(([key, ja, cls]) => {
      const cards = key === 'done' && closed ? closed : visible().filter(t => stageOf(t) === key);
      if (key === 'done') cards.sort(newestDone);
      const note = key === 'done' && closed ? `<small title="「完了したタスクも表示」ですべて表示">最近 ${cards.length}</small>` : `<small>${cards.length}</small>`;
      return `<section class="tk-column" data-stage="${key}"><div class="tk-column-head"><span><span class="tk-stage ${cls}">${ja}</span></span>${note}</div><div class="tk-column-cards">
      ${cards.map(kanbanCard).join('')}
      </div></section>`;
    }).join('')}</div>`;
  }
  const DAY = 86400000, WEEK = ['日', '月', '火', '水', '木', '金', '土'];
  const dayOf = d => Date.parse(d + 'T00:00:00Z') / DAY, weekday = n => new Date(n * DAY).getUTCDay();
  // 日程 shows as 横の帯 (renderBars) or as a month calendar (renderCalendar); the choice is kept per PC.
  let timelineMode = 'bars';
  try { timelineMode = localStorage.getItem('ecobuild-gui-timeline-mode') === 'calendar' ? 'calendar' : 'bars'; } catch (e) { /* storage blocked */ }
  const modeSwitch = () => `<div class="tl-modes" role="group" aria-label="日程の表示">${[['bars', '横の帯'], ['calendar', 'カレンダー']].map(([key, ja]) =>
    `<button type="button" data-tl-mode="${key}" aria-pressed="${timelineMode === key}">${ja}</button>`).join('')}</div>`;
  // One toolbar over both: the month moves (カレンダー) on the left, the mode switch on the right (as Google Calendar).
  const timelineTools = (left = '') => `<div class="tl-tools">${left}<span class="tl-tools-end">${modeSwitch()}</span></div>`;
  const renderTimeline = () => timelineMode === 'calendar' ? renderCalendar() : renderBars();
  // 日程（横の帯）: every task is a row. Tasks with planned start and end have a bar (drag to move, right edge to change the end);
  // the others are rows without a bar, below them: drag across their days to give them a plan (task edit).
  function renderBars() {
    const dated = visible().filter(t => t.planned_start && t.planned_end).sort((a, b) => a.planned_start.localeCompare(b.planned_start) || a.number - b.number);
    const undated = visible().filter(t => !t.planned_start || !t.planned_end).sort((a, b) => (a.state === 'open') === (b.state === 'open') ? a.number - b.number : a.state === 'open' ? -1 : 1);
    const now = dayOf(today()), tasks = [...dated, ...undated];
    // The rows without a plan come under a heading row of their own (it says how to give them one).
    const gap = undated.length ? 1 : 0, rowCount = tasks.length + gap;
    const all = tasks.flatMap(t => [t.planned_start, t.planned_end, t.due].filter(Boolean)).map(dayOf).concat(now);
    let first = Math.min(...all), last = Math.max(...all, now + 20);
    first -= (weekday(first) + 6) % 7; last += 6 - (weekday(last) + 6) % 7;
    const days = Array.from({length: last - first + 1}, (_, i) => first + i), col = n => n - first + 2, off = n => weekday(n) === 0 || weekday(n) === 6;
    const head = days.map(n => { const d = new Date(n * DAY); return `<div class="tl-day ${off(n) ? 'off' : ''} ${n === now ? 'today' : ''}" style="grid-column:${col(n)}">${d.getUTCDate() === 1 || n === first ? `<b>${d.getUTCMonth() + 1}月</b>` : ''}<span>${d.getUTCDate()}</span><small>${WEEK[weekday(n)]}</small></div>`; }).join('');
    const shade = tasks.length ? days.filter(off).map(n => `<div class="tl-off" style="grid-column:${col(n)};grid-row:2 / span ${rowCount}"></div>`).join('') : '';
    const dueMark = (t, r) => t.due ? `<div class="tl-due ${t.state === 'open' && t.due < today() ? 'overdue' : ''}" style="grid-row:${r};grid-column:${col(dayOf(t.due))}" title="期限 ${md(t.due)}">◆</div>` : '';
    const label = (t, r, extra = '') => `<div class="tl-label ${extra}" style="grid-row:${r}" ${sel(t)}><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span></div>`;
    const rows = dated.map((t, i) => { const r = i + 2, late = t.state === 'open' && dayOf(t.planned_end) < now, s = STAGE[stageOf(t)];
      return label(t, r) + `<div class="tl-bar ${s[2]} ${late ? 'late' : ''} ${t.number === st.selected ? 'sel' : ''} ${t.state === 'open' ? 'movable' : ''}" style="grid-row:${r};grid-column:${col(dayOf(t.planned_start))} / ${col(dayOf(t.planned_end)) + 1}" data-task="${t.number}" title="${md(t.planned_start)}〜${md(t.planned_end)}${t.state === 'open' ? '（ドラッグで移動、右端のドラッグで終了予定を変更）' : ''}">${s[1]}<span class="tl-grip" aria-hidden="true"></span></div>` + dueMark(t, r); }).join('')
      + (gap ? `<div class="tl-group" style="grid-row:${dated.length + 2}">日程なし</div><div class="tl-group-line" style="grid-row:${dated.length + 2};grid-column:2 / ${days.length + 2}"></div>` : '')
      + undated.map((t, i) => { const r = dated.length + gap + i + 2, open = t.state === 'open', one = t.planned_start || t.planned_end;
        return label(t, r, 'undated')
          + `<div class="tl-empty ${open ? 'plannable' : ''}" style="grid-row:${r};grid-column:2 / ${days.length + 2}" data-plan-row="${t.number}" title="${open ? 'ドラッグで予定（開始〜終了）を設定' : '閉じたタスク'}"></div>`
          + (one ? `<div class="tl-point" style="grid-row:${r};grid-column:${col(dayOf(one))}" title="${t.planned_start ? '開始予定' : '終了予定'}だけ ${md(one)}"></div>` : '') + dueMark(t, r); }).join('');
    const rowSizes = [dated.length && `repeat(${dated.length}, 34px)`, gap && `28px repeat(${undated.length}, 34px)`].filter(Boolean).join(' ');
    return timelineTools() + `<div class="tl-wrap"><div class="tl-grid" data-first="${first}" data-days="${days.length}" style="grid-template-columns:220px repeat(${days.length}, 28px);grid-template-rows:54px ${rowSizes}">
      <div class="tl-corner">タスク</div>${head}${shade}<div class="tl-now" style="grid-column:${col(now)};grid-row:1 / span ${rowCount + 1}"></div>${rows}</div></div>
      <div class="tl-legend"><span><i class="tl-key bar"></i>開始予定〜終了予定</span><span><i class="tl-key due">◆</i>期限</span><span><i class="tl-key now"></i>今日</span><span><i class="tl-key late"></i>終了予定を過ぎている</span></div>`;
  }
  // 日程（カレンダー）: a month, a week per row (Monday first, as 横の帯). A task with a plan is a bar over its days, cut at
  // the week's edges; its due date is a ◆ under the bars. Click one to see the task. Plans are changed in 横の帯 or the detail.
  let calendarMonth = '';   // YYYY-MM; empty: this month
  const monthOf = (y, m) => new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 7);   // m from 0, may be out of 0〜11
  function renderCalendar() {
    const month = calendarMonth || today().slice(0, 7), y = Number(month.slice(0, 4)), m = Number(month.slice(5, 7)) - 1;
    const firstDay = dayOf(month + '-01'), lastDay = dayOf(monthOf(y, m + 1) + '-01') - 1, now = dayOf(today());
    const first = firstDay - (weekday(firstDay) + 6) % 7, last = lastDay + 6 - (weekday(lastDay) + 6) % 7;
    const tasks = visible(), dated = tasks.filter(t => t.planned_start && t.planned_end && t.planned_start <= t.planned_end);
    const weeks = [];
    for (let w = first; w <= last; w += 7) {
      const lanes = [];   // the bars that do not overlap share a row
      const bars = dated.filter(t => dayOf(t.planned_start) <= w + 6 && dayOf(t.planned_end) >= w)
        .sort((a, b) => a.planned_start.localeCompare(b.planned_start) || b.planned_end.localeCompare(a.planned_end) || a.number - b.number)
        .map(t => {
          const from = Math.max(dayOf(t.planned_start), w), to = Math.min(dayOf(t.planned_end), w + 6);
          let lane = lanes.findIndex(l => l.every(([a, b]) => to < a || from > b));
          if (lane < 0) { lane = lanes.length; lanes.push([]); }
          lanes[lane].push([from, to]);
          const late = t.state === 'open' && dayOf(t.planned_end) < now;
          return `<div class="cal-bar ${STAGE[stageOf(t)][2]} ${late ? 'late' : ''} ${from > dayOf(t.planned_start) ? 'cut-start' : ''} ${to < dayOf(t.planned_end) ? 'cut-end' : ''}" ${sel(t)}
            style="grid-column:${from - w + 1} / ${to - w + 2};grid-row:${lane + 2}" title="#${t.number} ${esc(t.title)}（${md(t.planned_start)}〜${md(t.planned_end)}）"><span class="tk-num">#${t.number}</span> ${esc(t.title)}</div>`;
        });
      const days = Array.from({length: 7}, (_, i) => w + i), dueRow = lanes.length + 2;
      weeks.push(`<div class="cal-week" style="grid-template-rows:24px repeat(${lanes.length}, 22px) minmax(26px, auto)">
        ${days.map((n, i) => { const d = new Date(n * DAY), dues = tasks.filter(t => t.due && dayOf(t.due) === n);
          return `<div class="cal-day ${i >= 5 ? 'off' : ''} ${n === now ? 'today' : ''} ${n < firstDay || n > lastDay ? 'other' : ''}" style="grid-column:${i + 1}"></div>`
            + `<div class="cal-date ${n === now ? 'today' : ''}" style="grid-column:${i + 1}">${d.getUTCDate() === 1 ? `${d.getUTCMonth() + 1}/` : ''}${d.getUTCDate()}</div>`
            + (dues.length ? `<div class="cal-dues" style="grid-column:${i + 1};grid-row:${dueRow}">${dues.map(t => `<div class="cal-due ${t.state === 'open' && t.due < today() ? 'overdue' : ''}" ${sel(t)} title="期限 ${md(t.due)}：#${t.number} ${esc(t.title)}">◆ <span class="tk-num">#${t.number}</span> ${esc(t.title)}</div>`).join('')}</div>` : ''); }).join('')}
        ${bars.join('')}</div>`);
    }
    const undated = tasks.filter(t => !t.planned_start || !t.planned_end).length;
    return timelineTools(`<button type="button" data-cal-move="0">今月</button><button type="button" class="tl-step" data-cal-move="-1" aria-label="前の月" title="前の月">‹</button><button type="button" class="tl-step" data-cal-move="1" aria-label="次の月" title="次の月">›</button><strong class="tl-month">${y}年${m + 1}月</strong>`) + `
      <div class="cal"><div class="cal-head">${['月', '火', '水', '木', '金', '土', '日'].map((w, i) => `<div class="${i >= 5 ? 'off' : ''}">${w}</div>`).join('')}</div>${weeks.join('')}</div>
      <div class="tl-legend"><span><i class="tl-key bar"></i>開始予定〜終了予定</span><span><i class="tl-key due">◆</i>期限</span><span><i class="tl-key late"></i>終了予定を過ぎている</span>${undated ? `<span>予定（開始・終了）のないタスク ${undated} 件は、「横の帯」でドラッグして予定を付けられます</span>` : ''}</div>`;
  }
  function scrollToToday() { const wrap = document.querySelector('.tl-wrap'), nowLine = document.querySelector('.tl-now'); if (wrap && nowLine) wrap.scrollLeft = Math.max(0, nowLine.offsetLeft - 220 - 7 * 28); }

  // 次にやる: task next (the order and the reasons are ecobuild's) and task overdue. Read when the view is shown.
  function renderNext() {
    const mine = st.assignee === '@me', key = 'next' + (mine ? '-mine' : '');
    const data = st.extra[key];
    if (!data) { fetchExtra(key, () => Promise.all([extra(key, 0, ['task', 'next', '--count', '10', ...(mine ? ['--mine'] : [])]), extra(key, 1, ['task', 'overdue', '--days', '7'])])); return ECO.loading('次にやるタスクを確認しています…'); }
    const [next, overdue] = data;
    if (!next.ok) return `<div class="eco-banner bad">${esc(next.error.message)}</div>`;
    const row = (t, extra = '') => `<div class="tk-next-row" ${sel(t)}><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span>${extra}${prio(t)}${due(t)}${est(t)}${sprintTag(t)}${avatars(t)}</div>`;
    const items = next.result.map((x, i) => row(x.task, `<span class="tk-rank">${i + 1}</span>${x.reasons.map(r => `<span class="tk-reason">${esc(r)}</span>`).join('')}`));
    const late = overdue.ok ? overdue.result.overdue : [], soon = overdue.ok ? overdue.result.soon : [];
    // The due-date lists only when they have something: otherwise one line says so.
    const dueCard = (title, sub, ts) => ts.length ? `<section class="tk-card"><div class="tk-section-head"><h3>${title}<span class="tk-muted">${sub}</span></h3></div>${ts.map(t => row(t)).join('')}</section>` : '';
    return `<section class="tk-card"><div class="tk-section-head"><h3>次にやるタスク${mine ? '<span class="tk-muted">自分の担当</span>' : ''}</h3></div>
      ${items.length ? items.join('') : '<p class="tk-muted">着手できるタスクはありません。</p>'}</section>
      ${dueCard('期限切れ', `${late.length} 件`, late)}${dueCard('期限が近い', '7日以内', soon)}
      ${overdue.ok && !late.length && !soon.length ? '<p class="tk-muted tk-next-none">期限切れ・期限が近い（7日以内）タスクはありません。</p>' : ''}`;
  }
  // スプリント: sprint status (counts, estimates, days left, carried over) for the chosen sprint (the current one first).
  function renderSprint() {
    if (!st.sprints.length) return '<p class="tk-empty">スプリントはまだありません。</p>';
    const name = st.sprintShown || currentSprint() || st.sprints[0].name, key = 'sprint:' + name;
    const select = `<label class="tk-sprint-pick">スプリント <select id="tk-sprint-shown">${st.sprints.map(s => `<option value="${esc(s.name)}" ${s.name === name ? 'selected' : ''}>${esc(s.name)}（${md(s.start)}〜${md(s.end)}）${s.name === currentSprint() ? ' ・今' : ''}</option>`).join('')}</select></label>`;
    const picker = `<div class="tk-sprint-bar">${select}</div>`;   // while it is read; then it sits in the sprint's heading
    const data = st.extra[key];
    if (!data) { fetchExtra(key, () => extra(key, null, ['sprint', 'status', name])); return picker + ECO.loading('スプリントを確認しています…'); }
    if (!data.ok) return picker + `<div class="eco-banner bad">${esc(data.error.message)}</div>`;
    const s = data.result, pct = (a, b) => b ? Math.round(a / b * 100) : 0;
    const tasks = s.tasks.map(t => byNumber(t.number) || t), numberOf = x => typeof x === 'number' ? x : x.number;
    const stat = (label, value, cls = '') => `<div class="tk-pf-stat ${cls}"><b>${value}</b><span>${label}</span></div>`;
    const counts = STAGES.filter(([k]) => s.stages[k]).map(([k, ja, cls]) => `<span class="tk-stage ${cls}">${ja} ${s.stages[k]}</span>`).join('');
    const list = (title, xs) => xs.length ? `<p class="tk-note">${title}：${xs.map(numberOf).map(n => `<span class="tk-label" data-task="${n}" style="cursor:pointer">#${n} ${esc(byNumber(n)?.title || '')}</span>`).join('')}</p>` : '';
    // An empty sprint: no counts (all 0), only how to add tasks to it.
    const numbers = s.total ? `<div class="tk-pf-stats">${stat('完了 / 全体', `${s.done} / ${s.total}`)}${stat('見積もりの残り', s.estimate_remaining)}${stat('見積もりの合計', s.estimate_total)}${stat('見積もりなし', s.unestimated.length, s.unestimated.length ? 'warn' : '')}</div>
      <div class="tk-progress" title="完了した見積もり ${s.estimate_done} / ${s.estimate_total}"><span style="width:${pct(s.estimate_done, s.estimate_total) || pct(s.done, s.total)}%"></span></div>
      ${list('見積もりのないタスク', s.unestimated)}${list('前のスプリントからの持ち越し', s.carried_over)}`
      : `<p class="tk-note">${tasks.length ? 'このスプリントに、数えるタスクはありません。親タスクは数えません。' : 'このスプリントのタスクはありません。タスクの詳細か右クリックメニューで、スプリントに入れられます。'}</p>`;
    return `<section class="tk-card"><div class="tk-section-head"><h3>${esc(s.sprint.name)}<span class="tk-muted">${md(s.sprint.start)}〜${md(s.sprint.end)}${s.current ? `・残り ${s.days_left} 日` : ''}</span></h3>${select}</div>
      ${counts ? `<div class="tk-stagekeys tk-sprint-stages">${counts}</div>` : ''}${numbers}</section>
      ${tasks.length ? taskTable(tasks) : ''}`;
  }
  // One read of a view (index: its place among the reads of that view, or null when it is the only one).
  const extra = (key, index, args) => ECO.query(root(), args, doc => {
    if (st.extra[key] == null) return;
    if (index === null) st.extra[key] = doc; else st.extra[key][index] = doc;
    refresh();
  });
  function fetchExtra(key, job) {
    if (st.extra[key] !== undefined) return;
    st.extra[key] = null;
    job().then(result => { st.extra[key] = result; if (st.loaded) render(); }).catch(() => { delete st.extra[key]; });
  }

  // The summary: the module's tasks at a glance. Every number is what an ecobuild command returns
  // (sprint status, task workload, milestone status, task next, task overdue, task list --submitted／--to-review, task list --all); click to go deeper.
  function renderSummary() {
    const data = st.extra.summary;
    if (!data) {
      fetchExtra('summary', () => Promise.all([
        currentSprint() ? extra('summary', 0, ['sprint', 'status']) : null,
        extra('summary', 1, ['task', 'workload']), extra('summary', 2, ['milestone', 'status']),
        extra('summary', 3, ['task', 'next', '--count', '5', '--mine']), extra('summary', 4, ['task', 'overdue', '--days', '7']),
        null, extra('summary', 6, ['task', 'list', '--to-review']),   // the submitted ones are in task list --all (index 7)
        extra('summary', 7, ['task', 'list', '--all'])]));
      return ECO.loading('集計しています…');
    }
    const [sprint, workload, milestones, next, overdue, prs, reviews, all] = data;
    const ok = doc => doc?.ok ? doc.result : null;
    const open = st.tasks.filter(t => t.state === 'open'), count = stage => open.filter(t => stageOf(t) === stage).length;
    const late = ok(overdue)?.overdue || [], soon = ok(overdue)?.soon || [];
    const weekAgo = ECO.localTime(new Date(Date.now() - 7 * 86400000).toISOString());   // this PC's date, like today()
    const finished = (ok(all) || []).filter(t => t.state !== 'open' && !deleted(t) && t.finished).sort((a, b) => b.finished.localeCompare(a.finished));
    const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
    const card = (title, body, {wide = false, go = '', sub = ''} = {}) => `<section class="tk-card tk-dash-card ${wide ? 'wide' : ''}"><div class="tk-section-head"><h3>${title}${sub ? `<span class="tk-muted">${sub}</span>` : ''}</h3>${go ? `<button type="button" class="tk-link" data-dash-go="${go}">開く ›</button>` : ''}</div>${body}</section>`;
    // A tile that opens a view looks pressable (›); the others are flat.
    const big = (label, value, {cls = '', go = ''} = {}) => go ? `<button type="button" class="tk-dash-stat go ${cls}" data-dash-go="${go}"><b>${value}</b><span>${label}</span></button>` : `<div class="tk-dash-stat ${cls}"><b>${value}</b><span>${label}</span></div>`;
    const row = (t, extra = '') => `<div class="tk-next-row" ${sel(t)}><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span>${extra}${prio(t)}${due(t)}${est(t)}${avatars(t)}</div>`;
    const none = text => `<p class="tk-muted">${text}</p>`;
    // The open tasks by stage, as one bar.
    const stageBar = `<div class="tk-stagebar">${STAGES.slice(0, 4).map(([k, ja, cls]) => count(k) ? `<button type="button" class="seg ${cls}" style="flex:${count(k)}" data-dash-go="stages" title="${ja} ${count(k)}"></button>` : '').join('')}</div>
      <div class="tk-stagekeys">${STAGES.slice(0, 4).map(([k, ja, cls]) => `<span class="tk-stage ${cls}">${ja} ${count(k)}</span>`).join('')}</div>`;
    const s = ok(sprint);
    const sprintBody = !s ? none(st.sprints.length ? '今日を含むスプリントはありません。' : 'スプリントはまだありません。')
      : `<div class="tk-dash-sprint"><div><b>${s.done} / ${s.total}</b><span>完了</span></div><div><b>${s.estimate_remaining}</b><span>見積もりの残り</span></div><div><b>${s.days_left}</b><span>残り日数</span></div></div>
        <div class="tk-progress" title="完了 ${pct(s.done, s.total)}%"><span style="width:${pct(s.estimate_done, s.estimate_total) || pct(s.done, s.total)}%"></span></div>
        ${s.unestimated.length ? `<p class="tk-note">見積もりのないタスク ${s.unestimated.length} 件</p>` : ''}${s.carried_over.length ? `<p class="tk-note">持ち越し ${s.carried_over.length} 件</p>` : ''}`;
    const ms = (ok(milestones) || []).map(m => `<button type="button" class="tk-dash-row" data-dash-milestone="${esc(m.title)}"><span class="tk-grow">${esc(m.title)}${m.due ? `<small class="${m.late ? 'tk-due overdue' : 'tk-muted'}"> ${md(m.due)}${m.late ? ' 期日超過' : ''}</small>` : ''}</span>
      <span class="tk-minibar"><span style="width:${pct(m.done, m.total)}%"></span></span><span class="tk-muted">${m.done}/${m.total}</span>${m.overdue_tasks.length ? `<span class="tk-reason">期限切れ ${m.overdue_tasks.length}</span>` : ''}</button>`).join('');
    const people = (ok(workload) || []).filter(w => w.open), most = Math.max(1, ...people.map(w => w.open));
    const wl = people.map(w => `<button type="button" class="tk-dash-row" ${w.assignee ? `data-person="${esc(w.assignee)}"` : 'data-dash-unassigned'}>${avatarMark(w.assignee)}<span class="tk-dash-name">${esc(w.assignee || '担当なし')}${w.assignee === me() ? '（自分）' : ''}</span>
      <span class="tk-minibar"><span style="width:${pct(w.open, most)}%"></span><span class="doing" style="width:${pct(w.in_progress, most)}%"></span></span><span class="tk-muted">${w.open} 件・作業中 ${w.in_progress}${w.estimate_remaining ? `・残り ${w.estimate_remaining}` : ''}</span>${w.overdue ? `<span class="tk-reason">期限切れ ${w.overdue}</span>` : ''}</button>`).join('');
    const prRow = t => `<div class="tk-next-row" ${sel(t)}><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span>${submissionPill(t.submission)}${avatars(t)}</div>`;
    const mineNext = ok(next) || [], asked = ok(reviews) || [];
    const openPrs = prs ? ok(prs) || [] : (ok(all) || []).filter(t => t.state === 'open' && t.submission);   // = task list --submitted
    return `<div class="tk-dash">
      <div class="tk-dash-stats wide">${big('開いているタスク', open.length, {go: 'list'})}${big('作業中', count('in_progress'), {go: 'stages'})}${big('レビュー待ち', count('in_review'), {go: 'stages'})}${big('期限切れ', late.length, {cls: late.length ? 'bad' : '', go: 'next'})}${big('この1週間に完了', finished.filter(t => t.finished >= weekAgo).length)}${big('レビューの依頼', asked.length, {cls: asked.length ? 'warn' : ''})}</div>
      ${card('段階', stageBar, {go: 'stages', sub: `開いている ${open.length} 件`})}
      ${card(s ? `今のスプリント：${esc(s.sprint.name)}` : '今のスプリント', sprintBody, {go: 'sprint', sub: s ? `${md(s.sprint.start)}〜${md(s.sprint.end)}` : ''})}
      ${card('自分の次のタスク', mineNext.length ? mineNext.map((x, i) => row(x.task, `<span class="tk-rank">${i + 1}</span>${x.reasons.slice(0, 2).map(r => `<span class="tk-reason">${esc(r)}</span>`).join('')}`)).join('') : none(next?.ok ? '自分が担当していて、着手できるタスクはありません。' : esc(next?.error?.message || '')), {go: 'next'})}
      ${card('期限', late.length || soon.length ? late.map(t => row(t, '<span class="tk-reason bad">期限切れ</span>')).join('') + soon.map(t => row(t, '<span class="tk-reason">7日以内</span>')).join('') : none('期限切れ・期限が近いタスクはありません。'), {go: 'next'})}
      ${card('マイルストーン', ms || none('開いているマイルストーンはありません。'))}
      ${card('担当者ごとの量', wl || none('開いているタスクはありません。'), {sub: '親タスクは数えません'})}
      ${card('提出', (asked.length ? `<h4 class="tk-dash-h">見るように頼まれた提出</h4>${asked.map(prRow).join('')}` : '') + (openPrs.length ? `<h4 class="tk-dash-h">提出中 ${openPrs.length}</h4>${openPrs.slice(0, 6).map(prRow).join('')}` : none('提出中のタスクはありません。')))}
      ${card('最近完了したタスク', finished.length ? finished.slice(0, 6).map(t => row(t, `<span class="tk-muted">${md(t.finished)}</span>`)).join('') : none('まだありません。'))}
    </div>`;
  }

  const VIEWS = {summary: renderSummary, next: renderNext, list: renderList, stages: renderStages, timeline: renderTimeline, sprint: renderSprint};
  // The filters that apply to each view: スプリント and the summary read their own totals (none apply); 次にやる is
  // ecobuild's order, narrowed only by 担当者「自分」. What does not apply is not shown.
  const NO_FILTER = ['summary', 'sprint'];
  function render() {
    for (const b of document.querySelectorAll('.tk-views [data-view]')) b.setAttribute('aria-selected', String(b.dataset.view === st.view));
    tkEl('tk-filter').hidden = NO_FILTER.includes(st.view); tkEl('tk-filter').dataset.view = st.view;
    if (st.loaded) tkEl('tk-main').innerHTML = VIEWS[st.view]();
    if (st.view === 'timeline' && timelineMode === 'bars') scrollToToday();
    tkEl('tk-detail').hidden = !st.selected; document.querySelector('.tk-body').classList.toggle('no-detail', !st.selected);
    if (st.selected) renderDetail();
  }

  // Detail ----------------------------------------------------------------------------------------
  async function loadDetail(n) {
    const doc = await ECO.query(root(), ['task', 'status', String(n)], fresh => {
      st.details.set(n, fresh.result);
      if (st.selected === n && !typing()) renderDetail();
    });
    st.details.set(n, doc.ok ? doc.result : {error: doc.error});
    if (st.selected === n) renderDetail();
  }
  function select(n) { st.selected = n; ECO.setState({task: n}); render(); if (!st.details.has(n)) loadDetail(n); }
  ECO.onChange(() => { if (st.loaded) { st.details.clear(); load(); if (st.selected) loadDetail(st.selected); } });
  window.TASKS_SELECT = n => { if (!st.loaded) load().then(() => select(n)); else select(n); };

  function renderDetail() {
    const n = st.selected, summary = byNumber(n), d = st.details.get(n);
    const close = '<button type="button" class="tk-d-close" data-close-detail title="詳細を閉じる" aria-label="詳細を閉じる">×</button>';
    if (!d) { tkEl('tk-detail').innerHTML = `<div class="tk-d-head"><span class="tk-num">#${n}</span>${close}</div>${summary ? `<h3 class="tk-d-title">${esc(summary.title)}</h3>` : ''}${ECO.loading()}`; return; }
    if (d.error) { tkEl('tk-detail').innerHTML = `<div class="tk-d-head"><span class="tk-num">#${n}</span>${close}</div><p class="tk-empty">${esc(d.error.message)}</p>`; return; }
    const t = d.task || {}, open = d.state === 'open', place = MOD.placeOfTask(n);
    const view = {...(summary || {}), ...t, state: d.state, task_branch: d.task_branch, remote: d.remote};
    const hasWorkspace = !!place || d.task_branch;
    const primary = !open ? `<button type="button" data-tk="reopen">${deleted(view) ? '元に戻す' : '開き直す'}</button>`
      : hasWorkspace ? '<button type="button" class="primary" data-tk="open-ws">タスクブランチを開く</button>'
      : `<button type="button" class="primary" data-tk="start">${d.remote ? '作業を再開' : '作業を開始'}</button>`;
    const dis = open ? '' : 'disabled';
    const rel = x => `<div class="tk-rel" data-task="${x.number}"><span class="tk-num">#${x.number}</span><span class="tk-grow">${esc(x.title)}</span>${x.state === 'open' ? '' : '<span class="tk-stage done">完了</span>'}</div>`;
    const relations = [d.parent && ['親タスク', [d.parent]], d.subtasks.length && ['子タスク', d.subtasks], d.blocked_by.length && ['先に終わるべき', d.blocked_by], d.blocking.length && ['待っているタスク', d.blocking]].filter(Boolean);
    const pr = d.pull_request;
    tkEl('tk-detail').innerHTML = `
    <div class="tk-d-head"><span class="tk-num">#${n}</span>${stageBadge(view)}${close}</div>
    <h3 class="tk-d-title">${esc(d.title)}</h3>
    <div class="tk-d-actions">${primary}${open ? (hasWorkspace || d.remote
        ? '<button type="button" data-tk="complete" title="タスクを完了にします。出している提出・まだ取り込んでいない変更があれば取り込んでから閉じ、タスクブランチを片付けます（作業をやめるなら ⋯ の「作業を捨てる」）">完了にする</button>'
        : '<button type="button" data-tk="complete">完了にする</button>') : ''}<button type="button" data-tk="edit">編集</button>
      <details class="tk-menu"><summary aria-label="その他の操作" title="その他の操作">⋯</summary><div>${detailMenu(n, {open, hasWorkspace, remote: d.remote, pr})}</div></details></div>
    <section class="tk-d-section"><div class="tk-d-body ${st.bodyOpen === n ? 'open' : ''}">${esc(d.body) || '<span class="tk-muted">本文はありません</span>'}</div><button type="button" class="tk-link tk-d-more" data-body-more hidden>${st.bodyOpen === n ? '折りたたむ' : 'すべて表示'}</button></section>
    <section class="tk-d-section"><h4>担当・ラベル</h4><dl class="tk-kv">
      <dt>担当者</dt><dd class="tk-chips">${d.assignees.map(a => `<span class="tk-chip"><button type="button" class="tk-person-name" data-person="${esc(a)}" title="${esc(a)} の画面">${esc(a)}${a === me() ? '（自分）' : ''}</button><button type="button" class="x" data-remove-assignee="${esc(a)}" title="外す">×</button></span>`).join('')}<button type="button" class="tk-add" data-tk="add-assignee" title="担当者を追加">＋</button></dd>
      <dt>ラベル</dt><dd class="tk-chips">${d.labels.map(l => `<span class="tk-chip">${esc(l)}<button type="button" class="x" data-remove-label="${esc(l)}" title="外す">×</button></span>`).join('')}<button type="button" class="tk-add" data-tk="add-label" title="ラベルを付ける">＋</button></dd>
    </dl></section>
    <section class="tk-d-section"><h4>計画</h4><dl class="tk-kv tk-controls">
      <dt>優先度</dt><dd><select data-plan="priority" ${dis}><option value="">なし</option>${PRIORITIES.map(p => `<option ${p === t.priority ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select></dd>
      <dt>見積もり</dt><dd><input type="number" min="0" step="0.5" data-plan="estimate" value="${t.estimate ?? ''}" placeholder="なし" ${dis}></dd>
      <dt>スプリント</dt><dd><select data-plan="sprint" ${dis}>${sprintOptions(sprintName(t)).map(([v, l]) => `<option value="${esc(v)}" ${v === sprintName(t) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></dd>
      <dt>マイルストーン</dt><dd><select data-milestone ${dis}><option value="">なし</option>${st.milestones.map(m => `<option ${m.title === d.milestone ? 'selected' : ''}>${esc(m.title)}</option>`).join('')}${d.milestone && !st.milestones.some(m => m.title === d.milestone) ? `<option selected>${esc(d.milestone)}</option>` : ''}</select></dd>
    </dl></section>
    <section class="tk-d-section"><h4>日程</h4><dl class="tk-kv tk-controls">
      <dt>開始予定</dt><dd>${dateInput('planned_start', t.planned_start, dis)}</dd>
      <dt>終了予定</dt><dd>${dateInput('planned_end', t.planned_end, dis)}</dd>
      <dt>期限</dt><dd>${dateInput('due', t.due, dis)}</dd>
      <dt>日付</dt><dd class="tk-muted">追加 ${esc(t.created || '-')}${t.started ? ' · 開始 ' + esc(t.started) : ''}${t.finished ? ' · 終了 ' + esc(t.finished) : ''}</dd>
    </dl></section>
    ${relations.length ? `<section class="tk-d-section"><h4>つながり</h4><dl class="tk-kv">${relations.map(([label, xs]) => `<dt>${label}</dt><dd>${xs.map(rel).join('')}</dd>`).join('')}</dl></section>` : ''}
    <section class="tk-d-section"><h4>作業</h4><dl class="tk-kv">
      <dt>タスクブランチ</dt><dd>${hasWorkspace ? `${esc(d.branch || t.branch || `task/${n}`)}${place && MOD.keyOf(place) !== MOD.keyOf(MOD.root) ? `<div class="tk-muted">${esc(place)}</div>` : ''}` : d.remote ? `<span class="tk-muted">GitHubだけ</span>` : '<span class="tk-muted">なし</span>'}${d.base ? `<div class="tk-muted">作成元 ${esc(d.base)}</div>` : ''}</dd>
      <dt>提出</dt><dd>${submissionText(pr, open)}</dd>
    </dl>${open ? submissionButtons(n, pr, hasWorkspace) : ''}</section>
    <section class="tk-d-section"><h4>コメント ${d.comments.length}</h4>${d.comments.map(c => `<article class="tk-comment"><header>${esc(c.author)}</header><p>${esc(c.body)}</p></article>`).join('')}
      <div class="tk-comment-box"><textarea id="tk-comment-text" placeholder="コメントを書く（作業の記録・申し送り）" aria-label="コメント"></textarea><div><button type="button" data-tk="comment">コメント</button></div></div></section>`;
    // A long body is folded (BODY_FOLD px, as in tasks.css) so the plan and dates stay in sight.
    const body = tkEl('tk-detail').querySelector('.tk-d-body'), more = tkEl('tk-detail').querySelector('[data-body-more]');
    if (body && more) more.hidden = body.scrollHeight <= BODY_FOLD + 4;
  }
  const BODY_FOLD = 220;
  const dateInput = (key, value, dis) => `<input type="date" data-plan="${key}" value="${esc(value || '')}" class="${value ? '' : 'empty'}" ${dis}>`;
  // The ⋯ menu of the detail: plain things first, then the separated ones that throw something away (red, at the bottom).
  // Every item that opens a dialog ends with 「…」.
  function detailMenu(n, {open, hasWorkspace, remote, pr}) {
    const item = (action, label, {danger = false, title = '', off = ''} = {}) => `<button type="button" ${danger ? 'class="danger-text"' : ''} data-tk="${action}"${title || off ? ` title="${esc(off || title)}"` : ''}${off ? ' disabled' : ''}>${label}</button>`;
    // Someone else's submission: approving is the button; taking it in without approving and withdrawing it are here.
    const d = st.details.get(n), others = open && pr?.state === 'open' && !ownSubmission(d);
    const why = ECO.canTakeIn(st.access, d?.base) ? '' : ECO.takeInNote(st.access, d?.base || '取り込み先');
    const groups = [
      [item('github', 'GitHubで開く'), !open && pr?.state === 'merged' ? item('revert', '取り込みを取り消す…') : '',
        others && !pr.draft ? item('finish', '承認せずに取り込む…', {title: ECO.submissionHelp.finish, off: why}) : '', others ? item('withdraw', '提出を取り下げる…', {title: ECO.submissionHelp.withdraw}) : ''],
      [hasWorkspace ? item('remove', 'このPCから片付ける…', {title: 'このPCのタスクブランチだけを消します。GitHubのブランチ・提出・タスクは残り、「作業を再開」で続きから始められます（別のPCで続けるとき等）。'}) : ''],
      [hasWorkspace || remote ? item('drop', '作業を捨てる…', {danger: true, title: '作業を取り込まずに捨てます。タスクブランチと提出はこのPCとGitHubから消え、タスクは未着手に戻ります。'}) : '',
        open ? item('delete', '削除…', {danger: true, title: 'タスクを削除します（あとで元に戻せます）'}) : ''],
    ].map(g => g.join('')).filter(Boolean);
    return groups.join('<hr>');
  }

  // How a submission reads (PullRequestState). After a partial submission was taken in, the task has none open.
  function submissionText(pr, open) {
    if (!pr) return '<span class="tk-muted">なし</span>';
    const kind = pr.partial ? '中間提出' : '提出';
    if (pr.state === 'merged') return open ? '<span class="tk-muted">なし（前回の中間提出は取り込み済み）</span>' : `${kind}は取り込み済み`;
    if (pr.state === 'closed') return `<span class="tk-muted">${kind}は取り下げ済み</span>`;
    return `${pr.draft ? '下書きの' : ''}${kind}中`;
  }
  // The same buttons as a submission on the page ブランチ: looking (差分) on the left, what to do on the right, the main one
  // last. One's own is withdrawn or taken in; someone else's is checked here, sent back or approved. Taking in, approving
  // and sending back are for whoever made the branch it goes into, and admins: grey for the others, with the reason.
  function submissionButtons(n, pr, hasWorkspace) {
    const submitted = pr?.state === 'open', d = st.details.get(n), draft = submitted && pr.draft;
    const why = ECO.canTakeIn(st.access, d?.base) ? '' : ECO.takeInNote(st.access, d?.base || '取り込み先');
    const button = (action, label, {cls = '', off = '', help = action} = {}) => `<button type="button" ${cls ? `class="${cls}"` : ''} data-tk="${action}" title="${esc([ECO.submissionHelp[help], off && `（${off}）`].filter(Boolean).join('\n'))}"${off ? ' disabled' : ''}>${label}</button>`;
    const act = !submitted ? []
      : ownSubmission(d) ? [button('withdraw', '提出を取り下げる', {cls: 'tk-quiet-danger'}), button('finish', '取り込む', {cls: 'primary', off: draft ? '下書きの提出は取り込めません。タスクブランチの作業空間で下書きを解除します' : why})]
      : [button('review', '手元で確認', {help: 'local-review'}), button('reject', '差し戻す', {off: why}), button('approve', '承認して取り込む', {cls: 'primary', off: draft ? '下書きの提出は承認できません' : why})];
    if (!submitted && !hasWorkspace) return '';
    return `<div class="tk-sub-actions"><div>${button('diff', '差分')}</div><div>${act.join('')}</div></div>`;
  }
  const ownSubmission = d => !!me() && !!d?.assignees?.includes(me());
  const submissionPill = state => state ? `<span class="tk-pill">${state.draft ? '下書き' : state.partial ? '中間提出' : '提出中'}</span>` : '';

  // Operations ------------------------------------------------------------------------------------
  const run = (args, options = {}) => ECO.run(options.dir || root(), args, options);
  const placeFor = n => MOD.placeOfTask(n) || root();

  // Choices for dialogs. ecobuild has no command for "members who can be assigned", so the candidates are
  // what its commands return: yourself and the assignees of the tasks (task list --all).
  async function members() {
    if (!st.members) {
      const tasks = await ECO.query(root(), ['task', 'list', '--all']);
      const names = new Set(tasks.ok ? tasks.result.flatMap(t => t.assignees) : []);
      if (me()) names.delete(me());
      st.members = [...(me() ? [me()] : []), ...[...names].sort((a, b) => a.localeCompare(b))];
    }
    return st.members;
  }
  const memberOptions = list => list.map(m => [m, m === me() ? `${m}（自分）` : m]);
  const sprintOptions = (current = '') => [['', 'なし'], ...st.sprints.map(s => [s.name, `${s.name}（${md(s.start)}〜${md(s.end)}）${s.name === currentSprint() ? ' ・今' : ''}`]),
    ...(current && !st.sprints.some(s => s.name === current) ? [[current, current]] : [])];
  const parentOptions = (self, current) => [['', 'なし'], ...st.tasks.filter(t => t.number !== self && (t.state === 'open' || t.number === current))
    .sort((a, b) => a.number - b.number).map(t => [String(t.number), `#${t.number} ${t.title}`]),
    ...(current && !st.tasks.some(t => t.number === current) ? [[String(current), `#${current}`]] : [])];
  // Defaults the module sets (ecobuild.toml), to put into the fields from the start.
  async function moduleDefaults() {
    if (!st.defaults) st.defaults = await ECO.call('module-defaults', {dir: root()}).catch(() => ({}));
    return st.defaults;
  }

  async function startDialog(n) {
    const t = byNumber(n) || {}, d = st.details.get(n) || {};
    const defaults = await moduleDefaults();
    const parent = d.parent?.number || t.parent || 0;
    // The task branch there is already (here or on GitHub): its name is kept. A new one needs a name (required).
    const existing = d.branch || t.branch || null;
    // The default base: a child task starts from its parent's task branch (named from the parent's title if it is
    // not made yet, as the CLI does); otherwise default_base (ecobuild.toml).
    const parentTask = parent ? byNumber(parent) : null;
    const parentBranch = parent ? parentTask?.branch || `task/${parent}` + (parentTask && ECO.branchLabel(parentTask.title) ? '-' + ECO.branchLabel(parentTask.title) : '') : '';
    const base = parent ? parentBranch : d.remote && d.base ? d.base : defaults.default_base || '';
    // The base is chosen from the branches (ecobuild branch list, read from GitHub: added when it arrives): the plain
    // ones first, then the other workspaces; not those that are no module (unusable). Read afresh (not the cached
    // list): a branch just made must be there. A
    // child task's base is its parent's task branch, and a task branch on GitHub resumes from its recorded base: no choice.
    const branchOptions = parent || d.remote ? null : ECO.cli(root(), ['branch', 'list'], {quiet: true}).then(branches => branches.ok ? [...branches.result.filter(b => !b.is_task_branch && !b.unusable), ...branches.result.filter(b => b.is_task_branch && !b.unusable && ECO.taskOfBranch(b.name) !== n)].map(b => {
      const task = b.is_task_branch ? byNumber(ECO.taskOfBranch(b.name)) : null;
      return [b.name, b.is_task_branch ? `${b.name}（タスクブランチ${task ? '：' + task.title : ''}）` : b.name + (b.name === defaults.default_base ? '（既定）' : '') + (b.local ? '' : '（GitHubだけ）')];
    }) : []);
    // The task branch goes into a workspace of its own (task start makes it in the module: .ecobuild/w/<n>; the module's
    // own clone stays on its branch), or none is made (--no-branch). The account the workspace works as (an AI's account
    // etc.) is chosen when more than one is logged in on this PC.
    const listed = await ECO.cli(null, ['account', 'list'], {quiet: true}), accounts = listed.ok ? listed.result : [];
    const accountField = accounts.length > 1 ? [{name: 'account', label: '作業空間で使う GitHub のアカウント（AI 用のアカウント等。push・提出・コミットの作者がそのアカウントになります）', type: 'select', showIf: v => v.place !== 'none',
      value: '', options: [['', `gh の使用中のアカウント（${accounts.find(a => a.active)?.login || '?'}）`], ...accounts.filter(a => !a.active).map(a => [a.login, a.login])]}] : [];
    const assignees = d.assignees || t.assignees || [], others = me() && !assignees.includes(me()) ? assignees : [];
    await ECO.form({title: (d.remote ? '作業を再開' : '作業を開始') + `：#${n}`, intro: esc(t.title || d.title || ''), busy: `#${n} のタスクブランチを用意しています…`, fields: [
      {name: 'place', label: '作業の場所', type: 'radio', value: 'workspace', options: [
        ['workspace', '作業空間を作る', `タスクブランチの作業空間をモジュールの中（.ecobuild/w/${n}）に作り、新しいタブで開きます。完了する・作業を捨てると消えます`],
        ['none', 'タスクブランチを作らない', '調査・設計など、コードを変えないタスク（状態を作業中にするだけ）']]},
      ...accountField,
      ...(existing ? [] : [{name: 'branchName', label: 'タスクブランチの名前', required: true, value: ECO.branchLabel(t.title || d.title || ''), showIf: v => v.place !== 'none',
        help: `task/${n}-〈名前〉のブランチになります。日本語も使えます（空白と ~ ^ : ? * [ ] \\ / " < > | は使えません）。`}]),
      {name: 'base', label: '作成元のブランチ', type: 'select', value: base, options: [[base, base + (base === defaults.default_base ? '（既定）' : '')]], showIf: v => v.place !== 'none', more: branchOptions,
        help: parent ? `子タスクは親タスクのタスクブランチ（${parentBranch}）から作ります。` : d.remote ? 'GitHubにあるタスクブランチから再開します（作成元は記録されているものを使います）。' : ''},
      ...((d.blocked_by || []).some(b => b.state === 'open') ? [{name: 'ignoreBlocked', label: '先に終わるべきタスクが開いていても始める', type: 'checkbox'}] : []),
      ...(others.length ? [{name: 'takeOver', label: `${others.join('、')} から引き継ぐ（担当者を自分にし、タスクに残します）`, type: 'checkbox', help: 'ほかの人が担当しています。重ねて作業しないよう、相談してから引き継いでください。'}] : [])], ok: '開始',
      submit: async v => {
        // Pass --base only when it was changed from the default (the CLI decides the default the same way).
        if (others.length && !v.takeOver) return `${others.join('、')} が担当しています。引き継ぐ場合は「引き継ぐ」に印を付けてください。`;
        const args = ['task', 'start', String(n), ...(v.base && v.base !== base && v.place !== 'none' ? ['--base', v.base] : []), ...(v.ignoreBlocked ? ['--ignore-blocked'] : []), ...(v.takeOver ? ['--take-over'] : [])];
        if (v.place === 'none') args.push('--no-branch');
        else if (!existing) { const error = ECO.branchNameError(v.branchName || ''); if (error) return error; args.push('--name', v.branchName.trim()); }
        if (v.place !== 'none' && v.account) args.push('--account', v.account);
        const doc = await run(args, {success: v.place === 'none' ? `#${n} を作業中にしました。` : r => `タスクブランチ ${r.branch} の作業空間を作りました（${r.workspace}）。`, quietErrors: true});
        if (!doc) return '開始できませんでした。';
        if (v.place !== 'none') await MOD.showPlace(doc.result.workspace);
        reloadAfter(n);
      }});
  }
  // The assignee candidates known now (me and the assignees of the tasks listed) are shown at once; the full list
  // (task list --all, read from GitHub) is added to the open dialog when it arrives.
  const knownMembers = () => st.members || [...new Set([...(me() ? [me()] : []), ...st.tasks.flatMap(t => t.assignees || []).filter(m => m !== me()).sort((a, b) => a.localeCompare(b))])];
  const moreMembers = (except = []) => st.members ? null : members().then(list => memberOptions(list.filter(m => !except.includes(m))));
  async function newTaskDialog(preset = {}) {
    const people = [...new Set([...knownMembers(), ...(preset.assignees || [])])];
    await ECO.form({title: '新しいタスク', busy: 'タスクを作成しています…', fields: [
      {name: 'title', label: '題名', required: true},
      {name: 'body', label: '本文', type: 'textarea', rows: 3, placeholder: '背景・完了の条件など（任意）'},
      {name: 'stage', label: '段階', type: 'radio', inline: true, value: preset.stage || 'todo', showIf: v => !v.start, options: [['todo', '未着手'], ['planned', '計画中', 'まだ着手しない（内容・時期を詰めている）']]},
      {name: 'assignees', label: '担当者', type: 'checks', value: preset.assignees || [], options: memberOptions(people), more: moreMembers(), empty: 'まだ候補がありません（下の「候補にいない担当者」で入力できます）'},
      // Seldom needed: folded under the choices.
      {type: 'section', label: '＋ 候補にいない担当者', collapsed: true},
      {name: 'otherAssignees', label: 'GitHubのアカウント', placeholder: 'カンマ区切り（任意）'},
      {type: 'section', end: true},
      {type: 'section', label: '計画'},
      {name: 'priority', label: '優先度', type: 'select', row: 'plan', value: preset.priority || '', options: [['', 'なし'], ...PRIORITIES.map(p => [p, p])]},
      {name: 'estimate', label: '見積もり', type: 'number', row: 'plan'},
      {name: 'sprint', label: 'スプリント', type: 'select', row: 'plan', value: preset.sprint || '', options: sprintOptions()},
      {name: 'plannedStart', label: '開始予定日', type: 'date', row: 'dates'}, {name: 'plannedEnd', label: '終了予定日', type: 'date', row: 'dates'}, {name: 'due', label: '期限', type: 'date', row: 'dates'},
      {type: 'section', label: '分類・つながり', note: 'ラベル・マイルストーン・親タスク・先に終わるべきタスク', collapsed: true, open: !!preset.parent},
      {name: 'label', label: 'ラベル', row: 'tags', placeholder: 'カンマ区切り。なければ作ります'},
      {name: 'milestone', label: 'マイルストーン', type: 'select', row: 'tags', options: [['', 'なし'], ...st.milestones.map(m => [m.title, m.title + (m.due ? `（${m.due}）` : '')])]},
      {name: 'parent', label: '親タスク', type: 'select', row: 'links', value: preset.parent ? String(preset.parent) : '', options: parentOptions(0, 0)},
      {name: 'blockedBy', label: '先に終わるべきタスク', row: 'links', placeholder: '番号（カンマ区切り）'},
      {type: 'section', end: true},
      {name: 'start', label: '作成したら、作業空間を作って作業を開始する（担当者を選ばなければ自分になります）', type: 'checkbox'},
      {name: 'branchName', label: 'タスクブランチの名前', required: true, showIf: v => v.start,
        help: 'task/〈番号〉-〈名前〉のブランチになります（既定は題名）。日本語も使えます（空白と ~ ^ : ? * [ ] \\ / " < > | は使えません）。'}], ok: '作成',
      extra: '<span class="tk-new-task-form" hidden></span>',   // marks this dialog for tasks.css (its buttons stay in sight)
      // The branch name follows the title until it is changed by hand.
      onChange: (v, formEl) => {
        const field = formEl.elements.branchName; if (!field) return;
        if (field.value === (field.dataset.auto ?? '')) field.value = field.dataset.auto = ECO.branchLabel(v.title);
      },
      submit: async v => {
        if (v.start) { const error = ECO.branchNameError(v.branchName || ''); if (error) return error; }
        const args = ['task', 'new', v.title];
        const assignees = [...v.assignees, ...ECO.commaList(v.otherAssignees)];
        if (assignees.length) args.push('--assignee', [...new Set(assignees)].join(','));
        for (const [key, option] of [['body', '--body'], ['label', '--label'], ['parent', '--parent'], ['blockedBy', '--blocked-by'], ['milestone', '--milestone'], ['due', '--due'], ['plannedStart', '--planned-start'], ['plannedEnd', '--planned-end']]) if (v[key]) args.push(option, v[key]);
        if (v.start) args.push('--start', '--name', v.branchName.trim());
        const doc = await run(args, {success: r => `タスク #${(r.task || r).number} を作成しました。`, quietErrors: true});
        if (!doc) return '作成できませんでした。';
        const n = (doc.result.task || doc.result).number;
        st.members = null;
        // task new has no priority, estimate, sprint or stage: set them with task edit.
        const planArgs = [...(v.priority ? ['--priority', v.priority] : []), ...(v.estimate ? ['--estimate', v.estimate] : []), ...(v.sprint ? ['--sprint', v.sprint] : []), ...(!v.start && v.stage === 'planned' ? ['--stage', 'planned'] : [])];
        if (planArgs.length && !await run(['task', 'edit', String(n), ...planArgs], {quietErrors: true})) { await reloadAfter(); select(n); return `#${n} は作成しましたが、計画の値を保存できませんでした。`; }
        if (v.start) await MOD.showPlace(doc.result.task_branch?.workspace);
        await reloadAfter(); select(n);
      }});
  }
  async function editDialog(n) {
    const d = st.details.get(n); if (!d || d.error) return;
    const current = d.parent?.number || 0;
    await ECO.form({title: `タスク #${n} を編集`, busy: `#${n} を保存しています…`, fields: [
      {name: 'title', label: '題名', value: d.title, required: true}, {name: 'body', label: '本文', type: 'textarea', value: d.body, rows: 6},
      {type: 'section', label: 'つながり'},
      {name: 'parent', label: '親タスク', type: 'select', value: current ? String(current) : '', options: parentOptions(n, current)},
      {name: 'addBlocked', label: '先に終わるべきタスクを追加', row: 'blocked', placeholder: '番号（カンマ区切り）'},
      {name: 'removeBlocked', label: '先に終わるべきタスクから外す', row: 'blocked', placeholder: '番号（カンマ区切り）',
        help: d.blocked_by.length ? '今：' + d.blocked_by.map(b => '#' + b.number).join('、') : '今はありません。'}], ok: '保存',
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
        if (args.length === 3 && !reparent) return '変更する内容がありません。';
        if (args.length > 3 && !await run(args, {success: '保存しました。', quietErrors: true})) return '保存できませんでした。';
        if (reparent) {
          if (!await run(['task', 'edit', String(n), '--clear-parent'], {quietErrors: true})) return `親タスク #${current} から外せませんでした。`;
          if (!await run(['task', 'edit', String(n), '--parent', String(parent)], {success: `親タスクを #${parent} にしました。`, quietErrors: true})) return `親タスクを #${parent} にできませんでした（#${current} からは外れています）。`;
        }
        reloadAfter(n);
      }});
  }
  async function addAssigneeDialog(n) {
    const already = st.details.get(n)?.assignees || byNumber(n)?.assignees || [], people = knownMembers().filter(m => !already.includes(m));
    const v = await ECO.form({title: `担当者を追加：#${n}`, fields: [
      {name: 'who', label: '担当者', type: 'checks', options: memberOptions(people), more: moreMembers(already), empty: '候補者はすべて担当済みです（下の欄に入力できます）'},
      {name: 'other', label: '候補にいない担当者（GitHubのアカウント、カンマ区切り。任意）'}], ok: '追加'});
    const who = v ? [...new Set([...v.who, ...ECO.commaList(v.other)])] : [];
    if (who.length) editList(n, '--add-assignee', who.join(','), '担当者を追加しました。');
  }
  // 完了にする: a task without a task branch is just closed; one with a task branch is finished (task finish --complete:
  // what is not taken in yet is taken in, then it is closed and the task branch cleaned up). 削除: closed as
  // "not planned" (task close --not-planned); its task branch, if any, is thrown away.
  const hasTaskBranch = n => { const d = st.details.get(n), t = byNumber(n); return !!(MOD.placeOfTask(n) || d?.task_branch || d?.remote || t?.task_branch || t?.remote); };
  async function completeDialog(n) {
    if (hasTaskBranch(n)) {
      const d = st.details.get(n) || {}, options = await ECO.completeForm({number: n, submitted: d.pull_request?.state === 'open', base: d.base});
      if (!options) return;
      const place = placeFor(n);
      const doc = await run(['task', 'finish', String(n), ...options],
        {dir: place, success: r => `#${n} を完了しました。` + (r.next ? `次の候補：#${r.next.number} ${r.next.title}` : '')});
      if (doc) { ECO.workspaceKept(doc.result, n); await MOD.reloadPlace(place); reloadAfter(n); }
      return;
    }
    const t = byNumber(n) || st.details.get(n) || {};
    if (!await ECO.confirm({title: `#${n} を完了にする`, message: `${t.title || ''}\nを完了にします。`, ok: '完了にする'})) return;
    if (await run(['task', 'close', String(n)], {success: `#${n} を完了にしました。`})) reloadAfter(n);
  }
  async function deleteDialog(n) {
    const t = byNumber(n) || st.details.get(n) || {}, branch = hasTaskBranch(n);
    // What cannot be undone stands out as a warning (as GitHub's danger zone).
    if (!await ECO.dialog({title: `#${n} を削除`, body: `<p class="eco-message">「${esc(t.title || '')}」を削除します。タスクは、あとで「元に戻す」で戻せます。</p>`
      + (branch ? '<div class="eco-banner bad">このタスクの作業（タスクブランチと提出）は、このPCとGitHubから消えます。作業は戻せません。</div>' : ''),
      buttons: [['キャンセル', '', false], ['削除', 'danger', true]]})) return;
    const place = placeFor(n);
    if (await run(['task', 'close', String(n), '--not-planned', '--yes'], {dir: place, success: `#${n} を削除しました。`})) { if (branch) await MOD.reloadPlace(place); reloadAfter(n); }
  }
  async function dropDialog(n) {
    const v = await ECO.form({title: `作業を捨てる：#${n}`, intro: '作業を取り込まずに捨てます。提出を閉じ、タスクブランチをこのPCとGitHubから消して、その作業空間も消します。捨てた作業は戻せません。', fields: [{name: 'close', label: 'タスクも削除する', type: 'checkbox'}], ok: '作業を捨てる', danger: true});
    if (!v) return;
    const place = placeFor(n), doc = await run(['task', 'drop', String(n), ...(v.close ? ['--close'] : [])], {dir: place, success: r => `タスクブランチ ${r.branch} の作業をやめました。` + (r.workspace_removed ? `作業空間 ${r.workspace_removed} を消しました。` : r.workspace_kept ? `作業空間を残しました（${r.workspace_kept}）。` : '')});
    if (doc) { await MOD.reloadPlace(place); reloadAfter(n); }
  }
  async function removeWorkspace(n) {
    const place = placeFor(n);
    const ok = await ECO.confirm({title: `このPCから片付ける：#${n}`, message: 'このPCのタスクブランチだけを消します。GitHubのブランチ・提出・タスクは残るので、「作業を再開」でPushしたところから続けられます。\n未コミット・未Pushの変更があるときは消しません。', ok: '消す', danger: true});
    if (!ok) return;
    const doc = await run(['task', 'prune', String(n)], {dir: place, success: r => `手元のタスクブランチ ${r.branch || r.removed?.join('、')} を削除しました。` + (r.workspace_removed ? `作業空間 ${r.workspace_removed} を消しました。` : r.workspace_kept ? `作業空間を残しました（${r.workspace_kept}）。` : '')});
    if (doc) { await MOD.reloadPlace(place); reloadAfter(n); }
  }
  // The task branches are the module's (every workspace's): one task prune in the module's own clone covers them all,
  // and removes the workspaces they were checked out in.
  async function cleanDialog() {
    const preview = await ECO.cli(root(), ['task', 'prune', '--dry-run']);
    if (!preview.ok) return ECO.showError(preview);
    const r = preview.result, removing = r.workspaces_removed || [];
    const body = (r.removed.length ? '<p>片付けるタスクブランチ：</p><ul class="eco-list">' + r.removed.map(b => `<li>${esc(b)}</li>`).join('') + '</ul>' : '<p>片付けるタスクブランチはありません。</p>')
      + (removing.length ? '<p>一緒に消える作業空間：</p><ul class="eco-list">' + removing.map(p => `<li>${esc(p)}</li>`).join('') + '</ul>' : '')
      + (r.skipped.length ? '<p>残すもの：</p><ul class="eco-list">' + r.skipped.map(s => `<li>${esc(s.branch)}：${esc(s.reason)}</li>`).join('') + '</ul>' : '');
    const ok = await ECO.dialog({title: '完了したタスクブランチを片付ける', body: '<p class="eco-intro">閉じたタスクのタスクブランチと、その作業空間を消します。取り込んでいないコミットがあるものは残します。</p>' + body,
      buttons: r.removed.length ? [['キャンセル', '', false], ['片付ける', 'primary', true]] : [['閉じる', 'primary', false]]});
    if (!ok) return;
    const doc = await run(['task', 'prune', '--yes'], {success: d => d.removed.length ? `片付けました：${d.removed.join('、')}` : '片付けたものはありません。'});
    if (doc) for (const s of doc.result.skipped) ECO.toast(`${s.branch} は残しました：${s.reason}`, 'info', 9000);
    await MOD.syncPlaces();
    reloadAfter();
  }
  // Submissions (task finish／approve／reject／withdraw): 取り込む takes an open submission in. Numbers are task numbers.
  async function finishDialog(n) {
    const d = st.details.get(n) || {};
    const options = await ECO.finishForm({number: n, base: d.base, partial: !!d.pull_request?.partial});
    if (!options) return;
    const place = placeFor(n);
    const doc = await run(['task', 'finish', String(n), ...options],
      {dir: place, success: r => r.partial ? `#${n} を取り込み、タスクブランチを作り直しました（タスクは続きます）。` : `#${n} を取り込み、完了しました。` + (r.next ? `次の候補：#${r.next.number} ${r.next.title}` : '')});
    if (doc) { ECO.workspaceKept(doc.result, n); await MOD.reloadPlace(place); reloadAfter(n); }
  }
  async function withdrawSubmission(n) {
    if (!await ECO.confirm({title: `提出を取り下げる：#${n}`, message: '提出を取り下げて、作業中に戻します。タスクブランチは残るので、あとでもう一度提出できます。', ok: '取り下げる'})) return;
    if (await run(['task', 'withdraw', String(n)], {dir: placeFor(n), success: `#${n} の提出を取り下げました。`})) reloadAfter(n);
  }
  async function reviewSubmission(n) {
    const doc = await run(['task', 'review', String(n)], {success: r => `#${n} の提出を確認用の作業空間に取り出しました（${r.workspace}）。そこでビルド・テスト・実行ができます。`});
    if (doc) { await MOD.showPlace(doc.result.workspace); reloadAfter(n); }
  }
  async function judgeDialog(n, approve) {
    const v = await ECO.form(approve
      ? {title: `承認して取り込む：#${n}`, intro: 'CIが終わるのを待ちます。タスクは提出のとおり閉じるか続けます。', fields: [{name: 'message', label: 'コメント（任意）', type: 'textarea'}], ok: '承認して取り込む'}
      : {title: `差し戻す：#${n}`, intro: 'タスクは作業中に戻ります。', fields: [{name: 'message', label: '直してほしいこと', type: 'textarea', required: true}], ok: '差し戻す', danger: true});
    if (!v) return;
    const doc = await run(['task', approve ? 'approve' : 'reject', String(n), ...(v.message ? ['--message', v.message] : [])],
      {success: approve ? r => `#${n} を承認して取り込みました。` + (r.partial ? 'タスクは続きます。' : 'タスクを完了しました。') : `#${n} を差し戻しました。`});
    if (doc) { if (approve) ECO.workspaceKept(doc.result, n); await MOD.reloadPlace(root()); reloadAfter(n); }
  }
  async function revertDialog(n) {
    if (!await ECO.confirm({title: `取り込みを取り消す：#${n}`, message: `#${n} で取り込んだ変更を元に戻すための、新しいタスクを作ります。変更を戻すコミットも用意するので、中身を確かめてから提出してください。`, ok: 'タスクを作る'})) return;
    const doc = await run(['task', 'revert', String(n)], {success: r => `#${n} を取り消すタスクブランチ ${r.branch}（タスク #${r.task}）を作りました。`});
    if (doc) { await MOD.reloadPlace(root()); reloadAfter(); }
  }
  async function plan(n, key, value) {
    const option = {priority: '--priority', due: '--due', estimate: '--estimate', sprint: '--sprint', planned_start: '--planned-start', planned_end: '--planned-end'}[key];
    const args = ['task', 'edit', String(n), ...(value ? [option, value] : ['--clear', key])];
    if (await run(args, {success: '計画を保存しました。'})) reloadAfter(n); else renderDetail();
  }
  async function editList(n, option, value, message) { if (await run(['task', 'edit', String(n), option, value], {success: message})) reloadAfter(n); }

  // Account popup: assigned tasks (task list), counts (task workload), submissions (task list --submitted), review requests (--to-review).
  async function showPerson(who) {
    st.person = who;
    const body = tkEl('tk-person-body'); body.innerHTML = ECO.loading(); if (!tkEl('tk-person-dialog').open) tkEl('tk-person-dialog').showModal();
    const [workload, prs, reviews] = await Promise.all([ECO.query(root(), ['task', 'workload']), ECO.query(root(), ['task', 'list', '--submitted']), who === me() ? ECO.query(root(), ['task', 'list', '--to-review']) : null]);
    if (st.person !== who) return;
    const w = workload.ok ? workload.result.find(x => x.assignee === who) : null;
    // 作業中 counts and lists the same tasks as task workload: not the parents (their children are counted).
    const ts = st.tasks.filter(t => t.state === 'open' && t.assignees.includes(who)), doing = ts.filter(t => !t.subtasks && ['in_progress', 'in_review'].includes(stageOf(t)));
    const own = prs.ok ? prs.result.filter(t => t.assignees.includes(who)) : [], asked = reviews?.ok ? reviews.result : [];
    const stat = (label, value, cls = '') => `<div class="tk-pf-stat ${cls}"><b>${value}</b><span>${label}</span></div>`;
    const taskRow = t => `<div class="tk-row" data-task="${t.number}"><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span>${stageBadge(t)}${due(t)}</div>`;
    const prRow = t => `<div class="tk-row" data-task="${t.number}"><span class="tk-num">#${t.number}</span><span class="tk-grow">${esc(t.title)}</span>${submissionPill(t.submission)}</div>`;
    const section = (title, html, extra = '') => `<section class="tk-pf-section ${extra}"><h4>${title}</h4>${html || '<p class="tk-muted">ありません</p>'}</section>`;
    body.innerHTML = `<div class="tk-pf"><header class="tk-pf-head">${avatarMark(who)}<div><div class="tk-pf-name">${esc(who)}${who === me() ? '<span class="tk-pill ok">自分</span>' : ''}</div></div>
      <button type="button" class="tk-d-close" data-close-person title="閉じる" aria-label="閉じる">×</button></header>
      <div class="tk-pf-stats">${stat('担当（親を除く）', w ? w.open : ts.length)}${stat('作業中（親を除く）', w ? w.in_progress : doing.length)}${stat('残りの見積もり', w ? w.estimate_remaining : '-')}${stat('期限切れ', w ? w.overdue : 0, w?.overdue ? 'bad' : '')}${stat('提出中', own.length)}</div>
      <div class="tk-pf-grid">${section('作業中', doing.map(taskRow).join(''))}${section('提出', own.map(prRow).join(''))}${who === me() ? section('見るように頼まれた提出', asked.map(prRow).join('')) : ''}
      ${section('担当タスク', ts.length ? taskTable(ts, false) : '', 'wide')}</div></div>`;
  }

  // Right-click menu on a task (list rows, stage cards, timeline, relations, the account popup) --------------
  async function detailOf(n) { if (!st.details.has(n) || st.details.get(n).error) await loadDetail(n); return st.details.get(n); }
  // No separator twice in a row or at the end (groups that came out empty).
  const tidyMenu = items => items.filter((x, i, all) => x !== '-' || (i > 0 && all[i - 1] !== '-' && i < all.length - 1));
  function taskMenu(n, x, y) {
    const t = byNumber(n); if (!t) return;
    const open = t.state === 'open', hasWorkspace = !!MOD.placeOfTask(n) || t.task_branch || t.current, mine = me() && t.assignees.includes(me());
    ECO.menu(tidyMenu([
      ['詳細を見る', () => select(n)],
      ...(open ? [hasWorkspace ? ['タスクブランチを開く', () => MOD.openWorkspace(n)] : [t.remote ? '作業を再開…' : '作業を開始…', async () => { await detailOf(n); startDialog(n); }]] : []),
      '-',
      ['担当者を追加…', async () => { await detailOf(n); addAssigneeDialog(n); }],
      ...(me() ? [mine ? ['自分を担当から外す', () => editList(n, '--remove-assignee', '@me', '担当から外れました。')] : ['自分を担当にする', () => editList(n, '--add-assignee', '@me', '担当にしました。')]] : []),
      // The priority as a group under a heading, the current one marked (as VS Code and Linear).
      ...(open ? ['-', ['優先度', null], ...PRIORITIES.map(p => [`${t.priority === p ? '✓ ' : '　 '}${p}`, () => plan(n, 'priority', p), t.priority !== p]),
        ...(t.priority ? [['　 優先度を消す', () => plan(n, 'priority', '')]] : [])] : []),
      ...(open ? ['-', ...(currentSprint() ? [[`今のスプリント（${currentSprint()}）に入れる`, () => plan(n, 'sprint', currentSprint()), sprintName(t) !== currentSprint()]] : []), ...(sprintName(t) ? [['スプリントから外す', () => plan(n, 'sprint', '')]] : [])] : []),
      ...(open && !hasWorkspace && !t.remote && ['planned', 'todo'].includes(stageOf(t)) ? [stageOf(t) === 'planned' ? ['未着手にする', () => setStage(n, 'todo')] : ['計画中に戻す', () => setStage(n, 'planned')]] : []),
      '-',
      ['子タスクを作る…', () => newTaskDialog({parent: n}), open],
      ['編集…', async () => { await detailOf(n); select(n); editDialog(n); }],
      // The same words and dialogs as the detail's buttons.
      open ? ['完了にする…', async () => { await detailOf(n); completeDialog(n); }]
        : [deleted(t) ? '元に戻す' : '開き直す', async () => { if (await run(['task', 'reopen', String(n)], {success: `#${n} を開き直しました。`})) reloadAfter(n); }],
      ['GitHubで開く', () => window.open(t.url, '_blank', 'noopener')],
      // What throws something away, apart at the bottom.
      ...(hasWorkspace ? ['-', ['このPCから片付ける（GitHubには残す）…', () => removeWorkspace(n)]] : []),
      ...(hasWorkspace || t.remote || open ? ['-'] : []),
      ...(hasWorkspace || t.remote ? [['作業を捨てる（GitHubからも消す）…', () => dropDialog(n), true, '', {danger: true}]] : []),
      ...(open ? [['削除…', () => deleteDialog(n), true, '', {danger: true}]] : []),
    ]), x, y);
  }
  document.addEventListener('contextmenu', e => {
    const target = e.target.closest('#tasks-content [data-task], #tk-person-dialog [data-task]');
    if (!target || !target.dataset.task) return;
    e.preventDefault(); taskMenu(Number(target.dataset.task), e.clientX, e.clientY);
  });

  // Drag a card to another column. The stages before the work (計画中・未着手) are set with task edit --stage; the work
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
    if (t.state !== 'open' && (stage === 'done' || stage === 'deleted')) return ECO.toast(`閉じたタスクは、開き直してから${STAGE[stage]?.[1] || '削除済み'}に移してください。`, 'info', 6000);
    if (stage === 'done') return completeDialog(n);
    if (stage === 'deleted') return deleteDialog(n);
    if (t.state !== 'open') {
      // Out of 完了・削除済み: reopen (task reopen), then put it in the stage it was dropped on when that is 計画中.
      if (!['planned', 'todo'].includes(stage)) return ECO.toast('閉じたタスクは、開き直して未着手か計画中に戻してから開始してください。', 'info', 6000);
      if (!await ECO.confirm({title: `#${n} を開き直す`, message: `「${t.title}」を開き直して、${STAGE[stage][1]}にします。`, ok: '開き直す'})) return;
      if (await run(['task', 'reopen', String(n)], {success: `#${n} を開き直しました。`})) { if (stage === 'planned') await setStage(n, 'planned'); else reloadAfter(n); }
      return;
    }
    if (stage === 'in_progress') {
      if (MOD.placeOfTask(n) || t.task_branch) return ECO.toast('タスクブランチがあるタスクは、すでに作業中です。', 'info');
      await detailOf(n); return startDialog(n);
    }
    if (stage === 'in_review') return ECO.toast('タスクブランチで提出すると、レビュー待ちに移ります。', 'info', 6000);
    if (MOD.placeOfTask(n) || t.task_branch || t.remote) return ECO.toast('タスクブランチがあるタスクです。「作業を捨てる」と未着手に戻ります。', 'info', 6000);
    setStage(n, stage);
  });
  async function setStage(n, stage) { if (await run(['task', 'edit', String(n), '--stage', stage], {success: `#${n} を${STAGE[stage][1]}にしました。`})) reloadAfter(n); }

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
    const doc = await run(['task', 'edit', String(t.number), '--planned-start', start, '--planned-end', end], {success: `#${t.number} の予定を ${md(start)}〜${md(end)} にしました。`});
    if (doc) reloadAfter(t.number); else render();
  });

  // Drag across the days of a row without a plan to give it one (a click gives a one-day plan).
  let planDrag = null;
  const dayAt = (grid, x) => { const r = grid.getBoundingClientRect(), i = Math.floor((x - r.left - 220) / DAY_PX); return Number(grid.dataset.first) + Math.max(0, Math.min(Number(grid.dataset.days) - 1, i)); };
  const dateOf = n => new Date(n * DAY).toISOString().slice(0, 10);
  document.addEventListener('pointerdown', e => {
    const row = e.target.closest?.('#tasks-content .tl-empty.plannable'); if (!row || e.button !== 0) return;
    const grid = row.closest('.tl-grid'), from = dayAt(grid, e.clientX), ghost = document.createElement('div');
    ghost.className = 'tl-ghost'; ghost.style.gridRow = row.style.gridRow; grid.append(ghost);
    planDrag = {grid, row, n: Number(row.dataset.planRow), from, to: from, ghost};
    showGhost(); try { row.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer */ } e.preventDefault();
  });
  function showGhost() {
    const {grid, from, to, ghost} = planDrag, a = Math.min(from, to), b = Math.max(from, to), first = Number(grid.dataset.first);
    ghost.style.gridColumn = `${a - first + 2} / ${b - first + 3}`; ghost.textContent = `${md(dateOf(a))}〜${md(dateOf(b))}`;
  }
  document.addEventListener('pointermove', e => { if (!planDrag) return; const to = dayAt(planDrag.grid, e.clientX); if (to !== planDrag.to) { planDrag.to = to; showGhost(); } });
  document.addEventListener('pointerup', async () => {
    if (!planDrag) return;
    const {n, from, to, ghost} = planDrag; planDrag = null;
    const start = dateOf(Math.min(from, to)), end = dateOf(Math.max(from, to));
    const doc = await run(['task', 'edit', String(n), '--planned-start', start, '--planned-end', end], {success: `#${n} の予定を ${md(start)}〜${md(end)} にしました。`});
    ghost.remove();
    if (doc) reloadAfter(n); else render();
  });

  // Events ----------------------------------------------------------------------------------------
  document.querySelector('.tk-views').addEventListener('click', e => { const b = e.target.closest('[data-view]'); if (b) { st.view = b.dataset.view; render(); } });
  tkEl('tk-search').addEventListener('input', render);
  tkEl('tk-assignee').addEventListener('change', e => { st.assignee = e.target.value; render(); });
  tkEl('tk-sprint').addEventListener('change', e => { st.sprint = e.target.value; render(); });
  tkEl('tk-milestone').addEventListener('change', e => { st.milestone = e.target.value; render(); });
  tkEl('tk-ready').addEventListener('change', () => load());
  tkEl('tk-closed').addEventListener('change', () => load());
  tkEl('tk-deleted').addEventListener('change', () => load());
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
        case 'complete': return completeDialog(n);
        case 'delete': return deleteDialog(n);
        case 'edit': return editDialog(n);
        case 'drop': return dropDialog(n);
        case 'remove': return removeWorkspace(n);
        case 'finish': return finishDialog(n);
        case 'withdraw': return withdrawSubmission(n);
        case 'review': return reviewSubmission(n);
        case 'approve': return judgeDialog(n, true);
        case 'reject': return judgeDialog(n, false);
        case 'diff': return ECO.inTortoiseGit(placeFor(n), ['task', 'diff', String(n)], async () => { const doc = await ECO.cli(placeFor(n), ['task', 'diff', String(n)]); return doc.ok ? ECO.output(`#${n} の差分`, doc.result || '差分はありません。', {diff: true}) : ECO.showError(doc); });
        case 'revert': return revertDialog(n);
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
    const mode = e.target.closest('[data-tl-mode]');
    if (mode) { timelineMode = mode.dataset.tlMode; try { localStorage.setItem('ecobuild-gui-timeline-mode', timelineMode); } catch (error) { /* storage blocked */ } render(); return; }
    const move = e.target.closest('[data-cal-move]');
    if (move) {
      const step = Number(move.dataset.calMove), month = calendarMonth || today().slice(0, 7);
      calendarMonth = step ? monthOf(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1 + step) : '';
      render(); return;
    }
    const go = e.target.closest('[data-dash-go]'); if (go) { st.view = go.dataset.dashGo; render(); return; }
    const milestone = e.target.closest('[data-dash-milestone]'); if (milestone) { st.milestone = milestone.dataset.dashMilestone; renderFilterOptions(); st.view = 'list'; render(); return; }
    if (e.target.closest('[data-dash-unassigned]')) { st.assignee = '-'; tkEl('tk-assignee').value = '-'; st.view = 'list'; render(); return; }
    if (e.target.closest('[data-close-person]')) return tkEl('tk-person-dialog').close();
    const sortButton = e.target.closest('[data-sort]');
    if (sortButton) { const key = sortButton.dataset.sort; st.sort = {key, dir: st.sort.key === key ? -st.sort.dir : 1}; render(); if (st.person) showPerson(st.person); return; }
    const picked = e.target.closest('#tk-person-dialog [data-task]');
    if (picked && !e.target.closest('button')) { if (picked.dataset.task) { tkEl('tk-person-dialog').close(); select(Number(picked.dataset.task)); } return; }
    if (e.target.closest('[data-close-detail]')) { st.selected = 0; render(); return; }
    if (e.target.closest('[data-body-more]')) { st.bodyOpen = st.bodyOpen === st.selected ? 0 : st.selected; renderDetail(); return; }
    const task = e.target.closest('#tasks-content [data-task]');
    if (task && !e.target.closest('button, select, input, textarea')) select(Number(task.dataset.task));
  });
  // Enter / Space on a focused row or card opens it (the focus stays on it after the screen is drawn again).
  document.addEventListener('keydown', e => {
    if (!['Enter', ' '].includes(e.key)) return;
    const task = e.target.closest?.('#tasks-content [data-task][tabindex]'); if (!task || task !== e.target) return;
    e.preventDefault(); const n = Number(task.dataset.task); select(n);
    tkEl('tk-main').querySelector(`[data-task="${n}"][tabindex]`)?.focus();
  });
  document.addEventListener('change', e => {
    if (e.target.id === 'tk-sprint-shown') { st.sprintShown = e.target.value; render(); return; }
    if (!e.target.closest('#tk-detail')) return;
    if (e.target.dataset.plan) plan(st.selected, e.target.dataset.plan, e.target.value);
    if (e.target.matches('[data-milestone]')) {
      const n = st.selected, args = ['task', 'edit', String(n), ...(e.target.value ? ['--milestone', e.target.value] : ['--clear-milestone'])];
      run(args, {success: 'マイルストーンを変更しました。'}).then(doc => doc ? reloadAfter(n) : renderDetail());
    }
  });

  pageHooks.tasks = () => { if (!st.loaded || st.stale) { st.stale = false; load(); } else render(); };
  pageHooks.changed = () => { if (!st.loaded) return; if (mEl('tasks-content').hidden) st.stale = true; else load(); };
})();
