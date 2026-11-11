// 部品「日程」。横の帯（どのタスクも1行。予定のあるものは帯、ないものは下にまとめる）か、月のカレンダー。
// 表示の切り替えは、この PC に覚える。帯のドラッグは、放したときに edit（開始予定・終了予定）を出すだけ。
// <<タスクの印（タスクを描く部品で同じもの。部品はほかのファイルを読めないので、それぞれに同じ文を置く）
const STAGES = [['planned', '計画中', 'backlog'], ['todo', '未着手', 'todo'], ['in_progress', '作業中', 'in_progress'], ['in_review', 'レビュー待ち', 'in_review'], ['done', '完了', 'done']];
const STAGE = Object.fromEntries(STAGES.map((s) => [s[0], s]));
const PRIORITIES = ['High', 'Middle', 'Low'];
// 印を作る道具。sprints：スプリントの一覧（今のスプリントを色で分ける）。me：自分のアカウント。
function taskMarks(h, emit, menu, sprints, me) {
  const clock = new Date();
  const today = new Date(clock.getTime() - clock.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const md = (d) => (d ? Number(d.slice(5, 7)) + '/' + Number(d.slice(8, 10)) : '');
  const open = (t) => (t.state || 'open') === 'open';
  const deleted = (t) => !open(t) && t.closed_reason === 'not_planned';
  // 画面に出す段階：閉じていれば完了（か削除済み）。段階の記録がなければ、タスクブランチがあれば作業中、なければ未着手
  const stageOf = (t) => (deleted(t) ? 'deleted' : !open(t) ? 'done' : STAGE[t.stage] ? t.stage : (t.task_branch || t.remote || t.current ? 'in_progress' : 'todo'));
  const sprintName = (t) => (typeof t.sprint === 'string' ? t.sprint : (t.sprint && t.sprint.name) || '');
  const currentSprint = ((sprints || []).find((s) => s.start <= today && today < s.end) || {}).name || '';
  const isAgent = (who) => /agent|bot/i.test(who);
  const span = (cls, text, title) => h('span', title ? { class: cls, title } : { class: cls }, text);
  const stageMark = (key, text) => span('tk-stage ' + (key === 'deleted' ? 'not_planned' : STAGE[key][2]), text || (key === 'deleted' ? '削除済み' : STAGE[key][1]));
  const avatarMark = (who) => (!who ? span('tk-avatar none', '', '担当なし') : span('tk-avatar' + (isAgent(who) ? ' agent' : ''), isAgent(who) ? 'AI' : who[0].toUpperCase(), who));
  const avatar = (who) => {
    if (!who) return avatarMark('');
    const button = h('button', { type: 'button', class: 'tk-person-link', title: who + ' の画面' }, avatarMark(who));
    button.addEventListener('click', (event) => { event.stopPropagation(); emit('dialog', { screen: 'task-person', id: '0', text: who }); });
    return button;
  };
  const marks = {
    today, md, open, deleted, stageOf, sprintName, currentSprint, span, stageMark, avatarMark, avatar,
    stageBadge: (t) => (open(t) ? stageMark(stageOf(t)) : stageMark(deleted(t) ? 'deleted' : 'done')),
    prio: (t) => (t.priority ? span('tk-prio ' + t.priority, t.priority) : ''),
    due: (t) => (t.due ? span('tk-due' + (open(t) && t.due < today ? ' overdue' : ''), md(t.due)) : ''),
    est: (t) => (t.estimate !== null && t.estimate !== undefined ? span('tk-est', String(t.estimate), '見積もり') : ''),
    sprintTag: (t) => (sprintName(t) ? span('tk-sprint' + (sprintName(t) === currentSprint ? ' now' : ''), sprintName(t), 'スプリント') : ''),
    num: (t) => span('tk-num', '#' + t.number),
    flags: (t) => [
      t.blocked_by && open(t) ? span('tk-flag blocked', '待ち ' + t.blocked_by) : '',
      t.subtasks ? span('tk-flag', '子 ' + t.subtasks_done + '/' + t.subtasks) : '',
      t.current || t.task_branch ? span('tk-flag', 'タスクブランチ') : t.remote ? span('tk-flag', 'GitHubにタスクブランチ') : '',
    ].filter(Boolean),
    avatars: (t) => ((t.assignees || []).length ? t.assignees.map(avatar) : [avatar('')]),
    submissionPill: (s) => (s ? span('tk-pill', s.draft ? '下書き' : s.partial ? '中間提出' : '提出中') : ''),
    loading: (text) => h('p', { class: 'tk-empty', role: 'status' }, h('span', { class: 'spinner' }), ' ' + (text || '読み込んでいます…')),
    failed: (text) => h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, text)),
    // 行・カードを選べるようにする（押す・Enter・Space）。右クリックでメニュー
    pick: (node, t) => {
      node.addEventListener('click', (event) => { if (!event.target.closest('button, select, input, textarea, a')) emit('selected', { id: String(t.number) }); });
      node.addEventListener('keydown', (event) => {
        if ((event.key === 'Enter' || event.key === ' ') && event.target === node) { event.preventDefault(); emit('selected', { id: String(t.number) }); }
      });
      node.addEventListener('contextmenu', (event) => { event.preventDefault(); marks.menu(event, t); });
      return node;
    },
    // 右クリックのメニュー。選んだものを出すだけ（何が起きるかは、つないだコマンドと、開く入力の窓が決める）
    menu: async (event, t) => {
      const id = String(t.number), isOpen = open(t), hasWorkspace = Boolean(t.task_branch || t.current), stage = stageOf(t);
      const mine = Boolean(me) && (t.assignees || []).includes(me);
      const sep = { separator: true };
      const items = [{ id: 'show', label: '詳細を見る' }];
      if (isOpen && hasWorkspace && t.workspace) items.push({ id: 'workspace', label: 'タスクブランチを開く' });
      if (isOpen && !hasWorkspace) items.push({ id: 'start', label: t.remote ? '作業を再開…' : '作業を開始…' });
      items.push(sep, { id: 'assign', label: '担当者を追加…' });
      if (me) items.push(mine ? { id: 'unassign-me', label: '自分を担当から外す' } : { id: 'assign-me', label: '自分を担当にする' });
      if (isOpen) {
        items.push(sep, { heading: '優先度' }, ...PRIORITIES.map((p) => ({ id: 'priority:' + p, label: (t.priority === p ? '✓ ' : '　 ') + p, disabled: t.priority === p, reason: '今の優先度です' })));
        if (t.priority) items.push({ id: 'clear:priority', label: '　 優先度を消す' });
        const sprint = [];
        if (currentSprint) sprint.push({ id: 'sprint-in', label: '今のスプリント（' + currentSprint + '）に入れる', disabled: sprintName(t) === currentSprint, reason: '今のスプリントに入っています' });
        if (sprintName(t)) sprint.push({ id: 'clear:sprint', label: 'スプリントから外す' });
        if (sprint.length) items.push(sep, ...sprint);
        if (!hasWorkspace && !t.remote && (stage === 'planned' || stage === 'todo')) items.push(stage === 'planned' ? { id: 'stage:todo', label: '未着手にする' } : { id: 'stage:planned', label: '計画中に戻す' });
      }
      items.push(sep, { id: 'child', label: '子タスクを作る…', disabled: !isOpen, reason: '閉じたタスクです' }, { id: 'edit', label: '編集…' });
      items.push(isOpen ? { id: 'complete', label: '完了にする…' } : { id: 'reopen', label: deleted(t) ? '元に戻す' : '開き直す' });
      if (hasWorkspace) items.push(sep, { id: 'prune', label: 'このPCから片付ける（GitHubには残す）…' });
      if (hasWorkspace || t.remote || isOpen) items.push(sep);
      if (hasWorkspace || t.remote) items.push({ id: 'drop', label: '作業を捨てる（GitHubからも消す）…', danger: true });
      if (isOpen) items.push({ id: 'delete', label: '削除…', danger: true });
      const chosen = await menu(event, items);
      if (!chosen) return;
      const dialog = (screen, text) => emit('dialog', { screen, id, text: text || '' });
      const [kind, value] = chosen.split(':');
      if (chosen === 'show') emit('selected', { id });
      else if (chosen === 'workspace') emit('workspace', { path: t.workspace });
      else if (chosen === 'start') dialog('task-start');
      else if (chosen === 'assign') dialog('task-assign');
      else if (chosen === 'assign-me') emit('edit', { id, add_assignee: '@me' });
      else if (chosen === 'unassign-me') emit('edit', { id, remove_assignee: '@me' });
      else if (kind === 'priority') emit('edit', { id, priority: value });
      else if (kind === 'clear') emit('edit', { id, clear: value });
      else if (chosen === 'sprint-in') emit('edit', { id, sprint: currentSprint });
      else if (kind === 'stage') emit('edit', { id, stage: value });
      else if (chosen === 'child') dialog('task-new', id);
      else if (chosen === 'edit') dialog('task-edit');
      else if (chosen === 'complete') { if (hasWorkspace || t.remote) dialog('task-complete'); else emit('close', { id }); }
      else if (chosen === 'reopen') emit('reopen', { id });
      else if (chosen === 'prune') dialog('task-prune');
      else if (chosen === 'drop') dialog('task-drop');
      else if (chosen === 'delete') emit('remove', { id });
    },
  };
  return marks;
}
// 絞り込み（task-bar の出す値）に合うタスクだけにする。見せ方だけ
function taskFilter(tasks, f, marks, me) {
  const search = String(f.search || '').trim().toLowerCase();
  const who = f.assignee || '', sprint = f.sprint || '', milestone = f.milestone || '';
  return tasks.filter((t) => (marks.open(t) || (marks.deleted(t) ? f.deleted === true : f.closed === true))
    && (who === '' || (who === '-' ? !(t.assignees || []).length : (t.assignees || []).includes(who === '@me' ? me : who)))
    && (sprint === '' || (sprint === '-' ? !marks.sprintName(t) : marks.sprintName(t) === (sprint === 'current' ? marks.currentSprint : sprint)))
    && (milestone === '' || (milestone === '-' ? !t.milestone : t.milestone === milestone))
    && (!search || String(t.title || '').toLowerCase().includes(search) || '#' + t.number === search));
}
// タスクの印>>
const DAY = 86400000, DAY_PX = 28, LABEL_PX = 220;
const WEEK = ['日', '月', '火', '水', '木', '金', '土'];
const dayOf = (d) => Date.parse(d + 'T00:00:00Z') / DAY;
const weekday = (n) => new Date(n * DAY).getUTCDay();
const dateOf = (n) => new Date(n * DAY).toISOString().slice(0, 10);

