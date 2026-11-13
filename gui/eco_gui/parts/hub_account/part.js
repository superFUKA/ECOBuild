// 部品「アカウントの窓の中身」。今までの GUI（static/common.js の accountSettings）と同じ並び。
// 見せるだけ：ログイン・権限は ecobuild account show、作成者は ecobuild doctor、所有者は ecobuild config list の答え。
// 書き直した作成者・所有者は、出力（author・owner・owner_reset）で出す（保存するのは ecobuild setup・config）。
// ログイン・切り替え・権限の追加は、端末の窓で続ける（出力 login・scope。開くのは ecobuild gui login・gui scope）。
// [権限, 説明, 画面から足せるか]（repo はログインに付いている）
const SCOPES = [['repo', 'リポジトリの読み書き', false], ['project', 'タスク管理（GitHub Projects）', true],
  ['workflow', 'CI のワークフローの変更', true], ['delete_repo', 'リポジトリの削除', true]];

export default {
  render(root, props, { h, emit, state, redraw, open_url }) {
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
    const head = h('div', { class: 'head' }, h('span', { class: 'big-avatar', 'aria-hidden': 'true' }, (me[0] || '?').toUpperCase()), who);
    if (me) {
      const profile = h('button', { type: 'button', class: 'profile', title: `https://github.com/${me}` }, 'GitHub で開く');
      profile.addEventListener('click', () => open_url(`https://github.com/${encodeURIComponent(me)}`));
      head.append(profile);
    }
    box.append(head);

    // ログイン：端末の窓が開き、ブラウザーで承認する（gh auth login・gh auth switch）
    const signIn = h('button', { type: 'button' }, me ? '別のアカウントでログイン' : 'ログイン');
    signIn.addEventListener('click', () => emit('login', { switch: false }));
    const buttons = h('div', { class: 'buttons' }, signIn);
    if (me) {
      const change = h('button', { type: 'button' }, 'ログイン済みのアカウントに切り替える');
      change.addEventListener('click', () => emit('login', { switch: true }));
      buttons.append(change);
    }
    box.append(h('section', {}, h('h3', {}, 'GitHub のログイン'),
      h('p', { class: 'help' }, me ? 'ターミナルが開き、ブラウザで承認します。終わったら「読み直す」を押してください。'
        : ((login && login.hint) || 'GitHub CLI（gh）にログインしてください。') + ' ターミナルが開き、ブラウザで承認します。'),
      buttons));

    if (me) {
      const list = h('ul', { class: 'rows scopes' });
      for (const [scope, text, addable] of SCOPES) {
        const has = scopes.has(scope);
        let mark = h('span', { class: has ? 'ok' : 'no' }, has ? 'あります' : 'ありません');
        if (!has && addable) {
          mark = h('button', { type: 'button', title: `ターミナルで gh auth refresh -s ${scope} を開きます（ブラウザで承認します）` }, '権限を追加');
          mark.addEventListener('click', () => emit('scope', { scope }));
        }
        list.append(h('li', {}, h('span', {}, text, h('small', {}, scope)), mark));
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
