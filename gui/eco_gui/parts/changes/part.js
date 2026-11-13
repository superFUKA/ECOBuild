// 部品「変更のあるファイル」。今までの GUI（gui/static/workspace.js の renderChanges）と同じ見え方：
// サブプロジェクトごとのまとまり（名前・種類の印・件数・まとめてチェック）、その中はフォルダーの木
// （フォルダーが先・1つだけのフォルダーはつなぐ・件数・まとめてチェック）、ファイルは名前だけ。
// 右に種類を色で出す（いくつもあれば「ステージ済み · 変更」）。チェックしたものは changed で出す。
const KIND_LABEL = { conflicted: '衝突', staged: 'ステージ済み', unstaged: '変更', untracked: '追加' };
const PROJECT_KINDS = { static_library: '静的ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', executable: '実行ファイル', test: 'テスト', benchmark: '性能測定' };
const FOLDER_ICON = '<svg viewBox="0 0 16 16" width="13" height="13"><path d="M1.5 3.5h4.2l1.5 1.5h7.3v8.5h-13z" fill="currentColor" fill-opacity=".25" stroke="currentColor" stroke-linejoin="round"/></svg>';

export default {
  render(root, props, { h, emit, state, menu }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const s = props.status || {};
    const all = new Map();  // パス → 種類（出す順）
    const note = (list, kind) => { for (const path of list || []) { if (!all.has(path)) all.set(path, []); all.get(path).push(kind); } };
    note(s.conflicted, 'conflicted'); note(s.staged, 'staged'); note(s.unstaged, 'unstaged'); note(s.untracked, 'untracked');
    if (props.loading && all.size === 0 && !props.tools) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (all.size === 0 && !props.tools) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));

    const checked = new Set(props.checked.filter((path) => all.has(path)));
    const missing = new Set(props.missing || []);
    const eol = new Set(s.eol_only || []), excluded = new Set(s.excluded || []);
    // まとめて選ぶとき、改行だけが変わったファイルは入れない（task commit と同じ。そのファイルのチェックでは入る）
    const bulk = (paths) => { const some = paths.filter((path) => !eol.has(path)); return some.length ? some : paths; };
    const send = () => emit('changed', { paths: checked.size === 0 && props.none_when_empty ? null : [...all.keys()].filter((path) => checked.has(path)) });
    const groupBox = (paths, title) => {
      const taken = bulk(paths), on = paths.filter((path) => checked.has(path)).length;
      const input = h('input', { type: 'checkbox', title });
      input.checked = taken.length > 0 && taken.every((path) => checked.has(path));
      input.indeterminate = !input.checked && on > 0;
      input.addEventListener('change', () => {
        for (const path of paths) checked.delete(path);
        if (input.checked) for (const path of taken) checked.add(path);
        send();
      });
      return input;
    };
    const act = (name, path = '') => emit('action', { name, path, paths: path ? [path] : [...checked] });

    const box = h('div', { class: 'changes' });
    if (props.tools) {
      const button = (name, label, title, off) => {
        const item = h('button', { type: 'button', title: title || '' }, label);
        if (off) item.disabled = true;
        item.addEventListener('click', () => act(name));
        return item;
      };
      const tools = h('span', { class: 'change-tools' });
      // 変える操作は、タスクブランチで（提出の確認中は変えない）。退避は、確認中・衝突の途中は使わない（前の GUI と同じ）
      const locked = s.task && !s.reviewing ? '' : s.reviewing ? '提出を確認している間は変えられません。' : 'ファイルを変える操作はタスクブランチで行います。';
      const stashLocked = s.reviewing ? '提出を確認している間は使えません。' : s.merging ? '取り込みの途中です（衝突を直すか、やめてから）。' : '';
      // ステージは、衝突で止まった操作を終えるときだけ要る（コミットは、チェックしたものをステージする）
      if (s.merging || (s.conflicted || []).length) {
        tools.append(button('stage', 'ステージ', locked || '衝突を直したファイルを、直したものとして記録します', Boolean(locked) || checked.size === 0),
          button('unstage', 'ステージを取り消す', locked, Boolean(locked) || checked.size === 0));
      }
      const diff = h('button', { type: 'button' }, '差分');
      if (all.size === 0) diff.disabled = true;
      diff.addEventListener('click', () => emit('action', { name: 'diff_dialog', path: props.selected || '', paths: props.selected ? [props.selected] : [] }));
      const stash = h('button', { type: 'button', title: stashLocked || '未コミットの変更を一時的にしまう・戻す', 'aria-haspopup': 'menu' }, '退避');
      if (stashLocked) stash.disabled = true;
      stash.addEventListener('click', async (event) => {
        const own = (props.stashes || []).filter((entry) => { const m = /^(?:WIP )?[Oo]n (.+?): /.exec(entry); return m && m[1] === s.branch; });
        const others = (props.stashes || []).length - own.length;
        const r = stash.getBoundingClientRect();
        const id = await menu({ clientX: r.left, clientY: r.bottom + 4 }, [
          { id: 'stash', label: '変更を退避', disabled: all.size === 0, reason: '未コミットの変更はありません' },
          { id: 'stash_pop', label: '退避を戻す', disabled: own.length === 0, reason: 'このブランチで退避した変更はありません' },
          { id: 'stash_list', label: '退避の一覧…', hint: `${own.length} 件` + (others ? `・ほか ${others}` : '') },
          { separator: true },
          { id: 'stash_drop', label: '退避を削除…', danger: true, disabled: own.length === 0, reason: 'このブランチで退避した変更はありません' },
        ]);
        if (id) emit('action', { name: id, path: '', paths: [] });
      });
      tools.append(diff, button('discard', '元に戻す…', locked || 'チェックしたファイルの変更を捨てて、最後のコミットの状態に戻します（追加したファイルは消えます）', Boolean(locked) || checked.size === 0), stash);
      const allBox = groupBox([...all.keys()], '全部選ぶ');
      box.append(h('div', { class: 'change-head' },
        h('label', { class: 'select-all' }, allBox, ' 変更ファイル', h('span', { class: 'count' }, String(all.size))), tools));
    }

    const list = h('div', { class: 'list' });
    box.append(list);
    if (props.loading && all.size === 0) list.append(h('p', { class: 'muted' }, '読み込み中…'));
    else if (all.size === 0) list.append(h('p', { class: 'muted' }, props.empty_text));

    // サブプロジェクトごとに分ける（いちばん深いフォルダーのもの）
    const projects = [];
    for (const item of props.projects || []) {
      const project = typeof item === 'string' ? { name: item, directory: item } : item;
      const top = String(project.directory || project.name || '').replace(/\/+$/, '');
      projects.push({ ...project, top: top === '.' ? '' : top });
    }
    const projectOf = (path) => {
      let best = null;
      for (const project of projects) {
        if ((project.top === '' || path.startsWith(project.top + '/')) && (best === null || project.top.length > best.top.length)) best = project;
      }
      return best;
    };
    const groups = new Map();
    for (const [path, kinds] of all) {
      const project = projects.length ? projectOf(path) : null, key = project ? project.name : '';
      if (!groups.has(key)) groups.set(key, { project, rows: [] });
      groups.get(key).rows.push([path, kinds]);
    }
    const names = projects.map((project) => project.name);
    const keys = [...groups.keys()].sort((a, b) => (a === '' ? 1e9 : names.indexOf(a)) - (b === '' ? 1e9 : names.indexOf(b)));
    const grouped = keys.length > 1 || (keys.length === 1 && keys[0] !== '');

    const row = (path, kinds, shown, depth) => {
      const input = h('input', { type: 'checkbox', 'aria-label': path });
      input.checked = checked.has(path);
      input.addEventListener('change', () => { if (input.checked) checked.add(path); else checked.delete(path); send(); });
      const name = h('button', { type: 'button', class: 'name', title: (shown !== path ? path + '\n' : '') + 'ダブルクリックで差分（ほかの操作は右クリック）' }, shown);
      name.addEventListener('click', () => { clearTimeout(state.timer); state.timer = setTimeout(() => { if (props.selected !== path) emit('selected', { path }); }, 220); });
      name.addEventListener('dblclick', () => { clearTimeout(state.timer); act('diff', path); });
      const gone = missing.has(path);
      const kind = h('small', { class: 'kind ' + (gone ? 'deleted' : kinds[0]) },
        (gone ? '削除' : '') + (gone && kinds[0] !== 'staged' ? '' : (gone ? ' · ' : '') + kinds.map((k) => KIND_LABEL[k]).join(' · ')));
      const line = h('div', { class: 'change' + (props.selected === path ? ' focused' : ''), style: `padding-left:${depth * 14}px` }, input, name);
      if ((props.generated || []).includes(path)) line.append(h('span', { class: 'tag', title: '道具が作り直すファイル（サブプロジェクトやファイルを足す・消すと変わります）。一緒にコミットします。' }, '生成'));
      if (eol.has(path)) line.append(h('span', { class: 'tag', title: '改行コード（CRLF／LF）だけが変わっています。まとめて選んでもコミットに含めません（含めるならこのファイルに印を付けます）。' }, '改行のみ'));
      if (excluded.has(path)) line.append(h('span', { class: 'tag', title: '管理するファイル（ecobuild track）の対象外です。印を付ければコミットに含めます。' }, '管理外'));
      line.append(kind);
      line.addEventListener('contextmenu', async (event) => {
        event.preventDefault();
        const tracked = !kinds.includes('untracked'), conflicted = kinds.includes('conflicted');
        const id = await menu(event, [
          { id: 'diff', label: '差分' },
          ...(conflicted ? [{ id: 'resolve', label: '衝突を直す…' }] : []),
          { id: 'restore', label: '変更を元に戻す', disabled: !tracked || conflicted, reason: conflicted ? '衝突は「衝突を直す」で直します。' : 'まだ git の管理に入っていないファイルです（消すなら「削除」）。' },
          { id: 'ignore', label: '除外パターンに追加' }, { separator: true },
          { id: 'log', label: 'ログ', disabled: !tracked, reason: 'まだ git の管理に入っていないファイルです。' },
          { id: 'blame', label: '注釈履歴', disabled: !tracked || gone, reason: 'まだ git の管理に入っていないファイルです。' },
        ]);
        if (id) act(id, path);
      });
      return line;
    };
    const pathsOf = (node) => [...node.files.map(([path]) => path), ...[...node.dirs.values()].flatMap(pathsOf)];
    const appendTree = (node, prefix, depth) => {
      for (let [name, child] of [...node.dirs].sort(([a], [b]) => a.localeCompare(b))) {
        while (!child.files.length && child.dirs.size === 1) { const [[sub, next]] = child.dirs; name += '/' + sub; child = next; }  // 1つだけのフォルダーはつなぐ
        const paths = pathsOf(child);
        const icon = h('span', { class: 'change-folder-icon', 'aria-hidden': 'true' });
        icon.innerHTML = FOLDER_ICON;
        list.append(h('label', { class: 'change-folder', title: prefix + name, style: `padding-left:${depth * 14}px` },
          groupBox(paths, 'このフォルダーの変更を全部選ぶ'), h('span', {}, icon, name), h('small', {}, `${paths.length}件`)));
        appendTree(child, prefix + name + '/', depth + 1);
      }
      for (const [path, kinds, name] of node.files.sort((a, b) => a[2].localeCompare(b[2]))) list.append(row(path, kinds, name, depth));
    };
    for (const key of keys) {
      const { project, rows } = groups.get(key), top = grouped && project && project.top ? project.top + '/' : '';
      if (grouped) {
        const name = h('span', {}, project ? project.name : 'サブプロジェクトの外');
        if (project && project.kind) name.append(h('span', { class: 'change-group-kind' }, PROJECT_KINDS[project.kind] || project.kind));
        list.append(h('label', { class: 'change-group', title: project ? (project.top || '（モジュールの一番上）') : 'どのサブプロジェクトにも入らないファイル（モジュールの設定・CI 等）' },
          groupBox(rows.map(([path]) => path), 'このまとまりの変更を全部選ぶ'), name, h('small', {}, `${rows.length}件`)));
      }
      const tree = { dirs: new Map(), files: [] };
      for (const [path, kinds] of rows) {
        const parts = path.slice(top.length).split('/');
        let at = tree;
        for (const name of parts.slice(0, -1)) { if (!at.dirs.has(name)) at.dirs.set(name, { dirs: new Map(), files: [] }); at = at.dirs.get(name); }
        at.files.push([path, kinds, parts[parts.length - 1]]);
      }
      appendTree(tree, top, grouped ? 1 : 0);
    }
    const scroll = state.scroll || 0;
    list.addEventListener('scroll', () => { state.scroll = list.scrollTop; });
    root.replaceChildren(box);
    list.scrollTop = scroll;
  },
};
