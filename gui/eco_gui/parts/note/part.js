// 部品「文字」。見出し・補足・節の見出し・帯（注意・誤り）。文字がなければ何も出さない。
export default {
  render(root, props, { h }) {
    const text = props.text ? props.prefix + props.text : '';
    if (!text) return root.replaceChildren();
    if (props.heading) return root.replaceChildren(h('h2', {}, text));
    if (props.tone === 'section') return root.replaceChildren(h('h3', {}, text));
    if (props.tone === 'warn' || props.tone === 'bad') {
      return root.replaceChildren(h('div', { class: props.tone === 'bad' ? 'banner bad' : 'banner', role: 'status' }, h('span', {}, text)));
    }
    root.replaceChildren(h('p', { class: props.tone === 'muted' ? 'text muted' : 'text' }, text));
  },
};
