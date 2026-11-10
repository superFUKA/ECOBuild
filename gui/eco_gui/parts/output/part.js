// 部品「出力」。届いた順に行を並べ、いちばん下が見えるようにする。
export default {
  render(root, props, { h }) {
    const box = h('pre', { tabindex: '0', role: 'log', style: 'margin:0;padding:.5rem;max-height:14rem;overflow:auto;'
      + 'background:var(--gf-surface);border:1px solid var(--gf-border);border-radius:var(--gf-radius);white-space:pre-wrap' });
    box.textContent = props.lines.length ? props.lines.join('\n') : props.empty_text;
    root.replaceChildren(box);
    box.scrollTop = box.scrollHeight;
  },
};
