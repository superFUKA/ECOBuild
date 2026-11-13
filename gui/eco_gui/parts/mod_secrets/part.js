// 部品「シークレットの一覧」。値の入力欄は作らない（登録は端末で：値を画面・表示の状況に置かない）。
export default {
  render(root, props, { h, emit }) {
    const out = [];
    if (props.error) out.push(h('p', { class: 'note' }, 'シークレットの一覧を読めませんでした（リポジトリの管理者の権限が要ります）。'));
    else if (props.loading && props.names.length === 0) out.push(h('p', { role: 'status' }, '読み込み中…'));
    else if (props.names.length === 0) out.push(h('p', { class: 'note' }, 'シークレットはありません。'));
    else {
      const list = h('ul', { class: 'secrets' });
      for (const name of props.names) {
        const remove = h('button', { type: 'button', class: 'small danger-text' }, '削除…');
        if (props.admin === false) { remove.disabled = true; remove.title = '管理者だけが行えます'; }
        remove.addEventListener('click', () => emit('removed', { name }));
        list.append(h('li', {}, h('code', {}, name), remove));
      }
      out.push(list);
    }
    out.push(h('p', { class: 'note' }, '登録は端末で：', h('code', { class: 'cmd' }, 'ecobuild ci secret set <名前>'),
      '（値は、聞かれたときに打ちます。GitHub に送るだけで、表示も保存もしません。同じ名前なら置き換え）'));
    out.push(h('p', { class: 'note' }, '非公開の依存先を CI で取得するには、それを読めるトークンを ECOBUILD_DEPS_TOKEN に登録します。'));
    root.replaceChildren(...out);
  },
};
