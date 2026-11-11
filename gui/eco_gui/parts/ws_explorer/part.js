// 部品「作業空間のエクスプローラー」。今までの GUI（gui/static/explorer.js）と同じ見え方：
// フォルダーは ▸ とアイコン、サブプロジェクトのフォルダーは ◆ と種類の印、ファイルは状態の色と印
// （+ 新しい・• 変更・✓ ステージ済み・衝突は赤の太字・削除は取り消し線）。変更を含むフォルダーは橙。
// クリックで選ぶ（Ctrl で足す・外す、Shift で範囲）。右クリック・F2・Delete・Enter。名前はその場で変える。
// 開閉はこの PC に覚える。「.」で始まるフォルダーは、初めは閉じておく。
const FOLDER_ICON = '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M1.5 3.5h4.2l1.5 1.5h7.3v8.5h-13z" fill="currentColor" fill-opacity=".25" stroke="currentColor" stroke-linejoin="round"/></svg>';
const FILE_ICON = '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M3.5 1.5h6l3 3v10h-9z" fill="none" stroke="currentColor" stroke-linejoin="round"/><path d="M9.5 1.5v3h3" fill="none" stroke="currentColor" stroke-linejoin="round"/></svg>';
const TOOL_ICONS = {
  new_file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14h6"/>',
  reload: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  eye_on: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  eye_off: '<path d="M17.9 17.9A10 10 0 0 1 12 19c-6.5 0-10-7-10-7a18 18 0 0 1 4.1-5M9.9 5.2A9 9 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2M2 2l20 20"/>',
};
const PROJECT_KINDS = { static_library: '静的ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', executable: '実行ファイル', test: 'テスト', benchmark: '性能測定' };
const STATE_LABEL = { deleted: '削除', conflicted: '衝突', untracked: '未追跡', modified: '変更', staged: 'ステージ済み' };
const BAD_NAME = /[<>:"/\\|?*\x00-\x1f]/;

const dirOf = (path) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '');
const baseOf = (path) => path.split('/').pop();
const join = (dir, name) => (dir ? dir + '/' + name : name);
const isReadme = (path) => /^readme(\.[^/]*)?$/i.test(path);
const validName = (name) => name && !BAD_NAME.test(name) && !/[. ]$/.test(name);
const isTest = (path, folder) => (path === 'tests' || path.startsWith('tests/')) && (folder || /(^|\/)test_[^/]*\.py$|_test\.py$/.test(path));

