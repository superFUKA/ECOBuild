// 部品「オペレーターへの入力欄」。Enter で送る・Shift+Enter で改行（変換中の Enter は送らない）。今までの GUI と同じ。
// 欄は描き直しても作り直さない（打っている途中の文字を残す）。
export default {
  render(root, props, { h, emit }) {
    let area = root.querySelector('textarea');
    if (area) { area.placeholder = props.placeholder; return; }
    area = h('textarea', { rows: 2, placeholder: props.placeholder, 'aria-label': props.label });
    const send = () => {
      const text = area.value;
      if (!text.trim()) return;
      area.value = '';
      emit('sent', { text });
    };
    const form = h('form', {}, area, h('button', { type: 'submit', class: 'primary' }, '送る'));
    form.addEventListener('submit', (event) => { event.preventDefault(); send(); });
    area.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(); }
    });
    root.replaceChildren(form);
  },
};
