// 部品「ボード」。段階ごとの列に分けるのは見せ方だけ。カードを別の列へ落とすと、その列に合う入力を出す：
// 計画中・未着手＝段階を変える（edit）、作業中＝開始の窓、完了＝完了の窓（タスクブランチがなければ close）、削除済み＝削除（remove）。
// 落としても何も起きない列（レビュー待ち・今と同じ列・タスクブランチのあるタスクの未着手 等）は、落とす先にならない。
const RECENT_DONE = 15;

export default {
  render(root, props, { h, lib, emit, menu, state }) {
    const { STAGES } = lib.task;
    const marks = lib.task.marks(h, emit, menu, props.sprints, props.me);
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    if (props.loading && props.tasks.length === 0) return root.replaceChildren(marks.loading('タスクを読み込んでいます…'));
    const f = props.filter || props.start || {};
    const visible = lib.task.filter(props.tasks, f, marks, props.me);
    const newestDone = (a, b) => String(b.finished || '').localeCompare(String(a.finished || '')) || b.number - a.number;
    // 完了の列：「完了したタスクも表示」でなければ、最近完了したものだけ（task list --all から）
    let closed = null;
    if (f.closed !== true) {
      const source = f.deleted === true ? props.tasks : props.recent;
      closed = lib.task.filter(source.filter((t) => !marks.open(t) && !marks.deleted(t)), { ...f, closed: true }, marks, props.me).sort(newestDone).slice(0, RECENT_DONE);
    }
    const byNumber = (n) => props.tasks.find((t) => String(t.number) === n) || props.recent.find((t) => String(t.number) === n);
    // カードをその列へ落としたときに出す入力（なければ、落とす先にならない）
    const dropOf = (t, stage) => {
      const id = String(t.number), has = Boolean(t.task_branch || t.current), now = marks.stageOf(t);
      if (now === stage) return null;
      if (!marks.open(t)) return stage === 'todo' || stage === 'planned' ? ['reopen', { id }] : null;
      if (stage === 'done') return has || t.remote ? ['dialog', { screen: 'task-complete', id, text: '' }] : ['close', { id }];
      if (stage === 'deleted') return ['remove', { id }];
      if (stage === 'in_progress') return has ? null : ['dialog', { screen: 'task-start', id, text: '' }];
      if (stage === 'in_review') return null;
      return has || t.remote ? null : ['edit', { id, stage }];
    };
    const columns = [...STAGES.map((s) => [s[0], s[1]]), ...(f.deleted === true ? [['deleted', '削除済み']] : [])];
    const board = h('div', { class: f.deleted === true ? 'kanban with-deleted' : 'kanban' });
    for (const [key, label] of columns) {
      const cards = key === 'done' && closed ? closed : visible.filter((t) => marks.stageOf(t) === key);
      if (key === 'done') cards.sort(newestDone);
      const count = key === 'done' && closed ? h('small', { title: '「完了したタスクも表示」ですべて表示' }, '最近 ' + cards.length) : h('small', {}, String(cards.length));
      const list = h('div', { class: 'cards' });
      const column = h('section', { class: 'column', 'aria-label': label }, h('div', { class: 'column-head' }, h('span', {}, marks.stageMark(key)), count), list);
      column.dataset.stage = key;
      column.addEventListener('dragover', (event) => {
        const t = state.dragged && byNumber(state.dragged);
        if (!t || !dropOf(t, key)) return;
        event.preventDefault();
        column.classList.add('drop');
      });
      column.addEventListener('dragleave', (event) => { if (!column.contains(event.relatedTarget)) column.classList.remove('drop'); });
      column.addEventListener('drop', (event) => {
        column.classList.remove('drop');
        const t = state.dragged && byNumber(state.dragged);
        const out = t && dropOf(t, key);
        state.dragged = null;
        if (!out) return;
        event.preventDefault();
        emit(out[0], out[1]);
      });
      for (const t of cards) {
        const card = h('article', { class: 'kcard', draggable: 'true', tabindex: '0' },
          h('div', { class: 'kcard-title' }, t.title),
          h('div', { class: 'kcard-foot' },
            h('div', { class: 'kcard-meta' }, marks.num(t), marks.prio(t), marks.est(t), marks.sprintTag(t), marks.due(t), ...marks.flags(t)),
            marks.avatar((t.assignees || [])[0])));
        card.setAttribute('aria-selected', String(String(t.number) === String(props.selected || '')));
        card.addEventListener('dragstart', (event) => {
          state.dragged = String(t.number);
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', '#' + t.number);
          card.classList.add('dragging');
        });
        card.addEventListener('dragend', () => { card.classList.remove('dragging'); state.dragged = null; });
        list.append(marks.pick(card, t));
      }
      board.append(column);
    }
    root.replaceChildren(board);
  },
};
