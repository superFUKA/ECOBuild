'use strict';
// Explorer: the files of this place (listed by the GUI: git's tracked and untracked files, plus empty folders).
// File operations run ecobuild (file add / move / remove, restore, ignore, diff, log, blame); new folders are made by the GUI.
const folded = new Set(), opened = new Set();
let activeDirectory = '';
const tree = get('file-tree'), menu = get('file-menu');

// File operations (ecobuild file add / move / remove) work inside the Projects' folders only, so when the module type
// has Projects (project list), the explorer shows only those folders, without tool folders (.cppbuild 等) inside.
// Types without Projects (generic) show the whole place.
let projectRoots = null, projectsByDir = new Map();   // directory → the Project (project list: name, kind)
// Ordinary folders and files: an icon before the name (as in Explorer).
const FOLDER_ICON = '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M1.5 3.5h4.2l1.5 1.5h7.3v8.5h-13z" fill="currentColor" fill-opacity=".25" stroke="currentColor" stroke-linejoin="round"/></svg>';
const FILE_ICON = '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M3.5 1.5h6l3 3v10h-9z" fill="none" stroke="currentColor" stroke-linejoin="round"/><path d="M9.5 1.5v3h3" fill="none" stroke="currentColor" stroke-linejoin="round"/></svg>';
// How a Project folder is told apart from an ordinary folder: an icon and the kind of the Project.
const PROJECT_KINDS = {static_library: '静的ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', executable: '実行ファイル', test: 'テスト', benchmark: '性能測定'};
WS.reloadFiles = async () => {
  try {
    const [files, projects] = await Promise.all([ECO.call('files', {dir: WS.dir}), projectRoots ? null : WS.cli(['project', 'list'], {quiet: true})]);
    WS.files = files;
    if (projects) {
      const list = projects.ok ? projects.result.filter(p => p.directory) : [];
      projectRoots = list.map(p => p.directory.replace(/\/+$/, ''));
      projectsByDir = new Map(list.map(p => [p.directory.replace(/\/+$/, ''), p]));
    }
  } catch (e) { tree.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  renderTree(); WS.renderChanges();
};
const restricted = () => !!(projectRoots && projectRoots.length);
// The Project a path is in (the deepest Project folder that has it: the changes are shown per Project). null: in none,
// or the type has no Projects.
WS.projectOf = path => {
  let best = null;
  for (const root of projectRoots || []) {
    const top = root === '.' ? '' : root;
    if ((top === '' || path === top || path.startsWith(top + '/')) && (best === null || top.length > best.top.length)) best = {top, project: projectsByDir.get(root)};
  }
  return best && best.project ? {...best.project, top: best.top} : null;
};
WS.projectOrder = () => (projectRoots || []).map(root => projectsByDir.get(root)?.name).filter(Boolean);
// Inside a Project's source folders (src・include). A Project not telling its folders (an older ecobuild) is not checked.
const inSources = path => {
  const root = (projectRoots || []).find(r => path === r || path.startsWith(r + '/')), project = projectsByDir.get(root);
  if (!project) return false;
  if (!project.source_directories) return true;
  const rel = path.slice(root.length).replace(/^\//, '');
  return project.source_directories.some(s => rel === s || rel.startsWith(s + '/'));
};
// The module's README (at the top) is shown too, though it is in no Project: it is the module's own page to edit.
const isReadme = path => /^readme(\.[^/]*)?$/i.test(path);
const shown = path => !restricted() || isReadme(path) || projectRoots.some(root => {
  if (path !== root && !path.startsWith(root + '/')) return false;
  return !path.slice(root.length).split('/').some(part => part.startsWith('.'));
});
const editable = () => !!(WS.status && WS.status.task && !WS.status.reviewing);

function fileClass(path) {
  const kinds = WS.changes().get(path) || [];
  if (WS.files.missing.includes(path)) return 'deleted';
  if (kinds.includes('conflicted')) return 'conflicted';
  if (kinds.includes('untracked')) return 'untracked';
  if (kinds.includes('unstaged')) return 'modified';
  if (kinds.includes('staged')) return 'staged';
  return '';
}
function renderTree() {
  if (!WS.files) return;
  const rootNode = {dirs: new Map(), files: []};
  const nodeFor = dir => { let node = rootNode; if (!dir) return node; for (const part of dir.split('/')) { if (!node.dirs.has(part)) node.dirs.set(part, {dirs: new Map(), files: []}); node = node.dirs.get(part); } return node; };
  for (const d of WS.files.dirs) if (shown(d)) nodeFor(d);
  const changed = new Set(WS.changes().keys());
  const generated = new Set(WS.files.generated || []);
  const missingDirs = new Set(WS.files.missing_dirs || []);
  for (const f of new Set([...WS.files.files, ...[...changed].filter(p => !p.endsWith('/'))])) { if (!shown(f) || (generated.has(f) && !showGenerated)) continue; const i = f.lastIndexOf('/'); nodeFor(i < 0 ? '' : f.slice(0, i)).files.push(f); }
  const changedDirs = new Set([...changed].flatMap(p => p.split('/').slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join('/'))));
  const walk = (node, parent, prefix) => {
    for (const [name, child] of [...node.dirs].sort(([a], [b]) => a.localeCompare(b))) {
      const dir = prefix ? prefix + '/' + name : name;
      const folder = document.createElement('details'), title = document.createElement('summary');
      if (name.startsWith('.') && !opened.has(dir)) folded.add(dir);  // tool folders (.cppbuild 等) start closed
      opened.add(dir);
      folder.open = !folded.has(dir); folder.dataset.directory = dir;
      const project = projectsByDir.get(dir);
      if (project) {
        const kind = PROJECT_KINDS[project.kind] || project.kind || '';
        title.innerHTML = `<span class="tree-caret" aria-hidden="true">▸</span><span class="tree-icon project" aria-hidden="true">◆</span><span class="tree-name">${esc(name)}</span>${project.name !== name ? `<span class="tree-sub">${esc(project.name)}</span>` : ''}<span class="tree-kind ${esc(project.kind || '')}">${esc(kind)}</span>`;
        title.title = `Project ${project.name}（${kind}）：${dir}`; title.classList.add('project');
      } else {
        title.innerHTML = `<span class="tree-caret" aria-hidden="true">▸</span><span class="tree-icon folder" aria-hidden="true">${FOLDER_ICON}</span><span class="tree-name">${esc(name)}</span>`;
        title.title = `フォルダ：${dir}`;
      }
      // A folder that is gone (moved or deleted; git still knows its files, shown struck through) is struck through too.
      const gone = missingDirs.has(dir);
      title.dataset.directory = dir; title.draggable = !project && !gone;   // a Project's own folder moves with project move
      if (changedDirs.has(dir)) title.classList.add('has-changes');
      if (gone) { title.classList.add('deleted'); title.title += '（削除）'; }
      title.addEventListener('click', e => {
        activeDirectory = dir;
        if (e.detail > 0 && !e.target.closest('.tree-caret')) {   // not the triangle: choose only (again: rename)
          e.preventDefault(); slowRename('d:' + dir, e, () => !projectsByDir.has(dir) && renameFolder(dir)); choose('d:' + dir, e);
        }
      });
      title.addEventListener('dblclick', e => { cancelSlowRename(); if (!e.target.closest('.tree-caret')) folder.open = !folder.open; });
      title.addEventListener('keydown', e => {
        if (e.key === 'F2') { e.preventDefault(); e.stopPropagation(); renameFolder(dir); }
        if (e.key === 'Delete' && editable()) { e.preventDefault(); e.stopPropagation(); if (!chosen.has('d:' + dir)) choose('d:' + dir); removeChosen(); }
      });
      folder.addEventListener('toggle', () => { if (folder.open) folded.delete(dir); else folded.add(dir); });
      folder.append(title); walk(child, folder, dir); parent.append(folder);
    }
    for (const path of [...new Set(node.files)].sort((a, b) => a.localeCompare(b))) {
      const row = document.createElement('button'); row.type = 'button'; row.dataset.path = path; row.draggable = !isReadme(path);
      const cls = fileClass(path);
      row.className = 'file ' + cls + (WS.activeFile === path ? ' active' : '') + (generated.has(path) ? ' generated' : '');
      row.innerHTML = `<span class="tree-icon" aria-hidden="true">${FILE_ICON}</span>`;
      row.append((cls === 'untracked' ? '+ ' : cls && cls !== 'staged' ? '• ' : cls === 'staged' ? '✓ ' : '') + path.split('/').pop());
      row.title = path + (cls ? '（' + {deleted: '削除', conflicted: '衝突', untracked: '未追跡', modified: '変更', staged: 'ステージ済み'}[cls] + '）' : '') + (generated.has(path) ? '　生成ファイル：CppBuild が作り直すので、編集しないでください' : '');
      parent.append(row);
    }
  };
  tree.replaceChildren(); walk(rootNode, tree, '');
  if (!tree.childElementCount) tree.innerHTML = '<p class="muted">ファイルはありません。</p>';
  if (restricted() && (!activeDirectory || !shown(activeDirectory))) activeDirectory = projectRoots[0];
  get('new-file').disabled = get('new-folder').disabled = !editable();
  paintChosen();
}
WS.onRefresh(renderTree);
// Generated files (CppBuild's CMakeLists.txt etc.: rewritten by the tool, not to be edited) are hidden unless asked for.
let showGenerated = false;
try { showGenerated = localStorage.getItem('ecobuild-gui-show-generated') === '1'; } catch (e) { /* storage blocked */ }
const generatedButton = get('toggle-generated');
const showGeneratedState = () => { generatedButton.setAttribute('aria-pressed', String(showGenerated)); generatedButton.title = showGenerated ? '生成ファイル（CMakeLists.txt 等）を隠す' : '生成ファイル（CMakeLists.txt 等）も表示'; };
showGeneratedState();
generatedButton.addEventListener('click', () => {
  showGenerated = !showGenerated; showGeneratedState(); renderTree();
  try { localStorage.setItem('ecobuild-gui-show-generated', showGenerated ? '1' : '0'); } catch (e) { /* storage blocked */ }
});
// Update the solution (.sln) and the other generated files by hand (ecobuild project update: they are made from
// ecobuild.toml and the files; ecobuild does it after its own operations, this is for changes made elsewhere — in an
// editor, or inside the container: project update runs on this PC, for its Visual Studio).
const slnButton = get('refresh-sln');
ECO.moduleType(WS.dir).then(type => { slnButton.hidden = type !== 'cpp'; }).catch(() => {});
WS.onRefresh(() => { slnButton.disabled = !editable(); slnButton.title = editable() ? 'ソリューション（.sln）と生成ファイルを今の構成で作り直す' : why('sln'); });
slnButton.addEventListener('click', async () => {
  slnButton.disabled = true;
  try {
    const doc = await WS.cli(['project', 'update'], {quiet: true});
    if (!doc.ok) return ECO.toast('SLN を更新できませんでした：' + doc.error.message, 'bad', 10000);
    await WS.refresh(); await WS.reloadFiles();
    ECO.toast(doc.result.configured ? 'SLN（生成ファイル）を作り直しました。' : 'SLN は今のファイルのとおりです（作り直すものはありませんでした）。', 'ok', 6000);
  } finally { slnButton.disabled = !editable(); }
});
WS.selectInTree = path => { WS.activeFile = path; chosen.clear(); chosen.add('f:' + path); anchor = 'f:' + path; renderTree(); tree.querySelector(`[data-path="${CSS.escape(path)}"]`)?.scrollIntoView({block: 'nearest'}); };

tree.addEventListener('click', e => {
  const row = e.target.closest('[data-path]'); if (!row) return;
  // Only move the highlight: rebuilding the tree here would replace the row under the second click of a double-click,
  // and the dblclick (open in Visual Studio) would never arrive.
  const path = row.dataset.path;
  slowRename('f:' + path, e, () => !isReadme(path) && inlineName({rename: path}));
  WS.activeFile = path; activeDirectory = dirOf(path);
  choose('f:' + path, e);
  WS.renderChanges(); row.focus();
});

// What is chosen in the explorer: files (f:path) and folders (d:dir). A click chooses one; Ctrl adds or takes away;
// Shift chooses from the last one to this one (in the order shown). Delete and the menu act on all chosen.
const chosen = new Set();
let anchor = '';
const keyOfItem = el => el.dataset.path !== undefined ? 'f:' + el.dataset.path : 'd:' + el.dataset.directory;
const shownItems = () => [...tree.querySelectorAll('[data-path], summary[data-directory]')].filter(el => el.offsetParent);
function choose(key, e) {
  if (e?.ctrlKey || e?.metaKey) { if (chosen.has(key)) chosen.delete(key); else chosen.add(key); anchor = key; }
  else if (e?.shiftKey && anchor) {
    const keys = shownItems().map(keyOfItem), from = keys.indexOf(anchor), to = keys.indexOf(key);
    chosen.clear();
    if (from < 0 || to < 0) chosen.add(key);
    else for (const k of keys.slice(Math.min(from, to), Math.max(from, to) + 1)) chosen.add(k);
  } else { chosen.clear(); chosen.add(key); anchor = key; }
  paintChosen();
}
// A click on the one chosen item again (not a double-click, no Ctrl/Shift) renames it after a moment, as in Explorer.
let renameTimer = 0;
function cancelSlowRename() { clearTimeout(renameTimer); renameTimer = 0; }
function slowRename(key, e, start) {
  const again = chosen.size === 1 && chosen.has(key) && e.detail === 1 && !(e.ctrlKey || e.metaKey || e.shiftKey);
  cancelSlowRename();
  if (again && editable()) renameTimer = setTimeout(() => { renameTimer = 0; start(); }, 500);
}
// One highlight: what is chosen (the file shown as "active" is no separate mark; with a folder chosen, no file is).
function paintChosen() {
  for (const el of tree.querySelectorAll('[data-path], summary[data-directory]')) {
    const on = chosen.has(keyOfItem(el));
    el.classList.toggle('chosen', on);
    if (el.dataset.path !== undefined) el.classList.toggle('active', on && el.dataset.path === WS.activeFile);
  }
}
// Nothing chosen: a click on the empty part of the explorer, or Esc (as in Explorer).
function clearChosen() { chosen.clear(); anchor = ''; paintChosen(); }
tree.closest('aside').addEventListener('click', e => {
  if (!e.target.closest('[data-path], summary, input, button, .inline-name, #file-menu')) clearChosen();
});
tree.addEventListener('keydown', e => { if (e.key === 'Escape' && !e.target.matches('input')) clearChosen(); });
// The chosen ones, without those inside a chosen folder (they go with it).
function chosenItems() {
  const dirs = [...chosen].filter(k => k.startsWith('d:')).map(k => k.slice(2));
  const inside = p => dirs.some(d => p !== d && p.startsWith(d + '/'));
  return {dirs: dirs.filter(d => !inside(d)), files: [...chosen].filter(k => k.startsWith('f:')).map(k => k.slice(2)).filter(p => !inside(p) && !isReadme(p))};
}
async function removeChosen() {
  const {dirs, files} = chosenItems();
  if (!dirs.length && !files.length) return;
  const projects = dirs.filter(d => projectsByDir.has(d));
  if (projects.length) return ECO.toast(`Projectのフォルダ（${projects.join('・')}）は、「モジュール」→「Project」の「削除」で削除します。`, 'info', 7000);
  const tests = (files.length || dirs.length) && await typeHasFileTests();
  const list = [...dirs.map(d => d + '/'), ...files];
  const v = await ECO.form({title: `${list.length} 件を削除`, intro: esc(list.join('\n')).replaceAll('\n', '<br>') + '<br>を削除します（フォルダは中身ごと）。',
    fields: tests ? [{name: 'test', label: `${sourceTests(restricted())}なら、対応するテストも削除する`, type: 'checkbox', value: true}] : [], ok: '削除', danger: true});
  if (!v) return;
  if (files.length) {
    let doc = await WS.cli(['file', 'remove', ...files, ...(!tests || v.test ? [] : ['--no-test'])]);
    if (!doc.ok && doc.error?.code === 'not_supported') {
      for (const path of files) { doc = await withoutFileCommand(doc, 'remove-file', {path}); if (!doc.ok) break; }
    }
    if (!doc.ok) return ECO.showError(doc);
  }
  try { for (const dir of dirs) await removeFolder(dir, !tests || v.test); }
  catch (error) { ECO.toast(error.message, 'bad', 8000); }
  chosen.clear();
  await WS.refresh(); await afterFileChange(true, `削除しました：${list.join('、')}`);
}
tree.addEventListener('dblclick', e => { cancelSlowRename(); const row = e.target.closest('[data-path]'); if (row) openInEditor(row.dataset.path); });
const dirOf = path => path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
const openFile = (path, reveal = false) => ECO.action('folder', {dir: WS.dir, path, reveal}).catch(e => ECO.toast(e.message, 'bad'));
// Open a file in Visual Studio (the version chosen next to 「VS〜で開く」): in the one that has this module's solution open,
// or start it with the solution. Without Visual Studio, the file opens in its default app.
async function openInEditor(path) {
  try {
    const r = await ECO.action('vs', {dir: WS.dir, path, version: ECO.vsVersion()});
    say(r.started ? `Visual Studio ${ECO.vsVersion()} を起動して ${path} を開きます（起動に少しかかります）。` : `Visual Studio で ${path} を開きました。`);
  } catch (e) {
    say(e.message + ' 既定のアプリで開きます。');
    return openFile(path);
  }
}
WS.openInEditor = openInEditor;   // the output pane's file(line)

// Context menu ----------------------------------------------------------------------------------------
let returnFocus = null;
function closeMenu() { menu.hidden = true; }
const DANGER = new Set(['remove', 'remove-dir', 'remove-chosen', 'p-remove']);   // deleting: shown in red
// Menus: an operation that cannot be done here now (not a task branch, no change, ...) is grey; one that never applies to
// the item (a new file on a file, renaming README, blame on a folder) is not shown.
// Why an item is grey (the usual reasons; the menus pass false for these).
function why(key) {
  if (['rename', 'move', 'remove'].includes(key) && WS.activeFile && isReadme(WS.activeFile)) return 'README はモジュールの一番上に置くファイルです（名前の変更・移動・削除はしません。開いて編集はできます）。';
  if (['m-open', 'm-open-default'].includes(key)) return '選んだ中にファイルがありません（フォルダだけ）。';
  if (['log', 'blame'].includes(key)) return 'まだ git の管理に入っていないファイルです。';
  if (!editable()) return WS.status?.reviewing ? '提出を確認している間は変えられません。' : 'ファイルを変える操作はタスクブランチで行います（タスク管理で「作業を開始」）。';
  if (['restore', 'diff', 'm-restore', 'm-commit'].includes(key)) return '変更がありません。';
  if (key === 'm-move') return 'Projectのフォルダは「Project」の「移動」で移します。';
  return 'いまは使えません。';
}
function showMenu(items, x, y) {
  returnFocus = document.activeElement;
  // An item that cannot be used now is grey (still there); hovering it tells why (why). [key, label, enabled, shortcut]:
  // the shortcut shows at the right of the item.
  menu.innerHTML = items.map(item => item === '-' ? '<hr>' : `<button type="button" role="menuitem" data-menu="${item[0]}" ${DANGER.has(item[0]) ? 'class="danger"' : ''} ${item[2] === false ? `disabled title="${esc(why(item[0]))}"` : ''}><span>${esc(item[1])}</span>${item[3] ? `<kbd>${esc(item[3])}</kbd>` : ''}</button>`).join('');
  menu.hidden = false;
  menu.style.left = Math.max(8, Math.min(x, innerWidth - menu.offsetWidth - 8)) + 'px';
  menu.style.top = Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8)) + 'px';
  menu.querySelector('button:not(:disabled)')?.focus();
}
function fileMenu(path, x, y) {
  WS.activeFile = path; activeDirectory = dirOf(path); renderTree();
  const kinds = WS.changes().get(path) || [], tracked = !kinds.includes('untracked'), exists = !WS.files.missing.includes(path), can = editable();
  showMenu([
    ['open', `Visual Studio ${ECO.vsVersion()} で開く`, exists], ['open-default', '既定のアプリで開く', exists], ['reveal', 'Windows のエクスプローラーで表示', exists], '-',
    ...(isReadme(path) ? [] : [['rename', '名前の変更', can && exists, 'F2'], ['move', '移動先を指定…', can && exists], ['remove', '削除', can && exists, 'Delete']]),
    ...(testable(path) ? [['test', 'テストを作成…', can && exists]] : []),
    ['restore', '変更を元に戻す', can && tracked && kinds.length > 0], ['ignore', '除外パターンに追加', can], '-',
    ['diff', '差分', kinds.length > 0], ['log', 'ログ', tracked], ['blame', '注釈履歴', tracked && exists],
  ], x, y);
}
// A Project's own folder: what Visual Studio's Solution Explorer offers on a project (build, test, run, the target).
function projectMenu(dir, x, y) {
  activeDirectory = dir; const can = editable(), project = projectsByDir.get(dir), kind = project.kind || '';
  const runnable = ['executable', 'app'].includes(kind), testing = ['test', 'benchmark', 'bench'].includes(kind);
  showMenu([['p-build', 'ビルド'], ['p-rebuild', 'リビルド'], ['p-clean', 'クリーン'], '-',
    ...(testing ? [['p-test', 'テストを実行']] : []), ...(runnable ? [['p-run', '実行']] : []),
    ['p-target', '実行の対象にする（▶ で動かす）'], '-',
    ['new-file', '新しいファイル', can], ['new-folder', '新しいフォルダ', can], '-',
    ['reveal-dir', 'Windows のエクスプローラーで表示'], ['log', 'ログ'], '-',
    ['p-move', '移動…', can], ['p-remove', 'Projectを削除…', can], ['p-settings', 'Projectの設定（リンク等）']], x, y);
  menu.dataset.dir = dir;
}
function folderMenu(dir, x, y) {
  if (projectsByDir.has(dir)) return projectMenu(dir, x, y);
  activeDirectory = dir; const can = editable();
  showMenu([['new-file', '新しいファイル', can], ['new-folder', '新しいフォルダ', can], ...(dir ? [['rename-dir', '名前の変更', can, 'F2'], ['remove-dir', '削除', can, 'Delete']] : []), '-', ['reveal-dir', 'Windows のエクスプローラーで表示'], ['log', 'ログ'], ...(dir ? [['ignore-dir', '除外パターンに追加', can]] : []), '-',
    ['toggle-generated', get('toggle-generated').getAttribute('aria-pressed') === 'true' ? '生成ファイルを隠す' : '生成ファイルを表示'], ['reload', '読み直す']], x, y);
  menu.dataset.dir = dir;
}
// Several chosen: what can be done to all of them at once. Open, test: the chosen files; restore, commit: the changed files
// among the chosen ones and in the chosen folders.
const chosenPaths = () => [...chosen].map(k => k.startsWith('d:') ? k.slice(2) + '/' : k.slice(2));
function chosenChanges() {
  const files = [...chosen].filter(k => k.startsWith('f:')).map(k => k.slice(2)), dirs = [...chosen].filter(k => k.startsWith('d:')).map(k => k.slice(2));
  return [...WS.changes().keys()].filter(p => files.includes(p) || dirs.some(d => !d || p.startsWith(d + '/')));
}
function chosenMenu(x, y) {
  delete menu.dataset.dir;
  const {files, dirs} = chosenItems(), can = editable();
  const existing = files.filter(p => !WS.files.missing.includes(p)), tests = existing.filter(testable);
  const changed = chosenChanges(), restorable = changed.filter(p => !(WS.changes().get(p) || []).includes('untracked'));
  showMenu([
    ['m-open', `Visual Studio ${ECO.vsVersion()} で開く（${existing.length} 件）`, existing.length > 0], ['m-open-default', `既定のアプリで開く（${existing.length} 件）`, existing.length > 0], '-',
    ['m-move', '移動先を指定…', can && (files.length > 0 || dirs.some(d => !projectsByDir.has(d)))], ['remove-chosen', `選んだ ${chosen.size} 件を削除`, can, 'Delete'],
    ...(tests.length ? [['m-test', `テストを作成（${tests.length} 件）…`, can]] : []),
    ['m-restore', `変更を元に戻す（${restorable.length} 件）…`, can && restorable.length > 0], '-',
    ['m-commit', `コミットの対象にする（${changed.length} 件）`, can && changed.length > 0], ['m-copy', 'パスをコピー'],
  ], x, y);
}
// Move the chosen ones into a folder (the same as dropping them there).
async function moveChosenDialog() {
  const {files, dirs} = chosenItems(), moving = dirs.filter(d => !projectsByDir.has(d)), gone = WS.files.missing_dirs || [];
  const folders = WS.files.dirs.filter(d => shown(d) && !gone.includes(d) && !d.split('/').some(part => part.startsWith('.') || part === 'build')
    && !moving.some(m => d === m || d.startsWith(m + '/')));
  const options = [...(restricted() ? [] : [['', '（作業空間の一番上）']]), ...folders.map(d => [d, d])];
  const list = [...moving.map(d => d + '/'), ...files];
  const v = await ECO.form({title: `${list.length} 件を移動`, intro: esc(list.join('\n')).replaceAll('\n', '<br>') + '<br>を移します' + (moving.length < dirs.length ? '（Projectのフォルダは「Project」の「移動」で移します）' : '') + '。',
    fields: [{name: 'folder', label: '移動先のフォルダ', type: 'select', value: options.some(([d]) => d === activeDirectory) ? activeDirectory : options[0]?.[0], options}], ok: '移動'});
  if (v) await moveItems({files, dirs: moving}, v.folder);
}
// The tests of the chosen files, each at its default place (a file that has its test already is left as it is).
async function testChosen() {
  const files = chosenItems().files.filter(p => !WS.files.missing.includes(p) && testable(p));
  if (!await ECO.confirm({title: `テストを作成（${files.length} 件）`, message: `${files.join('\n')}\nのテストを、組のテスト用Projectの同じ構成の場所に作ります。`, ok: '作成'})) return;
  const made = [], skipped = [];
  for (const path of files) {
    const doc = await WS.cli(['file', 'test', path], {quiet: true});
    if (doc.ok) made.push(...doc.result.paths); else skipped.push(`${path}：${doc.error.message}`);
  }
  if (made.length) { await WS.refresh(); await afterFileChange(true, 'テストを作りました：' + made.join('、')); }
  if (skipped.length) ECO.toast(`作らなかったもの：\n${skipped.join('\n')}`, made.length ? 'info' : 'bad', 10000);
}
async function restoreChosen() {
  const paths = chosenChanges().filter(p => !(WS.changes().get(p) || []).includes('untracked'));
  if (!await ECO.confirm({title: `変更を元に戻す（${paths.length} 件）`, message: `${paths.join('\n')}\nの変更を捨てて、最後のコミットの状態に戻します。\nこの操作は元に戻せません。`, ok: '元に戻す', danger: true})) return;
  await WS.run(['restore', ...paths], {success: `変更を元に戻しました（${paths.length} 件）`}); await WS.reloadFiles();
}
function commitChosen() {
  WS.selected = new Set(chosenChanges()); WS.renderChanges(); WS.showTab('commit-panel'); get('commit-message').focus();
}

