// 部品「ボタン」。使えない・実行中は外側の包みが表す（この部品は知らない）。
export default {
  render(root, props, { h, emit }) {
    const button = h('button', { type: 'button' }, props.label);
    if (props.hint) button.title = props.hint;
    if (props.primary) button.style.cssText = 'background:var(--gf-accent);border-color:var(--gf-accent);color:var(--gf-bg)';
    button.addEventListener('click', () => emit('pressed', {}));
    root.replaceChildren(button);
  },
};
