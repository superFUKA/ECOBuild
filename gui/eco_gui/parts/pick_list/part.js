// 部品「文字の並びから選ぶ」。行を押すと、その番号（0 から）を出す。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.items.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.items.length === 0) return root.replaceChildren(h('p', { role: 'status', style: 'color:var(--gf-muted);margin:0' }, props.empty_text));
    const list = h('ul', { role: 'listbox', style: 'margin:0;padding:0;list-style:none;max-height:16rem;overflow:auto;gap:0' });
    props.items.forEach((text, index) => {
      const on = index === props.selected;
      const line = h('button', { type: 'button', role: 'option', 'aria-selected': String(on),
        style: 'width:100%;text-align:left;border:0;border-bottom:1px solid var(--gf-border);border-radius:0;padding:.3rem .6rem;background:transparent' },
        (props.numbered ? `${index}：` : '') + text);
      if (on) line.style.fontWeight = '600';
      if (on) line.style.background = 'var(--gf-surface)';
      line.addEventListener('click', () => emit('selected', { index }));
      list.append(h('li', {}, line));
    });
    root.replaceChildren(list);
  },
};
