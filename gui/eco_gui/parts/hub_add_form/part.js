// 部品「モジュールを追加する窓の入力欄」。今までの GUI（static/hub.html の #add-form・hub.js の updateFields）と同じ欄と文言。
// ここでするのは見せ方だけ：方法に合う欄を出す・型に合う「最初に作るもの」を並べる・作成先を見せる・候補を欄に入れる。
// 作る・取得する・登録するは、画面のボタンが ecobuild を呼ぶ（この部品は、今の値を changed で出すだけ）。
const METHODS = [
  ['new', '新規作成', 'GitHub にリポジトリも作る'],
  ['clone', 'GitHubから取得', 'ECOBuild のモジュールを clone'],
  ['register', '手元のフォルダを登録', 'clone 済みのモジュールを一覧に足す'],
  ['adopt', 'リポジトリをモジュールに', 'ほかのリポジトリに .ecobuild を足す'],
];
const TYPE_LABELS = { cpp: 'C++', python: 'Python', generic: 'その他（generic）' };
const FALLBACK_TYPES = [{ name: 'cpp', new_kinds: ['app', 'library', 'shared', 'none'], default_new_kind: 'app' },
  { name: 'python', new_kinds: ['app', 'library', 'none'], default_new_kind: 'app' }, { name: 'generic', new_kinds: [], default_new_kind: null }];
