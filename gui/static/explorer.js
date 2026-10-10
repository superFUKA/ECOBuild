'use strict';
// Explorer: the files of this place (listed by the GUI: git's tracked and untracked files, plus empty folders).
// File operations run ecobuild (file add / move / remove, restore, ignore, diff, log, blame); new folders are made by the GUI.
const folded = new Set(), opened = new Set();
let activeDirectory = '';
const tree = get('file-tree'), menu = get('file-menu');

// File operations (ecobuild file add / move / remove) work inside the Projects' folders only, so when the module type
// has Projects (project list), the explorer shows only those folders, without tool folders (.cppbuild 等) inside.
// Types without Projects (generic) show the whole place.
let projectRoots = null;
WS.reloadFiles = async () => {
  try {
    const [files, projects] = await Promise.all([ECO.call('files', {dir: WS.dir}), projectRoots ? null : WS.cli(['project', 'list'], {quiet: true})]);
    WS.files = files;
    if (projects) projectRoots = projects.ok ? projects.result.map(p => p.directory.replace(/\/+$/, '')).filter(Boolean) : [];
  } catch (e) { tree.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  renderTree(); WS.renderChanges();
};
const restricted = () => !!(projectRoots && projectRoots.length);
const shown = path => !restricted() || projectRoots.some(root => {
  if (path !== root && !path.startsWith(root + '/')) return false;
  return !path.slice(root.length).split('/').some(part => part.startsWith('.'));
});
const editable = () => !!(WS.status && WS.status.workspace && !WS.status.reviewing);

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
  for (const f of new Set([...WS.files.files, ...[...changed].filter(p => !p.endsWith('/'))])) { if (!shown(f)) continue; const i = f.lastIndexOf('/'); nodeFor(i < 0 ? '' : f.slice(0, i)).files.push(f); }
  const changedDirs = new Set([...changed].flatMap(p => p.split('/').slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join('/'))));
  const walk = (node, parent, prefix) => {
    for (const [name, child] of [...node.dirs].sort(([a], [b]) => a.localeCompare(b))) {
      const dir = prefix ? prefix + '/' + name : name;
      const folder = document.createElement('details'), title = document.createElement('summary');
      if (name.startsWith('.') && !opened.has(dir)) folded.add(dir);  // tool folders (.cppbuild 等) start closed
      opened.add(dir);
      folder.open = !folded.has(dir); folder.dataset.directory = dir;
      title.textContent = name; title.dataset.directory = dir; title.title = dir;
      if (changedDirs.has(dir)) title.className = 'has-changes';
      title.addEventListener('click', () => { activeDirectory = dir; });
      folder.addEventListener('toggle', () => { if (folder.open) folded.delete(dir); else folded.add(dir); });
      folder.append(title); walk(child, folder, dir); parent.append(folder);
    }
    for (const path of [...new Set(node.files)].sort((a, b) => a.localeCompare(b))) {
      const row = document.createElement('button'); row.type = 'button'; row.dataset.path = path; row.draggable = true;
      const cls = fileClass(path);
      row.className = 'file ' + cls + (WS.activeFile === path ? ' active' : '');
      row.textContent = (cls === 'untracked' ? '+ ' : cls && cls !== 'staged' ? '• ' : cls === 'staged' ? '✓ ' : '') + path.split('/').pop();
      row.title = path + (cls ? '（' + {deleted: '削除', conflicted: '衝突', untracked: '未追跡', modified: '変更', staged: 'ステージ済み'}[cls] + '）' : '');
      parent.append(row);
    }
  };
  tree.replaceChildren(); walk(rootNode, tree, '');
  if (!tree.childElementCount) tree.innerHTML = '<p class="muted">ファイルはありません。</p>';
  if (restricted()) tree.insertAdjacentHTML('afterbegin', '<p class="explorer-note">Projectのフォルダを表示しています（ファイルの追加・削除はProjectの中で行います）。</p>');
  if (restricted() && (!activeDirectory || !shown(activeDirectory))) activeDirectory = projectRoots[0];
  get('new-file').disabled = get('new-folder').disabled = !editable();
}
WS.onRefresh(renderTree);
WS.selectInTree = path => { WS.activeFile = path; renderTree(); tree.querySelector(`[data-path="${CSS.escape(path)}"]`)?.scrollIntoView({block: 'nearest'}); };

tree.addEventListener('click', e => {
  const row = e.target.closest('[data-path]'); if (!row) return;
  WS.activeFile = row.dataset.path; activeDirectory = dirOf(row.dataset.path); renderTree(); WS.renderChanges();
  tree.querySelector(`[data-path="${CSS.escape(row.dataset.path)}"]`)?.focus();
});
tree.addEventListener('dblclick', e => { const row = e.target.closest('[data-path]'); if (row) openFile(row.dataset.path); });
const dirOf = path => path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
const openFile = (path, reveal = false) => ECO.call('open', {dir: WS.dir, path, reveal}).catch(e => ECO.toast(e.message, 'bad'));

