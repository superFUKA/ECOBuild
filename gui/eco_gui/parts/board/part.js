// 部品「ボード」。列に分けるのは見せ方だけ。移すのは、カードの「移す」の欄か、移せる列へのドラッグ（moved を出す）。
// どの列にも当てはまらないカードは、最後の列「そのほか」に出す。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.cards.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.cards.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const known = new Set(props.columns.map((column) => column.key));
    const groupOf = (card) => String(card[props.group] ?? '');
    const columns = [...props.columns];
    if (props.cards.some((card) => !known.has(groupOf(card)))) columns.push({ key: null, label: 'そのほか' });
    const labelOf = (key) => (props.columns.find((column) => column.key === key) || { label: key }).label;
    const text = (value) => (value === null || value === undefined ? '' : Array.isArray(value) ? value.join('、') : String(value));
    const board = h('div', { style: 'display:flex;gap:.6rem;align-items:flex-start;overflow-x:auto' });
    for (const column of columns) {
      const cards = props.cards.filter((card) => (column.key === null ? !known.has(groupOf(card)) : groupOf(card) === column.key));
      const box = h('section', { 'aria-label': column.label, style: 'flex:1 0 10rem;min-width:10rem;padding:.4rem;'
        + 'background:var(--gf-surface);border:1px solid var(--gf-border);border-radius:var(--gf-radius)' },
        h('div', { style: 'display:flex;justify-content:space-between;font-weight:600;margin-bottom:.4rem' },
          h('span', {}, column.label), h('small', { style: 'color:var(--gf-muted)' }, String(cards.length))));
      if (column.key !== null && props.moves.includes(column.key)) {  // 移せる列だけが、ドラッグを受ける
        box.addEventListener('dragover', (event) => event.preventDefault());
        box.addEventListener('drop', (event) => {
          event.preventDefault();
          const id = event.dataTransfer.getData('text/plain');
          const card = props.cards.find((item) => String(item[props.key]) === id);
          if (card && groupOf(card) !== column.key) emit('moved', { id, to: column.key });
        });
      }
      for (const card of cards) {
        const id = String(card[props.key]);
        const open = h('button', { type: 'button', style: 'border:0;background:transparent;padding:0;text-align:left;font-weight:600' },
          text(card[props.title]));
        open.addEventListener('click', () => emit('selected', { id }));
        const item = h('article', { draggable: 'true', style: 'display:flex;flex-direction:column;gap:.25rem;padding:.4rem;margin-bottom:.4rem;'
          + 'background:var(--gf-bg);border:1px solid var(--gf-border);border-radius:var(--gf-radius)' },
          h('small', { style: 'color:var(--gf-muted)' }, '#' + id), open);
        item.addEventListener('dragstart', (event) => event.dataTransfer.setData('text/plain', id));
        const facts = props.details.filter((detail) => text(card[detail.key]) !== '')
          .map((detail) => h('small', { style: 'color:var(--gf-muted)' }, detail.label + '：' + text(card[detail.key])));
        item.append(...facts);
        const targets = props.moves.filter((key) => key !== groupOf(card));
        if (targets.length) {
          const select = h('select', { 'aria-label': '#' + id + ' を移す' }, h('option', { value: '' }, '移す…'),
            ...targets.map((key) => h('option', { value: key }, labelOf(key))));
          select.addEventListener('change', () => { if (select.value) emit('moved', { id, to: select.value }); });
          item.append(select);
        }
        box.append(item);
      }
      board.append(box);
    }
    root.replaceChildren(board);
  },
};