tree.addEventListener('contextmenu', e => {
  const row = e.target.closest('[data-path]'), folder = e.target.closest('summary[data-directory]');
  const item = row || folder;
  if (item && chosen.size > 1 && chosen.has(keyOfItem(item))) { e.preventDefault(); e.stopPropagation(); return chosenMenu(e.clientX, e.clientY); }
  if (item) choose(keyOfItem(item));
  if (row) { e.preventDefault(); delete menu.dataset.dir; fileMenu(row.dataset.path, e.clientX, e.clientY); }
  else if (folder) { e.preventDefault(); folderMenu(folder.dataset.directory, e.clientX, e.clientY); }
  else { e.preventDefault(); folderMenu(restricted() ? activeDirectory : '', e.clientX, e.clientY); }
});
// The empty part of the explorer below the files: the same menu as the top of the workspace (as in Explorer).
// (Not when the tree has shown its menu: fileMenu redraws the tree, so e.target is no longer in it.)
tree.closest('aside').addEventListener('contextmenu', e => {
  if (e.defaultPrevented || tree.contains(e.target) || e.target.closest('.explorer-heading, input, textarea')) return;
  e.preventDefault(); folderMenu(restricted() ? activeDirectory : '', e.clientX, e.clientY);
});
get('changes').addEventListener('contextmenu', e => {
  const row = e.target.closest('.change'); if (!row) return;
  e.preventDefault(); delete menu.dataset.dir; fileMenu(row.dataset.path, e.clientX, e.clientY);
});
document.addEventListener('pointerdown', e => { if (!menu.contains(e.target)) closeMenu(); });
document.addEventListener('keydown', e => {
  if (!menu.hidden && e.key === 'Escape') { closeMenu(); returnFocus?.focus(); }
  if (!menu.hidden && ['ArrowDown', 'ArrowUp'].includes(e.key)) {
    e.preventDefault(); const items = [...menu.querySelectorAll('button:not(:disabled)')], i = items.indexOf(document.activeElement);
    items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
  }
});
tree.addEventListener('keydown', e => {
  if (e.target.matches('input')) return;
  const row = e.target.closest('[data-path]'); if (!row) return;
  WS.activeFile = row.dataset.path;
  if (isReadme(row.dataset.path) && (e.key === 'F2' || e.key === 'Delete')) { e.preventDefault(); ECO.toast(why('rename'), 'info', 6000); return; }
  if (e.key === 'F2') { e.preventDefault(); menuAction('rename'); }
  if (e.key === 'Delete') { e.preventDefault(); if (chosen.size > 1 && chosen.has('f:' + row.dataset.path)) removeChosen(); else menuAction('remove'); }
  if (e.key === 'Enter') { e.preventDefault(); openInEditor(row.dataset.path); }
  if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) {
    e.preventDefault(); const r = row.getBoundingClientRect();
    if (chosen.size > 1 && chosen.has('f:' + row.dataset.path)) chosenMenu(r.left + 20, r.bottom); else fileMenu(row.dataset.path, r.left + 20, r.bottom);
  }
});
menu.addEventListener('click', e => { const b = e.target.closest('[data-menu]'); if (b) { closeMenu(); menuAction(b.dataset.menu, menu.dataset.dir); } });

