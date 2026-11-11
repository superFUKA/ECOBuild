// 部品「スプリントの進み具合」。数は届いたまま（数えるのは ecobuild）。バーの幅・色は見せ方だけ。
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
    const marks = taskMarks(h, emit, menu, props.sprints, props.me);
    const { md } = marks;
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    const s = props.status;
    if (!s && props.loading) return root.replaceChildren(marks.loading('スプリントを確認しています…'));
    if (!props.sprints.length && !s) return root.replaceChildren(h('p', { class: 'tk-empty', role: 'status' }, 'スプリントはまだありません。'));
    const shown = s ? s.sprint.name : '';
    const select = h('select', { 'aria-label': 'スプリント' });
    if (!s) select.append(h('option', { value: '' }, '選んでください'));
    for (const sprint of props.sprints) {
      const option = h('option', { value: sprint.name }, sprint.name + '（' + md(sprint.start) + '〜' + md(sprint.end) + '）' + (sprint.name === marks.currentSprint ? ' ・今' : ''));
      if (sprint.name === shown) option.selected = true;
      select.append(option);
    }
    select.addEventListener('change', () => { if (select.value) emit('chosen', { name: select.value }); });
    const pick = h('label', { class: 'pick' }, 'スプリント ', select);
    if (!s) return root.replaceChildren(h('div', { class: 'bar' }, pick), h('p', { class: 'tk-empty', role: 'status' }, '今日を含むスプリントはありません。上で選べます。'));

    const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
    const byNumber = (n) => props.tasks.find((t) => t.number === n) || (s.tasks || []).find((t) => t.number === n);
    const numberOf = (x) => (typeof x === 'number' ? x : x.number);
    const stat = (label, value, cls) => h('div', { class: cls ? 'tk-pf-stat ' + cls : 'tk-pf-stat' }, h('b', {}, String(value)), h('span', {}, label));
    const list = (title, xs) => {
      if (!xs.length) return [];
      return [h('p', { class: 'tk-note' }, title + '：', ...xs.map(numberOf).map((n) => {
        const tag = h('button', { type: 'button', class: 'tag' }, '#' + n + ' ' + ((byNumber(n) || {}).title || ''));
        tag.addEventListener('click', () => emit('selected', { id: String(n) }));
        return tag;
      }))];
    };
    const stages = s.stages || {}, unestimated = s.unestimated || [], carried = s.carried_over || [];
    const counts = STAGES.filter(([k]) => stages[k]).map(([k, label]) => marks.stageMark(k, label + ' ' + stages[k]));
    const card = h('section', { class: 'tk-card' },
      h('div', { class: 'tk-section-head' }, h('h3', {}, s.sprint.name, h('span', { class: 'tk-muted' }, md(s.sprint.start) + '〜' + md(s.sprint.end) + (s.current ? '・残り ' + s.days_left + ' 日' : ''))), pick));
    if (counts.length) card.append(h('div', { class: 'tk-stagekeys stages' }, ...counts));
    if (s.total) {
      const fill = h('span', {});
      fill.setAttribute('style', 'width:' + (pct(s.estimate_done, s.estimate_total) || pct(s.done, s.total)) + '%');
      card.append(h('div', { class: 'tk-pf-stats' }, stat('完了 / 全体', s.done + ' / ' + s.total), stat('見積もりの残り', s.estimate_remaining), stat('見積もりの合計', s.estimate_total),
        stat('見積もりなし', unestimated.length, unestimated.length ? 'warn' : '')),
      h('div', { class: 'tk-progress', title: '完了した見積もり ' + s.estimate_done + ' / ' + s.estimate_total }, fill),
      ...list('見積もりのないタスク', unestimated), ...list('前のスプリントからの持ち越し', carried));
    } else {
      card.append(h('p', { class: 'tk-note' }, (s.tasks || []).length ? 'このスプリントに、数えるタスクはありません。親タスクは数えません。'
        : 'このスプリントのタスクはありません。タスクの詳細か右クリックメニューで、スプリントに入れられます。'));
    }
    root.replaceChildren(card);
  },
};
