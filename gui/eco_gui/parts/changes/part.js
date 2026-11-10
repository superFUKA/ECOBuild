// 部品「変更のあるファイル」。種類ごとに見出しを付け、チェックで選ぶ。選んだものは changed で出す。
const GROUPS = [['conflicted', '衝突'], ['staged', 'ステージ済み'], ['unstaged', '変更'], ['untracked', '新しいファイル']];

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const groups = GROUPS.map(([key, label]) => [label, props.status[key] || []]).filter(([, files]) => files.length);
    if (props.loading && groups.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (groups.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const checked = new Set(props.checked);
    const box = h('div', {});
    for (const [label, files] of groups) {
      box.append(h('small', { style: 'display:block;margin-top:.4rem' }, label));
      for (const path of files) {
        const input = h('input', { type: 'checkbox', checked: checked.has(path) });
        input.addEventListener('change', () => {
          if (input.checked) checked.add(path); else checked.delete(path);
          emit('changed', { paths: [...checked] });
        });
        box.append(h('label', { style: 'display:flex;gap:.4rem;align-items:center' }, input, path));
      }
    }
    root.replaceChildren(box);
  },
};
