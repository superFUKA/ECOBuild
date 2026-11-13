// 部品「表示の場所」。今までの GUI（modinfo.js の placeSelect）と同じ：モジュールのフォルダ（既定のブランチ）か、作業空間のどれか。
// 選んだ場所は窓の間だけ覚え、ページを移っても同じ場所を見せる（届いた値が覚えたものと違えば、changed で戻す）。
export default {
  render(root, props, { h, emit, memory }) {
    const mine = memory.session;  // 窓を開いている間だけ覚える
    const spaces = props.workspaces || [];
    const now = props.value || '';
    const known = (path) => !path || spaces.some((w) => w.path === path);
    if (now) mine.set('place', now);  // 外から変わった（保存した場所を見せる 等）も覚える
    const kept = mine.get('place', '');
    if (props.workspaces && !known(kept)) {  // 閉じた作業空間は忘れ、モジュールのフォルダーに戻す
      mine.set('place', '');
      if (now) Promise.resolve().then(() => emit('changed', { path: '' }));
    } else if (props.workspaces && kept && !now) {
      // ページを移った（共有の値は空から）：覚えた場所に戻す
      Promise.resolve().then(() => emit('changed', { path: kept }));
    }
    if (!spaces.length) return root.replaceChildren();  // 作業空間がない：選ぶものがない
    const folder = (path) => String(path).split(/[\\/]/).pop();
    const label = (w) => `${w.branch || (w.review != null ? `確認用 #${w.review}` : folder(w.path))}（${folder(w.path)}）`;
    const select = h('select', { 'aria-label': '表示する場所' }, h('option', { value: '' }, 'モジュールのフォルダ（既定のブランチ）'),
      ...spaces.map((w) => h('option', { value: w.path }, label(w))));
    select.value = known(now) ? now : '';
    select.addEventListener('change', () => { mine.set('place', select.value); emit('changed', { path: select.value }); });
    root.replaceChildren(h('label', { class: 'place' }, '表示', select));
  },
};
