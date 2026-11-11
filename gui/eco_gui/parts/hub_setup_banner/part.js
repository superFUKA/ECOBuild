// 部品「環境の案内の帯」。必須で足りない項目があるときだけ出す（どれが足りないかは ecobuild doctor の答え。ここは並べるだけ）。
export default {
  render(root, props, { h, emit }) {
    const missing = props.items.filter((item) => !item.ok && item.required);
    if (!missing.length) return root.replaceChildren();
    const button = h('button', { type: 'button' }, '準備する');
    button.addEventListener('click', () => emit('pressed', {}));
    root.replaceChildren(h('div', { class: 'setup', role: 'status' },
      h('div', {}, h('strong', {}, 'はじめに：開発の環境を準備してください'),
        h('small', {}, '足りないもの：' + missing.map((item) => item.name).join('、'))),
      button));
  },
};
