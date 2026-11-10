// 部品「文字の並びから選ぶ欄」。先頭は「選ばない」（null を出す）。
export default {
  render(root, props, { h, emit }) {
    const select = h('select', {});
    select.append(h('option', { value: '' }, props.loading && props.options.length === 0 ? '読み込み中…' : props.none_label));
    for (const text of props.options) {
      const item = h('option', { value: text }, text);
      if ((props.value ?? '') === text) item.selected = true;
      select.append(item);
    }
    select.addEventListener('change', () => emit('changed', { value: select.value === '' ? null : select.value }));
    const box = h('label', {}, props.title, select);
    if (props.error) box.append(h('small', { role: 'alert' }, props.error));
    root.replaceChildren(box);
  },
};
