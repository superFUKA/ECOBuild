// 部品「入力欄」。打つたびに changed、Enter で submitted。
export default {
  render(root, props, { h, emit }) {
    const input = h('input', { type: 'text', value: props.text, placeholder: props.placeholder });
    input.addEventListener('input', () => emit('changed', { text: input.value }));
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.isComposing) emit('submitted', { text: input.value });
    });
    root.replaceChildren(h('label', {}, props.title, input));
  },
};