const validName = name => name && !/[<>:"/\\|?*\x00-\x1f]/.test(name) && !/[. ]$/.test(name) && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)/i.test(name);
const join = (dir, name) => dir ? dir + '/' + name : name;
async function afterFileChange(doc, message) { if (doc) say(message); await WS.reloadFiles(); }

async function menuAction(action, dir) {
  const path = WS.activeFile;
  switch (action) {
    case 'open': return openInEditor(path);
    case 'open-default': return openFile(path);
    case 'reveal': return openFile(path, true);
    case 'reveal-dir': return openFile(dir || '');
    case 'p-build': case 'p-rebuild': case 'p-clean': case 'p-test': case 'p-run':
      return WS.buildProject(action.slice(2), projectsByDir.get(dir).name);
    case 'p-target': { const name = projectsByDir.get(dir).name; return WS.setTarget(name) ? say(`実行の対象：${name}`) : null; }
    case 'p-move': {
      const name = projectsByDir.get(dir).name;
      return ECO.form({title: `Projectを移動：${name}`, intro: 'Projectのフォルダを移します（名前は変わりません）。', fields: [
        {name: 'destination', label: '移動先（モジュールからの相対パス。まだないもの）', value: dir, required: true}], ok: '移動',
        submit: async v => {
          if (!await WS.run(['project', 'move', name, v.destination], {success: `${name} を ${v.destination} へ移しました。`})) return '移動できませんでした。';
          projectRoots = null; await WS.refresh(); await WS.reloadFiles(); WS.reloadBuildOptions?.();
        }});
    }
    case 'p-remove': {
      const name = projectsByDir.get(dir).name;
      // our question only (--yes: ecobuild would ask the same again)
      if (!await WS.run(['project', 'remove', name, '--yes'], {confirm: `Project ${name} を外し、そのフォルダ（${dir}/）を削除します。他のProjectからのリンクも外します。`, title: 'Projectを削除', success: `${name} を削除しました。`})) return;
      projectRoots = null; await WS.refresh(); await WS.reloadFiles(); WS.reloadBuildOptions?.(); return;
    }
    case 'p-settings': return ECO.action('open', {module: WS.module || WS.dir, tab: 'projects'}).catch(e => ECO.toast(e.message, 'bad'));
    case 'rename-dir': return renameFolder(dir);
    case 'remove-dir': choose('d:' + dir); return removeChosen();
    case 'remove-chosen': return removeChosen();
    case 'm-open': for (const p of chosenItems().files.filter(p => !WS.files.missing.includes(p))) await openInEditor(p); return;
    case 'm-open-default': for (const p of chosenItems().files.filter(p => !WS.files.missing.includes(p))) await openFile(p); return;
    case 'm-move': return moveChosenDialog();
    case 'm-test': return testChosen();
    case 'm-restore': return restoreChosen();
    case 'm-commit': return commitChosen();
    case 'm-copy': return ECO.copyText(chosenPaths().join('\n'));
    case 'toggle-generated': return get('toggle-generated').click();
    case 'reload': return get('reload-files').click();
    case 'new-file': return newFileDialog(dir ?? activeDirectory);
    case 'new-folder': return inlineName({create: 'folder', dir: dir ?? activeDirectory});
    case 'rename': return inlineName({rename: path});
    case 'move': return moveDialog(path);
    case 'test': return testDialog(path);
    case 'remove': return removeFile(path);
    case 'restore': if (await ECO.confirm({title: '変更を元に戻す', message: `${path} の変更を捨てて、最後のコミットの状態に戻します。\nこの操作は元に戻せません。`, ok: '元に戻す', danger: true})) { await WS.run(['restore', path], {success: '変更を元に戻しました：' + path}); await WS.reloadFiles(); } return;
    case 'ignore': case 'ignore-dir': {
      const v = await ECO.form({title: '除外パターンに追加', intro: '.gitignore に追加して、git で管理しないようにします（すでに管理しているファイルには効きません）。変えた .gitignore はコミットしてください。', fields: [{name: 'pattern', label: 'パターン', value: action === 'ignore-dir' ? (dir ? dir + '/' : '') : path, required: true}], ok: '追加'});
      if (v) { await WS.run(['ignore', v.pattern], {success: '.gitignore に追加しました：' + v.pattern}); await WS.reloadFiles(); }
      return;
    }
    case 'diff': {
      return WS.openDiff(path, WS.changes().get(path) || []);
    }
    case 'log': {
      // The GUI's own log (not TortoiseGit's, whose window offers many operations on the history).
      const target = dir !== undefined ? dir : path;
      return WS.showLog(target);
    }
    case 'blame': return WS.inTortoiseGit(['blame', path], async () => { const doc = await WS.cli(['blame', path]); return doc.ok ? ECO.output('注釈履歴', doc.result, {sub: path}) : ECO.showError(doc); });
  }
}

async function addFile(relatives, withTest = true, template = '') {
  let doc = await WS.cli(['file', 'add', ...relatives, ...(template ? ['--template', template] : withTest ? [] : ['--no-test'])]);
  if (!doc.ok && doc.error?.code === 'not_supported') {
    // Module types without file commands: make empty files.
    try { for (const path of relatives) await ECO.call('touch', {dir: WS.dir, path}); doc = {ok: true, result: {paths: relatives}}; }
    catch (e) { return e.message; }
  }
  if (!doc.ok) return doc.error.message + (doc.error.hint ? '\n' + doc.error.hint : '');
  await WS.refresh(); await afterFileChange(true, 'ファイルを追加しました：' + doc.result.paths.join('、'));
  WS.selectInTree(relatives[relatives.length - 1]);
  openInEditor(relatives[relatives.length - 1]);   // the new file (of a pair, the source) opens in Visual Studio
  return '';
}

// New file: where (the folder, in a Project), what (a header and a source / a source / a header / any file) and the name.
// The files to make are shown as they are typed. A pair goes in the folder (src/ is for the implementation: its headers sit
// beside the sources); with 「分ける」 (off by default) the header goes in the folder and the source in the chosen folder,
// by default src/ at the same place as the header below include/<Project>/ (a public header and its implementation);
// ecobuild file add makes the header first, so the source includes it, and adds the test of a library source.
const HEADER = '.h', SOURCE = '.cpp';
function newFilePlan(v) {
  const name = v.name.trim(), folder = v.folder;
  if (!name) return {error: ''};
  if (!validName(name)) return {error: '使用できない文字が含まれています。'};
  const base = v.kind === 'other' || v.kind === 'template' ? name : name.replace(/\.(h|hpp|hh|hxx|c|cc|cpp|cxx)$/i, '');
  if (v.kind === 'other' || v.kind === 'template') return {paths: [join(folder, base)]};
  if (v.kind === 'source') return {paths: [join(folder, base + SOURCE)]};
  if (v.kind === 'header') return {paths: [join(folder, base + HEADER)]};
  const header = join(folder, base + HEADER);
  if (!v.split) return {paths: [header, join(folder, base + SOURCE)]};
  if (v.sourceFolder) return {paths: [header, join(v.sourceFolder, base + SOURCE)]};
  const root = (projectRoots || []).find(r => folder === r || folder.startsWith(r + '/'));
  const project = root !== undefined ? projectsByDir.get(root)?.name : null;
  const rel = root !== undefined ? folder.slice(root.length).replace(/^\//, '') : null;
  if (rel === null || !project || !(rel === `include/${project}` || rel.startsWith(`include/${project}/`)))
    return {error: 'ソースの場所を選んでください。'};
  const sub = rel.slice(`include/${project}`.length).replace(/^\//, '');
  return {paths: [header, join(sub ? join(join(root, 'src'), sub) : join(root, 'src'), base + SOURCE)]};
}
// A test of a library's header or source (ecobuild file test): only where the library has its test Project (<名前>Test).
const CPP_FILE = /\.(h|hpp|hh|hxx|c|cc|cpp|cxx)$/i;
const projectOfPath = path => projectsByDir.get((projectRoots || []).find(r => path.startsWith(r + '/')));
function testable(path) {
  const project = projectOfPath(path);
  if (!restricted() || !CPP_FILE.test(path) || !project || !/library/.test(project.kind || '')) return false;
  return [...projectsByDir.values()].some(p => p.name === project.name + 'Test' && p.kind === 'test');
}
// The new file screen for the test: by default in the test Project's src/, at the same place as the file
// (include/<Project>/a/B.h・src/a/B.cpp → <Project>Test/src/a/BTest.cpp: what ecobuild says with --dry-run).
async function testDialog(path) {
  if (!editable()) return;
  const planned = await WS.cli(['file', 'test', path, '--dry-run'], {quiet: true});
  if (!planned.ok) return ECO.showError(planned);
  const suggested = planned.result.paths[0], defaultFolder = dirOf(suggested), defaultName = suggested.split('/').pop();
  const folders = WS.files.dirs.filter(d => shown(d) && !d.split('/').some(part => part.startsWith('.') || part === 'build') && inSources(d));
  const options = [...(folders.includes(defaultFolder) ? [] : [[defaultFolder, `${defaultFolder}（新しいフォルダ）`]]), ...folders.map(d => [d, d])];
  const exists = p => WS.files.files.includes(p);
  return ECO.form({title: 'テストを作成', intro: esc(path) + ' のテストを作ります（そのヘッダーを読み込むテストのひな形）。', busy: 'テストを作成しています…（生成ファイルも更新します）', ok: '作成', fields: [
    {name: 'folder', label: '場所', type: 'select', value: defaultFolder, options, row: 'where'},
    {name: 'name', label: '名前', value: defaultName, required: true, row: 'where', focus: true},
    {name: 'preview', type: 'html', html: '<p class="eco-help new-file-preview"></p>'}],
    onChange: (v, formEl) => {
      const target = join(v.folder, v.name.trim());
      formEl.querySelector('.new-file-preview').textContent = !validName(v.name.trim()) ? '使用できない文字が含まれています。'
        : exists(target) ? `${target} は既にあります。` : '作成するファイル：' + target;
    },
    submit: async v => {
      const name = v.name.trim(), target = join(v.folder, name);
      if (!validName(name)) return '有効な名前を入力してください。';
      const doc = await WS.cli(['file', 'test', path, ...(target === suggested ? [] : ['--to', target])]);
      if (!doc.ok) return doc.error.message + (doc.error.hint ? '\n' + doc.error.hint : '');
      await WS.refresh(); await afterFileChange(true, 'テストを作りました：' + doc.result.paths.join('、'));
      WS.selectInTree(doc.result.paths[0]);
      openInEditor(doc.result.paths[0]);
      return '';
    }});
}

async function newFileDialog(dir = activeDirectory) {
  if (!editable()) return;
  const cpp = restricted(), pythonTests = !cpp && !!ECO.typeFeatures(await ECO.moduleType(WS.dir)).fileTests;
  const settings = cpp ? await WS.cli(['module', 'settings'], {quiet: true}) : null;
  const templates = settings?.ok ? Object.keys(settings.result.templates || {}) : [];
  // In a Project, files go in its source folders (src・include): files elsewhere are not built (ecobuild file add refuses them).
  const folders = WS.files.dirs.filter(d => shown(d) && !d.split('/').some(part => part.startsWith('.') || part === 'build') && (!cpp || inSources(d)));
  const options = [...(cpp ? [] : [['', '（ルート）']]), ...folders.map(d => [d, d])];
  const root = (projectRoots || []).find(r => dir === r || dir.startsWith(r + '/'));
  const near = root === undefined ? null : options.find(([v]) => v.startsWith(root + '/'))?.[0];   // the folder's Project's src etc.
  const folder = options.some(([v]) => v === dir) ? dir : near ?? options[0]?.[0] ?? '';
  return ECO.form({title: '新しいファイル', busy: 'ファイルを作成しています…（生成ファイルも更新します）', ok: '作成', fields: [
    {name: 'folder', label: '場所', type: 'select', value: folder, options, row: 'where'},
    {name: 'name', label: '名前', required: true, row: 'where', focus: true, placeholder: cpp ? '例：Parser（拡張子なし）' : '例：notes.md'},
    ...(cpp ? [{name: 'kind', label: '種類', type: 'radio', inline: true, value: 'pair', options: [
      ['pair', 'ヘッダーとソース', `${HEADER} と ${SOURCE}`], ['source', 'ソース', SOURCE], ['header', 'ヘッダー', HEADER], ['other', 'その他', '拡張子も入力'],
      ...(templates.length ? [['template', 'テンプレートから', '拡張子も入力']] : [])]}] : []),
    ...(templates.length ? [{name: 'template', label: 'テンプレート', type: 'select', options: templates.map(t => [t, t]), showIf: v => v.kind === 'template',
      help: 'モジュール画面の「Project」タブで登録したもの・ECOBuildの既定のものです。'}] : []),
    ...(cpp ? [{name: 'split', label: 'ヘッダーとソースを別の場所に置く（ヘッダーは「場所」に）', type: 'checkbox', value: false, showIf: v => v.kind === 'pair',
      help: 'include/<Project>/ のヘッダーは、このProjectを使う側からも読み込めます（公開するヘッダー）。src/ は実装用で、ヘッダーとソースを並べます。'},
      {name: 'sourceFolder', label: 'ソースの場所', type: 'select', value: '', showIf: v => v.kind === 'pair' && v.split,
        options: [['', '自動（src/ の、ヘッダーと同じ構成の場所）'], ...folders.map(d => [d, d])]}] : []),
    ...(cpp ? [{name: 'test', label: 'ライブラリのソースなら、テストも作成する', type: 'checkbox', value: true, showIf: v => v.kind === 'pair' || v.kind === 'source'}] : []),
    ...(pythonTests ? [{name: 'test', label: 'src/<パッケージ>/ のソースなら、tests/ にテストも作成する', type: 'checkbox', value: true}] : []),
    {name: 'preview', type: 'html', html: '<p class="eco-help new-file-preview"></p>'}],
    onChange: (v, formEl) => {
      const plan = newFilePlan(cpp ? v : {...v, kind: 'other'}), box = formEl.querySelector('.new-file-preview');
      box.textContent = plan.error ?? '作成するファイル：' + plan.paths.join('、');
    },
    submit: v => {
      const plan = newFilePlan(cpp ? v : {...v, kind: 'other'});
      if (plan.error !== undefined) return plan.error || '名前を入力してください。';
      return addFile(plan.paths, cpp || pythonTests ? v.test : true, cpp && v.kind === 'template' ? v.template : '');
    }});
}

// Inline input in the tree for a new file / folder or a new name.
function inlineName({create, dir = '', rename}) {
  if (!editable() || tree.querySelector('.inline-name')) return;
  const row = rename ? tree.querySelector(`[data-path="${CSS.escape(rename)}"]`) : null;
  if (rename && !row) return;
  const directory = rename ? dirOf(rename) : dir;
  const parent = directory ? tree.querySelector(`details[data-directory="${CSS.escape(directory)}"]`) : tree;
  if (!parent) return;
  if (parent.tagName === 'DETAILS') { parent.open = true; folded.delete(directory); }
  const box = document.createElement('div'), input = document.createElement('input'), error = document.createElement('small'), test = document.createElement('label');
  box.className = 'inline-name'; input.value = rename ? rename.split('/').pop() : ''; input.placeholder = create === 'folder' ? 'フォルダ名' : 'ファイル名';
  input.setAttribute('aria-label', input.placeholder); error.setAttribute('role', 'alert');
  box.append(input, error);
  if (rename) { row.hidden = true; row.after(box); } else if (parent === tree) tree.prepend(box); else parent.querySelector('summary').after(box);
  const cancel = () => { box.remove(); if (row) row.hidden = false; };
  input.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== input && box.isConnected && !box.dataset.busy) cancel(); }, 150));
  input.addEventListener('keydown', async e => {
    if (e.key === 'Escape') { e.preventDefault(); cancel(); return; }
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const name = input.value.trim();
    if (!validName(name)) { error.textContent = '有効な名前を入力してください。'; return; }
    if (rename && name === rename.split('/').pop()) { cancel(); return; }
    box.dataset.busy = '1'; input.disabled = true;
    let message = '';
    if (create === 'folder') {
      try { await ECO.call('mkdir', {dir: WS.dir, path: join(directory, name)}); cancel(); folded.delete(join(directory, name)); activeDirectory = join(directory, name); await WS.reloadFiles(); say('フォルダを作成しました：' + join(directory, name)); return; }
      catch (err) { message = err.message; }
    } else {
      message = await moveFile(rename, join(directory, name));
      if (!message) { box.remove(); return; }
    }
    delete box.dataset.busy; input.disabled = false; error.textContent = message; input.focus();
  });
  input.focus(); input.setSelectionRange(0, input.value.lastIndexOf('.') > 0 ? input.value.lastIndexOf('.') : input.value.length);
}

