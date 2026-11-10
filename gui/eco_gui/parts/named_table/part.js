// 部品「名前の付いたものの表」。辞書（名前 → 中身）を、届いた順のまま1行ずつ見せる。値の言い換えは見せ方だけ。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const names = Object.keys(props.entries);
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
      const entry = props.entries[name] || {};
      const on = name === props.current;
      const first = h('td', { style: cell + (on ? ';font-weight:600' : '') }, on ? `${name}（${props.current_mark}）` : name);
      const line = h('tr', { 'aria-current': String(on) }, first, ...props.columns.map((column) => h('td', { style: cell }, show(column, entry[column.key]))));
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
