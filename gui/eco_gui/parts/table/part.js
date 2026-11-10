// 部品「表」。値の言い換え（labels）は見せ方だけ。行のボタンは action を出す。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const cell = 'text-align:left;padding:.35rem .6rem;border-bottom:1px solid var(--gf-border)';
    const show = (column, value) => {
      const names = props.labels[column.key] || {};
      const text = value === null || value === undefined ? '' : Array.isArray(value) ? value.join('、') : String(value);
      return text in names ? names[text] : text;
    };
    const head = h('tr', {}, ...props.columns.map((column) => h('th', { style: cell }, column.label)));
    if (props.actions.length) head.append(h('th', { style: cell }, ''));
    const body = h('tbody', {});
    for (const row of props.rows) {
      const line = h('tr', {}, ...props.columns.map((column) => h('td', { style: cell }, show(column, row[column.key]))));
      if (props.actions.length) {
        const buttons = props.actions.map((action) => {
          const button = h('button', { type: 'button' }, action.label);
          button.addEventListener('click', () => emit('action', { id: String(row[props.key]), action: action.name }));
          return button;
        });
        line.append(h('td', { style: cell }, h('div', { class: 'row' }, ...buttons)));
      }
      body.append(line);
    }
    root.replaceChildren(h('table', { style: 'border-collapse:collapse;width:100%' }, h('thead', {}, head), body));
  },
};
