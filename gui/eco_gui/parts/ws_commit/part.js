// 部品「コミットの欄」。今までの GUI（workspace.html の .commit-panel の上の部分）と同じ。
// 欄は作り直さない（打っている途中の文字・変換・カーソルを残す）。外から空になったときだけ、欄を空にする。
export default {
  render(root, props, { h, emit }) {
    let area = root.querySelector('textarea');
    if (!area) {
      area = h('textarea', { rows: 3, placeholder: 'コミットメッセージ（何を・なぜ変えたか）', 'aria-label': 'コミットメッセージ' });
      area.value = props.text || '';
      const amend = h('input', { type: 'checkbox' });
      const commit = h('button', { type: 'button', class: 'primary' }, 'コミット');
      area.addEventListener('input', () => { emit('changed', { text: area.value }); root.gfSync(); });
      amend.addEventListener('change', () => emit('amend', { on: amend.checked }));
      commit.addEventListener('click', () => emit('commit', {}));
      root.replaceChildren(h('div', { class: 'commit-box' }, area, h('div', { class: 'actions' }, h('label', {}, amend, ' 直前のコミットを修正'), commit)));
      root.gfParts = { amend, commit };
    }
    const { amend, commit } = root.gfParts;
    if (!props.text && root.gfText) area.value = '';  // コミットが済んだ（共有の値が空になった）
    root.gfText = props.text || '';
    amend.checked = Boolean(props.amend);
    const count = (props.checked || []).length;
    root.gfSync = () => {
      commit.textContent = count ? `コミット（${count}件）` : 'コミット';
      commit.disabled = !area.value.trim() || (!count && !amend.checked);
      commit.title = !area.value.trim() ? 'コミットメッセージを書いてください' : !count && !amend.checked ? 'コミットするファイルに印を付けてください' : '';
    };
    root.gfSync();
  },
};
