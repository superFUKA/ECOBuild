// 部品「一覧から、いくつか選ぶ」。絞り込みの文字は、この部品の中だけの状態（描く先ごとに覚える）。
// 絞っても、選んだもの（checked）は変わらない。「見えているものを全部」「全部外す」も、選んだものを出すだけ。
const QUERY = new WeakMap();  // 描く先 → 絞り込みの文字

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status', style: 'color:var(--gf-muted);margin:0' }, props.empty_text));
    const all = props.rows.map((row) => String(row[props.value_key] ?? ''));
    const checked = new Set(props.checked);
    const send = () => emit('changed', { values: all.filter((value) => checked.has(value)) });
    const search = h('input', { type: 'search', value: QUERY.get(root) || '', placeholder: props.placeholder, 'aria-label': props.placeholder, style: 'flex:1' });
    const count = h('small', {}, '');
    const list = h('ul', { style: 'margin:0;padding:0;list-style:none;max-height:14rem;overflow:auto;gap:0;border:1px solid var(--gf-border);border-radius:var(--gf-radius)' });
    const shown = () => {
      const words = (QUERY.get(root) || '').toLowerCase().split(/\s+/).filter(Boolean);
      return props.rows.filter((row) => {
        const text = `${row[props.value_key] ?? ''} ${props.note_key ? row[props.note_key] ?? '' : ''}`.toLowerCase();
        return words.every((word) => text.includes(word));
      });
    };
    const draw = () => {
      const rows = shown();
      count.textContent = `${rows.length} / ${props.rows.length} 件（選んだもの ${checked.size}）`;
      if (rows.length === 0) return list.replaceChildren(h('li', { style: 'padding:.3rem .6rem;color:var(--gf-muted)' }, '当てはまるものはありません'));
      list.replaceChildren(...rows.map((row) => {
        const value = String(row[props.value_key] ?? '');
        const box = h('input', { type: 'checkbox', checked: checked.has(value) });
        box.addEventListener('change', () => { if (box.checked) checked.add(value); else checked.delete(value); send(); });
        const line = h('label', { style: 'display:flex;gap:.4rem;align-items:center;padding:.2rem .6rem' }, box, h('span', {}, value));
        const note = props.note_key ? row[props.note_key] : '';
        if (note && String(note) !== value) line.append(h('small', {}, String(note)));
        return h('li', {}, line);
      }));
    };
    search.addEventListener('input', () => { QUERY.set(root, search.value); draw(); });
    const every = h('button', { type: 'button' }, '見えているものを全部');
    every.addEventListener('click', () => { for (const row of shown()) checked.add(String(row[props.value_key] ?? '')); send(); });
    const none = h('button', { type: 'button' }, '全部外す');
    none.addEventListener('click', () => { checked.clear(); send(); });
    draw();
    root.replaceChildren(h('div', { style: 'display:grid;gap:.4rem' },
      h('div', { style: 'display:flex;gap:.5rem;align-items:center' }, search, every, none), count, list));
  },
};
