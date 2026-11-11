// 部品「ページの上のタブ」。左のメニューで選んだまとまりの中を、画面ごとに切り替える（今のタブに印）。
export default {
  render(root, props, { h, emit }) {
    const strip = h('div', { class: 'strip', role: 'tablist' });
    const shown = (props.items || []).filter((item) => !item.only || item.only === props.kind);
    for (const item of shown) {
      const on = item.id === props.current;
      const button = h('button', { type: 'button', role: 'tab' }, item.label);
      button.setAttribute('aria-selected', String(on));
      button.tabIndex = on || !shown.some((other) => other.id === props.current) ? 0 : -1;
      button.addEventListener('click', () => { if (!on) emit('selected', { id: item.id }); });
      strip.append(button);
    }
    strip.addEventListener('keydown', (event) => {  // 左右のキーで隣のタブへ
      const buttons = [...strip.querySelectorAll('button')];
      const at = buttons.indexOf(event.target);
      const next = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: buttons.length - 1 }[event.key];
      if (at < 0 || next === undefined) return;
      event.preventDefault();
      buttons[(next + buttons.length) % buttons.length].focus();
    });
    root.replaceChildren(strip);
  },
};