// A folder's name, edited in place (F2 or the menu). The folder moves with what is in it. A Project's own folder is
// moved with project move (its build settings change too).
function renameFolder(dir) {
  if (!editable() || !dir || tree.querySelector('.inline-name')) return;
  if (projectsByDir.has(dir)) return ECO.toast('Projectのフォルダは、「モジュール」→「Project」の「移動」で移します（ビルドの設定も変わるため）。', 'info', 7000);
  const folder = tree.querySelector(`details[data-directory="${CSS.escape(dir)}"]`); if (!folder) return;
  const box = document.createElement('div'), input = document.createElement('input'), error = document.createElement('small');
  box.className = 'inline-name'; input.value = dir.split('/').pop(); input.setAttribute('aria-label', 'フォルダ名'); error.setAttribute('role', 'alert');
  box.append(input, error); folder.before(box); folder.hidden = true;
  const cancel = () => { box.remove(); folder.hidden = false; };
  input.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== input && box.isConnected && !box.dataset.busy) cancel(); }, 150));
  input.addEventListener('keydown', async e => {
    if (e.key === 'Escape') { e.preventDefault(); cancel(); return; }
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const name = input.value.trim(), destination = join(dirOf(dir), name);
    if (!validName(name)) { error.textContent = '有効な名前を入力してください。'; return; }
    if (destination === dir) { cancel(); return; }
    box.dataset.busy = '1'; input.disabled = true;
    try {
      await moveFolder(dir, destination);
      box.remove(); if (activeDirectory === dir) activeDirectory = destination;
      await WS.refresh(); await afterFileChange(true, `名前を変えました：${dir} → ${destination}`);
    } catch (err) { delete box.dataset.busy; input.disabled = false; error.textContent = err.message; input.focus(); }
  });
  input.focus(); input.select();
}

