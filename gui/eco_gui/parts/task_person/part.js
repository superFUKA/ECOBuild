// 部品「人の画面（上の部分）」。数は task workload のまま（なければ、渡されたタスクから数える見せ方）。行を選ぶと selected。
export default {
  render(root, props, { h, lib, emit, menu, open_url }) {
    const marks = lib.task.marks(h, emit, menu, [], props.me, open_url);
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
