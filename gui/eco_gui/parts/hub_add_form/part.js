// 部品「モジュールを追加する窓の入力欄」。今までの GUI（static/hub.html の #add-form・hub.js の updateFields）と同じ欄と文言。
// ここでするのは、欄を組むことだけ：方法に合う欄を出す・型に合う「最初に作るもの」を並べる・作成先の文・候補。
// 描くのは共有のコード（lib.js の form）。作る・取得する・登録するは、画面のボタンが ecobuild を呼ぶ（この部品は、今の値を changed で出すだけ）。
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
const REDRAW = ['method', 'type', 'kind'];  // 変えると、出す欄が変わるもの
const sameRepository = (a, b) => {
  if (!a || !b) return false;
  const full = a.includes('/') && b.includes('/');
  const key = (x) => (full ? x : x.split('/').pop()).toLowerCase();
  return key(a) === key(b);
};
const day = (text) => { const d = new Date(text); return Number.isNaN(d.getTime()) ? '' : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const folder = (text) => String(text || '').trim().replace(/[\\/]+$/, '');

export default {
  render(root, props, tools) {
    const { emit, memory, state, redraw, lib } = tools;
    const options = lib.form.options;
    const types = props.types && props.types.length ? props.types : FALLBACK_TYPES;
    state.touched = state.touched || {};
    state.values = state.values || {};
    // 今入っている値（打っていなければ、初めの値）
    const now = (name, initial) => (state.touched[name] ? state.values[name] : initial);
    const method = now('method', 'new'), type = now('type', types[0].name);
    const info = types.find((t) => t.name === type) || types[0];
    const kinds = info.new_kinds || [];
    const firstKind = kinds.length ? (info.default_new_kind || kinds[0]) : '';
    if (!kinds.includes(now('kind', firstKind))) delete state.touched.kind;   // 型を変えたら、その型の既定に戻す
    const kind = now('kind', firstKind);
    const named = kinds.length > 0 && kind !== 'none';
    const library = kinds.length > 0 && LIBRARY_KINDS.includes(kind);
    // 保存先の初めの値：前に使ったもの。なければ、この PC のモジュールの親フォルダ（一覧が後から届いても、打つまでは合わせる）
    const known = props.modules.find((m) => m.path);
    const directory = memory.get(PARENT, '') || (known ? String(known.path).replace(/[\\/][^\\/]+$/, '') : '');
    const typeOptions = options(types.map((t) => [t.name, TYPE_LABELS[t.name] || t.name]));

    const fields = [{ name: 'method', label: '追加方法', label_hidden: true, type: 'radio', columns: 2, strong: true, value: 'new', options: options(METHODS) }];
    if (method === 'new') {
      fields.push({ name: 'name', label: 'モジュール名', row: 'name', width: 2, placeholder: '例：MathCore', hint: '英字で始まる英数字・アンダースコア・ハイフン' },
        { name: 'type', label: '型', type: 'select', row: 'name', value: types[0].name, options: typeOptions });
      if (kinds.length) fields.push({ name: 'kind', label: '最初に作るもの', type: 'select', row: 'kind', width: 2, value: firstKind, options: options(kinds.map((k) => [k, (KIND_TEXT[type] || {})[k] || k])) });
      if (named) {
        fields.push({ name: 'project', label: '名前（任意）', row: 'kind', hint: '英字で始まる英数字・アンダースコア',
          placeholder: type === 'python' ? '省略時はモジュール名の小文字（パッケージ名）' : '省略時はモジュール名' });
      }
      if (library) {
        fields.push({ name: 'test', type: 'checkbox', value: true, label: (get) => (type === 'cpp'
          ? `テスト用のProject（${String(get('project') || '').trim() || String(get('name') || '').trim() || '名前'}Test）も作る` : 'テスト（tests/）も作る') });
      }
    }
    if (method === 'clone') {
      // GitHub にあって、まだ一覧にないモジュール（後から届く）：押すと、リポジトリの欄に入る
      const rest = props.candidates && props.candidates.filter((g) => !g.archived && !props.modules.some((m) => sameRepository(g.repository, m.repository || '')));
      fields.push({ name: 'repository', label: 'GitHubリポジトリ', placeholder: '所有者/名前 または 名前',
        candidates: rest && rest.map((g) => ({ value: g.repository, label: g.repository,
          help: [g.type, g.private ? '非公開' : '公開', g.updated ? '更新 ' + day(g.updated) : ''].filter(Boolean).join('・') + (g.description ? '　' + g.description : '') })),
        candidates_title: 'GitHubにあるモジュール', candidates_loading: 'GitHubにあるモジュールを読み込んでいます…',
        candidates_empty: props.candidates && props.candidates.length ? 'GitHubのモジュールは、すべて一覧に登録済みです。' : 'GitHubにモジュールが見つかりませんでした。' });
    }
    if (method === 'new' || method === 'clone') {
      fields.push({ name: 'directory', label: '保存先の親フォルダ', value: directory, placeholder: '例：C:\\work' },
        { type: 'note', label: (get) => {
          const parent = folder(get('directory')), name = method === 'new' ? String(get('name') || '').trim() : (String(get('repository') || '').trim().split('/').pop() || '');
          return parent && name ? `作成先：${parent}/${name}` : '';
        } });
    }
    if (method === 'new') {
      fields.push({ type: 'section', label: '詳細設定', note: '説明・所有者・公開範囲', collapsed: true },
        { name: 'description', label: '説明（任意）', type: 'textarea', rows: 2 },
        { name: 'owner', label: '所有者（任意）', placeholder: props.owner ? `省略時は既定の所有者（${props.owner}）` : '省略時は既定の所有者（未設定ならログイン中のユーザー）' },
        { name: 'public', label: '公開リポジトリにする', type: 'checkbox' },
        { type: 'section', end: true });
    }
    if (method === 'register') fields.push({ name: 'folder', label: 'モジュールのフォルダ', placeholder: '.ecobuild のあるフォルダ' });
    if (method === 'adopt') {
      fields.push({ name: 'adopt_folder', label: 'リポジトリのフォルダ', row: 'adopt', width: 3, placeholder: 'GitHub のリポジトリを clone したフォルダ' },
        { name: 'adopt_type', label: '型', type: 'select', row: 'adopt', value: types[0].name, options: typeOptions },
        { type: 'note', label: 'できるのはリポジトリの管理者だけです（個人のリポジトリなら持ち主）。置くファイルと push 先は、実行する前の確かめに出ます。' });
    }

    // 今の値をまとめて出す（今は出していない欄の値も、打ったものは残っている）
    const send = (raw) => {
      const value = (name, initial) => (name in raw ? raw[name] : now(name, initial));
      const text = (name) => String(value(name, '') || '').trim();
      emit('changed', { method, directory: folder(value('directory', directory)), name: text('name'), type, kind: kind || '',
        project: named ? text('project') : '', test: library ? value('test', true) === true : null, description: text('description'), owner: text('owner'),
        public: value('public', false) === true ? true : null, repository: text('repository'), folder: text('folder'), adopt_folder: text('adopt_folder'),
        adopt_type: value('adopt_type', types[0].name) });
    };
    const drawn = lib.form.render(root, { plain: true, bare: true, fields, problem: props.problem }, tools, {
      changed: (name, raw) => {
        if (name === 'directory' && folder(raw.directory)) memory.set(PARENT, folder(raw.directory));
        if (REDRAW.includes(name)) redraw(); else send(raw);
      },
    });
    // 初めと、型の一覧・保存先が届いたとき、出す欄が変わったとき：今の値（既定の型・最初に作るもの）を出しておく
    const stamp = JSON.stringify([types.map((t) => t.name), method, type, kind, now('adopt_type', ''), state.touched.directory ? '' : directory]);
    if (state.sent !== stamp) { state.sent = stamp; send(drawn.raw); }
  },
};
