'use strict';
// Module window: left menu and the workspace tabs. A tab is a place on disk (the module's clone, or a dedicated clone
// made by "task start --dir"); it shows whatever branch / workspace is checked out there.
const MOD = (() => {
  const root = ECO.params.get('path') || '';
  const name = root.split(/[\\/]/).filter(Boolean).pop() || 'モジュール';
  return {root, name, places: [], states: new Map(), titles: new Map(), me: ''};
})();
const mEl = id => document.getElementById(id);
document.getElementById('module-title').textContent = MOD.name;
document.getElementById('module-path').textContent = MOD.root;
document.title = MOD.name + ' — ECOBuild';
mEl('open-folder').addEventListener('click', () => ECO.call('open', {dir: MOD.root, path: ''}).catch(e => ECO.toast(e.message, 'bad')));
ECO.info().then(info => { MOD.me = info.me || ''; });

// Left menu -----------------------------------------------------------------------------------------
const PAGES = ['workspace', 'tasks', 'modinfo'];
const pageHooks = {};
function showModulePage(page) {
  for (const key of PAGES) {
    mEl(key + '-content').hidden = key !== page;
    if (key === page) mEl(key + '-menu').setAttribute('aria-current', 'page'); else mEl(key + '-menu').removeAttribute('aria-current');
  }
  pageHooks[page]?.();
}
for (const key of PAGES) mEl(key + '-menu').addEventListener('click', () => showModulePage(key));
// Reorder the left menu by drag and drop (Alt+↑／↓ with the keyboard). The order is kept per PC (localStorage).
const NAV_ORDER_KEY = 'ecobuild-gui-nav-order', nav = document.querySelector('.module-nav');
const navItems = () => [...nav.querySelectorAll('[data-nav]')];
function saveNavOrder() { try { localStorage.setItem(NAV_ORDER_KEY, JSON.stringify(navItems().map(b => b.dataset.nav))); } catch (e) { /* storage blocked */ } }
for (const key of PAGES) { const b = mEl(key + '-menu'); b.dataset.nav = key; b.draggable = true; b.title = b.title + '（ドラッグで並び替え）'; }
try {
  const saved = JSON.parse(localStorage.getItem(NAV_ORDER_KEY) || '[]');
  for (const key of saved) if (PAGES.includes(key)) nav.append(mEl(key + '-menu'));
} catch (e) { /* storage blocked or broken */ }
let draggedNav = null;
nav.addEventListener('dragstart', e => { draggedNav = e.target.closest('[data-nav]'); if (!draggedNav) return; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', draggedNav.dataset.nav); draggedNav.classList.add('dragging'); });
nav.addEventListener('dragover', e => {
  if (!draggedNav) return;
  const over = e.target.closest('[data-nav]'); e.preventDefault();
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
mEl('nav-toggle').addEventListener('click', () => {
  const collapsed = document.querySelector('.module-shell').classList.toggle('nav-collapsed'), toggle = mEl('nav-toggle');
  toggle.setAttribute('aria-expanded', String(!collapsed)); toggle.title = collapsed ? 'メニューを広げる' : 'メニューを細くする';
});

// Workspace tabs --------------------------------------------------------------------------------------
const tabs = document.querySelector('#workspace-content .tabs'), panels = document.querySelector('#workspace-content .panels');
const frames = new Map(), hidden = new Set();
let activePlace = null;
const keyOf = dir => dir.replaceAll('\\', '/').toLowerCase();
const addTabButton = document.createElement('button');
addTabButton.type = 'button'; addTabButton.textContent = '＋'; addTabButton.className = 'add-workspace-tab'; addTabButton.title = '作業空間を表示'; addTabButton.setAttribute('aria-label', addTabButton.title);
const tabBar = document.createElement('div'); tabBar.className = 'workspace-tab-bar'; tabs.before(tabBar); tabBar.append(tabs, addTabButton);
const emptyNote = document.createElement('div'); emptyNote.className = 'empty-workspaces';
emptyNote.innerHTML = '<p>表示している作業空間はありません。</p><p>作業空間はタスクごとの作業の場所（task/〈番号〉）です。タスク管理でタスクの「作業を開始」をすると、ここに表示されます。閉じたタブは「＋」から表示し直せます。</p><button type="button" data-go-tasks>タスク管理を開く</button>';
emptyNote.querySelector('[data-go-tasks]').addEventListener('click', () => showModulePage('tasks'));
panels.append(emptyNote);

// Only workspaces are tabs: a place shows a tab while a workspace (task/<n>) is checked out there, or while a PR is
// being checked there (task review). The module's clone on main / develop etc. is not a workspace, so it has no tab.
const isWorkspace = dir => { const state = MOD.states.get(keyOf(dir)); return !!(state && (state.workspace || state.reviewing)); };
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
  const title = state?.workspace ? MOD.titles.get(keyOf(dir)) || '' : '';
  return {branch, title, where: keyOf(dir) === keyOf(MOD.root) ? '' : dir.split(/[\\/]/).pop()};
};
function renderTab(dir) {
  const button = tabs.querySelector(`[data-dir="${CSS.escape(keyOf(dir))}"]`); if (!button) return;
  const {branch, title, where} = placeLabel(dir);
  button.innerHTML = `${ECO.esc(branch)}${title ? `<small>${ECO.esc(title)}</small>` : ''}${where ? `<small class="where">${ECO.esc(where)}</small>` : ''}`;
  button.title = dir;
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
  close.type = 'button'; close.className = 'close-workspace-tab'; close.textContent = '×'; close.title = 'タブを閉じる（表示だけ）';
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
  hidden.delete(key); activePlace = key;
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
async function loadPlaces() {
  let extra = [];
  try { extra = await ECO.call('workspaces', {module: MOD.root}); } catch (e) { ECO.toast(e.message, 'bad'); }
  MOD.places = [MOD.root, ...extra];
  MOD.places.forEach(addTab);
  for (const group of tabs.querySelectorAll('.workspace-tab-group')) group.draggable = true;
  restoreTabOrder();
  await Promise.all(MOD.places.map(refreshState));
}
async function addPlace(dir) {
  const list = await ECO.call('workspaces/add', {module: MOD.root, dir});
  for (const d of list) if (!MOD.places.some(p => keyOf(p) === keyOf(d))) { MOD.places.push(d); addTab(d); await refreshState(d); }
  const added = list.find(d => keyOf(d) === keyOf(dir)) || dir;
  return added;
}
// The place where workspace task/<n> is checked out (if any).
MOD.placeOfTask = n => MOD.places.find(p => MOD.states.get(keyOf(p))?.workspace === n) || null;
MOD.workspacePlaces = () => MOD.places.filter(p => MOD.states.get(keyOf(p))?.workspace);
MOD.openInVisualStudio = dir => ECO.openInVisualStudio(dir).then(() => reloadPlace(dir));
MOD.keyOf = keyOf; MOD.activate = activate; MOD.reloadPlace = reloadPlace; MOD.addPlace = addPlace; MOD.refreshState = refreshState;
MOD.openWorkspace = async n => {
  // Show the tab where task/<n> is checked out; otherwise switch the module's clone to it (task start).
  let place = MOD.placeOfTask(n);
  if (!place) {
    const doc = await ECO.run(MOD.root, ['task', 'start', String(n)], {success: `作業空間 task/${n} に切り替えました。`});
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
    ['タブを閉じる（表示だけ）', () => closeTab(dir)],
    ['ほかのタブを閉じる', () => others.forEach(closeTab), others.length > 0],
    '-',
    ['エクスプローラーでフォルダを開く', () => ECO.call('open', {dir, path: ''}).catch(err => ECO.toast(err.message, 'bad'))],
    [`Visual Studio ${ECO.vsVersion()} で開く`, () => MOD.openInVisualStudio(dir)],
    ['状態を読み直す', () => reloadPlace(dir)],
    ...(state.workspace ? ['-', [`タスク #${state.workspace} を見る`, () => { showModulePage('tasks'); window.TASKS_SELECT?.(state.workspace); }]] : []),
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

// "+" : show a hidden place, register an existing dedicated clone, or forget one. -----------------------------
addTabButton.addEventListener('click', async () => {
  const rows = MOD.places.map((p, i) => {
    const {branch, title, where} = placeLabel(p), main = keyOf(p) === keyOf(MOD.root), ws = isWorkspace(p);
    const place = main ? 'モジュールのclone' : '専用のclone ' + where;
    const label = ws ? `${ECO.esc(branch)}${title ? '　' + ECO.esc(title) : ''}${tabVisible(p) ? '（表示中）' : ''}` : `${ECO.esc(branch)}（作業空間ではありません）`;
    return `<div class="picker-row"><button type="button" data-show="${i}" ${ws ? '' : 'disabled'}>${label}<small>${ECO.esc(place)}：${ECO.esc(p)}</small></button>${main ? '' : `<button type="button" data-forget="${i}" title="一覧から外す（フォルダは消さない）">外す</button>`}</div>`;
  }).join('');
  const d = document.createElement('dialog'); d.className = 'workspace-picker';
  d.innerHTML = `<h2>作業空間を表示</h2><p>作業空間（task/〈番号〉）が出ている場所だけをタブにします。作業空間はタスク管理の「作業を開始」で作ります（並行作業用の専用のcloneも選べます）。</p><div>${rows}</div>
    <div class="picker-actions"><button type="button" data-register>手元の専用のcloneを登録…</button><button type="button" data-close>閉じる</button></div>`;
  document.body.append(d); d.showModal();
  d.addEventListener('close', () => d.remove());
  d.addEventListener('click', async e => {
    const show = e.target.closest('[data-show]'), forget = e.target.closest('[data-forget]');
    if (show) { d.close(); activate(MOD.places[Number(show.dataset.show)], true); }
    if (forget) {
      const dir = MOD.places[Number(forget.dataset.forget)]; d.close();
      if (await ECO.confirm({title: '一覧から外す', message: `${dir} をタブの一覧から外します。フォルダは消しません（手元から消すには、タスク管理の「手元の作業空間を消す」を使います）。`, ok: '外す'})) {
        await ECO.call('workspaces/remove', {module: MOD.root, dir}); removeTab(dir);
      }
    }
    if (e.target.closest('[data-register]')) {
      try {
        const {path} = await ECO.call('pick-folder', {title: '専用のcloneのフォルダを選ぶ', initial: MOD.root});
        if (path) { const dir = await addPlace(path); d.close(); activate(dir, true); }
      } catch (err) { ECO.toast(err.message, 'bad'); }
    }
    if (e.target.closest('[data-close]')) d.close();
  });
});

// Messages from workspace frames: their state changed (commit, switch...), so update the tab label.
window.addEventListener('message', event => {
  if (event.origin !== location.origin) return;
  const data = event.data || {};
  if (data.type === 'workspace-changed' && data.dir) {
    if (data.title !== undefined) MOD.titles.set(keyOf(data.dir), data.title);
    if (data.status) { MOD.states.set(keyOf(data.dir), data.status); renderTab(data.dir); } else refreshState(data.dir);
    pageHooks.changed?.();
  }
  if (data.type === 'open-place' && data.dir) addPlace(data.dir).then(dir => activate(dir, true));
  if (data.type === 'show-task' && data.n) { showModulePage('tasks'); window.TASKS_SELECT?.(Number(data.n)); }
});

MOD.ready = loadPlaces().then(syncTabs);