export default {
  render(root, props, { h, emit, menu, state, memory, redraw }) {
    const marks = taskMarks(h, emit, menu, props.sprints, props.me);
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    if (props.loading && props.tasks.length === 0) return root.replaceChildren(marks.loading('タスクを読み込んでいます…'));
    const { md, today, open } = marks;
    const visible = taskFilter(props.tasks, props.filter || props.start || {}, marks, props.me);
    const mode = memory.get('mode', 'bars') === 'calendar' ? 'calendar' : 'bars';
    const isSelected = (t) => String(t.number) === String(props.selected || '');
    const at = (node, style) => { node.setAttribute('style', style); return node; };

    // 上の道具：左に月の移動（カレンダー）、右に表示の切り替え
    const tools = (...left) => {
      const modes = h('div', { class: 'modes', role: 'group', 'aria-label': '日程の表示' });
      for (const [key, label] of [['bars', '横の帯'], ['calendar', 'カレンダー']]) {
        const button = h('button', { type: 'button' }, label);
        button.setAttribute('aria-pressed', String(mode === key));
        button.addEventListener('click', () => { memory.set('mode', key); redraw(); });
        modes.append(button);
      }
      return h('div', { class: 'tools' }, ...left, h('span', { class: 'tools-end' }, modes));
    };
    const legend = (...more) => h('div', { class: 'legend' },
      h('span', {}, h('i', { class: 'key bar' }), '開始予定〜終了予定'), h('span', {}, h('i', { class: 'key due' }, '◆'), '期限'), ...more);

    if (mode === 'calendar') {
      const month = state.month || today.slice(0, 7), y = Number(month.slice(0, 4)), m = Number(month.slice(5, 7)) - 1;
      const monthOf = (yy, mm) => new Date(Date.UTC(yy, mm, 1)).toISOString().slice(0, 7);
      const firstDay = dayOf(month + '-01'), lastDay = dayOf(monthOf(y, m + 1) + '-01') - 1, now = dayOf(today);
      const first = firstDay - (weekday(firstDay) + 6) % 7, last = lastDay + 6 - (weekday(lastDay) + 6) % 7;
      const dated = visible.filter((t) => t.planned_start && t.planned_end && t.planned_start <= t.planned_end);
      const cal = h('div', { class: 'cal' }, h('div', { class: 'cal-head' }, ...['月', '火', '水', '木', '金', '土', '日'].map((w, i) => h('div', i >= 5 ? { class: 'off' } : {}, w))));
      for (let w = first; w <= last; w += 7) {
        const lanes = [];  // 重ならない帯は、同じ段に並べる
        const bars = dated.filter((t) => dayOf(t.planned_start) <= w + 6 && dayOf(t.planned_end) >= w)
          .sort((a, b) => a.planned_start.localeCompare(b.planned_start) || b.planned_end.localeCompare(a.planned_end) || a.number - b.number)
          .map((t) => {
            const from = Math.max(dayOf(t.planned_start), w), to = Math.min(dayOf(t.planned_end), w + 6);
            let lane = lanes.findIndex((l) => l.every(([a, b]) => to < a || from > b));
            if (lane < 0) { lane = lanes.length; lanes.push([]); }
            lanes[lane].push([from, to]);
            const late = open(t) && dayOf(t.planned_end) < now;
            const bar = at(h('div', { class: 'cal-bar ' + STAGE[marks.stageOf(t) === 'deleted' ? 'done' : marks.stageOf(t)][2] + (late ? ' late' : '') + (from > dayOf(t.planned_start) ? ' cut-start' : '')
              + (to < dayOf(t.planned_end) ? ' cut-end' : ''), tabindex: '0', title: '#' + t.number + ' ' + t.title + '（' + md(t.planned_start) + '〜' + md(t.planned_end) + '）' },
            marks.num(t), ' ' + t.title), 'grid-column:' + (from - w + 1) + ' / ' + (to - w + 2) + ';grid-row:' + (lane + 2));
            bar.setAttribute('aria-selected', String(isSelected(t)));
            return marks.pick(bar, t);
          });
        const week = at(h('div', { class: 'cal-week' }), 'grid-template-rows:24px repeat(' + lanes.length + ', 22px) minmax(26px, auto)');
        for (let i = 0; i < 7; i += 1) {
          const n = w + i, d = new Date(n * DAY), dues = visible.filter((t) => t.due && dayOf(t.due) === n);
          week.append(at(h('div', { class: 'cal-day' + (i >= 5 ? ' off' : '') + (n === now ? ' today' : '') + (n < firstDay || n > lastDay ? ' other' : '') }), 'grid-column:' + (i + 1)),
            at(h('div', { class: n === now ? 'cal-date today' : 'cal-date' }, (d.getUTCDate() === 1 ? (d.getUTCMonth() + 1) + '/' : '') + d.getUTCDate()), 'grid-column:' + (i + 1)));
          if (dues.length) {
            week.append(at(h('div', { class: 'cal-dues' }, ...dues.map((t) => {
              const due = h('div', { class: open(t) && t.due < today ? 'cal-due overdue' : 'cal-due', tabindex: '0', title: '期限 ' + md(t.due) + '：#' + t.number + ' ' + t.title }, '◆ ', marks.num(t), ' ' + t.title);
              due.setAttribute('aria-selected', String(isSelected(t)));
              return marks.pick(due, t);
            })), 'grid-column:' + (i + 1) + ';grid-row:' + (lanes.length + 2)));
          }
        }
        week.append(...bars);
        cal.append(week);
      }
      const move = (label, step, cls, title) => {
        const button = h('button', cls ? { type: 'button', class: cls } : { type: 'button' }, label);
        if (title) { button.title = title; button.setAttribute('aria-label', title); }
        button.addEventListener('click', () => { state.month = step ? monthOf(y, m + step) : ''; redraw(); });
        return button;
      };
      const undated = visible.filter((t) => !t.planned_start || !t.planned_end).length;
      return root.replaceChildren(tools(move('今月', 0), move('‹', -1, 'step', '前の月'), move('›', 1, 'step', '次の月'), h('strong', { class: 'month' }, y + '年' + (m + 1) + '月')), cal,
        legend(h('span', {}, h('i', { class: 'key late' }), '終了予定を過ぎている'),
          ...(undated ? [h('span', {}, '予定（開始・終了）のないタスク ' + undated + ' 件は、「横の帯」でドラッグして予定を付けられます')] : [])));
    }

    // --- 横の帯 ---
    const dated = visible.filter((t) => t.planned_start && t.planned_end).sort((a, b) => a.planned_start.localeCompare(b.planned_start) || a.number - b.number);
    const undated = visible.filter((t) => !t.planned_start || !t.planned_end).sort((a, b) => (open(a) === open(b) ? a.number - b.number : open(a) ? -1 : 1));
    const now = dayOf(today), tasks = [...dated, ...undated];
    const gap = undated.length ? 1 : 0, rowCount = tasks.length + gap;
    const all = tasks.flatMap((t) => [t.planned_start, t.planned_end, t.due].filter(Boolean)).map(dayOf).concat(now);
    let first = Math.min(...all), last = Math.max(...all, now + 20);
    first -= (weekday(first) + 6) % 7; last += 6 - (weekday(last) + 6) % 7;
    const days = Array.from({ length: last - first + 1 }, (_, i) => first + i), col = (n) => n - first + 2, off = (n) => weekday(n) === 0 || weekday(n) === 6;
    const rowSizes = [dated.length && 'repeat(' + dated.length + ', 34px)', gap && '28px repeat(' + undated.length + ', 34px)'].filter(Boolean).join(' ');
    const grid = at(h('div', { class: 'grid' }), 'grid-template-columns:' + LABEL_PX + 'px repeat(' + days.length + ', ' + DAY_PX + 'px);grid-template-rows:54px ' + rowSizes);
    grid.append(h('div', { class: 'corner' }, 'タスク'));
    for (const n of days) {
      const d = new Date(n * DAY);
      grid.append(at(h('div', { class: 'day' + (off(n) ? ' off' : '') + (n === now ? ' today' : '') },
        ...(d.getUTCDate() === 1 || n === first ? [h('b', {}, (d.getUTCMonth() + 1) + '月')] : []), h('span', {}, String(d.getUTCDate())), h('small', {}, WEEK[weekday(n)])), 'grid-column:' + col(n)));
    }
    if (tasks.length) for (const n of days.filter(off)) grid.append(at(h('div', { class: 'off-day' }), 'grid-column:' + col(n) + ';grid-row:2 / span ' + rowCount));
    const nowLine = at(h('div', { class: 'now' }), 'grid-column:' + col(now) + ';grid-row:1 / span ' + (rowCount + 1));
    grid.append(nowLine);
    const label = (t, r, extra) => {
      const node = at(h('div', { class: extra ? 'label ' + extra : 'label', tabindex: '0' }, marks.num(t), h('span', { class: 'grow' }, t.title)), 'grid-row:' + r);
      node.setAttribute('aria-selected', String(isSelected(t)));
      return marks.pick(node, t);
    };
    const dueMark = (t, r) => (t.due ? [at(h('div', { class: open(t) && t.due < today ? 'due overdue' : 'due', title: '期限 ' + md(t.due) }, '◆'), 'grid-row:' + r + ';grid-column:' + col(dayOf(t.due)))] : []);
    const save = (t, start, end) => emit('edit', { id: String(t.number), planned_start: start, planned_end: end });
    dated.forEach((t, i) => {
      const r = i + 2, late = open(t) && dayOf(t.planned_end) < now, key = marks.stageOf(t) === 'deleted' ? 'done' : marks.stageOf(t);
      const from = col(dayOf(t.planned_start)), to = col(dayOf(t.planned_end)) + 1;
      const grip = h('span', { class: 'grip', 'aria-hidden': 'true' });
      const bar = at(h('div', { class: 'bar ' + STAGE[key][2] + (late ? ' late' : '') + (isSelected(t) ? ' sel' : '') + (open(t) ? ' movable' : ''),
        title: md(t.planned_start) + '〜' + md(t.planned_end) + (open(t) ? '（ドラッグで移動、右端のドラッグで終了予定を変更）' : '') }, STAGE[key][1], grip), 'grid-row:' + r + ';grid-column:' + from + ' / ' + to);
      // ドラッグで動かす（右端は終了予定だけ）。動かさずに放したら、選ぶ
      bar.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        const drag = { x: event.clientX, days: 0, resize: event.target === grip };
        if (!open(t)) { state.drag = null; return; }
        state.drag = drag;
        try { bar.setPointerCapture(event.pointerId); } catch (error) { /* 作り物のポインター */ }
        bar.classList.add('dragging');
        bar.onpointermove = (moved) => {
          const n = Math.round((moved.clientX - drag.x) / DAY_PX);
          if (n === drag.days) return;
          drag.days = n;
          const start = drag.resize ? from : from + n, end = Math.max(start + 1, to + n);
          bar.style.gridColumn = start + ' / ' + end;
        };
      });
      bar.addEventListener('pointerup', () => {
        const drag = state.drag;
        state.drag = null; bar.onpointermove = null; bar.classList.remove('dragging');
        if (!drag || !drag.days) return emit('selected', { id: String(t.number) });
        const start = drag.resize ? t.planned_start : dateOf(dayOf(t.planned_start) + drag.days);
        let end = dateOf(dayOf(t.planned_end) + drag.days);
        if (end < start) end = start;
        save(t, start, end);
      });
      bar.addEventListener('contextmenu', (event) => { event.preventDefault(); marks.menu(event, t); });
      grid.append(label(t, r), bar, ...dueMark(t, r));
    });
    if (gap) {
      grid.append(at(h('div', { class: 'group' }, '日程なし'), 'grid-row:' + (dated.length + 2)),
        at(h('div', { class: 'group-line' }), 'grid-row:' + (dated.length + 2) + ';grid-column:2 / ' + (days.length + 2)));
    }
    undated.forEach((t, i) => {
      const r = dated.length + gap + i + 2, one = t.planned_start || t.planned_end;
      const empty = at(h('div', { class: open(t) ? 'empty plannable' : 'empty', title: open(t) ? 'ドラッグで予定（開始〜終了）を設定' : '閉じたタスク' }), 'grid-row:' + r + ';grid-column:2 / ' + (days.length + 2));
      if (open(t)) {
        // 予定のない行：日をまたいでドラッグすると、その間が予定になる（押すだけなら1日）
        const dayAt = (x) => { const box = grid.getBoundingClientRect(); return first + Math.max(0, Math.min(days.length - 1, Math.floor((x - box.left - LABEL_PX) / DAY_PX))); };
        empty.addEventListener('pointerdown', (event) => {
          if (event.button !== 0) return;
          event.preventDefault();
          const ghost = at(h('div', { class: 'ghost' }), 'grid-row:' + r);
          const plan = { from: dayAt(event.clientX), to: dayAt(event.clientX), ghost };
          const show = () => {
            const a = Math.min(plan.from, plan.to), b = Math.max(plan.from, plan.to);
            ghost.style.gridColumn = (a - first + 2) + ' / ' + (b - first + 3);
            ghost.textContent = md(dateOf(a)) + '〜' + md(dateOf(b));
          };
          show();
          grid.append(ghost);
          state.plan = plan;
          try { empty.setPointerCapture(event.pointerId); } catch (error) { /* 作り物のポインター */ }
          empty.onpointermove = (moved) => { const to = dayAt(moved.clientX); if (to !== plan.to) { plan.to = to; show(); } };
        });
        empty.addEventListener('pointerup', () => {
          const plan = state.plan;
          state.plan = null; empty.onpointermove = null;
          if (!plan) return;
          plan.ghost.remove();
          save(t, dateOf(Math.min(plan.from, plan.to)), dateOf(Math.max(plan.from, plan.to)));
        });
      }
      grid.append(label(t, r, 'undated'), empty,
        ...(one ? [at(h('div', { class: 'point', title: (t.planned_start ? '開始予定' : '終了予定') + 'だけ ' + md(one) }), 'grid-row:' + r + ';grid-column:' + col(dayOf(one)))] : []), ...dueMark(t, r));
    });
    const wrap = h('div', { class: 'wrap' }, grid);
    wrap.addEventListener('scroll', () => { state.left = wrap.scrollLeft; });
    root.replaceChildren(tools(), wrap, legend(h('span', {}, h('i', { class: 'key now' }), '今日'), h('span', {}, h('i', { class: 'key late' }), '終了予定を過ぎている')));
    // 初めは今日の少し前から。その後は、動かした位置のまま
    wrap.scrollLeft = typeof state.left === 'number' ? state.left : Math.max(0, nowLine.offsetLeft - LABEL_PX - 7 * DAY_PX);
  },
};
