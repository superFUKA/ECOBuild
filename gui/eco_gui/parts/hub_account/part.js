// 部品「アカウントの窓の中身」。今までの GUI（static/common.js の accountSettings）と同じ並び。
// 見せるだけ：ログイン・権限は ecobuild account show、作成者は ecobuild doctor、所有者は ecobuild config list の答え。
// 書き直した作成者・所有者は、出力（author・owner・owner_reset）で出す（保存するのは ecobuild setup・config）。
const SCOPES = [['repo', 'リポジトリの読み書き'], ['project', 'タスク管理（GitHub Projects）'],
  ['workflow', 'CI のワークフローの変更'], ['delete_repo', 'リポジトリの削除']];

export default {
  render(root, props, { h, emit, state, redraw }) {
    if (!props.account) {
      return root.replaceChildren(h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' アカウントの情報を読み込んでいます…'));
    }
    const me = props.account.login || '';
    const scopes = new Set(props.account.scopes || []);
    const item = (id) => props.doctor.find((entry) => entry.id === id);
    const author = item('git_identity');
    const parsed = (author && author.ok && /^(.*?)\s*<(.*)>$/.exec(author.detail || '')) || [];
    const name = parsed[1] || '';
    const email = parsed[2] || '';
    const owner = (props.config || {}).owner || '';
    const login = item('gh_auth');

    const box = h('div', { class: 'account' });
    const who = h('div', {}, h('div', { class: 'name' }, me || 'ログインしていません'));
    if (!me) who.append(h('div', { class: 'help' }, 'GitHub CLI（gh）にログインしてください'));
    box.append(h('div', { class: 'head' }, h('span', { class: 'big-avatar', 'aria-hidden': 'true' }, (me[0] || '?').toUpperCase()), who));

    box.append(h('section', {}, h('h3', {}, 'GitHub のログイン'),
      h('p', { class: 'help' }, me
        ? '別のアカウントでログインするには、端末で gh auth login（ブラウザで承認します）。ログイン済みのアカウントに切り替えるには gh auth switch。終わったら「読み直す」を押してください。'
        : ((login && login.hint) || '端末で gh auth login を実行してください（ブラウザでログインします）。') + ' 終わったら「読み直す」を押してください。')));

    if (me) {
      const list = h('ul', { class: 'rows scopes' });
      for (const [scope, text] of SCOPES) {
        const has = scopes.has(scope);
        list.append(h('li', {}, h('span', {}, text, h('small', {}, has || scope === 'repo' ? scope : `${scope}（足すには、端末で gh auth refresh -s ${scope}）`)),
          h('span', { class: has ? 'ok' : 'no' }, has ? 'あります' : 'ありません')));
      }
      box.append(h('section', {}, h('h3', {}, '権限'), list));
    }

    // コミットの作成者（この PC の git の設定。すべてのモジュールに共通）
    const authorBox = h('section', {}, h('h3', {}, 'コミットの作成者'));
    if (state.editing === 'author') {
      const nameInput = h('input', { placeholder: '名前', 'aria-label': '名前' });
      const emailInput = h('input', { type: 'email', placeholder: 'メールアドレス', 'aria-label': 'メールアドレス' });
      nameInput.value = state.name === undefined ? name : state.name;
      emailInput.value = state.email === undefined ? email : state.email;
      nameInput.addEventListener('input', () => { state.name = nameInput.value; });
      emailInput.addEventListener('input', () => { state.email = emailInput.value; });
      const save = h('button', { type: 'button', class: 'primary' }, '保存');
      save.addEventListener('click', () => {
        if (!nameInput.value.trim() || !emailInput.value.trim()) return;
        state.editing = '';
        emit('author', { name: nameInput.value.trim(), email: emailInput.value.trim() });
        redraw();
      });
      authorBox.append(h('p', { class: 'help' }, 'このPCの git の設定（すべてのモジュールに共通）'),
        h('div', { class: 'edit' }, nameInput, emailInput, save, cancel()));
    } else {
      const text = author && author.ok ? h('span', {}, name, h('small', {}, email)) : h('span', {}, '未設定', h('small', {}, (author && author.hint) || ''));
      authorBox.append(h('ul', { class: 'rows' }, h('li', {}, text, change('author'))));
    }
    box.append(authorBox);

    // 新しいモジュールの所有者（ecobuild config owner。空ならログイン中のユーザー）
    const ownerBox = h('section', {}, h('h3', {}, '新しいモジュールの所有者'));
    if (state.editing === 'owner') {
      const input = h('input', { placeholder: '未設定ならログイン中のユーザー', 'aria-label': 'GitHub のユーザー名・組織名' });
      input.value = state.owner === undefined ? owner : state.owner;
      input.addEventListener('input', () => { state.owner = input.value; });
      const save = h('button', { type: 'button', class: 'primary' }, '保存');
      save.addEventListener('click', () => {
        const value = input.value.trim();
        state.editing = '';
        if (value) emit('owner', { owner: value }); else emit('owner_reset', {});
        redraw();
      });
      ownerBox.append(h('div', { class: 'edit' }, input, save, cancel()));
    } else {
      ownerBox.append(h('ul', { class: 'rows' }, h('li', {}, h('span', {}, owner || `ログイン中のユーザー${me ? `（${me}）` : ''}`), change('owner'))));
    }
    box.append(ownerBox);
    root.replaceChildren(box);

    function change(what) {
      const button = h('button', { type: 'button' }, '変更');
      button.addEventListener('click', () => { state.editing = what; state.name = undefined; state.email = undefined; state.owner = undefined; redraw(); });
      return button;
    }
    function cancel() {
      const button = h('button', { type: 'button' }, 'やめる');
      button.addEventListener('click', () => { state.editing = ''; redraw(); });
      return button;
    }
  },
};
