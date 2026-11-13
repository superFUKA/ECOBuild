// 部品「コミットの欄」。今までの GUI（workspace.html の .commit-panel の上の部分）と同じ。
// 欄は作り直さない（打っている途中の文字・変換・カーソルを残す）。外から空になったときだけ、欄を空にする。
// 押したとき：「直前のコミットを修正」でファイルを選んでいなければ all（すべての変更を含めるか、確かめてもらう）、
// Push 済みのコミットを修正するなら pushed（強制Push の案内を出してもらう）を付けて出す。
export default {
  render(root, props, { h, emit }) {
    let area = root.querySelector('textarea');
    if (!area) {
      area = h('textarea', { rows: 3, placeholder: 'コミットメッセージ（何を・なぜ変えたか）', 'aria-label': 'コミットメッセージ' });
      area.value = props.text || '';
      const amend = h('input', { type: 'checkbox' });
      const commit = h('button', { type: 'button', class: 'primary' }, 'コミット');
      const note = h('p', { class: 'amend-note', role: 'note' });
      area.addEventListener('input', () => { emit('changed', { text: area.value }); root.gfSync(); });
      amend.addEventListener('change', () => emit('amend', { on: amend.checked }));
      commit.addEventListener('click', () => emit('commit', root.gfWhat()));
      root.replaceChildren(h('div', { class: 'commit-box' }, area, h('div', { class: 'actions' }, h('label', {}, amend, ' 直前のコミットを修正'), commit), note));
      root.gfParts = { amend, commit, note };
    }
    const { amend, commit, note } = root.gfParts;
    if (!props.text && root.gfText) area.value = '';  // コミットが済んだ（共有の値が空になった）
    root.gfText = props.text || '';
    amend.checked = Boolean(props.amend);
    const count = (props.checked || []).length;
    const s = props.status || {};
    const changes = new Set([...(s.conflicted || []), ...(s.staged || []), ...(s.unstaged || []), ...(s.untracked || [])]).size;
    const pushed = Boolean(props.amend) && Boolean(s.task) && !s.ahead;  // 直すコミットは、もう GitHub にある
    note.textContent = pushed ? 'Push 済みのコミットを修正します。修正した後は「強制Push…」で送ります。' : '';
    note.hidden = !pushed;
    root.gfWhat = () => ({ amend: amend.checked, all: amend.checked && count === 0 && changes > 0, pushed: amend.checked && Boolean(s.task) && !s.ahead });
    const locked = s.task && !s.reviewing ? '' : s.reviewing ? '提出を確認している間はコミットできません。' : 'コミットはタスクブランチで行います（タスク管理で「作業を開始」）。';
    root.gfSync = () => {
      commit.textContent = count ? `コミット（${count}件）` : 'コミット';
      commit.disabled = Boolean(locked) || !area.value.trim() || (!count && !amend.checked);
      commit.title = locked || (!area.value.trim() ? 'コミットメッセージを書いてください' : !count && !amend.checked ? 'コミットするファイルに印を付けてください' : '');
    };
    root.gfSync();
  },
};
