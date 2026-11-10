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
    const list = h('dl', {});
    for (const item of props.items) {
      const value = props.data[item.key];
      const raw = value === null || value === undefined ? '' : typeof value === 'object' ? null : String(value);
      const tones = props.tones[item.key];
      const tone = tones && raw !== null && raw in tones ? tones[raw] : '';
      const text = show(item);
      list.append(h('dt', {}, item.label), h('dd', {}, tone && text !== '' ? h('span', { class: tone === 'plain' ? 'pill' : 'pill ' + tone }, text) : text));
    }
    root.replaceChildren(list);
  },
};
