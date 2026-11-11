// 部品「日程」。横の帯（どのタスクも1行。予定のあるものは帯、ないものは下にまとめる）か、月のカレンダー。
// 表示の切り替えは、この PC に覚える。帯のドラッグは、放したときに edit（開始予定・終了予定）を出すだけ。
const DAY = 86400000, DAY_PX = 28, LABEL_PX = 220;
const WEEK = ['日', '月', '火', '水', '木', '金', '土'];
const dayOf = (d) => Date.parse(d + 'T00:00:00Z') / DAY;
const weekday = (n) => new Date(n * DAY).getUTCDay();
const dateOf = (n) => new Date(n * DAY).toISOString().slice(0, 10);

export default {
  render(root, props, { h, lib, emit, menu, state, memory, redraw }) {
    const { STAGE } = lib.task;
    const marks = lib.task.marks(h, emit, menu, props.sprints, props.me);
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    if (props.loading && props.tasks.length === 0) return root.replaceChildren(marks.loading('タスクを読み込んでいます…'));
    const { md, today, open } = marks;
    const visible = lib.task.filter(props.tasks, props.filter || props.start || {}, marks, props.me);
    const mode = memory.get('mode', 'bars') === 'calendar' ? 'calendar' : 'bars';
    const isSelected = (t) => String(t.number) === String(props.selected || '');
    const at = (node, style) => { node.setAttribute('style', style); return node; };
    // 帯の色と名前：段階のもの（削除済みは完了と同じ色。段階が届いていなければ、色なし）
    const stageKey = (t) => STAGE[marks.stageOf(t) === 'deleted' ? 'done' : marks.stageOf(t)] || null;
    const stageClass = (t) => (stageKey(t) ? stageKey(t)[2] : '');

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
            const bar = at(h('div', { class: 'cal-bar ' + stageClass(t) + (late ? ' late' : '') + (from > dayOf(t.planned_start) ? ' cut-start' : '')
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
      const r = i + 2, late = open(t) && dayOf(t.planned_end) < now, stage = stageKey(t);
      const from = col(dayOf(t.planned_start)), to = col(dayOf(t.planned_end)) + 1;
      const grip = h('span', { class: 'grip', 'aria-hidden': 'true' });
      const bar = at(h('div', { class: 'bar ' + stageClass(t) + (late ? ' late' : '') + (isSelected(t) ? ' sel' : '') + (open(t) ? ' movable' : ''),
        title: md(t.planned_start) + '〜' + md(t.planned_end) + (open(t) ? '（ドラッグで移動、右端のドラッグで終了予定を変更）' : '') }, stage ? stage[1] : '', grip), 'grid-row:' + r + ';grid-column:' + from + ' / ' + to);
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
