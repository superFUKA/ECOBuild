// 部品「メニュー」。今の項目に印を付ける。
export default {
  render(root, props, { h, emit }) {
    const bar = h('div', { class: 'row', role: 'navigation', style: 'flex-wrap:wrap;border-bottom:1px solid var(--gf-border);padding-bottom:.5rem' });
    for (const item of props.items) {
      const on = item.id === props.current;
      const button = h('button', { type: 'button' }, item.label);
      if (on) {
        button.setAttribute('aria-current', 'page');
        button.style.cssText = 'border-color:var(--gf-accent);font-weight:600';
      }
      button.addEventListener('click', () => emit('selected', { id: item.id }));
      bar.append(button);
    }
    root.replaceChildren(bar);
  },
};
