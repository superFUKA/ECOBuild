// 部品「長い文字」。差分の行（+ と -）には色を付ける（見せ方だけ）。
export default {
  render(root, props, { h }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && !props.text) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (!props.text) return root.replaceChildren(h('p', { role: 'status', style: 'color:var(--gf-muted);margin:0' }, props.empty_text));
    const box = h('pre', { tabindex: '0', style: 'margin:0;padding:.5rem;max-height:20rem;overflow:auto;'
      + 'background:var(--gf-surface);border:1px solid var(--gf-border);border-radius:var(--gf-radius)' });
    for (const line of props.text.split('\n')) {
      const row = h('div', {}, line || ' ');
      if (line.startsWith('+') && !line.startsWith('+++')) row.style.color = 'var(--gf-accent)';
      if (line.startsWith('-') && !line.startsWith('---')) row.style.color = 'var(--gf-danger)';
      box.append(row);
    }
    root.replaceChildren(box);
  },
};
