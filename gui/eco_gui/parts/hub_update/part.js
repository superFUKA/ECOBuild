// 部品「新しい版の知らせ」。比べるのは ecobuild installer check。ここは、その答えを帯か1行で見せるだけ。
const short = (commit) => (commit ? String(commit).slice(0, 7) : '不明');

export default {
  render(root, props, { h, emit }) {
    const r = props.check;
    const newer = Boolean(r) && !r.up_to_date;
    const update = () => {
      const button = h('button', { type: 'button', class: props.look === 'status' ? 'primary' : '' }, '更新する');
      button.addEventListener('click', () => emit('pressed', {}));
      return button;
    };
    if (props.look === 'status') {
      if (props.error) return root.replaceChildren(h('p', { class: 'line', role: 'status' }, '更新を確かめられません：' + props.error));
      if (!r) return root.replaceChildren(h('p', { class: 'line', role: 'status' }, props.loading ? '確かめています…' : ''));
      const text = newer ? `新しい版があります：${short(r.current)} → ${short(r.latest)}（${r.ref}）` : `最新です：${short(r.latest)}（${r.ref}）`;
      const line = h('p', { class: newer ? 'line newer' : 'line', role: 'status' }, h('span', {}, text));
      if (newer) line.append(update());
      return root.replaceChildren(line);
    }
    if (!newer) return root.replaceChildren();
    root.replaceChildren(h('div', { class: 'update', role: 'status' },
      h('div', {}, h('strong', {}, 'ECOBuild の新しい版があります'),
        h('small', {}, `${short(r.current)} → ${short(r.latest)}（${r.ref}）。${r.gui ? 'CLI と GUI' : 'CLI'}を入れ直します。`)),
      update()));
  },
};
