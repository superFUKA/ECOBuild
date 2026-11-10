// 部品「名前の付いた組の表」。名前 → 中身の辞書を、名前の順に1行ずつ見せる。行のボタンは action を出す。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const names = Object.keys(props.data);
    if (props.loading && names.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (names.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const cell = 'text-align:left;padding:.35rem .6rem;border-bottom:1px solid var(--gf-border)';
    const show = (column, value) => {
      const words = props.labels[column.key] || {};
      const text = value === null || value === undefined ? '' : Array.isArray(value) ? value.join('、') : String(value);
      return text in words ? words[text] : text;
    };
    const head = h('tr', {}, h('th', { style: cell }, props.name_label), ...props.columns.map((column) => h('th', { style: cell }, column.label)));
    if (props.actions.length) head.append(h('th', { style: cell }, ''));
    const body = h('tbody', {});
    for (const name of names) {
      const values = props.data[name] || {};
      const line = h('tr', {}, h('td', { style: cell }, name), ...props.columns.map((column) => h('td', { style: cell }, show(column, values[column.key]))));
      if (props.actions.length) {
        const buttons = props.actions.map((action) => {
          const button = h('button', { type: 'button' }, action.label);
          button.addEventListener('click', () => emit('action', { id: name, action: action.name }));
          return button;
        });
        line.append(h('td', { style: cell }, h('div', { class: 'row' }, ...buttons)));
      }
      body.append(line);
    }
    root.replaceChildren(h('table', { style: 'border-collapse:collapse;width:100%' }, h('thead', {}, head), body));
  },
};
