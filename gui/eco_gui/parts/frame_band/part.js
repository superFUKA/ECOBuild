// 部品「モジュールの窓の帯」。今までの GUI（module.js の showRootBand・shell.css の .root-band）と同じ文と見た目。
const keyOf = (path) => String(path || '').replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();

export default {
  render(root, props, { h, state, redraw }) {
    const mine = (props.modules || []).find((item) => keyOf(item.path) === keyOf(props.module));
    const off = mine && mine.exists && mine.default_branch && mine.branch !== mine.default_branch;
    if (!off || state.closed) { root.replaceChildren(); return; }
    const close = h('button', { type: 'button', class: 'root-band-close', 'aria-label': '閉じる', title: '閉じる' }, '×');
    close.addEventListener('click', () => { state.closed = true; redraw(); });
    root.replaceChildren(h('div', { class: 'eco-banner root-band', role: 'status' },
      h('span', {}, `このモジュールのフォルダ（${props.module}）が ${mine.branch || '切り離された状態'} にいます。作業は作業空間でするので、既定のブランチ ${mine.default_branch} に戻してください。`),
      close));
  },
};