// Context menu ----------------------------------------------------------------------------------------
let returnFocus = null;
function closeMenu() { menu.hidden = true; }
function showMenu(items, x, y) {
  returnFocus = document.activeElement;
  menu.innerHTML = items.map(item => item === '-' ? '<hr>' : `<button type="button" role="menuitem" data-menu="${item[0]}" ${item[2] === false ? 'disabled' : ''}>${esc(item[1])}</button>`).join('');
  menu.hidden = false;
  menu.style.left = Math.max(8, Math.min(x, innerWidth - 240)) + 'px';
  menu.style.top = Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8)) + 'px';
  menu.querySelector('button:not(:disabled)')?.focus();
}
function fileMenu(path, x, y) {
  WS.activeFile = path; activeDirectory = dirOf(path); renderTree();
  const kinds = WS.changes().get(path) || [], tracked = !kinds.includes('untracked'), exists = !WS.files.missing.includes(path), can = editable();
  showMenu([
    ['open', '開く', exists], ['reveal', 'エクスプローラーで表示', exists], '-',
    ['new-file', '新しいファイル', can], ['new-folder', '新しいフォルダ', can], '-',
    ['rename', '名前の変更　F2', can && exists], ['move', '移動先を指定…', can && exists], ['remove', '削除　Delete', can && exists],
    ['restore', '変更を元に戻す', can && tracked && kinds.length > 0], ['ignore', '除外パターンに追加', can], '-',
    ['diff', '差分', kinds.length > 0], ['log', '履歴', tracked], ['blame', '行ごとの変更履歴', tracked && exists],
    ['log-gui', 'TortoiseGitで履歴', tracked],
  ], x, y);
}
function folderMenu(dir, x, y) {
  activeDirectory = dir; const can = editable();
  showMenu([['new-file', '新しいファイル', can], ['new-folder', '新しいフォルダ', can], '-', ['reveal-dir', 'エクスプローラーで開く'], ['log', 'このフォルダの履歴'], ['ignore-dir', '除外パターンに追加', can]], x, y);
  menu.dataset.dir = dir;
}
tree.addEventListener('contextmenu', e => {
  const row = e.target.closest('[data-path]'), folder = e.target.closest('summary[data-directory]');
  if (row) { e.preventDefault(); delete menu.dataset.dir; fileMenu(row.dataset.path, e.clientX, e.clientY); }
  else if (folder) { e.preventDefault(); folderMenu(folder.dataset.directory, e.clientX, e.clientY); }
  else { e.preventDefault(); folderMenu(restricted() ? activeDirectory : '', e.clientX, e.clientY); }
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
  if (e.key === 'F2') { e.preventDefault(); menuAction('rename'); }
  if (e.key === 'Delete') { e.preventDefault(); menuAction('remove'); }
  if (e.key === 'Enter') { e.preventDefault(); openFile(row.dataset.path); }
  if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); const r = row.getBoundingClientRect(); fileMenu(row.dataset.path, r.left + 20, r.bottom); }
});
menu.addEventListener('click', e => { const b = e.target.closest('[data-menu]'); if (b) { closeMenu(); menuAction(b.dataset.menu, menu.dataset.dir); } });

const validName = name => name && !/[<>:"/\\|?*\x00-\x1f]/.test(name) && !/[. ]$/.test(name) && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)/i.test(name);
const join = (dir, name) => dir ? dir + '/' + name : name;
async function afterFileChange(doc, message) { if (doc) say(message); await WS.reloadFiles(); }

async function menuAction(action, dir) {
  const path = WS.activeFile;
  switch (action) {
    case 'open': return openFile(path);
    case 'reveal': return openFile(path, true);
    case 'reveal-dir': return openFile(dir || '');
    case 'new-file': return inlineName({create: 'file', dir: dir ?? activeDirectory});
    case 'new-folder': return inlineName({create: 'folder', dir: dir ?? activeDirectory});
    case 'rename': return inlineName({rename: path});
    case 'move': return moveDialog(path);
    case 'remove': return removeFile(path);
    case 'restore': if (await ECO.confirm({title: '変更を元に戻す', message: `${path} の未コミットの変更を捨てます。元に戻せません。`, ok: '元に戻す', danger: true})) { await WS.run(['restore', path], {success: '変更を元に戻しました：' + path}); await WS.reloadFiles(); } return;
    case 'ignore': case 'ignore-dir': {
      const v = await ECO.form({title: '除外パターンに追加', intro: '.gitignore にパターンを足します（既に追跡しているファイルは追跡したままです）。作業空間でコミットしてください。', fields: [{name: 'pattern', label: 'パターン', value: action === 'ignore-dir' ? (dir ? dir + '/' : '') : path, required: true}], ok: '追加'});
      if (v) { await WS.run(['ignore', v.pattern], {success: '.gitignore に追加しました：' + v.pattern}); await WS.reloadFiles(); }
      return;
    }
    case 'diff': return WS.showDiff(path, WS.changes().get(path) || []);
    case 'log': { const target = dir !== undefined ? dir : path; const doc = await WS.cli(['log', ...(target ? [target] : []), '--count', '50']); return doc.ok ? WS.showLog(doc.result, target) : ECO.showError(doc); }
    case 'log-gui': { const doc = await WS.cli(['log', path, '--gui']); if (!doc.ok) ECO.showError(doc); return; }
    case 'blame': { const doc = await WS.cli(['blame', path]); return doc.ok ? ECO.output('行ごとの変更履歴', doc.result, {sub: path}) : ECO.showError(doc); }
  }
}

async function addFile(relative, withTest = true) {
  let doc = await WS.cli(['file', 'add', relative, ...(withTest ? [] : ['--no-test'])]);
  if (!doc.ok && doc.error?.code === 'not_supported') {
    // Module types without a file template (generic): make an empty file here.
    try { await ECO.call('touch', {dir: WS.dir, path: relative}); doc = {ok: true, result: {paths: [relative]}}; }
    catch (e) { return e.message; }
  }
  if (!doc.ok) return doc.error.message + (doc.error.hint ? '\n' + doc.error.hint : '');
  await WS.refresh(); await afterFileChange(true, 'ファイルを追加しました：' + doc.result.paths.join('、'));
  WS.selectInTree(relative);
  return '';
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
      try { await ECO.call('mkdir', {dir: WS.dir, path: join(directory, name)}); cancel(); folded.delete(join(directory, name)); activeDirectory = join(directory, name); await WS.reloadFiles(); say('フォルダを作りました：' + join(directory, name)); return; }
      catch (err) { message = err.message; }
    } else if (create === 'file') {
      message = await addFile(join(directory, name));
      if (!message) { box.remove(); return; }
    } else {
      message = await moveFile(rename, join(directory, name));
      if (!message) { box.remove(); return; }
    }
    delete box.dataset.busy; input.disabled = false; error.textContent = message; input.focus();
  });
  input.focus(); input.setSelectionRange(0, input.value.lastIndexOf('.') > 0 ? input.value.lastIndexOf('.') : input.value.length);
}

