'use strict';
// Module window: left menu and the workspace tabs. A tab is a workspace on disk (the module's clone, or another
// workspace of it on this PC, e.g. one made by "task start --dir": ecobuild workspace list); it shows whatever branch /
// task branch is checked out there.
const MOD = (() => {
  const root = ECO.params.get('path') || '';
  const name = root.split(/[\\/]/).filter(Boolean).pop() || 'モジュール';
  return {root, name, places: [], states: new Map(), titles: new Map(), me: ''};
})();
const mEl = id => document.getElementById(id);
document.getElementById('module-title').textContent = MOD.name;
document.title = MOD.name + ' — ECOBuild';
ECO.info().then(info => { MOD.me = info.me || ''; });

// Left menu -----------------------------------------------------------------------------------------
const PAGES = ['workspace', 'tasks', 'manage', 'modinfo', 'settings', 'help'];
// 管理 was the page ブランチ (now its tab): the old name still leads there.
const pageOf = page => page === 'branches' ? 'manage' : page;
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
// The tabs of 管理 (ブランチ, …): the chosen one's panel and its buttons (data-manage-for) show.
document.getElementById('manage-tabs').addEventListener('click', e => {
  const view = e.target.closest('[data-manage-view]')?.dataset.manageView; if (!view) return;
  for (const b of document.querySelectorAll('#manage-tabs [data-manage-view]')) b.setAttribute('aria-selected', String(b.dataset.manageView === view));
  for (const p of document.querySelectorAll('#manage-content [data-manage-view-panel]')) p.hidden = p.dataset.manageViewPanel !== view;
  for (const p of document.querySelectorAll('#manage-content [data-manage-for]')) p.hidden = p.dataset.manageFor !== view;
});
// The tabs of 設定 (the others of a tab are モジュール's).
const SETTINGS_TABS = ['profiles', 'general', 'templates'];
// The left menu goes through the action "open" (as ecobuild gui open does); the window moves in onNavigate below.
for (const key of PAGES) mEl(key + '-menu').addEventListener('click', () => ECO.action('open', {module: MOD.root, page: key}).catch(() => showModulePage(key)));
ECO.onNavigate(({page, tab, task, command}) => {
  // The tab 「ブランチ」 (once モジュール's) is 管理's: --tab branches leads there.
  const target = page || (tab ? (tab === 'branches' ? 'manage' : SETTINGS_TABS.includes(tab) ? 'settings' : 'modinfo') : task ? 'tasks' : command ? 'help' : '');
  if (target) showModulePage(target);
  if (tab && tab !== 'branches') window.MODINFO_SHOW?.(tab);
  if (task) window.TASKS_SELECT?.(Number(task));
  if (command && typeof HELP !== 'undefined') HELP.show('help/commands/' + encodeURIComponent(command));
});
// Something ran elsewhere (an agent, another window): the places it touched are read again.
ECO.onChange(e => {
  const touched = e.dir ? MOD.places.filter(p => keyOf(p) === keyOf(e.dir)) : MOD.places;
  for (const place of touched) reloadPlace(place);
  pageHooks.changed?.();
});
// module.html?…#modinfo・#tasks opens that page (after the pages' scripts are loaded); #modinfo/projects etc. that tab too.
const hashPage = pageOf(location.hash.slice(1).split('/')[0]);
if (PAGES.includes(hashPage)) window.addEventListener('load', () => {
  showModulePage(hashPage);
  const task = hashPage === 'tasks' && Number(location.hash.split('/')[1]);
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
emptyNote.innerHTML = '<p>表示中の作業空間はありません。</p><p>作業空間は、このPCでモジュールの作業をする場所（clone）です。「＋」から新しい作業空間を作ったり、閉じたタブを再表示したりできます。タスク管理で「作業を開始」すると、選んだ作業空間にタスクブランチ（task/〈番号〉-〈名前〉）を置いて作業できます。</p><button type="button" data-go-tasks>タスク管理を開く</button>';
emptyNote.querySelector('[data-go-tasks]').addEventListener('click', () => showModulePage('tasks'));
panels.append(emptyNote);

// Every workspace of the module has a tab (the one made with the module first, on main etc. too: there the files can be
// seen and built; changes are made on a task branch, which the page says).
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
  return {branch, title, where: keyOf(dir) === keyOf(MOD.root) ? '' : dir.split(/[\\/]/).pop()};
};
function renderTab(dir) {
  const button = tabs.querySelector(`[data-dir="${CSS.escape(keyOf(dir))}"]`); if (!button) return;
  const {branch, title, where} = placeLabel(dir);
  // A task's tab shows the task's title (its branch, task/<n>-<name>, on hover); another workspace shows its branch.
  button.innerHTML = `${ECO.esc(title || branch)}${where ? `<small class="where">${ECO.esc(where)}</small>` : ''}`;
  button.title = `${branch}　${dir}`;
  syncTabs();
}
async function refreshState(dir) {
  const doc = await ECO.cli(dir, ['status'], {quiet: true});
  if (doc.ok) MOD.states.set(keyOf(dir), doc.result); else MOD.states.delete(keyOf(dir));
  renderTab(dir);
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
// The same repository: 所有者/名前 (GitHub), otherwise the origin URL.
const identity = c => (c.repository || (c.url || '').replaceAll('\\', '/').replace(/\/+$/, '').replace(/\.git$/, '')).toLowerCase();
let moduleIdentity = null, recorded = [];
async function ownIdentity(clones) {
  const mine = clones.find(c => keyOf(c.path) === keyOf(MOD.root));
  if (mine && identity(mine)) return identity(mine);
  if (moduleIdentity === null) moduleIdentity = ((await ECO.call('module-repository', {dir: MOD.root}).catch(() => ({}))).repository || '').toLowerCase();
  return moduleIdentity;
}
// The other workspaces of this module on this PC (recorded by ecobuild: workspace list).
async function otherClones() {
  const doc = await ECO.cli(null, ['workspace', 'list'], {quiet: true});
  if (!doc.ok) { ECO.toast(doc.error?.message || 'このPCの作業空間の一覧を読めませんでした。', 'bad'); return []; }
  recorded = doc.result;
  const id = await ownIdentity(doc.result);
  return id ? doc.result.filter(c => c.exists && keyOf(c.path) !== keyOf(MOD.root) && identity(c) === id).map(c => c.path) : [];
}
async function loadPlaces() {
  MOD.places = [MOD.root, ...await otherClones()];
  MOD.places.forEach(addTab);
  for (const group of tabs.querySelectorAll('.workspace-tab-group')) group.draggable = true;
  restoreTabOrder();
  await Promise.all(MOD.places.map(refreshState));
}
// A workspace made by "task start --dir" is recorded by the CLI; a clone made otherwise is recorded here (workspace add).
async function addPlace(dir) {
  let list = await otherClones();
  if (!list.some(d => keyOf(d) === keyOf(dir)) && keyOf(dir) !== keyOf(MOD.root)) {
    // A folder in another recorded clone is not this module's: register would only change that record.
    const inside = (p, root) => keyOf(p) === keyOf(root) || keyOf(p).startsWith(keyOf(root).replace(/\/+$/, '') + '/');
    const theirs = recorded.find(c => inside(dir, c.path) && !inside(c.path, MOD.root) && !list.some(d => keyOf(d) === keyOf(c.path)));
    if (theirs) throw new Error(`${dir} は ${MOD.name} のcloneではありません（${theirs.path} は別のモジュールのcloneです）。`);
    const known = recorded.map(c => keyOf(c.path));
    const doc = await ECO.cli(null, ['workspace', 'add', dir], {quiet: true});
    if (!doc.ok) throw new Error([doc.error?.message, doc.error?.hint].filter(Boolean).join('\n'));
    dir = doc.result.path;   // the clone's root (a folder inside it may be given)
    list = await otherClones();
    if (keyOf(dir) !== keyOf(MOD.root) && !list.some(d => keyOf(d) === keyOf(dir))) {   // another module's
      if (!known.includes(keyOf(dir))) await ECO.cli(null, ['workspace', 'forget', dir], {quiet: true});
      throw new Error(`${dir} は ${MOD.name} のcloneではありません。`);
    }
  }
  for (const d of list) if (!MOD.places.some(p => keyOf(p) === keyOf(d))) { MOD.places.push(d); addTab(d); await refreshState(d); }
  const added = [MOD.root, ...list].find(d => keyOf(d) === keyOf(dir));
  if (!added) throw new Error(`${dir} は ${MOD.name} のcloneではありません。`);
  return added;
}
// The place where task <n>'s task branch (task/<n>-<name>) is checked out (if any).
MOD.placeOfTask = n => MOD.places.find(p => MOD.states.get(keyOf(p))?.task === n) || null;
MOD.workspacePlaces = () => MOD.places.filter(p => MOD.states.get(keyOf(p))?.task);
MOD.openInVisualStudio = dir => ECO.openInVisualStudio(dir).then(() => reloadPlace(dir));
// The tab shown now (the place started tasks go to by default), or null.
MOD.activePlace = () => MOD.places.find(p => keyOf(p) === activePlace) || null;
// A new workspace (workspace create: another clone of the module, on the default branch) next to the module's clone.
MOD.createWorkspace = async () => {
  const taken = new Set(MOD.places.map(keyOf)), base = MOD.root.replace(/[\\/]+$/, '');
  let n = 2; while (taken.has(keyOf(`${base}-${n}`))) n++;
  let created = null;
  await ECO.form({title: '新しい作業空間', intro: `${ECO.esc(MOD.name)} をもう1つcloneして、並行作業の場所にします（ブランチは既定のまま）。タスクはそこで「作業を開始」します。`,
    busy: '作業空間を作っています…', fields: [{name: 'dir', label: '場所（まだないフォルダ）', value: `${base}-${n}`, required: true}], ok: '作成',
    submit: async v => {
      const doc = await ECO.run(MOD.root, ['workspace', 'create', v.dir], {success: r => `作業空間を作りました：${r.root}`});
      if (!doc) return '作成できませんでした。';
      created = await addPlace(doc.result.root);
    }});
  if (created) { await reloadPlace(created); showModulePage('workspace'); activate(created, true); }
  return created;
};
MOD.keyOf = keyOf; MOD.activate = activate; MOD.reloadPlace = reloadPlace; MOD.addPlace = addPlace; MOD.refreshState = refreshState;
MOD.openWorkspace = async n => {
  // Show the tab where task <n>'s task branch is checked out; otherwise switch the module's clone to it (task start).
  let place = MOD.placeOfTask(n);
  if (!place) {
    const doc = await ECO.run(MOD.root, ['task', 'start', String(n)], {success: r => `タスクブランチ ${r.branch} に切り替えました。`});
    if (!doc) return false;
    place = MOD.root; await reloadPlace(place);
  }
  showModulePage('workspace'); activate(place, true); return true;
};

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
    ['状態を更新', () => reloadPlace(dir)],
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

// "+" : create a workspace, show a hidden place, register an existing clone as a workspace, forget one or close one. -----------------------------
addTabButton.addEventListener('click', async () => {
  const rows = MOD.places.map((p, i) => {
    const {branch, title, where} = placeLabel(p), main = keyOf(p) === keyOf(MOD.root), ws = isWorkspace(p);
    const place = main ? 'この作業空間' : '作業空間 ' + where;
    const label = ws ? `${ECO.esc(branch)}${title ? '　' + ECO.esc(title) : ''}${tabVisible(p) ? '（表示中）' : ''}` : `${ECO.esc(branch)}（状態を読めません）`;
    return `<div class="picker-row"><button type="button" data-show="${i}" ${ws ? '' : 'disabled'}>${label}<small>${ECO.esc(place)}：${ECO.esc(p)}</small></button>${main ? '' : `<button type="button" data-forget="${i}" title="一覧から外す（フォルダは削除しません）">外す</button><button type="button" data-close-place="${i}" title="作業空間を閉じる（フォルダごと削除します）">閉じる</button>`}</div>`;
  }).join('');
  const d = document.createElement('dialog'); d.className = 'workspace-picker';
  d.innerHTML = `<h2>作業空間</h2><p>このPCにある、このモジュールの作業空間です。並行して作業するなら、作業空間を増やします。タスクブランチはタスク管理の「作業を開始」で、置く作業空間を選んで作ります。</p><div>${rows}</div>
    <div class="picker-actions"><button type="button" data-create>新しい作業空間を作る…</button><button type="button" data-register>既存のcloneを作業空間として登録…</button><button type="button" data-close>閉じる</button></div>`;
  document.body.append(d); d.showModal();
  d.addEventListener('close', () => d.remove());
  d.addEventListener('click', async e => {
    const show = e.target.closest('[data-show]'), forget = e.target.closest('[data-forget]'), closing = e.target.closest('[data-close-place]');
    if (show) { d.close(); activate(MOD.places[Number(show.dataset.show)], true); }
    if (forget) {
      const dir = MOD.places[Number(forget.dataset.forget)]; d.close();
      if (await ECO.confirm({title: '一覧から外す', message: `${dir} をタブの一覧から外します。フォルダは消しません。\nこのフォルダで ecobuild を使うと、また一覧に出ます。`, ok: '外す'})) {
        if (await ECO.run(null, ['workspace', 'forget', dir])) removeTab(dir);
      }
    }
    if (closing) {
      const dir = MOD.places[Number(closing.dataset.closePlace)]; d.close();
      if (await ECO.confirm({title: '作業空間を閉じる', message: `作業空間 ${dir} をフォルダごと消します。ビルドの出力なども消えます。\nGitHubにない作業（未コミットの変更・未Pushのコミット・退避）があるときは消しません。`, ok: '閉じる', danger: true})) {
        if (await ECO.run(null, ['workspace', 'close', dir])) removeTab(dir);
      }
    }
    if (e.target.closest('[data-create]')) { d.close(); MOD.createWorkspace(); }
    if (e.target.closest('[data-register]')) {
      try {
        const {path} = await ECO.call('pick-folder', {title: '作業空間にするcloneのフォルダを選択', initial: MOD.root});
        if (path) { const dir = await addPlace(path); d.close(); activate(dir, true); }
      } catch (err) { ECO.toast(err.message, 'bad'); }
    }
    if (e.target.closest('[data-close]')) d.close();
  });
});

// What the other pages care about in a place's state (the task list shows which tasks have a task branch or a PR).
const stateSignature = s => s ? [s.branch, s.task, s.reviewing, s.pull_request ? `${s.pull_request.number}:${s.pull_request.state}` : ''].join('|') : '';
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
  if (data.type === 'open-place' && data.dir) addPlace(data.dir).then(dir => activate(dir, true));
  if (data.type === 'show-task' && data.n) { showModulePage('tasks'); window.TASKS_SELECT?.(Number(data.n)); }
});

MOD.ready = loadPlaces().then(syncTabs);
