// 部品「選ぶ欄」。空の値は「選ばない」（null を出す）。
export default {
  render(root, props, { h, emit }) {
    const select = h('select', {});
    for (const option of props.options) {
      const item = h('option', { value: option.value }, option.label);
      if ((props.value ?? '') === option.value) item.selected = true;
      select.append(item);
    }
    select.addEventListener('change', () => emit('changed', { value: select.value === '' ? null : select.value }));
    root.replaceChildren(h('label', {}, props.title, select));
  },
};
