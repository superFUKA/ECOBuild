// 部品「数の入力欄」。今の数を入れておく。打つたびに changed（打った文字のまま）。
// 今の数（value）が変わって届いたときだけ、その数で描き直す（読み直しで同じ数が届いても、打っている途中の文字は残す）。
export default {
  render(root, props, { h, emit }) {
    const text = props.value === null || props.value === undefined ? '' : String(props.value);
    if (root.shownText === text && root.querySelector('input')) return;
    const input = h('input', { type: 'text', inputmode: 'decimal', value: text, placeholder: props.placeholder, style: 'max-width:10rem' });
    input.addEventListener('input', () => emit('changed', { text: input.value }));
    root.shownText = text;
    root.replaceChildren(h('label', {}, props.title, input));
  },
};
