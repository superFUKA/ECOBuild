// 部品「1行選べる表」。値の言い換え（labels）・時刻の書き方（format）は見せ方だけ。
const at = (row, path) => String(path).split('.').reduce((value, step) => (value === null || value === undefined ? undefined : value[step]), row);
const two = (number) => String(number).padStart(2, '0');
const time = (value) => {
  if (value === null || value === undefined || value === '') return '';
  const date = new Date(typeof value === 'number' ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())} ${two(date.getHours())}:${two(date.getMinutes())}`;
};

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const cell = 'text-align:left;padding:.35rem .6rem;border-bottom:1px solid var(--gf-border)';
    const show = (column, value) => {
      if (column.format === 'time') return time(value);
      const names = props.labels[column.key] || {};
      const text = value === null || value === undefined ? '' : Array.isArray(value) ? value.join('、') : String(value);
      return text in names ? names[text] : text;
    };
    const head = h('tr', {});
    if (props.selectable) head.append(h('th', { style: cell }, ''));
    head.append(...props.columns.map((column) => h('th', { style: `${cell};white-space:nowrap` }, column.label)));
    if (props.actions.length) head.append(h('th', { style: cell }, ''));
    const body = h('tbody', {});
    for (const row of props.rows) {
      const id = String(row[props.key]);
      const chosen = props.selectable && id === props.selected;
      const line = h('tr', chosen ? { 'aria-selected': 'true', style: 'background:var(--gf-border)' } : {});
      if (props.selectable) {
        const pick = h('input', { type: 'radio', checked: chosen, 'aria-label': `${id} を選ぶ` });
        pick.addEventListener('change', () => emit('selected', { id, row }));
        line.append(h('td', { style: cell }, pick));
      }
      line.append(...props.columns.map((column) => h('td', { style: column.format === 'time' ? `${cell};white-space:nowrap` : cell },
        show(column, at(row, column.key)))));
      if (props.actions.length) {
        const buttons = props.actions.map((action) => {
          const button = h('button', { type: 'button' }, action.label);
          button.addEventListener('click', () => emit('action', { id, action: action.name }));
          return button;
        });
        line.append(h('td', { style: cell }, h('div', { class: 'row' }, ...buttons)));
      }
      body.append(line);
    }
    root.replaceChildren(h('table', { style: 'border-collapse:collapse;width:100%' }, h('thead', {}, head), body));
  },
};