// A folder of a C++ Project goes through ecobuild (file move・remove: the tests in the same place of the test Project
// follow, the #include lines that read the moved files are fixed, the solution is made again). Other folders (other
// types, outside the source folders) the GUI moves itself; for C++ the solution follows (project update).
const OUTSIDE_FILE_COMMANDS = ['not_supported', 'not_in_project', 'not_in_source_directory'];
async function moveFolder(source, destination) {
  const cpp = (await ECO.moduleType(WS.dir)) === 'cpp';
  if (cpp) {
    const doc = await WS.cli(['file', 'move', source, destination], {quiet: true});
    if (doc.ok) return doc.result;
    if (!OUTSIDE_FILE_COMMANDS.includes(doc.error?.code)) throw new Error(doc.error.message + (doc.error.hint ? '　' + doc.error.hint : ''));
  }
  await ECO.call('rename-folder', {dir: WS.dir, source, destination});
  if (cpp) await WS.cli(['project', 'update'], {quiet: true});
  return null;
}
async function removeFolder(path, withTest = true) {
  const cpp = (await ECO.moduleType(WS.dir)) === 'cpp';
  if (cpp) {
    const doc = await WS.cli(['file', 'remove', path, ...(withTest ? [] : ['--no-test'])], {quiet: true});
    if (doc.ok) return;
    if (!OUTSIDE_FILE_COMMANDS.includes(doc.error?.code)) throw new Error(doc.error.message + (doc.error.hint ? '　' + doc.error.hint : ''));
  }
  await ECO.call('remove-folder', {dir: WS.dir, path});
  if (cpp) await WS.cli(['project', 'update'], {quiet: true});
}

