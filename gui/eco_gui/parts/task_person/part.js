// 部品「人の画面（上の部分）」。数は task workload のまま（なければ、渡されたタスクから数える見せ方）。行を選ぶと selected。
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

export default {
  render(root, props, { h, emit, menu }) {
    const marks = taskMarks(h, emit, menu, [], props.me);
    const who = props.who;
    const close = h('button', { type: 'button', class: 'd-close', title: '閉じる', 'aria-label': '閉じる' }, '×');
    close.addEventListener('click', () => emit('closed', {}));
    const head = h('header', { class: 'pf-head' }, marks.avatarMark(who),
      h('div', { class: 'pf-name' }, who, ...(who === props.me ? [h('span', { class: 'tk-pill ok' }, '自分')] : [])), close);
    if (props.error) return root.replaceChildren(head, marks.failed(props.error));
    if (props.loading && props.tasks.length === 0) return root.replaceChildren(head, marks.loading());
    const w = props.workload.find((x) => x.assignee === who) || null;
    // 作業中は task workload と同じ数え方：親タスクは数えない（子が数えられる）
    const ts = props.tasks.filter((t) => marks.open(t) && (t.assignees || []).includes(who));
    const doing = ts.filter((t) => !t.subtasks && ['in_progress', 'in_review'].includes(marks.stageOf(t)));
    const own = props.submitted.filter((t) => (t.assignees || []).includes(who));
    const stat = (label, value, cls) => h('div', { class: cls ? 'tk-pf-stat ' + cls : 'tk-pf-stat' }, h('b', {}, String(value)), h('span', {}, label));
    const pickRow = (t, ...marksOf) => {
      const row = h('div', { class: 'row', tabindex: '0' }, marks.num(t), h('span', { class: 'grow' }, t.title), ...marksOf);
      row.addEventListener('click', () => emit('selected', { id: String(t.number) }));
      row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); emit('selected', { id: String(t.number) }); } });
      return row;
    };
    const section = (title, rows) => h('section', { class: 'pf-section' }, h('h4', {}, title), ...(rows.length ? rows : [h('p', { class: 'tk-muted' }, 'ありません')]));
    root.replaceChildren(head,
      h('div', { class: 'tk-pf-stats' }, stat('担当（親を除く）', w ? w.open : ts.length), stat('作業中（親を除く）', w ? w.in_progress : doing.length),
        stat('残りの見積もり', w ? w.estimate_remaining : '-'), stat('期限切れ', w ? w.overdue : 0, w && w.overdue ? 'bad' : ''), stat('提出中', own.length)),
      h('div', { class: 'pf-grid' }, section('作業中', doing.map((t) => pickRow(t, marks.stageBadge(t), marks.due(t)))),
        section('提出', own.map((t) => pickRow(t, marks.submissionPill(t.submission || {})))),
        ...(who === props.me ? [section('見るように頼まれた提出', props.reviews.map((t) => pickRow(t, marks.submissionPill(t.submission || {}))))] : [])),
      h('h4', { class: 'pf-tasks' }, '担当タスク'));
  },
};
