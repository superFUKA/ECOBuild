'use strict';
// Module window: left menu and the workspace tabs. MOD.root is the module's own clone: it stays on the default branch
// and is no tab (the module's reads run there: -C MOD.root). A tab is a workspace of the module (a git worktree in
// MOD.root/.ecobuild/w/: ecobuild workspace list), made by task start (a task's) or task review (checking a submission)
// and removed by task finish・drop・close etc.
const MOD = (() => {
  const root = ECO.params.get('path') || '';
  const name = root.split(/[\\/]/).filter(Boolean).pop() || 'モジュール';
  return {root, name, places: [], states: new Map(), titles: new Map(), me: ''};
})();
const mEl = id => document.getElementById(id);
document.getElementById('module-title').textContent = MOD.name;
document.title = MOD.name + ' — ECOBuild';
ECO.info().then(info => { MOD.me = info.me || ''; });
// The account's role in this module (GitHub's permission, account show) after its name at the bottom of the left menu.
ECO.access(MOD.root).then(a => {
  const box = document.getElementById('nav-account'); if (!a || !box) return;
  const tag = box.querySelector('.nav-account-role') || box.appendChild(Object.assign(document.createElement('span'), {className: 'nav-account-role'}));
  tag.textContent = ECO.roleNames[a.role] || a.role;
  tag.title = `このモジュールでの役割：${tag.textContent}（GitHub の権限）。` + (a.admin ? '管理（ブランチ・メンバー・CI）ができます。' : '管理は管理者だけです。');
});

