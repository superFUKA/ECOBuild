// 部品「確認」。はい・いいえを answered で出す。初めのフォーカスは「いいえ」（うっかり実行しない）。
export default {
  render(root, props, { h, emit }) {
    const no = h('button', { type: 'button' }, 'いいえ');
    const yes = h('button', { type: 'button' }, 'はい');
    no.addEventListener('click', () => emit('answered', { yes: false }));
    yes.addEventListener('click', () => emit('answered', { yes: true }));
    root.replaceChildren(
      h('p', { style: 'margin:.2rem 0' }, props.message),
      h('small', { style: 'display:block;white-space:pre-wrap;margin-bottom:.6rem' }, props.preview),
      h('div', { class: 'row' }, no, yes),
    );
  },
};
