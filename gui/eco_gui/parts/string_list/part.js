// 部品「文字の並び」。
export default {
  render(root, props, { h }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.items.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.items.length === 0) return root.replaceChildren(h('p', { role: 'status', style: 'color:var(--gf-muted);margin:0' }, props.empty_text));
    const list = h('ul', { tabindex: '0', style: 'margin:0;padding:0;list-style:none;max-height:16rem;overflow:auto' });
    props.items.forEach((text, index) => {
      const line = h('li', { style: 'padding:.3rem .6rem;border-bottom:1px solid var(--gf-border)' }, (props.numbered ? `${index}：` : '') + text);
      if (index === 0 && props.first_mark) line.append(h('small', { style: 'margin-left:.6rem;color:var(--gf-muted)' }, props.first_mark));
      list.append(line);
    });
    root.replaceChildren(list);
  },
};
