// 部品「タスクの一覧」。並べ替え・絞り込み・色分けは見せ方だけ。選ぶ・メニューは出力を出す。
export default {
  render(root, props, { h, lib, emit, menu, state, redraw, open_url }) {
    const { STAGES, PRIORITIES } = lib.task;
    const marks = lib.task.marks(h, emit, menu, props.sprints, props.me, open_url);
    // ほかの画面から開いたタスク：選んで、右に詳細を出す（窓を開いて1回だけ）
    if (props.pick && String(props.pick) !== '0' && state.picked !== String(props.pick)) {
      state.picked = String(props.pick);
      Promise.resolve().then(() => emit('selected', { id: state.picked }));
    }
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    if (props.loading && props.tasks.length === 0) return root.replaceChildren(marks.loading('タスクを読み込んでいます…'));
    const sort = state.sort || (state.sort = { key: 'number', dir: 1 });
    const tasks = props.filtered ? lib.task.filter(props.tasks, props.filter || props.start || {}, marks, props.me) : props.tasks;
    const keys = {
      number: (t) => t.number, title: (t) => t.title,
      stage: (t) => (marks.deleted(t) ? STAGES.length : STAGES.findIndex((s) => s[0] === marks.stageOf(t))),
      priority: (t) => (t.priority ? PRIORITIES.indexOf(t.priority) : 99), due: (t) => t.due || '9999',
      estimate: (t) => (t.estimate === null || t.estimate === undefined ? 1e9 : Number(t.estimate)),
      sprint: (t) => { const i = props.sprints.findIndex((s) => s.name === marks.sprintName(t)); return i < 0 ? 9999 : i; },
      assignee: (t) => (t.assignees || [])[0] || '￿',
    };
    const sorted = [...tasks].sort((a, b) => { const f = keys[sort.key], x = f(a), y = f(b); return (x < y ? -1 : x > y ? 1 : a.number - b.number) * sort.dir; });
    const parts = [];
    if (sorted.length) {
      const head = (key, label) => {
        const on = sort.key === key;
        const button = h('button', { type: 'button', class: on ? 'tk-sort on' : 'tk-sort' }, label, h('span', { 'aria-hidden': 'true' }, on ? (sort.dir > 0 ? '▲' : '▼') : ''));
        button.addEventListener('click', () => { state.sort = { key, dir: on ? -sort.dir : 1 }; redraw(); });
        return h('th', {}, button);
      };
      const columns = [['number', '#'], ['title', '題名'], ['stage', '状態'], ['priority', '優先度'], ['due', '期限'], ['estimate', '見積'], ['sprint', 'スプリント']];
      if (props.assignee) columns.push(['assignee', '担当']);
      const body = h('tbody', {});
      for (const t of sorted) {
        const row = h('tr', { tabindex: '0', class: marks.open(t) ? '' : 'closed' },
          h('td', { class: 'tk-num-cell' }, marks.num(t)), h('td', { class: 'tk-title-cell' }, t.title, ' ', ...marks.flags(t)),
          h('td', {}, marks.stageBadge(t)), h('td', {}, marks.prio(t)), h('td', {}, marks.due(t)), h('td', {}, marks.est(t)), h('td', {}, marks.sprintTag(t)));
        if (props.assignee) row.append(h('td', { class: 'tk-people' }, ...marks.avatars(t)));
        row.setAttribute('aria-selected', String(String(t.number) === String(props.selected || '')));
        body.append(marks.pick(row, t));
      }
      parts.push(h('table', { class: 'tk-table' }, h('thead', {}, h('tr', {}, ...columns.map((c) => head(c[0], c[1])))), body));
    } else {
      parts.push(h('p', { class: 'tk-empty', role: 'status' }, props.tasks.length ? '条件に合うタスクはありません。' : props.empty_text));
    }
    if (props.foot) {  // 片付けはめったにしない：一覧の下の、控えめなリンク
      const clean = h('button', { type: 'button', class: 'tk-link' }, '完了したタスクブランチを片付ける…');
      clean.addEventListener('click', () => emit('dialog', { screen: 'task-clean', id: '0', text: '' }));
      parts.push(h('div', { class: 'foot' }, clean));
    }
    root.replaceChildren(...parts);
  },
};