const LIBRARY_KINDS = ['library', 'shared'];  // テストも一緒に作るもの
const KIND_TEXT = {
  cpp: { app: 'app（実行ファイル）', library: 'library（静的ライブラリ .lib）', shared: 'shared（共有ライブラリ .dll）', none: 'none（Projectを作らない）' },
  python: { app: 'app（実行できるパッケージ）', library: 'library（パッケージ）', none: 'none（パッケージを作らない）' },
};
const PARENT = 'parent';  // 前に使った保存先（この PC に覚える）
const sameRepository = (a, b) => {
  if (!a || !b) return false;
  const full = a.includes('/') && b.includes('/');
  const key = (x) => (full ? x : x.split('/').pop()).toLowerCase();
  return key(a) === key(b);
};
const day = (text) => { const d = new Date(text); return Number.isNaN(d.getTime()) ? '' : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

export default {
  render(root, props, { h, emit, memory, state, redraw }) {
    const types = props.types && props.types.length ? props.types : FALLBACK_TYPES;
    if (!state.v) {
      const first = props.modules.find((m) => m.path);
      state.v = { method: 'new', directory: memory.get(PARENT, '') || (first ? String(first.path).replace(/[\\/][^\\/]+$/, '') : ''),
        name: '', type: types[0].name, kind: null, project: '', test: true, description: '', owner: '', public: false,
        repository: '', folder: '', adopt_folder: '', adopt_type: types[0].name, more: false };
    }
    const v = state.v;
    const info = types.find((t) => t.name === v.type) || types[0];
    const kinds = info.new_kinds || [];
    if (!kinds.includes(v.kind)) v.kind = kinds.length ? (info.default_new_kind || kinds[0]) : '';
    const named = kinds.length > 0 && v.kind !== 'none';
    const library = kinds.length > 0 && LIBRARY_KINDS.includes(v.kind);
    const send = () => {
      if (v.directory) memory.set(PARENT, v.directory.trim().replace(/[\\/]+$/, ''));
      emit('changed', { method: v.method, directory: v.directory.trim().replace(/[\\/]+$/, ''), name: v.name.trim(), type: v.type, kind: v.kind || '',
        project: named ? v.project.trim() : '', test: library ? v.test : null, description: v.description.trim(), owner: v.owner.trim(),
        public: v.public ? true : null, repository: v.repository.trim(), folder: v.folder.trim(), adopt_folder: v.adopt_folder.trim(), adopt_type: v.adopt_type });
    };
    // 初めと、型の一覧が届いたとき：今の値（既定の型・最初に作るもの）を出しておく
    const stamp = JSON.stringify([types.map((t) => t.name), v.method, v.type, v.kind, v.adopt_type]);
    if (state.sent !== stamp) { state.sent = stamp; send(); }

    const form = h('div', { class: 'add' });
    const methods = h('fieldset', { class: 'methods' }, h('legend', { class: 'sr-only' }, '追加方法'));
    for (const [value, label, help] of METHODS) {
      const radio = h('input', { type: 'radio', name: 'method', value });
      radio.checked = v.method === value;
      radio.addEventListener('change', () => { v.method = value; redraw(); });
      methods.append(h('label', { class: v.method === value ? 'method on' : 'method' }, radio, h('span', {}, h('strong', {}, label), h('small', {}, help))));
    }
    form.append(methods);

    const dest = h('p', { class: 'note' });
    const showDestination = () => {
      const parent = v.directory.trim().replace(/[\\/]+$/, '');
      const name = v.method === 'new' ? v.name.trim() : (v.repository.trim().split('/').pop() || '');
      dest.textContent = parent && name ? `作成先：${parent}/${name}` : '';
    };
    const input = (key, attrs, after) => {
      const box = h(attrs.rows ? 'textarea' : 'input', attrs);
      box.value = v[key];
      box.addEventListener('input', () => { v[key] = box.value; showDestination(); if (after) after(); send(); });
      return box;
    };
    const select = (key, options) => {
      const box = h('select', {}, ...options.map(([value, label]) => h('option', { value }, label)));
      box.value = v[key];
      box.addEventListener('change', () => { v[key] = box.value; redraw(); });
      return box;
    };
    const check = (key, label) => {
      const box = h('input', { type: 'checkbox' });
      box.checked = Boolean(v[key]);
      box.addEventListener('change', () => { v[key] = box.checked; send(); });
      return h('label', { class: 'check' }, box, ' ', label);
    };
    const field = (label, control) => h('label', { class: 'field' }, label, control);
    const typeOptions = types.map((t) => [t.name, TYPE_LABELS[t.name] || t.name]);

    if (v.method === 'new') {
      const testLabel = h('span', {});
      const showTest = () => {
        testLabel.textContent = v.type === 'cpp' ? `テスト用のProject（${v.project.trim() || v.name.trim() || '名前'}Test）も作る` : 'テスト（tests/）も作る';
      };
      showTest();
      form.append(h('div', { class: 'grid' }, field('モジュール名', input('name', { placeholder: '例：MathCore', title: '英字で始まる英数字・アンダースコア・ハイフン' }, showTest)),
        field('型', select('type', typeOptions))));
      if (kinds.length) {
        const row = h('div', { class: 'grid' }, field('最初に作るもの', select('kind', kinds.map((k) => [k, (KIND_TEXT[v.type] || {})[k] || k]))));
        if (named) {
          row.append(field('名前（任意）', input('project', { placeholder: v.type === 'python' ? '省略時はモジュール名の小文字（パッケージ名）' : '省略時はモジュール名',
            title: '英字で始まる英数字・アンダースコア' }, showTest)));
        }
        form.append(row);
      }
      if (library) {
        const box = h('input', { type: 'checkbox' });
        box.checked = Boolean(v.test);
        box.addEventListener('change', () => { v.test = box.checked; send(); });
        form.append(h('label', { class: 'check' }, box, ' ', testLabel));
      }
    }
    if (v.method === 'clone') {
      const repository = input('repository', { placeholder: '所有者/名前 または 名前' });
      form.append(field('GitHubリポジトリ', repository), candidates(repository));
    }
    if (v.method === 'new' || v.method === 'clone') {
      form.append(field('保存先の親フォルダ', input('directory', { placeholder: '例：C:\\work' })), dest);
      showDestination();
    }
    if (v.method === 'new') {
      const more = h('details', { class: 'more' }, h('summary', {}, '詳細設定 ', h('span', {}, '説明・所有者・公開範囲')),
        field('説明（任意）', input('description', { rows: 2 })),
        field('所有者（任意）', input('owner', { placeholder: props.owner ? `省略時は既定の所有者（${props.owner}）` : '省略時は既定の所有者（未設定ならログイン中のユーザー）' })),
        check('public', '公開リポジトリにする'));
      more.open = Boolean(v.more);
      more.addEventListener('toggle', () => { v.more = more.open; });
      form.append(more);
    }
    if (v.method === 'register') {
      form.append(field('モジュールのフォルダ', input('folder', { placeholder: '.ecobuild のあるフォルダ' })));
    }
    if (v.method === 'adopt') {
      form.append(h('div', { class: 'grid wide' }, field('リポジトリのフォルダ', input('adopt_folder', { placeholder: 'GitHub のリポジトリを clone したフォルダ' })),
        field('型', select('adopt_type', typeOptions))),
      h('p', { class: 'note' }, 'できるのはリポジトリの管理者だけです（個人のリポジトリなら持ち主）。置くファイルと push 先は、実行する前の確かめに出ます。'));
    }
    if (props.problem) form.append(h('p', { role: 'alert' }, props.problem));
    root.replaceChildren(form);

    // GitHub にあって、まだ一覧にないモジュール：押すと、リポジトリの欄に入る
    function candidates(target) {
      const box = h('div', { class: 'candidates', 'aria-live': 'polite' });
      if (!props.candidates) {
        box.append(h('p', { class: 'note' }, h('span', { class: 'spinner' }), ' GitHubにあるモジュールを読み込んでいます…'));
        return box;
      }
      const rest = props.candidates.filter((g) => !g.archived && !props.modules.some((m) => sameRepository(g.repository, m.repository || '')));
      if (!rest.length) {
        box.append(h('p', { class: 'note' }, props.candidates.length ? 'GitHubのモジュールは、すべて一覧に登録済みです。' : 'GitHubにモジュールが見つかりませんでした。'));
        return box;
      }
      const list = h('ul', {});
      for (const g of rest) {
        const facts = [g.type, g.private ? '非公開' : '公開', g.updated ? '更新 ' + day(g.updated) : ''].filter(Boolean).join('・');
        const pick = h('button', { type: 'button', class: v.repository === g.repository ? 'selected' : '' },
          h('strong', {}, g.repository), h('small', {}, facts + (g.description ? '　' + g.description : '')));
        pick.addEventListener('click', () => {
          v.repository = g.repository;
          target.value = g.repository;
          for (const other of list.querySelectorAll('button')) other.classList.toggle('selected', other === pick);
          showDestination();
          send();
        });
        list.append(h('li', {}, pick));
      }
      box.append(h('p', { class: 'note' }, 'GitHubにあるモジュール'), list);
      return box;
    }
  },
};
