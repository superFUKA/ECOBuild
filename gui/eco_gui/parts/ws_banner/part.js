// 部品「作業空間の帯」。今までの GUI（gui/static/workspace.js の renderBanners）と同じ文とボタン。
// 状況に当てはまらなければ、何も出さない（高さも取らない）。「あとで」は、窓を開いているあいだだけ隠す。
const STOPPED = { merge: '取り込み', rebase: 'タスクブランチの作り直し', revert: '取り消し', stash: '退避した変更の戻し' };

export default {
  render(root, props, { h, emit, state, redraw }) {
    const s = props.status || {}, remote = props.remote || {};
    const loaded = 'branch' in s || 'task' in s || 'merging' in s;
    const button = (name, label, primary) => {
      const item = h('button', { type: 'button', class: primary ? 'primary' : '' }, label);
      item.addEventListener('click', () => emit('action', { name, paths: name === 'discard_left' ? [...changes] : [] }));
      return item;
    };
    const banner = (bad, ...children) => root.replaceChildren(h('div', { class: 'eco-banner' + (bad ? ' bad' : ''), role: 'status' }, ...children));
    const none = () => root.replaceChildren(h('button', { type: 'button', hidden: true }));
    const changes = new Set([...(s.conflicted || []), ...(s.staged || []), ...(s.unstaged || []), ...(s.untracked || [])]);

    if (props.kind === 'unreadable') return props.error ? banner(true, `この場所の状態を取得できませんでした：${props.error}`) : none();
    if (props.kind === 'conflict') {
      if (!s.merging) return none();
      return banner(true, `${STOPPED[s.stopped] || '取り込み'}の途中で衝突しました。衝突したファイルを直して（「衝突を直す」の画面・右クリックで片方の側を採る）、「続ける」を押してください。`,
        ...((s.conflicted || []).length ? [button('resolve', '衝突を直す…', true)] : []), button('continue', '続ける'), button('abort', 'やめる'));
    }
    if (props.kind === 'review') {
      if (!s.reviewing) return none();
      return banner(false, `#${s.reviewing_task || '?'} の提出を手元で確認しています（コミットはできません）。`,
        ...(s.reviewing_task ? [button('approve', '承認して取り込む'), button('reject', '差し戻す')] : []), button('review_done', '判定せずに終える'));
    }
    if (props.kind === 'notask') {
      if (!loaded || s.task || s.reviewing) return none();
      return banner(false, `タスクブランチではありません（${s.branch || 'ブランチなし'}）。コミットはタスクブランチで。`, button('tasks', 'タスク管理を開く', true));
    }
    if (props.kind === 'archived') {
      if (!(remote.archived || s.archived)) return none();
      return banner(true, 'GitHubのリポジトリはアーカイブ（読み取り専用）されています。Push・PR・タスクの変更はできません。', button('unarchive', 'アーカイブを解除'));
    }
    if (props.kind === 'gone') {
      if (!s.upstream_gone) return none();
      if (s.finished) return banner(false, `#${s.task} は完了しています。`, button('prune', 'タスクブランチを片付ける'));
      return banner(true, `GitHub上の ${s.branch} は削除されています（別の場所で中止された可能性があります）。タスク管理の「作業を捨てる」で片付けてください。`);
    }
    if (props.kind === 'behind') {
      const clashes = remote.base_conflicts || s.base_conflicts || [];
      if (!(s.behind || remote.base_behind || s.base_behind) || s.merging) return none();
      const text = h('span', {}, '最新の変更を取り込んでいません。');
      if (clashes.length) text.append(`取り込むと ${clashes.length} 件のファイルが衝突します（`, h('span', { class: 'files' }, clashes.join('、')), '）。取り込んで直してから提出してください。');
      return banner(clashes.length > 0, text, button('sync', '最新を取り込む'));
    }
    if (props.kind === 'left') {
      if (!loaded || s.task || s.reviewing || s.merging || changes.size === 0) return none();
      return banner(false, `未コミットの変更が ${changes.size} 件あります。`, button('discard_left', '変更を捨てる…'));
    }
    if (props.kind === 'format') {
      if (!(s.format < s.latest_format) || state.later) return none();
      const later = h('button', { type: 'button' }, 'あとで');
      later.addEventListener('click', () => { state.later = true; redraw(); });
      return banner(false, `ECOBuild の仕様が古くなっています（版 ${s.format} → ${s.latest_format}）。`,
        ...(s.reviewing || s.merging ? [] : [button('upgrade', '最新の仕様にする')]), later);
    }
    return none();
  },
};
