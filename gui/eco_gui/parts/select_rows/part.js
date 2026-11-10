// 部品「一覧から選ぶ欄」。先頭は「選ばない」（null を出す）。見せる文字は「label（value）」。
export default {
  render(root, props, { h, emit }) {
    const select = h('select', {});
    select.append(h('option', { value: '' }, props.loading && props.rows.length === 0 ? '読み込み中…' : props.none_label));
    for (const row of props.rows) {
      const value = String(row[props.value_key] ?? '');
      const label = props.label_key && row[props.label_key] ? `${row[props.label_key]}（${value}）` : value;
      const item = h('option', { value }, label);
      if ((props.value ?? '') === value) item.selected = true;
      select.append(item);
    }
    select.addEventListener('change', () => emit('changed', { value: select.value === '' ? null : select.value }));
    const box = h('label', {}, props.title, select);
    if (props.error) box.append(h('small', { role: 'alert' }, props.error));
    root.replaceChildren(box);
  },
};
