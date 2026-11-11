// 部品「スプリントの進み具合」。数は届いたまま（数えるのは ecobuild）。バーの幅・色は見せ方だけ。
export default {
  render(root, props, { h, lib, emit, menu }) {
    const { STAGES } = lib.task;
    const marks = lib.task.marks(h, emit, menu, props.sprints, props.me);
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