export default {
  render(root, props, { h, emit, state, redraw, memory, menu }) {
    const svg = (inner, size = 15) => {
      const box = h('span', { class: 'icon', 'aria-hidden': 'true' });
      box.innerHTML = inner.startsWith('<svg') ? inner
        : `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
      return box;
    };
    const tool = (name, title) => {
      const button = h('button', { type: 'button', title, 'aria-label': title }, svg(TOOL_ICONS[name]));
      button.addEventListener('click', () => emit('action', { name, path: state.directory || '', paths: [] }));
      return button;
    };
    // 生成ファイル（道具が作り直すもの）は、ふだんは隠す。目の印で出す（この PC に覚える）
    const generated = new Set(props.generated || []);
    const showGenerated = memory.get('generated', false) === true;
    const tools = h('span', { class: 'explorer-tools' }, tool('new_file', '新しいファイル'));
    if (generated.size) {
      const title = showGenerated ? '生成ファイル（CMakeLists.txt 等）を隠す' : '生成ファイル（CMakeLists.txt 等）も表示';
      const eye = h('button', { type: 'button', title, 'aria-label': '生成ファイルの表示', 'aria-pressed': String(showGenerated) }, svg(TOOL_ICONS[showGenerated ? 'eye_on' : 'eye_off']));
      eye.addEventListener('click', () => { memory.set('generated', !showGenerated); redraw(); });
      tools.append(eye);
    }
    tools.append(tool('reload', '読み直す'));
    const head = h('div', { class: 'explorer-heading' }, h('h2', {}, 'エクスプローラー'), tools);
    const tree = h('div', { class: 'tree', role: 'tree' });
    const box = h('div', { class: 'explorer' }, head, tree);
    const finish = () => root.replaceChildren(box);
    if (props.error) { tree.append(h('p', { role: 'alert' }, props.error)); return finish(); }
    if (props.loading && props.files.length === 0) { tree.append(h('p', { class: 'muted' }, '読み込み中…')); return finish(); }

    // 状態：ファイル → 種類
    const s = props.status || {};
    const kinds = new Map();
    const note = (list, kind) => { for (const path of list || []) { if (!kinds.has(path)) kinds.set(path, []); kinds.get(path).push(kind); } };
    note(s.conflicted, 'conflicted'); note(s.staged, 'staged'); note(s.unstaged, 'unstaged'); note(s.untracked, 'untracked');
    const missing = new Set(props.missing || []);
    const classOf = (path) => {
      const of = kinds.get(path) || [];
      if (missing.has(path)) return 'deleted';
      if (of.includes('conflicted')) return 'conflicted';
      if (of.includes('untracked')) return 'untracked';
      if (of.includes('unstaged')) return 'modified';
      if (of.includes('staged')) return 'staged';
      return '';
    };

    // サブプロジェクトのフォルダー（あれば、その中だけを出す。README は出す）
    const projects = new Map();
    for (const item of props.projects || []) {
      const project = typeof item === 'string' ? { name: item, directory: item } : item;
      const directory = String(project.directory || project.name || '').replace(/\/+$/, '');
      if (directory) projects.set(directory, project);
    }
    const roots = [...projects.keys()];
    const shown = (path) => roots.length === 0 || isReadme(path) || roots.some((top) => (path === top || path.startsWith(top + '/'))
      && !path.slice(top.length).split('/').some((name) => name.startsWith('.')));

    // 木を作る
    const top = { dirs: new Map(), files: [] };
    const nodeFor = (dir) => {
      let at = top;
      if (!dir) return at;
      for (const name of dir.split('/')) { if (!at.dirs.has(name)) at.dirs.set(name, { dirs: new Map(), files: [] }); at = at.dirs.get(name); }
      return at;
    };
    const all = new Set([...props.files, ...[...kinds.keys()].filter((path) => !path.endsWith('/'))]);
    for (const path of all) if (shown(path) && (showGenerated || !generated.has(path))) nodeFor(dirOf(path)).files.push(path);
    const changedDirs = new Set();
    for (const path of kinds.keys()) path.split('/').slice(0, -1).forEach((_, i, names) => changedDirs.add(names.slice(0, i + 1).join('/')));
    const goneDirs = new Set();
    const filesUnder = (node) => [...node.files, ...[...node.dirs.values()].flatMap(filesUnder)];

    // 開閉（この PC に覚える）と、選んでいるもの（窓の中だけ）
    if (!state.folded) state.folded = new Set(memory.get('folded', []));
    if (!state.seen) state.seen = new Set(memory.get('seen', []));
    if (!state.chosen) state.chosen = new Set();
    const keep = () => { memory.set('folded', [...state.folded]); memory.set('seen', [...state.seen]); };
    if (props.selected && state.followed !== props.selected) {  // 変更の一覧で選んだファイルを、こちらでも選ぶ
      state.followed = props.selected;
      if (!state.chosen.has('f:' + props.selected)) { state.chosen = new Set(['f:' + props.selected]); state.anchor = 'f:' + props.selected; }
    }
    const order = [];  // 見えている順（Shift の範囲）
    const choose = (key, event) => {
      if (event && (event.ctrlKey || event.metaKey)) { if (state.chosen.has(key)) state.chosen.delete(key); else state.chosen.add(key); state.anchor = key; }
      else if (event && event.shiftKey && state.anchor) {
        const from = order.indexOf(state.anchor), to = order.indexOf(key);
        state.chosen = new Set(from < 0 || to < 0 ? [key] : order.slice(Math.min(from, to), Math.max(from, to) + 1));
      } else { state.chosen = new Set([key]); state.anchor = key; }
    };
    const chosenPaths = () => {
      const dirs = [...state.chosen].filter((key) => key.startsWith('d:')).map((key) => key.slice(2));
      const inside = (path) => dirs.some((dir) => path !== dir && path.startsWith(dir + '/'));
      return [...dirs.filter((dir) => !inside(dir)), ...[...state.chosen].filter((key) => key.startsWith('f:')).map((key) => key.slice(2)).filter((path) => !inside(path))];
    };
    const changesIn = (paths) => [...kinds.keys()].filter((path) => paths.some((at) => path === at || path.startsWith(at + '/')));
    const act = (name, path, more = {}) => emit('action', { name, path: path || '', paths: path ? [path] : [], ...more });
    const copy = (text) => { try { navigator.clipboard.writeText(text); } catch { /* 写せない環境 */ } };

    // その場で名前を変える欄
    const nameBox = (path) => {
      const input = h('input', { type: 'text', value: baseOf(path), 'aria-label': '新しい名前' });
      const error = h('small', { role: 'alert' });
      const stop = () => { state.renaming = null; redraw(); };
      input.addEventListener('keydown', (event) => {
        event.stopPropagation();
        if (event.key === 'Escape') { event.preventDefault(); stop(); return; }
        if (event.key !== 'Enter') return;
        event.preventDefault();
        const name = input.value.trim();
        if (!validName(name)) { error.textContent = '有効な名前を入力してください。'; return; }
        if (name === baseOf(path)) return stop();
        state.renaming = null;
        emit('action', { name: 'rename', path, paths: [path], to: join(dirOf(path), name) });
        redraw();
      });
      input.addEventListener('blur', () => { if (state.renaming) { state.renaming = null; redraw(); } });
      setTimeout(() => { input.focus(); const dot = input.value.lastIndexOf('.'); input.setSelectionRange(0, dot > 0 ? dot : input.value.length); }, 0);
      return h('div', { class: 'inline-name' }, input, error);
    };
    const startRename = (key) => { state.renaming = key; redraw(); };
    const slowRename = (key, event) => {  // 選んでいる1つをもう一度クリック：少し待って名前を変える（エクスプローラーと同じ）
      clearTimeout(state.timer);
      const again = state.chosen.size === 1 && state.chosen.has(key) && event.detail === 1 && !(event.ctrlKey || event.metaKey || event.shiftKey);
      if (again) state.timer = setTimeout(() => startRename(key), 500);
    };

    // メニュー
    const fileMenu = async (path, event) => {
      const of = kinds.get(path) || [], tracked = !of.includes('untracked'), exists = !missing.has(path), conflicted = of.includes('conflicted');
      const gone = exists ? {} : { disabled: true, reason: 'このファイルは、もうフォルダーにありません。' };
      const id = await menu(event, [
        { id: 'open_vs', label: 'Visual Studio で開く', ...gone }, { id: 'open_default', label: '既定のアプリで開く', ...gone },
        { id: 'reveal', label: 'エクスプローラーで表示', ...gone }, { separator: true },
        ...(isReadme(path) ? [] : [
          { id: 'rename', label: '名前の変更', hint: 'F2', ...gone }, { id: 'move', label: '移動先を指定…', ...gone },
          { id: 'remove', label: '削除', hint: 'Delete', danger: true, ...gone }, { separator: true }]),
        ...(isTest(path, false) ? [{ id: 'run_test', label: 'テストを実行', ...gone }] : []),
        ...(/^src\/.+\.py$|\.(h|hpp|hh|hxx|c|cc|cpp|cxx)$/i.test(path) ? [{ id: 'make_test', label: 'テストを作成…', ...gone }] : []),
        ...(conflicted ? [{ id: 'resolve', label: '衝突を直す…' }, { id: 'take_current', label: '今の側を採る' }, { id: 'take_incoming', label: '入ってくる側を採る' }, { separator: true }] : []),
        { id: 'restore', label: '変更を元に戻す', disabled: !tracked || of.length === 0 || conflicted, reason: conflicted ? '衝突は「衝突を直す」で直します。' : '変更がありません。' },
        { id: 'ignore', label: '除外パターンに追加' }, { separator: true },
        { id: 'diff', label: '差分', disabled: of.length === 0, reason: '変更がありません。' },
        { id: 'log', label: 'ログ', disabled: !tracked, reason: 'まだ git の管理に入っていないファイルです。' },
        { id: 'blame', label: '注釈履歴', disabled: !tracked || !exists, reason: 'まだ git の管理に入っていないファイルです。' },
        { separator: true }, { id: 'copy', label: 'パスをコピー' },
      ]);
      if (id === 'rename') return startRename('f:' + path);
      if (id === 'copy') return copy(path);
      if (id) act(id, path);
    };
    const folderMenu = async (dir, event) => {
      const project = projects.get(dir);
      const id = await menu(event, [
        ...(isTest(dir, true) ? [{ id: 'run_test', label: 'テストを実行' }, { separator: true }] : []),
        { id: 'new_file', label: '新しいファイル' },
        ...(dir && !project ? [{ id: 'rename', label: '名前の変更', hint: 'F2' }, { id: 'remove', label: '削除', hint: 'Delete', danger: true }] : []),
        { separator: true }, { id: 'reveal', label: 'エクスプローラーで開く' }, { id: 'log', label: 'ログ' },
        ...(dir ? [{ id: 'ignore', label: '除外パターンに追加' }, { id: 'copy', label: 'パスをコピー' }] : []),
        { separator: true }, { id: 'reload', label: '読み直す' },
      ]);
      if (id === 'rename') return startRename('d:' + dir);
      if (id === 'copy') return copy(dir);
      if (id === 'ignore') return act('ignore', dir + '/');
      if (id) act(id, dir);
    };
    const chosenMenu = async (event) => {
      const paths = chosenPaths(), changed = changesIn(paths);
      const restorable = changed.filter((path) => !(kinds.get(path) || []).includes('untracked'));
      const id = await menu(event, [
        { id: 'remove', label: `選んだ ${state.chosen.size} 件を削除`, hint: 'Delete', danger: true },
        { id: 'restore', label: `変更を元に戻す（${restorable.length} 件）…`, disabled: restorable.length === 0, reason: '変更がありません。' },
        { separator: true },
        { id: 'commit', label: `コミットの対象にする（${changed.length} 件）`, disabled: changed.length === 0, reason: '変更がありません。' },
        { id: 'copy', label: 'パスをコピー' },
      ]);
      if (id === 'copy') return copy(paths.join('\n'));
      if (id === 'remove') emit('action', { name: 'remove', path: '', paths });
      if (id === 'restore') emit('action', { name: 'restore', path: '', paths: restorable });
      if (id === 'commit') emit('action', { name: 'commit', path: '', paths: changed });
    };
    const openMenu = (key, event) => {
      event.preventDefault(); event.stopPropagation();
      if (state.chosen.size > 1 && state.chosen.has(key)) return chosenMenu(event);
      state.chosen = new Set([key]); state.anchor = key; paint();
      return key.startsWith('f:') ? fileMenu(key.slice(2), event) : folderMenu(key.slice(2), event);
    };
    const below = (element) => { const r = element.getBoundingClientRect(); return { clientX: r.left + 20, clientY: r.bottom }; };
    const keys = (key, element) => (event) => {
      if (event.target.matches && event.target.matches('input')) return;
      const path = key.slice(2), file = key.startsWith('f:');
      if (event.key === 'F2' && path && !(file && isReadme(path)) && !projects.has(path)) { event.preventDefault(); startRename(key); }
      if (event.key === 'Delete' && path) {
        event.preventDefault();
        if (state.chosen.size > 1 && state.chosen.has(key)) emit('action', { name: 'remove', path: '', paths: chosenPaths() });
        else if (!(file && isReadme(path)) && !projects.has(path)) act('remove', path);
      }
      if (event.key === 'Enter' && file) { event.preventDefault(); if (kinds.has(path)) act('diff', path); }
      if (event.key === 'Escape') { state.chosen = new Set(); state.anchor = ''; paint(); }
      if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) openMenu(key, { ...below(element), preventDefault() {}, stopPropagation() {} });
    };

    // 描く
    const rows = new Map();  // キー → 行の要素（選んだ印を付け直す）
    const paint = () => { for (const [key, element] of rows) element.classList.toggle('chosen', state.chosen.has(key)); };
    const walk = (node, parent, prefix) => {
      for (const [name, child] of [...node.dirs].sort(([a], [b]) => a.localeCompare(b))) {
        const dir = join(prefix, name), key = 'd:' + dir;
        if (name.startsWith('.') && !state.seen.has(dir)) state.folded.add(dir);  // 道具のフォルダーは、初めは閉じておく
        state.seen.add(dir);
        const under = filesUnder(child);
        if (under.length && under.every((path) => missing.has(path))) goneDirs.add(dir);
        const folder = h('details', {});
        folder.open = !state.folded.has(dir);
        const project = projects.get(dir);
        const title = h('summary', { title: (project ? `サブプロジェクト ${project.name}：` : 'フォルダ：') + dir });
        const caret = h('span', { class: 'tree-caret', 'aria-hidden': 'true' }, '▸');
        if (project) {
          const kind = PROJECT_KINDS[project.kind] || project.kind || '';
          title.append(caret, h('span', { class: 'tree-icon project', 'aria-hidden': 'true' }, '◆'), h('span', { class: 'tree-name' }, name));
          if (project.name && project.name !== name) title.append(h('span', { class: 'tree-sub' }, project.name));
          if (kind) title.append(h('span', { class: 'tree-kind ' + (project.kind || '') }, kind));
          title.classList.add('project');
        } else {
          const icon = h('span', { class: 'tree-icon folder', 'aria-hidden': 'true' });
          icon.innerHTML = FOLDER_ICON;
          title.append(caret, icon, h('span', { class: 'tree-name' }, name));
        }
        if (changedDirs.has(dir)) title.classList.add('has-changes');
        if (goneDirs.has(dir)) { title.classList.add('deleted'); title.title += '（削除）'; }
        order.push(key); rows.set(key, title);
        title.addEventListener('click', (event) => {
          state.directory = dir;
          if (event.detail > 0 && !event.target.closest('.tree-caret')) {  // 三角の外：選ぶだけ（開閉は三角かダブルクリック）
            event.preventDefault();
            if (!project) slowRename(key, event);
            choose(key, event); paint();
          }
        });
        title.addEventListener('dblclick', (event) => { clearTimeout(state.timer); if (!event.target.closest('.tree-caret')) folder.open = !folder.open; });
        title.addEventListener('contextmenu', (event) => openMenu(key, event));
        title.addEventListener('keydown', keys(key, title));
        folder.addEventListener('toggle', () => { if (folder.open) state.folded.delete(dir); else state.folded.add(dir); keep(); });
        if (state.renaming === key) { parent.append(nameBox(dir)); continue; }
        folder.append(title);
        walk(child, folder, dir);
        parent.append(folder);
      }
      for (const path of [...new Set(node.files)].sort((a, b) => a.localeCompare(b))) {
        const key = 'f:' + path;
        if (state.renaming === key) { parent.append(nameBox(path)); continue; }
        const cls = classOf(path);
        const mark = cls === 'untracked' ? '+ ' : cls === 'staged' ? '✓ ' : cls ? '• ' : '';
        const icon = h('span', { class: 'tree-icon', 'aria-hidden': 'true' });
        icon.innerHTML = FILE_ICON;
        const made = generated.has(path);
        const row = h('button', { type: 'button', class: 'file ' + cls + (made ? ' generated' : ''),
          title: path + (cls ? '（' + STATE_LABEL[cls] + '）' : '') + (made ? '　生成ファイル：道具が作り直します（手で編集しません）' : '') }, icon, mark + baseOf(path));
        order.push(key); rows.set(key, row);
        row.addEventListener('click', (event) => {
          slowRename(key, event);
          state.directory = dirOf(path);
          choose(key, event); paint();
          if (!(event.ctrlKey || event.metaKey || event.shiftKey) && props.selected !== path) { state.followed = path; emit('selected', { path }); }
        });
        // ダブルクリック：開く（開発の道具で。もうフォルダーにないファイルは、差分）
        row.addEventListener('dblclick', () => { clearTimeout(state.timer); if (!missing.has(path)) act('open', path); else if (kinds.has(path)) act('diff', path); });
        row.addEventListener('contextmenu', (event) => openMenu(key, event));
        row.addEventListener('keydown', keys(key, row));
        parent.append(row);
      }
    };
    walk(top, tree, '');
    keep();
    if (!tree.childElementCount) tree.append(h('p', { class: 'muted' }, props.empty_text));
    tree.addEventListener('click', (event) => { if (event.target === tree) { state.chosen = new Set(); state.anchor = ''; paint(); } });
    tree.addEventListener('contextmenu', (event) => { if (event.target === tree) { event.preventDefault(); folderMenu('', event); } });
    paint();
    const scroll = state.scroll || 0;
    tree.addEventListener('scroll', () => { state.scroll = tree.scrollTop; });
    finish();
    tree.scrollTop = scroll;
  },
};
