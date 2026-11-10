// 部品「並びの入力欄」。今の並びを区切りでつないで入れておく。打つたびに changed（つないだ文字のまま）。
// 今の並び（items）が変わって届いたときだけ、その並びで描き直す（読み直しで同じ並びが届いても、打っている途中の文字は残す）。
export default {
  render(root, props, { h, emit }) {
    const text = (props.items ?? []).join(props.separator);
    if (root.shownText === text && root.querySelector('input')) return;
    const input = h('input', { type: 'text', value: text, placeholder: props.placeholder });
    input.addEventListener('input', () => emit('changed', { text: input.value }));
    root.shownText = text;
    root.replaceChildren(h('label', {}, props.title, input));
  },
};
