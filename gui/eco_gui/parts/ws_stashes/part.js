// 部品「退避の一覧」。今までの GUI（static/workspace.js の退避のメニューと「退避の一覧」）と同じ文言・同じ分け方（このブランチ／ほかのブランチ）。
// 押した操作を出すだけ（戻す・削除できるかは、ecobuild が確かめる）。
const ENTRY = /^(?:WIP )?[Oo]n (.+?): (.*)$/;

export default {
  render(root, props, { h, emit }) {
    const s = props.status || {}, branch = s.branch || '';
    const all = (props.stashes || []).map((text, index) => { const m = ENTRY.exec(text); return { index, text, branch: m ? m[1] : null, what: m ? m[2] : text, wip: /^WIP /.test(text) }; });
    const own = all.filter((e) => e.branch === branch), others = all.filter((e) => e.branch !== branch);
    const changed = (s.staged || []).length + (s.unstaged || []).length + (s.untracked || []).length;

    const stash = h('button', { type: 'button', class: 'primary', title: changed ? '未コミットの変更（新しいファイルも）をしまい、最後のコミットの状態にします' : '未コミットの変更はありません' }, '変更を退避');
    stash.disabled = !changed;
    stash.addEventListener('click', () => emit('action', { name: 'stash' }));
    const box = h('section', { class: 'stashes' },
      h('header', {}, h('div', {}, h('h3', {}, branch || 'このブランチ', ' ', h('span', { class: 'pill' }, own.length + ' 件')),
        h('p', { class: 'note' }, changed ? '未コミットの変更 ' + changed + ' 件を、一時的にしまえます。' : '未コミットの変更はありません。')), stash));
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      box.append(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    const row = (e, mine, latest) => {
      const li = h('li', { class: mine ? '' : 'other' }, h('span', { class: 'number' }, String(e.index)),
        h('span', { class: 'what', title: e.text }, e.what || '（説明なし）'));
      if (latest) li.append(h('span', { class: 'pill ok' }, '最後の退避'));
      if (e.wip) li.append(h('span', { class: 'pill dim' }, 'WIP'));
      if (mine) {
        const pop = h('button', { type: 'button', class: 'small', title: 'この退避を戻します：' + e.text, 'aria-label': e.index + ' 番の退避を戻す' }, '戻す');
        pop.addEventListener('click', () => emit('action', { name: 'pop', index: e.index }));
        const drop = h('button', { type: 'button', class: 'small danger-text', title: 'この退避を捨てます（元に戻せません）', 'aria-label': e.index + ' 番の退避を削除' }, '削除…');
        drop.addEventListener('click', () => emit('action', { name: 'drop', index: e.index }));
        li.append(h('span', { class: 'row-actions' }, pop, drop));
      } else li.append(h('span', { class: 'pill' }, e.branch || '不明'));
      return li;
    };
    if (own.length) box.append(h('ol', { class: 'list' }, ...own.map((e, i) => row(e, true, i === 0))));
    else box.append(props.loading ? h('p', { class: 'empty', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…')
      : h('p', { class: 'empty' }, 'このブランチで退避した変更はありません。'));
    if (others.length) {
      box.append(h('details', { class: 'others' }, h('summary', {}, 'ほかのブランチの退避 ' + others.length + ' 件（それぞれの作業空間で扱います）'),
        h('ol', { class: 'list' }, ...others.map((e) => row(e, false, false)))));
    }
    root.replaceChildren(box);
  },
};
