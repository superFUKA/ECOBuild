// 部品「ボタン」。使えない・実行中は外側の包みが表す。入力の窓を開くボタンは、answer（{can, reason}）で灰色と理由にする。
export default {
  render(root, props, { h, emit }) {
    const button = h('button', { type: 'button' }, props.label);
    const off = props.answer && props.answer.can === false ? props.answer.reason || '今はできません' : '';
    if (props.hint || off) button.title = [props.hint, off ? '（' + off + '）' : ''].filter(Boolean).join('\n');
    if (off) button.disabled = true;
    button.className = props.primary ? 'primary' : props.danger ? 'danger' : props.quiet ? 'quiet' : '';
    button.addEventListener('click', () => emit('pressed', {}));
    root.replaceChildren(button);
  },
};