// Module types without file commands: the GUI moves and removes the file itself, as it makes empty files.
async function withoutFileCommand(doc, api, body) {
  if (doc.ok || doc.error?.code !== 'not_supported') return doc;
  try { return {ok: true, result: await ECO.call(api, {dir: WS.dir, ...body})}; }
  catch (e) { return {ok: false, error: {message: e.message}}; }
}
// Whether the module's type makes tests with the files (file add・move・remove --test): cpp (a library's source), python.
const typeHasFileTests = async () => { const features = ECO.typeFeatures(await ECO.moduleType(WS.dir)); return !!(features.projects || features.fileTests); };
async function moveFile(source, destination, withTest = true) {
  const doc = await withoutFileCommand(await WS.cli(['file', 'move', source, destination, ...(withTest ? [] : ['--no-test'])]), 'move-file', {source, destination});
  if (!doc.ok) return doc.error.message + (doc.error.hint ? '\n' + doc.error.hint : '');
  await WS.refresh(); await afterFileChange(true, `移動しました：${source} → ${destination}`);
  WS.selectInTree(destination);
  return '';
}
const sourceTests = cpp => cpp ? 'ライブラリのソース' : 'src/ のソース';
async function moveDialog(path) {
  const tests = await typeHasFileTests(), cpp = restricted();
  return ECO.form({title: '名前の変更・移動', intro: esc(path), fields: [
    {name: 'destination', label: `移動先（モジュールからの相対パス${cpp ? '。同じProject内' : ''}）`, value: path, required: true},
    ...(tests ? [{name: 'test', label: `${sourceTests(cpp)}なら、対応するテストも移動する`, type: 'checkbox', value: true}] : [])], ok: '移動',
    submit: v => moveFile(path, v.destination, !tests || v.test)});
}
async function removeFile(path) {
  const tests = await typeHasFileTests();
  const v = await ECO.form({title: 'ファイルを削除', intro: esc(path) + ' を削除します。', fields: tests ? [{name: 'test', label: `${sourceTests(restricted())}なら、対応するテストも削除する`, type: 'checkbox', value: true}] : [], ok: '削除', danger: true});
  if (!v) return;
  const untracked = (WS.changes().get(path) || []).includes('untracked');
  const doc = await withoutFileCommand(await WS.cli(['file', 'remove', path, ...(!tests || v.test ? [] : ['--no-test'])]), 'remove-file', {path});
  if (!doc.ok) return ECO.showError(doc);
  await WS.refresh(); await afterFileChange(true, '削除しました：' + doc.result.paths.join('、') + (untracked ? '' : '（コミットすると削除が記録されます）'));
}

