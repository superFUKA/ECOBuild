// 部品「入力欄」。打つたびに changed、Enter で submitted。
// 欄は作り直さない（打っている途中の文字・変換・カーソルを残す）。届いた文字（text）が前と変わったときだけ、欄に入れる：
// 自分が出した文字が戻ってきただけ（text を共有の値に結んだとき）なら何もしない。外から変わった（保存の後に空に戻す等）なら、その文字にする。
export default {
  render(root, props, { h, emit }) {
    let input = root.querySelector('input');
    if (!input) {
      input = h('input', { type: 'text' });
      input.gfSent = [];  // 出した文字のうち、まだ表示として戻ってきていないもの
      input.addEventListener('input', () => {
        input.gfSent.push(input.value);
        if (input.gfSent.length > 50) input.gfSent.shift();
        emit('changed', { text: input.value });
      });
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.isComposing) emit('submitted', { text: input.value });
      });
      root.replaceChildren(h('label', {}, h('span', {}, props.title), input));
    }
    root.querySelector('span').textContent = props.title;
    input.placeholder = props.placeholder;
    if (props.text === input.gfText) return;  // 文字は変わっていない（ほかの要る情報だけが変わった）
    input.gfText = props.text;
    const echo = input.gfSent.indexOf(props.text);
    if (props.text === input.value) input.gfSent = [];  // 追いついた
    else if (echo >= 0) input.gfSent.splice(0, echo + 1);  // 少し前に出した文字が戻ってきた（その後も打っている）
    else {  // 外から変わった
      input.value = props.text;
      input.gfSent = [];
    }
  },
};