// Left menu -----------------------------------------------------------------------------------------
const PAGES = ['workspace', 'tasks', 'branches', 'manage', 'modinfo', 'modagent', 'settings', 'help'];
// ブランチ has the submissions coming in (the page 提出 once): the old name still leads there.
const pageOf = page => page === 'submissions' ? 'branches' : page;
const pageHooks = {help: () => typeof HELP !== 'undefined' && HELP.show(location.hash.slice(1).startsWith('help') ? location.hash.slice(1) : '')};
function showModulePage(page) {
  page = pageOf(page);
  ECO.setState({page});
  for (const key of PAGES) {
    mEl(key + '-content').hidden = key !== page;
    if (key === page) mEl(key + '-menu').setAttribute('aria-current', 'page'); else mEl(key + '-menu').removeAttribute('aria-current');
  }
  pageHooks[page]?.();
}
// The tabs of 管理 (メンバー, CI): the chosen one's panel and its buttons (data-manage-for) show.
const MANAGE_TABS = ['members', 'ci'];
const manageView = () => document.querySelector('#manage-tabs [aria-selected=true]')?.dataset.manageView || 'members';
function showManageTab(view) {
  for (const b of document.querySelectorAll('#manage-tabs [data-manage-view]')) b.setAttribute('aria-selected', String(b.dataset.manageView === view));
  for (const p of document.querySelectorAll('#manage-content [data-manage-view-panel]')) p.hidden = p.dataset.manageViewPanel !== view;
  for (const p of document.querySelectorAll('#manage-content [data-manage-for]')) p.hidden = p.dataset.manageFor !== view;
  if (view === 'ci') window.MANAGE_CI?.show(); else window.MANAGE_MEMBERS?.show();
}
pageHooks.manage = () => showManageTab(manageView());
// 更新 is 管理's: it reads again what the chosen tab shows.
document.getElementById('manage-reload').addEventListener('click', () => (manageView() === 'ci' ? window.MANAGE_CI : window.MANAGE_MEMBERS)?.reload());
document.getElementById('manage-tabs').addEventListener('click', e => {
  const view = e.target.closest('[data-manage-view]')?.dataset.manageView; if (view) showManageTab(view);
});
// The tabs of 設定 (the others of a tab are モジュール's).
const SETTINGS_TABS = ['profiles', 'general', 'templates', 'container'];
// The left menu moves at once (only the page's contents wait for their reads). ecobuild gui open comes in onNavigate below.
for (const key of PAGES) mEl(key + '-menu').addEventListener('click', () => showModulePage(key));
ECO.onNavigate(({page, tab, task, command}) => {
  // The tabs 「メンバー」 and 「CI」 are 管理's (--tab members・ci); --tab branches (once a tab) leads to the page ブランチ.
  const target = page || (tab ? (tab === 'branches' ? 'branches' : MANAGE_TABS.includes(tab) ? 'manage' : SETTINGS_TABS.includes(tab) ? 'settings' : 'modinfo') : task ? 'tasks' : command ? 'help' : '');
  if (target) showModulePage(target);
  if (MANAGE_TABS.includes(tab)) showManageTab(tab);
  else if (tab && tab !== 'branches') window.MODINFO_SHOW?.(tab);
  if (task) window.TASKS_SELECT?.(Number(task));
  if (command && typeof HELP !== 'undefined') HELP.show('help/commands/' + encodeURIComponent(command));
});
// Something ran elsewhere (an agent, another window): the places it touched are read again.
ECO.onChange(async e => {
  // A task・workspace・agent operation may have made or removed a workspace: the list is read again first.
  if (['task', 'workspace', 'agent'].includes(e.args?.[0])) await syncPlaces();
  const touched = e.dir ? MOD.places.filter(p => keyOf(p) === keyOf(e.dir)) : MOD.places;
  for (const place of touched) { frames.get(keyOf(place))?.contentWindow?.location.reload(); refreshState(place); }
  pageHooks.changed?.();
});
// module.html?…#modinfo・#tasks opens that page (after the pages' scripts are loaded); #modinfo/projects etc. that tab too.
const hashPage = pageOf(location.hash.slice(1).split('/')[0]);
if (PAGES.includes(hashPage)) window.addEventListener('load', () => {
  showModulePage(hashPage);
  const task = hashPage === 'tasks' && Number(location.hash.split('/')[1]), tab = location.hash.split('/')[1];
  if (hashPage === 'manage' && MANAGE_TABS.includes(tab)) showManageTab(tab);
  if (task) window.TASKS_SELECT?.(task);
});
// Reorder the left menu by drag and drop (Alt+↑／↓ with the keyboard). The order is kept per PC (localStorage).
const NAV_ORDER_KEY = 'ecobuild-gui-nav-order', nav = document.querySelector('.module-nav');
const navItems = () => [...nav.querySelectorAll('[data-nav]')];
function saveNavOrder() { try { localStorage.setItem(NAV_ORDER_KEY, JSON.stringify(navItems().map(b => b.dataset.nav))); } catch (e) { /* storage blocked */ } }
// 設定・ヘルプ stay at the bottom with the account (not reordered).
const ORDERED = PAGES.filter(key => key !== 'settings' && key !== 'help'), navBottom = nav.querySelector('.nav-bottom');
for (const key of ORDERED) { const b = mEl(key + '-menu'); b.dataset.nav = key; b.draggable = true; b.title = b.title + '（ドラッグで並び替え）'; }
try {
  const saved = JSON.parse(localStorage.getItem(NAV_ORDER_KEY) || '[]');
  for (const key of saved.map(pageOf)) if (ORDERED.includes(key)) nav.insertBefore(mEl(key + '-menu'), navBottom);
} catch (e) { /* storage blocked or broken */ }
let draggedNav = null;
nav.addEventListener('dragstart', e => { draggedNav = e.target.closest('[data-nav]'); if (!draggedNav) return; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', draggedNav.dataset.nav); draggedNav.classList.add('dragging'); });
nav.addEventListener('dragover', e => {
  if (!draggedNav) return;
  const over = e.target.closest('[data-nav]'); e.preventDefault();
  if (over && !over.dataset.nav) return;
  if (!over || over === draggedNav) return;
  const r = over.getBoundingClientRect();
  nav.insertBefore(draggedNav, e.clientY < r.top + r.height / 2 ? over : over.nextSibling);
});
nav.addEventListener('drop', e => { if (draggedNav) { e.preventDefault(); saveNavOrder(); } });
nav.addEventListener('dragend', () => { draggedNav?.classList.remove('dragging'); draggedNav = null; saveNavOrder(); });
nav.addEventListener('keydown', e => {
  const b = e.target.closest('[data-nav]'); if (!b || !e.altKey || !['ArrowUp', 'ArrowDown'].includes(e.key)) return;
  e.preventDefault(); const items = navItems(), i = items.indexOf(b), j = i + (e.key === 'ArrowUp' ? -1 : 1);
  if (j < 0 || j >= items.length) return;
  nav.insertBefore(b, e.key === 'ArrowUp' ? items[j] : items[j].nextSibling); b.focus(); saveNavOrder();
});
ECO.navToggle(mEl('nav-toggle'), document.querySelector('.module-shell'));

// Workspace tabs --------------------------------------------------------------------------------------
const tabs = document.querySelector('#workspace-content .tabs'), panels = document.querySelector('#workspace-content .panels');
const frames = new Map(), hidden = new Set();
let activePlace = null;
const keyOf = dir => dir.replaceAll('\\', '/').toLowerCase();
const addTabButton = document.createElement('button');
addTabButton.type = 'button'; addTabButton.textContent = '＋'; addTabButton.className = 'add-workspace-tab'; addTabButton.title = '作業空間を作る・表示'; addTabButton.setAttribute('aria-label', addTabButton.title);
const tabBar = document.createElement('div'); tabBar.className = 'workspace-tab-bar'; tabs.before(tabBar); tabBar.append(tabs, addTabButton);
const emptyNote = document.createElement('div'); emptyNote.className = 'empty-workspaces';
emptyNote.innerHTML = '<p>表示中の作業空間はありません。</p><p>作業空間は、タスクの作業をする場所です。タスク管理で「作業を開始」すると、モジュールの中（.ecobuild/w/〈番号〉）にタスクブランチ（task/〈番号〉-〈名前〉）の作業空間を作り、ここにタブで開きます。タスクを完了する・作業を捨てると、作業空間は消えます。閉じたタブは「＋」から再表示できます。</p><button type="button" data-go-tasks>タスク管理を開く</button>';
emptyNote.querySelector('[data-go-tasks]').addEventListener('click', () => showModulePage('tasks'));
panels.append(emptyNote);

// Every workspace of the module has a tab (its state read by ecobuild status).
const isWorkspace = dir => !!MOD.states.get(keyOf(dir));
const tabVisible = dir => isWorkspace(dir) && !hidden.has(keyOf(dir));
function syncTabs() {
  for (const group of tabs.querySelectorAll('.workspace-tab-group')) {
    const dir = MOD.places.find(p => keyOf(p) === group.dataset.group);
    group.hidden = !dir || !tabVisible(dir);
  }
  if (activePlace && !MOD.places.some(p => keyOf(p) === activePlace && tabVisible(p))) {
    panels.querySelector(`[role=tabpanel][data-dir="${CSS.escape(activePlace)}"]`)?.setAttribute('hidden', '');
    activePlace = null;
  }
  if (!activePlace) { const next = MOD.places.find(tabVisible); if (next) activate(next); }
  emptyNote.hidden = !!activePlace;
}

const placeLabel = dir => {
  const state = MOD.states.get(keyOf(dir));
  const branch = state ? (state.reviewing ? `PR #${state.reviewing} を確認中` : state.branch || '（ブランチなし）') : '…';
  const title = state?.task ? MOD.titles.get(keyOf(dir)) || '' : '';
  return {branch, title, where: dir.replace(/[\\/]+$/, '').split(/[\\/]/).pop()};
};
function renderTab(dir) {
  const button = tabs.querySelector(`[data-dir="${CSS.escape(keyOf(dir))}"]`); if (!button) return;
  const {branch, title, where} = placeLabel(dir);
  // A task's tab shows the task's title (its branch, task/<n>-<name>, on hover); another workspace shows its branch.
  const lock = ECO.lockOf(MOD.states.get(keyOf(dir)));
  button.innerHTML = `${ECO.esc(title || branch)}${where ? `<small class="where">${ECO.esc(where)}</small>` : ''}${lock.locked ? '<span class="lock-mark" aria-label="ロック中">🔒</span>' : ''}`;
  button.title = `${branch}　${dir}` + (lock.locked ? `\nロック中：${ECO.lockSummary(lock)}` : '');
  syncTabs();
}
async function refreshState(dir) {
  const doc = await ECO.cli(dir, ['status'], {quiet: true});
  if (doc.ok) MOD.states.set(keyOf(dir), doc.result); else MOD.states.delete(keyOf(dir));
  renderTab(dir);
  if (!doc.ok) syncPlaces();   // removed (task finish・prune etc. in its frame, or elsewhere)?
  return doc.ok ? doc.result : null;
}
function addTab(dir) {
  if (tabs.querySelector(`[data-dir="${CSS.escape(keyOf(dir))}"]`)) return;
  const group = document.createElement('div'), button = document.createElement('button'), close = document.createElement('button'), panel = document.createElement('section');
  const id = 'ws-' + Math.random().toString(36).slice(2);
  group.className = 'workspace-tab-group'; group.setAttribute('role', 'presentation'); group.dataset.group = keyOf(dir);
  button.type = 'button'; button.setAttribute('role', 'tab'); button.dataset.dir = keyOf(dir); button.setAttribute('aria-controls', id);
  close.type = 'button'; close.className = 'close-workspace-tab'; close.textContent = '×'; close.title = 'タブを閉じる（作業空間は残ります）';
  panel.id = id; panel.setAttribute('role', 'tabpanel'); panel.hidden = true; panel.dataset.dir = keyOf(dir);
  button.addEventListener('click', () => activate(dir));
  close.addEventListener('click', () => closeTab(dir));
  group.draggable = true;
  group.append(button, close); tabs.append(group); panels.append(panel);
  renderTab(dir);
}
function activate(dir, focus = false) {
  const key = keyOf(dir);
  if (!MOD.places.some(p => keyOf(p) === key) || !isWorkspace(dir)) return;
  hidden.delete(key); activePlace = key; ECO.setState({workspace: dir});
  for (const group of tabs.querySelectorAll('.workspace-tab-group')) {
    const on = group.dataset.group === key; const place = MOD.places.find(p => keyOf(p) === group.dataset.group); group.hidden = !place || !tabVisible(place);
    const button = group.querySelector('[role=tab]'); button.setAttribute('aria-selected', String(on)); button.tabIndex = on ? 0 : -1;
    if (on && focus) button.focus();
  }
  for (const panel of panels.querySelectorAll('[role=tabpanel]')) panel.hidden = panel.dataset.dir !== key;
  if (!frames.has(key)) {
    const frame = document.createElement('iframe'); frame.title = MOD.name + ' 作業空間 ' + dir;
    frame.src = 'workspace.html?' + new URLSearchParams({module: MOD.root, dir, embedded: '1'});
    panels.querySelector(`[role=tabpanel][data-dir="${CSS.escape(key)}"]`).append(frame); frames.set(key, frame);
  }
  emptyNote.hidden = true;
}
function closeTab(dir) {
  const key = keyOf(dir); hidden.add(key);
  tabs.querySelector(`[data-group="${CSS.escape(key)}"]`).hidden = true;
  panels.querySelector(`[role=tabpanel][data-dir="${CSS.escape(key)}"]`).hidden = true;
  if (activePlace === key) {
    const next = MOD.places.find(tabVisible);
    if (next) activate(next, true); else { activePlace = null; emptyNote.hidden = false; }
  }
}
function removeTab(dir) {
  const key = keyOf(dir);
  frames.get(key)?.remove(); frames.delete(key);
  tabs.querySelector(`[data-group="${CSS.escape(key)}"]`)?.remove();
  panels.querySelector(`[role=tabpanel][data-dir="${CSS.escape(key)}"]`)?.remove();
  MOD.places = MOD.places.filter(p => keyOf(p) !== key); MOD.states.delete(key);
  if (activePlace === key) { activePlace = null; const next = MOD.places.find(tabVisible); if (next) activate(next); else emptyNote.hidden = false; }
}
// Reload what a place shows (after a task operation changed the branch there, etc.).
function reloadPlace(dir) {
  const key = keyOf(dir);
  frames.get(key)?.contentWindow?.location.reload();
  return refreshState(dir);
}
// The module's workspaces on this PC (workspace list: the module's own clone's workspaces): the tabs. A clone of the
// previous version (a workspace of its own, listed as legacy) opened as a module is its own one place.
MOD.workspaces = new Map();   // keyOf(path) → {name, path, branch, task, account, review}
let rootNoticed = false;
async function listedWorkspaces() {
  const doc = await ECO.cli(null, ['workspace', 'list'], {quiet: true});
  if (!doc.ok) { ECO.toast(doc.error?.message || 'このPCのモジュールの一覧を読めませんでした。', 'bad'); return null; }
  const mine = (doc.result.modules || []).find(m => keyOf(m.path) === keyOf(MOD.root));
  if (mine) {
    // The module's own clone is kept on the default branch (work is done in the workspaces): said once.
    if (!rootNoticed && mine.exists && mine.default_branch && mine.branch !== mine.default_branch) {
      rootNoticed = true;
      ECO.toast(`このモジュールのフォルダ（${MOD.root}）が ${mine.branch || '切り離された状態'} にいます。作業は作業空間でするので、既定のブランチ ${mine.default_branch} に戻してください。`, 'info', 12000);
    }
    return mine.workspaces || [];
  }
  const old = (doc.result.legacy || []).find(m => keyOf(m.path) === keyOf(MOD.root));
  return old ? [{name: '', path: MOD.root, branch: old.branch, task: old.task}] : [];
}
// Read the list again: tabs for new workspaces, none for removed ones (after a task operation here or elsewhere).
let syncing = null;
function syncPlaces() {
  syncing ??= (async () => {
    try {
      const listed = await listedWorkspaces(); if (!listed) return;
      MOD.workspaces = new Map(listed.map(w => [keyOf(w.path), w]));
      for (const p of [...MOD.places]) if (!MOD.workspaces.has(keyOf(p))) removeTab(p);
      const added = listed.map(w => w.path).filter(p => !MOD.places.some(q => keyOf(q) === keyOf(p)));
      for (const p of added) { MOD.places.push(p); addTab(p); }
      await Promise.all(added.map(refreshState));
      syncTabs();
    } finally { syncing = null; }
  })();
  return syncing;
}
async function loadPlaces() {
  await syncPlaces();
  for (const group of tabs.querySelectorAll('.workspace-tab-group')) group.draggable = true;
  restoreTabOrder();
}
// Reload what a place shows (after a task operation changed something there). The list is read again first: the
// operation may have made or removed a workspace (MOD.root, no tab, only reads the list again).
async function reloadPlace(dir) {
  await syncPlaces();
  const key = keyOf(dir);
  if (!MOD.places.some(p => keyOf(p) === key)) return null;
  frames.get(key)?.contentWindow?.location.reload();
  return refreshState(dir);
}
// Show the tab of a workspace (one just made: task start・task review give its place).
async function showPlace(dir) {
  if (!dir) return null;
  if (!MOD.places.some(p => keyOf(p) === keyOf(dir))) await syncPlaces();
  const place = MOD.places.find(p => keyOf(p) === keyOf(dir));
  if (!place) return null;
  await refreshState(place);
  showModulePage('workspace'); activate(place, true);
  return place;
}
// The place where task <n>'s task branch (task/<n>-<name>) is checked out (if any).
MOD.placeOfTask = n => MOD.places.find(p => MOD.states.get(keyOf(p))?.task === n || MOD.workspaces.get(keyOf(p))?.task === n) || null;
MOD.workspacePlaces = () => MOD.places.filter(p => MOD.states.get(keyOf(p))?.task);
MOD.openInVisualStudio = dir => ECO.openInVisualStudio(dir).then(() => reloadPlace(dir));
// The tab shown now, or null.
MOD.activePlace = () => MOD.places.find(p => keyOf(p) === activePlace) || null;
MOD.keyOf = keyOf; MOD.activate = activate; MOD.reloadPlace = reloadPlace; MOD.refreshState = refreshState; MOD.syncPlaces = syncPlaces; MOD.showPlace = showPlace;
// The image editor of a workspace (the settings' コンテナ leads there): shows its tab and opens the editor in its frame
// (once the frame is loaded). Without a workspace (no tab) there is nowhere to open it.
MOD.openImageEditor = dir => {
  const place = MOD.places.find(p => keyOf(p) === keyOf(dir || '')) || MOD.activePlace() || MOD.places.find(tabVisible);
  if (!place) { ECO.toast('イメージは作業空間の画面で編集します。タスク管理で「作業を開始」して作業空間を作ってください。', 'info', 8000); return false; }
  showModulePage('workspace'); activate(place, true);
  const frame = frames.get(keyOf(place));
  if (!frame) return false;
  const open = () => frame.contentWindow?.openImageEditor?.();
  if (frame.contentWindow?.openImageEditor && frame.contentDocument?.readyState === 'complete') open();
  else frame.addEventListener('load', open, {once: true});
  return true;
};
MOD.openWorkspace = async n => {
  // Show the tab where task <n>'s task branch is checked out; otherwise make its workspace (task start: the task branch
  // here or on GitHub is checked out in MOD.root/.ecobuild/w/<n>; the module's own clone stays as it is).
  let place = MOD.placeOfTask(n);
  if (!place) {
    const doc = await ECO.run(MOD.root, ['task', 'start', String(n)], {success: r => `タスクブランチ ${r.branch} の作業空間を開きました（${r.workspace}）。`});
    if (!doc) return false;
    place = await showPlace(doc.result.workspace);
    return !!place;
  }
  showModulePage('workspace'); activate(place, true); return true;
};
// Close a workspace: workspace close removes its folder (it stops when something there is not on GitHub). A task's
// branch stays (on this PC and GitHub): 「タスクブランチを開く」 makes the workspace again.
async function closePlace(dir) {
  const state = MOD.states.get(keyOf(dir)), review = state?.reviewing;
  if (ECO.whyLocked(state)) { if (await ECO.lockDialog(dir, state)) refreshState(dir); return; }   // in use: not removed
  if (!await ECO.confirm({title: '作業空間を閉じる', message: `作業空間 ${dir} をフォルダごと消します。ビルドの出力なども消えます。\n${review ? '確認をやめます（承認も差し戻しもしません）。' : 'タスクブランチは残るので、タスク管理の「タスクブランチを開く」でまた作業空間を作れます。'}\nGitHubにない作業（未コミットの変更・未Pushのコミット・退避）があるときは消しません。`, ok: '閉じる', danger: true})) return;
  if (await ECO.run(null, ['workspace', 'close', dir], {success: `作業空間 ${dir} を閉じました。`})) { removeTab(dir); await syncPlaces(); pageHooks.changed?.(); }
}

const TAB_ORDER_KEY = 'ecobuild-gui-tab-order:' + keyOf(MOD.root);
function saveTabOrder() { try { localStorage.setItem(TAB_ORDER_KEY, JSON.stringify([...tabs.querySelectorAll('.workspace-tab-group')].map(g => g.dataset.group))); } catch (e) { /* storage blocked */ } }
function restoreTabOrder() {
  try { for (const key of JSON.parse(localStorage.getItem(TAB_ORDER_KEY) || '[]')) { const g = tabs.querySelector(`[data-group="${CSS.escape(key)}"]`); if (g) tabs.append(g); } } catch (e) { /* storage blocked */ }
  MOD.places.sort((a, b) => [...tabs.children].findIndex(g => g.dataset.group === keyOf(a)) - [...tabs.children].findIndex(g => g.dataset.group === keyOf(b)));
}
let draggedTab = null;
tabs.addEventListener('dragstart', e => { draggedTab = e.target.closest('.workspace-tab-group'); if (draggedTab) { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', draggedTab.dataset.group); draggedTab.classList.add('dragging'); } });
tabs.addEventListener('dragover', e => {
  if (!draggedTab) return;
  const over = e.target.closest('.workspace-tab-group'); e.preventDefault();
  if (!over || over === draggedTab) return;
  const r = over.getBoundingClientRect();
  tabs.insertBefore(draggedTab, e.clientX < r.left + r.width / 2 ? over : over.nextSibling);
});
tabs.addEventListener('drop', e => { if (draggedTab) e.preventDefault(); });
tabs.addEventListener('dragend', () => { draggedTab?.classList.remove('dragging'); draggedTab = null; saveTabOrder(); restoreTabOrder(); });
tabs.addEventListener('contextmenu', e => {
  const group = e.target.closest('.workspace-tab-group'); if (!group) return;
  e.preventDefault();
  const dir = MOD.places.find(p => keyOf(p) === group.dataset.group), state = MOD.states.get(group.dataset.group) || {};
  const others = MOD.places.filter(p => keyOf(p) !== group.dataset.group && tabVisible(p));
  ECO.menu([
    ['このタブを表示', () => activate(dir, true)],
    ['タブを閉じる（作業空間は残ります）', () => closeTab(dir)],
    ['他のタブを閉じる', () => others.forEach(closeTab), others.length > 0],
    '-',
    ['エクスプローラーでフォルダを開く', () => ECO.action('folder', {dir}).catch(err => ECO.toast(err.message, 'bad'))],
    [`Visual Studio ${ECO.vsVersion()} で開く`, () => MOD.openInVisualStudio(dir)],
    [ECO.lockOf(state).locked ? 'ロックの詳細…' : '手動でロックする…', () => ECO.lockDialog(dir, state).then(changed => changed && refreshState(dir))],
    ['状態を更新', () => reloadPlace(dir)],
    ...(MOD.workspaces.get(group.dataset.group)?.name ? [['作業空間を閉じる…', () => closePlace(dir)]] : []),
    ...(state.task ? ['-', [`タスク #${state.task} を表示`, () => { showModulePage('tasks'); window.TASKS_SELECT?.(state.task); }]] : []),
  ], e.clientX, e.clientY);
});
tabs.addEventListener('keydown', event => {
  const tab = event.target.closest('[role=tab]'); if (!tab) return;
  if (event.key === 'Delete') { event.preventDefault(); closeTab(MOD.places.find(p => keyOf(p) === tab.dataset.dir)); return; }
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const visible = MOD.places.filter(tabVisible), index = visible.findIndex(p => keyOf(p) === tab.dataset.dir);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? visible.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + visible.length) % visible.length;
  activate(visible[next], true);
});

// "+" : show a hidden workspace or close one. Workspaces are made by starting a task (タスク管理) or checking a submission.
addTabButton.addEventListener('click', async () => {
  const rows = MOD.places.map((p, i) => {
    const {branch, title, where} = placeLabel(p), ws = isWorkspace(p);
    const label = ws ? `${ECO.esc(branch)}${title ? '　' + ECO.esc(title) : ''}${tabVisible(p) ? '（表示中）' : ''}${ECO.lockOf(MOD.states.get(keyOf(p))).locked ? '　🔒ロック中：' + ECO.esc(ECO.lockSummary(ECO.lockOf(MOD.states.get(keyOf(p))))) : ''}` : `${ECO.esc(branch)}（状態を読めません）`;
    const own = MOD.workspaces.get(keyOf(p))?.name;   // a workspace in the module (not the previous version's clone itself)
    return `<div class="picker-row"><button type="button" data-show="${i}" ${ws ? '' : 'disabled'}>${label}<small>作業空間 ${ECO.esc(where)}：${ECO.esc(p)}</small></button>${own ? `<button type="button" data-close-place="${i}" title="作業空間を閉じる（フォルダごと削除します）">閉じる</button>` : ''}</div>`;
  }).join('') || '<p class="eco-help">作業空間はまだありません。</p>';
  const d = document.createElement('dialog'); d.className = 'workspace-picker';
  d.innerHTML = `<h2>作業空間</h2><p>このモジュールの作業空間です。作業空間はタスクごとにモジュールの中（.ecobuild/w/）に作られ、タスクを完了する・作業を捨てると消えます。新しい作業空間は、タスク管理でタスクの「作業を開始」をすると作られます。</p><div>${rows}</div>
    <div class="picker-actions"><button type="button" data-go-tasks>タスク管理を開く</button><button type="button" data-close>閉じる</button></div>`;
  document.body.append(d); d.showModal();
  d.addEventListener('close', () => d.remove());
  d.addEventListener('click', async e => {
    const show = e.target.closest('[data-show]'), closing = e.target.closest('[data-close-place]');
    if (show) { d.close(); activate(MOD.places[Number(show.dataset.show)], true); }
    if (closing) { const dir = MOD.places[Number(closing.dataset.closePlace)]; d.close(); closePlace(dir); }
    if (e.target.closest('[data-go-tasks]')) { d.close(); showModulePage('tasks'); }
    if (e.target.closest('[data-close]')) d.close();
  });
});

// What the other pages care about in a place's state (the task list shows which tasks have a task branch or a PR).
const stateSignature = s => s ? [s.branch, s.task, s.reviewing, ECO.lockOf(s).locked, s.pull_request ? `${s.pull_request.number}:${s.pull_request.state}` : ''].join('|') : '';
// Messages from workspace frames: their state changed (commit, switch...), so update the tab label.
window.addEventListener('message', event => {
  if (event.origin !== location.origin) return;
  const data = event.data || {};
  if (data.type === 'workspace-changed' && data.dir) {
    if (data.title !== undefined) MOD.titles.set(keyOf(data.dir), data.title);
    const before = stateSignature(MOD.states.get(keyOf(data.dir)));
    const after = () => { if (stateSignature(MOD.states.get(keyOf(data.dir))) !== before) pageHooks.changed?.(); };
    if (data.status) { MOD.states.set(keyOf(data.dir), data.status); renderTab(data.dir); after(); } else refreshState(data.dir).then(after);
  }
  if (data.type === 'open-place' && data.dir) showPlace(data.dir);
  if (data.type === 'open-task' && data.n) MOD.openWorkspace(Number(data.n));
  if (data.type === 'show-task' && data.n) { showModulePage('tasks'); window.TASKS_SELECT?.(Number(data.n)); }
});

// Automatic locks (agent・container・command) come and go without the GUI: read the places again now and then.
setInterval(() => { if (!document.hidden) MOD.places.forEach(refreshState); }, 20000);
MOD.ready = loadPlaces().then(syncTabs);