async function moveFile(source, destination, withTest = true) {
  const doc = await WS.cli(['file', 'move', source, destination, ...(withTest ? [] : ['--no-test'])]);
  if (!doc.ok) return doc.error.message + (doc.error.hint ? '\n' + doc.error.hint : '');
  await WS.refresh(); await afterFileChange(true, `移動しました：${source} → ${destination}`);
  WS.selectInTree(destination);
  return '';
}
function moveDialog(path) {
  return ECO.form({title: '名前の変更・移動', intro: esc(path), fields: [
    {name: 'destination', label: '移動先（場所からの相対パス。同じProjectの中）', value: path, required: true},
    {name: 'test', label: 'ライブラリのソースなら、対応するテストも移動する', type: 'checkbox', value: true}], ok: '移動',
    submit: v => moveFile(path, v.destination, v.test)});
}
async function removeFile(path) {
  const v = await ECO.form({title: 'ファイルを削除', intro: esc(path) + ' を削除します。', fields: [{name: 'test', label: 'ライブラリのソースなら、対応するテストも削除する', type: 'checkbox', value: true}], ok: '削除', danger: true});
  if (!v) return;
  const untracked = (WS.changes().get(path) || []).includes('untracked');
  let doc = await WS.cli(['file', 'remove', path, ...(v.test ? [] : ['--no-test'])]);
  if (!doc.ok) return ECO.showError(doc);
  await WS.refresh(); await afterFileChange(true, '削除しました：' + doc.result.paths.join('、') + (untracked ? '' : '（コミットすると削除が記録されます）'));
}

get('new-file').addEventListener('click', () => inlineName({create: 'file', dir: activeDirectory}));
get('new-folder').addEventListener('click', () => inlineName({create: 'folder', dir: activeDirectory}));
get('reload-files').addEventListener('click', async () => { await WS.refresh(); await WS.reloadFiles(); });

// Drag a file onto a folder to move it.
let dragged = '';
tree.addEventListener('dragstart', e => { const row = e.target.closest('[data-path]'); if (!row || !editable()) { e.preventDefault(); return; } dragged = row.dataset.path; e.dataTransfer.setData('text/plain', dragged); e.dataTransfer.effectAllowed = 'move'; });
tree.addEventListener('dragover', e => { const target = e.target.closest('summary[data-directory]'); if (target && dragged) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; target.classList.add('drop-target'); } });
tree.addEventListener('dragleave', e => e.target.closest?.('summary')?.classList.remove('drop-target'));
tree.addEventListener('drop', async e => {
  const target = e.target.closest('summary[data-directory]'); if (!target || !dragged) return;
  e.preventDefault(); target.classList.remove('drop-target');
  const destination = join(target.dataset.directory, dragged.split('/').pop()), source = dragged; dragged = '';
  if (destination !== source) { const message = await moveFile(source, destination); if (message) ECO.toast(message, 'bad', 8000); }
});
tree.addEventListener('dragend', () => { dragged = ''; });

WS.ready.then(WS.reloadFiles);
let lastFocus = Date.now();
window.addEventListener('focus', () => { if (Date.now() - lastFocus > 3000) { lastFocus = Date.now(); WS.refresh().then(WS.reloadFiles); } });
