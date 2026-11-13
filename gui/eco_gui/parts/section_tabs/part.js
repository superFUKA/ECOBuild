// 部品「ページの上のタブ」。左のメニューで選んだまとまりの中を、画面ごとに切り替える（今のタブに印）。
export default {
  render(root, props, { h, emit, memory, state }) {
    const strip = h('div', { class: 'strip', role: 'tablist' });
    const shown = (props.items || []).filter((item) => !item.only || item.only === props.kind);
    if (props.remember) {
      const kept = memory.get('tab', '');
      if (props.current && props.current !== kept) memory.set('tab', props.current);
      else if (!props.current && kept && !state.restored && shown.some((item) => item.id === kept)) { state.restored = true; emit('selected', { id: kept }); }
    }
    const current = props.current || (props.remember ? (shown[0] || {}).id : '');  // 覚えるタブ：まだ決まっていなければ先頭
    for (const item of shown) {
      const on = item.id === current;
      const button = h('button', { type: 'button', role: 'tab' }, item.label);
      button.setAttribute('aria-selected', String(on));
      button.tabIndex = on || !shown.some((other) => other.id === current) ? 0 : -1;
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
