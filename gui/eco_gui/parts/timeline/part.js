// 部品「日程の帯」。日付を軸に並べるのは見せ方だけ（値は変えない）。帯のある行が先、日付のない行は後ろ。
const DAY = 86400000;
const dayOf = (date) => Math.round(Date.parse(date + 'T00:00:00Z') / DAY);
const WEEK = ['日', '月', '火', '水', '木', '金', '土'];

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const date = (row, name) => (typeof row[name] === 'string' && !Number.isNaN(dayOf(row[name])) ? row[name] : '');
    const planned = (row) => date(row, props.start) !== '' && date(row, props.end) !== '' && date(row, props.start) <= date(row, props.end);
    const rows = [...props.rows.filter(planned).sort((a, b) => date(a, props.start).localeCompare(date(b, props.start))),
      ...props.rows.filter((row) => !planned(row))];
    const now = new Date();
    const today = Math.round(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / DAY);
    const days = rows.flatMap((row) => [props.start, props.end, props.due].map((name) => date(row, name)).filter(Boolean).map(dayOf));
    const first = Math.min(today, ...days) - 1;
    const count = Math.min(Math.max(today + 14, ...days) + 1 - first + 1, 400);  // 長すぎる軸は、400 日で切る
    const column = (day) => day - first + 2;
    const inside = (day) => day >= first && day < first + count;
    const grid = h('div', { style: `display:grid;grid-template-columns:14rem repeat(${count}, 1.5rem);align-items:center;row-gap:.2rem;min-width:max-content` });
    for (let index = 0; index < count; index += 1) {
      const at = new Date((first + index) * DAY);
      const off = at.getUTCDay() === 0 || at.getUTCDay() === 6;
      const on = first + index === today;
      grid.append(h('div', { style: `grid-row:1;grid-column:${index + 2};text-align:center;font-size:.7rem;line-height:1.1;`
        + `color:var(${on ? '--gf-accent' : '--gf-muted'});${off ? 'opacity:.6;' : ''}${on ? 'font-weight:700;' : ''}` },
        h('div', {}, at.getUTCDate() === 1 || index === 0 ? `${at.getUTCMonth() + 1}月` : ' '),
        h('div', {}, String(at.getUTCDate())), h('div', {}, WEEK[at.getUTCDay()])));
    }
    rows.forEach((row, index) => {
      const line = index + 2;
      const id = String(row[props.key]);
      const label = h('button', { type: 'button', title: String(row[props.title] ?? ''), style: `grid-row:${line};grid-column:1;border:0;background:transparent;`
        + 'padding:.1rem .3rem;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis' }, `#${id} ${row[props.title] ?? ''}`);
      label.addEventListener('click', () => emit('selected', { id }));
      grid.append(label);
      if (inside(today)) {
        grid.append(h('div', { style: `grid-row:${line};grid-column:${column(today)};align-self:stretch;border-left:2px solid var(--gf-accent);opacity:.5` }));
      }
      if (planned(row)) {
        const from = Math.max(dayOf(date(row, props.start)), first);
        const to = Math.min(dayOf(date(row, props.end)), first + count - 1);
        if (from <= to) {
          grid.append(h('div', { title: `${date(row, props.start)}〜${date(row, props.end)}`,
            style: `grid-row:${line};grid-column:${column(from)} / ${column(to) + 1};height:1.1rem;background:var(--gf-accent);opacity:.75;border-radius:var(--gf-radius)` }));
        }
      }
      const due = date(row, props.due);
      if (due && inside(dayOf(due))) {
        grid.append(h('div', { title: `期限 ${due}`,
          style: `grid-row:${line};grid-column:${column(dayOf(due))};text-align:center;color:var(--gf-danger);z-index:1` }, '◆'));
      }
    });
    const legend = h('p', { style: 'margin:.4rem 0 0;color:var(--gf-muted);font-size:.8rem' }, '帯：開始予定〜終了予定　◆：期限　縦の線：今日');
    root.replaceChildren(h('div', { tabindex: '0', style: 'overflow:auto;max-height:26rem' }, grid), legend);
  },
};
