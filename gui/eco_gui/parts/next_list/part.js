// 部品「次にやるものの並び」。順番も理由も、届いたとおりに見せる（並べ替えない）。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.items.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.items.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const text = (value) => (value === null || value === undefined ? '' : Array.isArray(value) ? value.join('、') : String(value));
    const list = h('ol', { style: 'margin:0;padding-left:1.6rem;display:flex;flex-direction:column;gap:.25rem' });
    const chip = 'padding:0 .4rem;border:1px solid var(--gf-border);border-radius:var(--gf-radius);font-size:.8rem';
    for (const item of props.items) {
      const task = item.task || {};
      const id = String(task.number ?? '');
      const open = h('button', { type: 'button', style: 'border:0;background:transparent;padding:0;text-align:left' }, `#${id} ${text(task.title)}`);
      open.addEventListener('click', () => emit('selected', { id }));
      const reasons = (item.reasons || []).map((reason) => h('span', { style: chip }, text(reason)));
      const facts = props.details.filter((detail) => text(task[detail.key]) !== '')
        .map((detail) => h('small', { style: 'color:var(--gf-muted)' }, detail.label + '：' + text(task[detail.key])));
      list.append(h('li', {}, h('div', { class: 'row', style: 'flex-wrap:wrap;align-items:baseline;gap:.5rem' }, open, ...reasons, ...facts)));
    }
    root.replaceChildren(list);
  },
};