get('new-file').addEventListener('click', () => newFileDialog(activeDirectory));
get('new-folder').addEventListener('click', () => inlineName({create: 'folder', dir: activeDirectory}));
get('reload-files').addEventListener('click', async () => { await WS.refresh(); await WS.reloadFiles(); });
get('open-folder').addEventListener('click', () => openFile(''));

// Drag files and folders onto a folder to move them there (as in Explorer). What is dragged: the chosen ones when the
// dragged item is one of them, otherwise that item alone. Dropped on a file: into the file's folder; on the empty part
// (a type without Projects): to the top. A closed folder opens when the drag rests on it. Files move with ecobuild file
// move (a library source's test follows), folders as in a rename (rename-folder; then the generated files follow).
let dragged = null;   // {files, dirs} while dragging inside the explorer
const panel = tree.closest('aside');
const clearDropTargets = () => panel.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target'));
tree.addEventListener('dragstart', e => {
  const item = e.target.closest?.('[data-path], summary[data-directory]');
  if (!item || !editable() || tree.querySelector('.inline-name')) { e.preventDefault(); return; }
  cancelSlowRename();
  const key = keyOfItem(item);
  if (!chosen.has(key)) choose(key);
  const {files, dirs} = chosenItems();
  dragged = {files, dirs: dirs.filter(d => !projectsByDir.has(d))};
  if (!dragged.files.length && !dragged.dirs.length) { dragged = null; e.preventDefault(); return; }
  e.dataTransfer.setData('text/plain', [...dragged.dirs.map(d => d + '/'), ...dragged.files].join('\n'));
  e.dataTransfer.effectAllowed = 'move';
});
// Where a drop goes: a folder, or null when it cannot go there (into itself, or nowhere a file may be).
function dropDestination(e) {
  const folder = e.target.closest('summary[data-directory]'), row = e.target.closest('[data-path]');
  const dir = folder ? folder.dataset.directory : row ? dirOf(row.dataset.path) : restricted() ? null : '';
  if (dir === null || (restricted() && !shown(dir)) || (WS.files.missing_dirs || []).includes(dir)) return null;   // not into a folder that is gone
  if (dragged.dirs.some(d => dir === d || dir.startsWith(d + '/'))) return null;
  const moving = [...dragged.dirs, ...dragged.files].filter(p => dirOf(p) !== dir);
  return moving.length ? dir : null;
}
let openTimer = 0, openFor = null;
panel.addEventListener('dragover', e => {
  if (!dragged) return;
  const dir = dropDestination(e);
  clearDropTargets();
  const summary = e.target.closest('summary[data-directory]'), folder = summary?.parentElement;
  if (folder !== openFor) { clearTimeout(openTimer); openFor = folder; if (folder && !folder.open) openTimer = setTimeout(() => { folder.open = true; }, 700); }
  if (dir === null) { e.dataTransfer.dropEffect = 'none'; return; }
  e.preventDefault(); e.dataTransfer.dropEffect = 'move';
  (dir ? tree.querySelector(`summary[data-directory="${CSS.escape(dir)}"]`) : tree)?.classList.add('drop-target');
});
panel.addEventListener('drop', async e => {
  if (!dragged) return;
  const dir = dropDestination(e), items = dragged;
  e.preventDefault(); clearDropTargets(); dragged = null;
  if (dir !== null) await moveItems(items, dir);
});
tree.addEventListener('dragend', () => { dragged = null; clearTimeout(openTimer); openFor = null; clearDropTargets(); });

