// 部品「文字」。
export default {
  render(root, props, { h }) {
    const style = props.heading ? 'margin:0;font-size:1.15rem;font-weight:600' : 'margin:0;white-space:pre-wrap';
    root.replaceChildren(h('p', { style }, props.text ? props.prefix + props.text : ''));
  },
};
