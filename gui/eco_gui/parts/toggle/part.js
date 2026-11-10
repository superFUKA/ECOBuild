// 部品「チェック」。
export default {
  render(root, props, { h, emit }) {
    const input = h('input', { type: 'checkbox', checked: props.on === true });
    input.addEventListener('change', () => emit('changed', { on: input.checked }));
    const label = h('label', { style: 'display:inline-flex;flex-direction:row;gap:.3rem;align-items:center' }, input, props.label);
    if (props.hint) label.title = props.hint;
    root.replaceChildren(label);
  },
};
