// 部品「名前と値の組」。値の言い換え（labels）は見せ方だけ。
export default {
  render(root, props, { h }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && Object.keys(props.data).length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    const show = (item) => {
      const value = props.data[item.key];
      const text = value === null || value === undefined ? '' : Array.isArray(value) ? value.join('、') : String(value);
      const names = props.labels[item.key] || {};
      return text in names ? names[text] : text;
    };
    const list = h('dl', { style: 'display:grid;grid-template-columns:max-content 1fr;gap:.3rem 1rem;margin:0' });
    for (const item of props.items) {
      list.append(h('dt', { style: 'color:var(--gf-muted)' }, item.label), h('dd', { style: 'margin:0' }, show(item)));
    }
    root.replaceChildren(list);
  },
};