async function moveItems({files, dirs}, dir) {
  const moved = [], failed = [];
  for (const source of dirs.filter(d => dirOf(d) !== dir)) {
    const destination = join(dir, source.split('/').pop());
    try { await moveFolder(source, destination); moved.push([source + '/', destination + '/']); if (activeDirectory === source) activeDirectory = destination; }
    catch (error) { failed.push(`${source}/：${error.message}`); }
  }
  for (const source of files.filter(p => dirOf(p) !== dir)) {
    const destination = join(dir, source.split('/').pop());
    const doc = await withoutFileCommand(await WS.cli(['file', 'move', source, destination]), 'move-file', {source, destination});
    if (doc.ok) moved.push([source, destination]); else failed.push(`${source}：${doc.error.message}${doc.error.hint ? '　' + doc.error.hint : ''}`);
  }
  // What was moved stays chosen, at its new place.
  chosen.clear();
  for (const [, destination] of moved) chosen.add(destination.endsWith('/') ? 'd:' + destination.slice(0, -1) : 'f:' + destination);
  const lastFile = moved.map(([, d]) => d).filter(d => !d.endsWith('/')).pop();
  if (lastFile) WS.activeFile = lastFile;
  folded.delete(dir); activeDirectory = dir;
  if (moved.length) { await WS.refresh(); await afterFileChange(true, `${dir || '作業空間の一番上'} へ移動しました：${moved.map(([s]) => s).join('、')}`); }
  if (failed.length) ECO.toast(`移動できませんでした：\n${failed.join('\n')}`, 'bad', 10000);
}

// Drop files or folders from elsewhere on this PC (Explorer etc.) onto the explorer: they are copied into the folder they
// are dropped on (anywhere else: the top of the workspace). Read here and written by the GUI (import-files); a file that
// is there already is not overwritten. In a C++ module the generated files follow (check --no-build updates them).
const fromOutside = e => !dragged && [...(e.dataTransfer?.types || [])].includes('Files');
const dropFolder = e => e.target.closest('summary[data-directory]');
panel.addEventListener('dragover', e => {
  if (!fromOutside(e)) return;
  e.preventDefault(); e.dataTransfer.dropEffect = editable() ? 'copy' : 'none';
  clearDropTargets();
  (dropFolder(e) || tree).classList.add('drop-target');
});
panel.addEventListener('dragleave', e => { if (!panel.contains(e.relatedTarget)) panel.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target')); });
panel.addEventListener('drop', async e => {
  if (!fromOutside(e)) return;
  e.preventDefault();
  panel.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target'));
  if (!editable()) { ECO.toast('ファイルを足すのはタスクブランチで行います（タスク管理で「作業を開始」）。', 'bad', 6000); return; }
  const target = dropFolder(e)?.dataset.directory || '';
  const entries = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry?.()).filter(Boolean);
  const files = [];
  let size = 0;
  const readFile = entry => new Promise((resolve, reject) => entry.file(resolve, reject));
  const readDirectory = reader => new Promise((resolve, reject) => reader.readEntries(resolve, reject));
  async function walk(entry, path) {
    if (entry.isFile) {
      const file = await readFile(entry); size += file.size;
      if (size > 100 * 1024 * 1024) throw new Error('大きすぎます（一度に100MBまで）。');
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = ''; for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      files.push({path, data: btoa(binary)});
      return;
    }
    if (entry.name === '.git') return;   // a clone's history is not part of the files
    const reader = entry.createReader(), children = [];
    for (let batch; (batch = await readDirectory(reader)).length;) children.push(...batch);
    if (!children.length) files.push({path});   // an empty folder
    for (const child of children) await walk(child, `${path}/${child.name}`);
  }
  try {
    for (const entry of entries) await walk(entry, entry.name);
    if (!files.length) return;
    const {files: written} = await ECO.call('import-files', {dir: WS.dir, target, files});
    if ((await ECO.moduleType(WS.dir)) === 'cpp') await WS.cli(['project', 'update'], {quiet: true});
    ECO.toast(`${written.length} 個のファイルを ${target || '作業空間'} に置きました。`);
    await WS.refresh(); await WS.reloadFiles();
  } catch (error) { ECO.toast(error.message, 'bad', 8000); }
});

// The files are listed without waiting for the status (its marks and the buttons follow when it arrives: WS.onRefresh).
WS.reloadFiles();
let lastFocus = Date.now();
window.addEventListener('focus', () => { if (Date.now() - lastFocus > 3000) { lastFocus = Date.now(); WS.refresh().then(WS.reloadFiles); } });

// The divider between the explorer and the work area (as in most applications): drag, ←→, or double-click to reset.
// The width is kept on this PC.
(() => {
  const main = document.querySelector('main'), aside = main.querySelector('aside'), KEY = 'ecobuild-gui-explorer-width', DEFAULT = 290;
  const splitter = document.createElement('div');
  splitter.className = 'splitter'; splitter.tabIndex = 0; splitter.setAttribute('role', 'separator'); splitter.setAttribute('aria-orientation', 'vertical');
  splitter.setAttribute('aria-label', 'エクスプローラーの幅'); splitter.title = 'ドラッグで幅を変える（ダブルクリックで元に戻す）';
  aside.after(splitter);
  const clamp = width => Math.round(Math.max(160, Math.min(width, Math.max(160, innerWidth - 360))));
  const apply = (width, keep = true) => {
    width = clamp(width);
    main.style.setProperty('--explorer-width', width + 'px'); splitter.setAttribute('aria-valuenow', String(width));
    if (keep) try { localStorage.setItem(KEY, String(width)); } catch (e) { /* storage blocked */ }
  };
  let saved = DEFAULT;
  try { saved = Number(localStorage.getItem(KEY)) || DEFAULT; } catch (e) { /* storage blocked */ }
  apply(saved, false);
  splitter.addEventListener('pointerdown', e => {
    e.preventDefault(); splitter.setPointerCapture(e.pointerId);
    const start = e.clientX, width = aside.getBoundingClientRect().width;
    splitter.classList.add('dragging'); document.body.classList.add('resizing');
    const move = ev => apply(width + ev.clientX - start, false);
    const up = ev => {
      apply(width + ev.clientX - start);
      splitter.classList.remove('dragging'); document.body.classList.remove('resizing');
      splitter.removeEventListener('pointermove', move); splitter.removeEventListener('pointerup', up); splitter.removeEventListener('pointercancel', up);
    };
    splitter.addEventListener('pointermove', move); splitter.addEventListener('pointerup', up); splitter.addEventListener('pointercancel', up);
  });
  splitter.addEventListener('keydown', e => {
    if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    e.preventDefault(); apply(aside.getBoundingClientRect().width + (e.key === 'ArrowRight' ? 16 : -16));
  });
  splitter.addEventListener('dblclick', () => apply(DEFAULT));
  addEventListener('resize', () => apply(aside.getBoundingClientRect().width, false));
})();
