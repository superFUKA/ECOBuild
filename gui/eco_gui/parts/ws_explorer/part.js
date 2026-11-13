// 部品「作業空間のエクスプローラー」。今までの GUI（gui/static/explorer.js）と同じ見え方：
// フォルダーは ▸ とアイコン、サブプロジェクトのフォルダーは ◆ と種類の印、ファイルは状態の色と印
// （+ 新しい・• 変更・✓ ステージ済み・衝突は赤の太字・削除は取り消し線）。変更を含むフォルダーは橙。
// クリックで選ぶ（Ctrl で足す・外す、Shift で範囲）。右クリック・F2・Delete・Enter。名前はその場で変える。
// ドラッグで、ファイル・フォルダーを別のフォルダーへ動かす（1つずつ）。開閉はこの PC に覚える。「.」で始まるフォルダーは、初めは閉じておく。
// ファイルのメニューは、変更の一覧と同じもの（lib.ws.fileMenu）。
const FOLDER_ICON = '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M1.5 3.5h4.2l1.5 1.5h7.3v8.5h-13z" fill="currentColor" fill-opacity=".25" stroke="currentColor" stroke-linejoin="round"/></svg>';
const FILE_ICON = '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M3.5 1.5h6l3 3v10h-9z" fill="none" stroke="currentColor" stroke-linejoin="round"/><path d="M9.5 1.5v3h3" fill="none" stroke="currentColor" stroke-linejoin="round"/></svg>';
const TOOL_ICONS = {
  new_file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14h6"/>',
  new_folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
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
const validName = (name) => name && !BAD_NAME.test(name) && !/[. ]$/.test(name);

export default {
  render(root, props, { h, emit, state, redraw, memory, menu, notice, lib }) {
    const { isReadme, isTest } = lib.ws;
    const svg = (inner, size = 15) => {
      const box = h('span', { class: 'icon', 'aria-hidden': 'true' });
      box.innerHTML = inner.startsWith('<svg') ? inner
        : `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
      return box;
    };
    // ファイルを変える操作は、タスクブランチで（提出の確認中は変えない）。ほかでは灰色と理由（前の GUI と同じ）
    const st = props.status || {};
    const lockReason = st.task && !st.reviewing ? '' : st.reviewing ? '提出を確認している間は変えられません。'
      : 'ファイルを変える操作はタスクブランチで行います（タスク管理で「作業を開始」）。';
    const locked = lockReason ? { disabled: true, reason: lockReason } : {};
    // 新しいフォルダ：その場で名前を打つ欄を出す（開いておくのは、木を作るとき）
    const startFolder = (dir) => { if (lockReason) return; state.creating = dir; state.unfoldFor = dir; redraw(); };
    const tool = (name, title, lockable, onClick) => {
      const button = h('button', { type: 'button', title: lockable && lockReason ? lockReason : title, 'aria-label': title }, svg(TOOL_ICONS[name]));
      if (lockable && lockReason) button.disabled = true;
      button.addEventListener('click', onClick || (() => emit('action', { name, path: state.directory || '', paths: [] })));
      return button;
    };
    // 生成ファイル（道具が作り直すもの）は、ふだんは隠す。目の印・フォルダーのメニューで出す（この PC に覚える）
    const generated = new Set(props.generated || []);
    const showGenerated = memory.get('generated', false) === true;
    const toggleGenerated = () => { memory.set('generated', !showGenerated); redraw(); };
    const tools = h('span', { class: 'explorer-tools' }, tool('new_file', '新しいファイル', true),
      tool('new_folder', '新しいフォルダ', true, () => startFolder(state.directory || '')));
    if (generated.size) {
      const title = showGenerated ? '生成ファイル（CMakeLists.txt 等）を隠す' : '生成ファイル（CMakeLists.txt 等）も表示';
      const eye = h('button', { type: 'button', title, 'aria-label': '生成ファイルの表示', 'aria-pressed': String(showGenerated) }, svg(TOOL_ICONS[showGenerated ? 'eye_on' : 'eye_off']));
      eye.addEventListener('click', toggleGenerated);
      tools.append(eye);
    }
    // C++：ソリューション（.sln）と生成ファイルを、今の構成で作り直す（ecobuild project update。外のエディター・コンテナで変えたとき）
    if (props.module_type === 'cpp') {
      const sln = h('button', { type: 'button', class: 'sln', title: lockReason || 'ソリューション（.sln）と生成ファイルを今の構成で作り直す' }, 'SLN');
      if (lockReason) sln.disabled = true;
      sln.addEventListener('click', () => emit('action', { name: 'sln', path: '', paths: [] }));
      tools.append(sln);
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
    const projectList = lib.ws.projects(props.projects);
    const projects = new Map(projectList.filter((project) => project.top).map((project) => [project.top, project]));
    const roots = [...projects.keys()];
    const shown = (path) => roots.length === 0 || isReadme(path) || roots.some((top) => (path === top || path.startsWith(top + '/'))
      && !path.slice(top.length).split('/').some((name) => name.startsWith('.')));

    // 開閉（この PC に覚える）と、選んでいるもの（窓の中だけ）
    if (!state.folded) state.folded = new Set(memory.get('folded', []));
    if (!state.seen) state.seen = new Set(memory.get('seen', []));
    if (!state.chosen) state.chosen = new Set();
    if (!state.folders) state.folders = new Set();  // 新しいフォルダ（中にファイルを作ると、git の一覧に出る）
    const keep = () => { memory.set('folded', [...state.folded]); memory.set('seen', [...state.seen]); };
    const unfold = (path) => { const names = path.split('/'); for (let i = 1; i < names.length; i += 1) state.folded.delete(names.slice(0, i).join('/')); };
    if (state.unfoldFor !== undefined) { if (state.unfoldFor) unfold(state.unfoldFor + '/x'); state.unfoldFor = undefined; }
    // 作った（made：選んで開く）・動かした（moved：選ぶ）ファイルを、木で選ぶ（前の GUI と同じ）。済んだら知らせて、値を空にしてもらう
    const made = (props.made || []).filter(Boolean), moved = props.moved || '';
    const told = JSON.stringify([made, moved]);
    if ((made.length || moved) && state.told !== told) {
      const path = made.length ? made[made.length - 1] : moved;
      state.told = told;
      state.chosen = new Set(['f:' + path]); state.anchor = 'f:' + path; state.followed = path; state.directory = dirOf(path); state.reveal = path;
      unfold(path);
      emit('action', { name: 'revealed', path, paths: [path] });
      emit('selected', { path });
      if (made.length) emit('action', { name: 'open', path, paths: [path] });
    }
    if (!made.length && !moved) state.told = '';
    if (props.selected && state.followed !== props.selected) {  // 変更の一覧で選んだファイルを、こちらでも選ぶ
      state.followed = props.selected;
      if (!state.chosen.has('f:' + props.selected)) { state.chosen = new Set(['f:' + props.selected]); state.anchor = 'f:' + props.selected; }
    }

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
    for (const dir of state.folders) { if (props.files.some((path) => path.startsWith(dir + '/'))) state.folders.delete(dir); else nodeFor(dir); }
    const changedDirs = new Set();
    for (const path of kinds.keys()) path.split('/').slice(0, -1).forEach((_, i, names) => changedDirs.add(names.slice(0, i + 1).join('/')));
    const goneDirs = new Set();
    const filesUnder = (node) => [...node.files, ...[...node.dirs.values()].flatMap(filesUnder)];

    const order = [];  // 見えている順（Shift の範囲）
    const choose = (key, event) => {
      if (event && (event.ctrlKey || event.metaKey)) { if (state.chosen.has(key)) state.chosen.delete(key); else state.chosen.add(key); state.anchor = key; }
      else if (event && event.shiftKey && state.anchor) {
        const from = order.indexOf(state.anchor), to = order.indexOf(key);
        state.chosen = new Set(from < 0 || to < 0 ? [key] : order.slice(Math.min(from, to), Math.max(from, to) + 1));
      } else { state.chosen = new Set([key]); state.anchor = key; }
    };
    const chosenItems = () => {
      const dirs = [...state.chosen].filter((key) => key.startsWith('d:')).map((key) => key.slice(2));
      const inside = (path) => dirs.some((dir) => path !== dir && path.startsWith(dir + '/'));
      return { dirs: dirs.filter((dir) => !inside(dir)), files: [...state.chosen].filter((key) => key.startsWith('f:')).map((key) => key.slice(2)).filter((path) => !inside(path) && !isReadme(path)) };
    };
    const chosenPaths = () => { const { dirs, files } = chosenItems(); return [...dirs, ...files]; };
    const changesIn = (paths) => [...kinds.keys()].filter((path) => paths.some((at) => !at || path === at || path.startsWith(at + '/')));
    const act = (name, path, more = {}) => emit('action', { name, path: path || '', paths: path ? [path] : [], ...more });
    const copy = (text) => { try { navigator.clipboard.writeText(text).then(() => notice('コピーしました。'), () => notice('コピーできませんでした。', 'error')); } catch { /* 写せない環境 */ } };

    // その場で名前を決める欄（名前の変更・新しいフォルダ）
    const nameBox = (path, folder) => {
      const input = h('input', { type: 'text', value: folder ? '' : baseOf(path), placeholder: folder ? 'フォルダ名' : '', 'aria-label': folder ? 'フォルダ名' : '新しい名前' });
      const error = h('small', { role: 'alert' });
      const stop = () => { state.renaming = null; state.creating = null; redraw(); };
      input.addEventListener('keydown', (event) => {
        event.stopPropagation();
        if (event.key === 'Escape') { event.preventDefault(); stop(); return; }
        if (event.key !== 'Enter' || event.isComposing) return;
        event.preventDefault();
        const name = input.value.trim();
        if (!validName(name)) { error.textContent = '有効な名前を入力してください。'; return; }
        if (folder) {
          const dir = join(path, name);
          if (all.has(dir) || [...all].some((p) => p.startsWith(dir + '/')) || state.folders.has(dir)) { error.textContent = `${dir} は既にあります。`; return; }
          state.folders.add(dir); state.creating = null; unfold(dir + '/x');
          state.chosen = new Set(['d:' + dir]); state.anchor = 'd:' + dir; state.directory = dir;
          notice(`フォルダ ${dir} を用意しました。中にファイルを作ると、できます。`);
          redraw();
          return;
        }
        if (name === baseOf(path)) return stop();
        state.renaming = null;
        emit('action', { name: 'rename', path, paths: [path], to: join(dirOf(path), name) });
        redraw();
      });
      input.addEventListener('blur', () => { if (state.renaming || state.creating !== null && state.creating !== undefined) { state.renaming = null; state.creating = null; redraw(); } });
      setTimeout(() => { input.focus(); const dot = input.value.lastIndexOf('.'); input.setSelectionRange(0, dot > 0 ? dot : input.value.length); }, 0);
      return h('div', { class: 'inline-name' }, input, error);
    };
    const startRename = (key) => { state.renaming = key; redraw(); };
    const slowRename = (key, event) => {  // 選んでいる1つをもう一度クリック：少し待って名前を変える（エクスプローラーと同じ）
      clearTimeout(state.timer);
      const again = !lockReason && state.chosen.size === 1 && state.chosen.has(key) && event.detail === 1 && !(event.ctrlKey || event.metaKey || event.shiftKey);
      if (again) state.timer = setTimeout(() => startRename(key), 500);
    };

    // メニュー
    const fileContext = (path) => ({ kinds: kinds.get(path) || [], exists: !missing.has(path), locked, projects: projectList, files: props.files, vs: props.vs_version || '', inline: true });
    const fileMenu = async (path, event) => {
      const ctx = fileContext(path);
      const id = await menu(event, lib.ws.fileMenu(path, ctx));
      if (id === 'rename') return startRename('f:' + path);
      if (id === 'copy') return copy(path);
      lib.ws.fileAction(id, path, ctx, emit);
    };
    // サブプロジェクトのフォルダー：Visual Studio のソリューション エクスプローラーと同じ（ビルド・テスト・実行・実行の対象）
    const projectMenu = async (dir, event) => {
      const project = projects.get(dir), kind = project.kind || '';
      const runnable = ['executable', 'app'].includes(kind), testing = ['test', 'benchmark', 'bench'].includes(kind);
      const id = await menu(event, [
        { id: 'project_build', label: 'ビルド' }, { id: 'project_rebuild', label: 'リビルド' }, { id: 'project_clean', label: 'クリーン' }, { separator: true },
        ...(testing ? [{ id: 'project_test', label: 'テストを実行' }] : []), ...(runnable ? [{ id: 'project_run', label: '実行' }] : []),
        { id: 'run_target', label: '実行の対象にする（▶ で動かす）' }, { separator: true },
        { id: 'new_file', label: '新しいファイル', ...locked }, { id: 'new_folder', label: '新しいフォルダ', ...locked }, { separator: true },
        { id: 'reveal', label: 'エクスプローラーで表示' }, { id: 'log', label: 'ログ' }, { separator: true },
        { id: 'project_move', label: '移動…', ...locked }, { id: 'project_remove', label: 'Projectを削除…', danger: true, ...locked },
        { id: 'project_settings', label: 'Projectの設定（リンク等）' },
      ]);
      if (id === 'new_folder') return startFolder(dir);
      if (id) act(id, dir, { project: project.name });
    };
    const folderMenu = async (dir, event) => {
      if (projects.has(dir)) return projectMenu(dir, event);
      const id = await menu(event, [
        ...(isTest(dir, true) ? [{ id: 'run_test', label: 'テストを実行' }, { separator: true }] : []),
        { id: 'new_file', label: '新しいファイル', ...locked }, { id: 'new_folder', label: '新しいフォルダ', ...locked },
        ...(dir ? [{ id: 'rename', label: '名前の変更', hint: 'F2', ...locked }, { id: 'remove', label: '削除', hint: 'Delete', danger: true, ...locked }] : []),
        { separator: true }, { id: 'reveal', label: 'エクスプローラーで表示' }, { id: 'log', label: 'ログ' },
        ...(dir ? [{ id: 'ignore', label: '除外パターンに追加', ...locked }, { id: 'copy', label: 'パスをコピー' }] : []),
        { separator: true },
        ...(generated.size ? [{ id: 'generated', label: showGenerated ? '生成ファイルを隠す' : '生成ファイルを表示' }] : []),
        { id: 'reload', label: '読み直す' },
      ]);
      if (id === 'rename') return startRename('d:' + dir);
      if (id === 'new_folder') return startFolder(dir);
      if (id === 'generated') return toggleGenerated();
      if (id === 'copy') return copy(dir);
      if (id === 'ignore') return act('ignore', dir + '/');
      if (id) act(id, dir);
    };
    const chosenMenu = async (event) => {
      const { dirs, files } = chosenItems(), paths = [...dirs, ...files], changed = changesIn(paths);
      const existing = files.filter((path) => !missing.has(path));
      const restorable = changed.filter((path) => !(kinds.get(path) || []).includes('untracked'));
      const none = { disabled: existing.length === 0, reason: '選んだ中にファイルがありません（フォルダだけ）。' };
      const id = await menu(event, [
        { id: 'open_all', label: `Visual Studio${props.vs_version ? ' ' + props.vs_version : ''} で開く（${existing.length} 件）`, ...none },
        { id: 'open_default_all', label: `既定のアプリで開く（${existing.length} 件）`, ...none }, { separator: true },
        { id: 'remove', label: `選んだ ${state.chosen.size} 件を削除`, hint: 'Delete', danger: true, ...locked },
        { id: 'restore', label: `変更を元に戻す（${restorable.length} 件）…`, disabled: restorable.length === 0, reason: '変更がありません。', ...locked },
        { separator: true },
        { id: 'commit', label: `コミットの対象にする（${changed.length} 件）`, disabled: changed.length === 0, reason: '変更がありません。', ...locked },
        { id: 'copy', label: 'パスをコピー' },
      ]);
      if (id === 'copy') return copy(paths.join('\n'));
      if (id === 'open_all' || id === 'open_default_all') emit('action', { name: id, path: '', paths: existing });
      if (id === 'remove') emit('action', { name: 'remove', path: '', paths: chosenPaths() });
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
      if ((event.key === 'F2' || event.key === 'Delete') && path && file && isReadme(path)) {
        event.preventDefault();
        notice('README はモジュールの一番上に置くファイルです（名前の変更・移動・削除はしません。開いて編集はできます）。');
        return;
      }
      if ((event.key === 'F2' || event.key === 'Delete') && path && projects.has(path) && !(event.key === 'Delete' && state.chosen.size > 1)) {
        event.preventDefault();
        notice('Projectのフォルダは、右クリックの「移動…」「Projectを削除…」で移す・削除します（ビルドの設定も変わるため）。');
        return;
      }
      if (event.key === 'F2' && path && !lockReason) { event.preventDefault(); startRename(key); }
      if (event.key === 'Delete' && path && !lockReason) {
        event.preventDefault();
        if (state.chosen.size > 1 && state.chosen.has(key)) emit('action', { name: 'remove', path: '', paths: chosenPaths() });
        else act('remove', path);
      }
      // Enter：ダブルクリックと同じ（開発の道具で開く。もうフォルダーにないファイルは、差分）
      if (event.key === 'Enter' && file) { event.preventDefault(); if (!missing.has(path)) act('open', path); else if (kinds.has(path)) act('diff', path); }
      if (event.key === 'Escape') { state.chosen = new Set(); state.anchor = ''; paint(); }
      if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) openMenu(key, { ...below(element), preventDefault() {}, stopPropagation() {} });
    };

    // ドラッグで動かす（ファイル・フォルダーを、別のフォルダーへ。1つずつ。サブプロジェクトのフォルダーは「移動…」で）
    const dragStart = (key) => (event) => {
      const path = key.slice(2);
      if (lockReason || state.renaming || (key.startsWith('f:') && isReadme(path)) || projects.has(path)) { event.preventDefault(); return; }
      clearTimeout(state.timer);
      if (state.chosen.size > 1 && state.chosen.has(key)) {
        event.preventDefault();
        notice('ドラッグで動かせるのは1つずつです（選んだものをまとめて動かすことは、まだできません）。', 'error');
        return;
      }
      state.dragging = path;
      try { event.dataTransfer.setData('text/plain', path); event.dataTransfer.effectAllowed = 'move'; } catch { /* 写せない環境 */ }
    };
    const dropInto = (dir) => {
      const path = state.dragging;
      if (path === null || path === undefined || dir === null) return null;
      if (dir === path || dir.startsWith(path + '/') || dirOf(path) === dir || (roots.length && !shown(dir)) || goneDirs.has(dir)) return null;
      return dir;
    };
    const clearTargets = () => { for (const element of tree.querySelectorAll('.drop-target')) element.classList.remove('drop-target'); };
    const dropTarget = (dir, element) => {
      element.addEventListener('dragover', (event) => {
        const files = [...((event.dataTransfer && event.dataTransfer.types) || [])].includes('Files');
        if (files) { event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'none'; return; }
        if (dropInto(dir) === null) return;
        event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'move';
        clearTargets(); element.classList.add('drop-target');
      });
      element.addEventListener('drop', (event) => {
        event.preventDefault(); event.stopPropagation(); clearTargets();
        if (![...((event.dataTransfer && event.dataTransfer.types) || [])].includes('Files')) {
          const into = dropInto(dir), path = state.dragging;
          state.dragging = null;
          if (into !== null) emit('action', { name: 'drop_move', path, paths: [path], to: join(into, baseOf(path)) });
          return;
        }
        notice('外からのファイルの取り込みは、まだできません。Windows のエクスプローラーで、作業空間のフォルダーに置いてください。', 'error');
      });
    };

    // 描く
    const rows = new Map();  // キー → 行の要素（選んだ印を付け直す）
    const paint = () => { for (const [key, element] of rows) element.classList.toggle('chosen', state.chosen.has(key)); };
    const walk = (node, parent, prefix) => {
      if (state.creating === prefix && (prefix === '' ? parent === tree : true)) parent.append(nameBox(prefix, true));
      for (const [name, child] of [...node.dirs].sort(([a], [b]) => a.localeCompare(b))) {
        const dir = join(prefix, name), key = 'd:' + dir;
        if (name.startsWith('.') && !state.seen.has(dir)) state.folded.add(dir);  // 道具のフォルダーは、初めは閉じておく
        state.seen.add(dir);
        const under = filesUnder(child);
        if (under.length && under.every((path) => missing.has(path))) goneDirs.add(dir);
        const folder = h('details', {});
        folder.open = !state.folded.has(dir);
        const project = projects.get(dir);
        const pending = state.folders.has(dir);
        const title = h('summary', { title: (project ? `サブプロジェクト ${project.name}：` : 'フォルダ：') + dir + (pending ? '（中にファイルを作ると、できます）' : '') });
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
          if (pending) title.classList.add('pending');
        }
        if (changedDirs.has(dir)) title.classList.add('has-changes');
        if (goneDirs.has(dir)) { title.classList.add('deleted'); title.title += '（削除）'; }
        title.draggable = !project && !goneDirs.has(dir) && !lockReason && !pending;
        order.push(key); rows.set(key, title);
        title.addEventListener('click', (event) => {
          state.directory = dir;
          if (event.detail > 0 && !event.target.closest('.tree-caret')) {  // 三角の外：選ぶだけ（開閉は三角かダブルクリック）
            event.preventDefault();
            if (!project && !pending) slowRename(key, event);
            choose(key, event); paint();
          }
        });
        title.addEventListener('dblclick', (event) => { clearTimeout(state.timer); if (!event.target.closest('.tree-caret')) folder.open = !folder.open; });
        title.addEventListener('contextmenu', (event) => openMenu(key, event));
        title.addEventListener('keydown', keys(key, title));
        title.addEventListener('dragstart', dragStart(key));
        title.addEventListener('dragend', () => { state.dragging = null; clearTargets(); });
        dropTarget(dir, title);
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
        row.draggable = !lockReason && !isReadme(path) && !missing.has(path);
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
        row.addEventListener('dragstart', dragStart(key));
        row.addEventListener('dragend', () => { state.dragging = null; clearTargets(); });
        dropTarget(dirOf(path), row);
        parent.append(row);
      }
    };
    walk(top, tree, '');
    keep();
    if (!tree.childElementCount) tree.append(h('p', { class: 'muted' }, props.empty_text));
    tree.addEventListener('click', (event) => { if (event.target === tree) { state.chosen = new Set(); state.anchor = ''; paint(); } });
    tree.addEventListener('contextmenu', (event) => { if (event.target === tree) { event.preventDefault(); folderMenu(roots.length ? (state.directory && shown(state.directory) ? state.directory : roots[0]) : '', event); } });
    dropTarget(roots.length ? null : '', tree);  // 空いている所：一番上へ（サブプロジェクトのある型では、どこにも置けない）
    paint();
    const scroll = state.scroll || 0;
    tree.addEventListener('scroll', () => { state.scroll = tree.scrollTop; });
    finish();
    tree.scrollTop = scroll;
    if (state.reveal) {  // 作った・動かしたファイルを見えるところへ
      const at = rows.get('f:' + state.reveal);
      if (at) { state.reveal = null; at.scrollIntoView({ block: 'nearest' }); }
    }
  },
};
