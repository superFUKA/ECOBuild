// 部品「何行もの入力欄」。打つたびに changed。今の中身（text）が変わって届いたときだけ、その文字で描き直す
// （読み直しで同じ中身が届いても、打っている途中の文字は残す）。
export default {
  render(root, props, { h, emit }) {
    const text = props.text ?? '';
    if (props.error) {
      root.shownText = undefined;
      return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    }
    if (root.shownText === text && root.querySelector('textarea')) return;
    if (props.loading && !text) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    const area = h('textarea', { rows: props.rows, placeholder: props.placeholder, spellcheck: false,
      style: 'width:100%;box-sizing:border-box;resize:vertical;font-family:ui-monospace,monospace;line-height:1.5' });
    area.value = text;
    area.addEventListener('input', () => emit('changed', { text: area.value }));
    root.shownText = text;
    root.replaceChildren(h('label', {}, props.title, area));
  },
};
