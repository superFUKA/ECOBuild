// 部品「次にやる」。並びと理由は届いたまま（決めるのは ecobuild）。色と印は見せ方だけ。
export default {
  render(root, props, { h, lib, emit, menu, open_url }) {
    const marks = lib.task.marks(h, emit, menu, props.sprints, props.me, open_url);
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    const mine = ((props.filter || props.start || {}).assignee || '') === '@me';
    const items = mine ? props.mine : props.next;
    if (props.loading && items.length === 0) return root.replaceChildren(marks.loading('次にやるタスクを確認しています…'));
    const row = (t, ...extra) => {
      const line = h('div', { class: 'tk-next-row', tabindex: '0' }, marks.num(t), h('span', { class: 'tk-grow' }, t.title), ...extra,
        marks.prio(t), marks.due(t), marks.est(t), marks.sprintTag(t), ...marks.avatars(t));
      line.setAttribute('aria-selected', String(String(t.number) === String(props.selected || '')));
      return marks.pick(line, t);
    };
    const head = (title, sub) => h('div', { class: 'tk-section-head' }, h('h3', {}, title, ...(sub ? [h('span', { class: 'tk-muted' }, sub)] : [])));
    const late = props.overdue.overdue || [], soon = props.overdue.soon || [];
    const parts = [h('section', { class: 'tk-card' }, head('次にやるタスク', mine ? '自分の担当' : ''),
      ...(items.length ? items.map((x, i) => row(x.task, h('span', { class: 'tk-rank' }, String(i + 1)), ...(x.reasons || []).map((r) => h('span', { class: 'tk-reason' }, r))))
        : [h('p', { class: 'tk-muted' }, '着手できるタスクはありません。')]))];
    // 期限の並びは、あるときだけ。どちらもなければ、1行で言う
    if (late.length) parts.push(h('section', { class: 'tk-card' }, head('期限切れ', late.length + ' 件'), ...late.map((t) => row(t))));
    if (soon.length) parts.push(h('section', { class: 'tk-card' }, head('期限が近い', '7日以内'), ...soon.map((t) => row(t))));
    if (!late.length && !soon.length) parts.push(h('p', { class: 'tk-muted none' }, '期限切れ・期限が近い（7日以内）タスクはありません。'));
    root.replaceChildren(...parts);
  },
};
