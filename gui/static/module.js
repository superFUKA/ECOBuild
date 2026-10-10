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
addTabButton.type = 'button'; addTabButton.textContent = '＋'; addTabButton.className = 'add-workspace-tab'; addTabButton.title = '作業の場所を表示・追加'; addTabButton.setAttribute('aria-label', addTabButton.title);
const tabBar = document.createElement('div'); tabBar.className = 'workspace-tab-bar'; tabs.before(tabBar); tabBar.append(tabs, addTabButton);
const emptyNote = document.createElement('p'); emptyNote.className = 'empty-workspaces'; emptyNote.textContent = '「＋」から作業の場所を選んで表示できます。'; panels.append(emptyNote);

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
  group.append(button, close); tabs.append(group); panels.append(panel);
  renderTab(dir);
}
function activate(dir, focus = false) {
  const key = keyOf(dir);
  if (!MOD.places.some(p => keyOf(p) === key)) return;
  hidden.delete(key); activePlace = key;
  for (const group of tabs.querySelectorAll('.workspace-tab-group')) {
    const on = group.dataset.group === key; group.hidden = hidden.has(group.dataset.group);
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
    const next = MOD.places.find(p => !hidden.has(keyOf(p)));
    if (next) activate(next, true); else { activePlace = null; emptyNote.hidden = false; }
  }
}
function removeTab(dir) {
  const key = keyOf(dir);
  frames.get(key)?.remove(); frames.delete(key);
  tabs.querySelector(`[data-group="${CSS.escape(key)}"]`)?.remove();
  panels.querySelector(`[role=tabpanel][data-dir="${CSS.escape(key)}"]`)?.remove();
  MOD.places = MOD.places.filter(p => keyOf(p) !== key); MOD.states.delete(key);
  if (activePlace === key) { activePlace = null; const next = MOD.places.find(p => !hidden.has(keyOf(p))); if (next) activate(next); else emptyNote.hidden = false; }
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

tabs.addEventListener('keydown', event => {
  const tab = event.target.closest('[role=tab]'); if (!tab) return;
  if (event.key === 'Delete') { event.preventDefault(); closeTab(MOD.places.find(p => keyOf(p) === tab.dataset.dir)); return; }
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const visible = MOD.places.filter(p => !hidden.has(keyOf(p))), index = visible.findIndex(p => keyOf(p) === tab.dataset.dir);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? visible.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + visible.length) % visible.length;
  activate(visible[next], true);
});

// "+" : show a hidden place, register an existing dedicated clone, or forget one. -----------------------------
addTabButton.addEventListener('click', async () => {
  const rows = MOD.places.map((p, i) => {
    const {branch, where} = placeLabel(p), main = keyOf(p) === keyOf(MOD.root);
    return `<div class="picker-row"><button type="button" data-show="${i}">${ECO.esc(branch)}${!hidden.has(keyOf(p)) ? '（表示中）' : ''}<small>${ECO.esc(main ? 'モジュールのclone' : '専用のclone ' + where)}：${ECO.esc(p)}</small></button>${main ? '' : `<button type="button" data-forget="${i}" title="一覧から外す（フォルダは消さない）">外す</button>`}</div>`;
  }).join('');
  const d = document.createElement('dialog'); d.className = 'workspace-picker';
  d.innerHTML = `<h2>作業の場所</h2><p>タブは作業の場所（このモジュールのclone、または並行作業用の専用のclone）です。作業空間はタスク管理の「作業を開始」で作ります。</p><div>${rows}</div>
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

MOD.ready = loadPlaces().then(() => activate(MOD.root));
