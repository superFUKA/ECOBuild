'use strict';
// Hub: the list of modules (each module's own clone on this PC: ecobuild workspace list) and the settings shared by every module.
const $ = id => document.getElementById(id);
const {esc} = ECO;

// Navigation ------------------------------------------------------------------------------------
ECO.navToggle($('nav-toggle'), document.body);
const navigation = document.querySelectorAll('[data-page]');
function showHubPage(name) {
  const button = document.querySelector(`[data-page="${name}"]`); if (!button) return;
  ECO.setState({page: name});
  navigation.forEach(item => {
    const selected = item === button;
    if (selected) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
    $(item.dataset.page).hidden = !selected;
  });
  if (button.dataset.page === 'settings') loadSettings();
  if (button.dataset.page === 'help') HELP.show(location.hash.slice(1));
  if (button.dataset.page === 'operator') OPERATOR.show();
}
navigation.forEach(button => button.addEventListener('click', () => {
  const page = button.dataset.page;
  // すぐ切り替える（サーバーの返事を待たない。読み直しで接続が埋まっていると、切り替えが待たされる）
  showHubPage(page);
}));
ECO.onNavigate(({page, tab, command}) => {
  if (command) { location.hash = 'help/commands/' + encodeURIComponent(command); showHubPage('help'); HELP.show(location.hash.slice(1)); return; }
  showHubPage(page === 'help' || page === 'settings' ? page : 'modules');   // settings：ハブの設定（コンテナのイメージ等）
  if (page === 'settings' && tab === 'agents') showSettingsGroup('agents');   // エージェントのプリセット
});
ECO.onChange(() => loadModules());
if (location.hash.startsWith('#help')) setTimeout(() => showHubPage('help'));
else if (location.hash.startsWith('#settings')) setTimeout(() => { showHubPage('settings'); if (location.hash === '#settings/agents') showSettingsGroup('agents'); });

// Module list -----------------------------------------------------------------------------------
let modules = [];
// The modules on GitHub (ecobuild module list --all): the archived ones are listed in 「アーカイブ済み」 below the list,
// and the others not in the list are offered to clone.
// Read once (it asks GitHub about every repository) and again after archiving or deleting one.
let githubModules = null, githubModulesLoading = null;
// workspace list answers at once but module list waits for GitHub: the list is shown at once. So that an archived module
// does not show among the others meanwhile, the archived ones of the last answer are kept on this PC (a display cache:
// GitHub's answer replaces it; one archived elsewhere since then moves when it comes).
let clonesLoaded = false;
const ARCHIVED_KEY = 'ecobuild-gui-archived-modules';
let lastArchived = [];
try { lastArchived = JSON.parse(localStorage.getItem(ARCHIVED_KEY) || '[]'); } catch (e) { /* storage blocked */ }
const knownModules = () => githubModules || lastArchived;
// Cached (ECO.query): the last answer shows at once; GitHub's newer one replaces it when it comes.
function applyGithubModules(doc) {
  githubModules = doc.ok ? doc.result : [];
  if (doc.ok) {
    lastArchived = githubModules.filter(g => g.archived).map(g => ({repository: g.repository, description: g.description || '', archived: true}));
    try { localStorage.setItem(ARCHIVED_KEY, JSON.stringify(lastArchived)); } catch (e) { /* storage blocked */ }
  }
  renderModules(); renderCloneCandidates();
}
function loadGithubModules() {
  githubModulesLoading = ECO.query(null, ['module', 'list', '--all'], applyGithubModules).then(doc => {
    githubModulesLoading = null; applyGithubModules(doc);
  });
  return githubModulesLoading;
}
// 所有者/名前 when both have it, otherwise the names (a module whose origin is not on GitHub has only its name).
const sameRepository = (a, b) => {
  if (!a || !b) return false;
  const full = a.includes('/') && b.includes('/'), key = x => (full ? x : x.split('/').pop()).toLowerCase();
  return key(a) === key(b);
};
const githubEntry = m => knownModules().find(g => sameRepository(g.repository, m.repository || m.name));
// 「アーカイブ済み」 is what the CLI says (module list). The workspaces of an archived module stay recorded (workspace list)
// but leave the list: they are shown under the archived module, and deleting it can remove them (--remove-workspaces).
let archived = [];
function renderArchived() {
  archived = knownModules().filter(g => g.archived).map(g => {
    const local = [...clones, ...legacy].filter(c => c.exists && sameRepository(g.repository, cloneRepository(c)));
    return {name: g.repository.split('/').pop(), repository: g.repository, description: g.description, clones: local,
            path: local[0]?.path || '', exists: local.length > 0};
  });
  $('archived-modules').hidden = !archived.length;
  $('archived-count').textContent = archived.length;
  $('archived-list').innerHTML = archived.map((m, i) => `<li><div><strong>${esc(m.repository)}</strong>${m.description ? `<small>${esc(m.description)}</small>` : ''}
      ${m.clones.map(c => `<small>このPC：${esc(c.path)}</small>`).join('')}</div>
      <span class="archived-actions">${m.exists ? `<button type="button" data-archived="folder" data-i="${i}">フォルダを開く</button>` : ''}<button type="button" data-archived="unarchive" data-i="${i}">解除</button><button type="button" class="danger-text" data-archived="delete" data-i="${i}">削除…</button></span></li>`).join('');
}
$('archived-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-archived]'); if (!button) return;
  const m = archived[Number(button.dataset.i)];
  if (button.dataset.archived === 'delete') { putAwayModule(m); return; }
  if (button.dataset.archived === 'folder') { ECO.action('folder', {dir: m.path}).catch(e => ECO.toast(e.message, 'bad')); return; }
  const doc = await ECO.run(m.exists ? m.path : null, ['module', 'unarchive', m.repository],
    {success: r => `${r.repository} のアーカイブを解除しました。` + (m.exists ? '一覧に戻しました。' : '使うには「＋ モジュール追加」の「GitHubから取得」で取得してください。'), busy: `${m.repository} のアーカイブを解除しています…`});
  if (doc) { await loadGithubModules(); loadModules(); }
});
// A module opens in its own app window (like the hub), not in a browser tab: Electron opens window.open as a window,
// otherwise the server starts it (Edge).
// (ECO.action open: an open window of the module comes forward instead of a second one.)
const openModule = path => ECO.action('open', {module: path}).catch(e => ECO.toast(e.message, 'bad'));

// clones: the modules on this PC (workspace list: modules, each a module's own clone with its workspaces inside);
// legacy: the workspaces the previous version made (clones of their own), to be closed.
let clones = [], legacy = [], order = [];
const pathKey = p => p.replaceAll('\\', '/').toLowerCase();
const baseName = p => p.split(/[\\/]/).filter(Boolean).pop() || p;
// 所有者/名前 when the origin is on GitHub, otherwise the name in the URL (matched by name: sameRepository).
const cloneRepository = c => c.repository || (c.url ? baseName(c.url).replace(/\.git$/, '') : '');
// The module's name: the GitHub repository's name (without its owner); '' for a clone of a local folder (its folder's
// name is shown: not mistaken for the module it was cloned from).
const repositoryName = c => baseName(c.repository || '');
async function loadModules() {
  if (!$('module-list')) return;   // after "GUIを終了"
  const take = result => { clones = result?.modules || []; legacy = result?.legacy || []; };
  const [doc, saved] = await Promise.all([ECO.query(null, ['workspace', 'list'], fresh => { take(fresh.result); renderModules(); }), ECO.call('modules/order', {}).catch(() => [])]);
  if (!doc.ok) ECO.showError(doc, 'このPCのモジュールの一覧を読めませんでした');
  take(doc.ok ? doc.result : null); clonesLoaded = true;
  order = saved.map(pathKey);
  renderModules();
}
function renderModules() {
  if (!$('module-list') || !clonesLoaded) return;
  const rank = m => { const i = order.indexOf(pathKey(m.path)); return i < 0 ? order.length : i; };
  // One card per module: its own clone (the CLI lists each module once; its workspaces are inside it). The card shows the
  // module's name, not the folder's.
  renderLegacy();
  modules = clones
    .map(c => ({path: c.path, name: repositoryName(c) || baseName(c.path), exists: c.exists, repository: cloneRepository(c), notClone: c.exists && !c.url,
      type: c.type || (cloneRepository(c) && githubEntry({repository: cloneRepository(c)})?.type) || ''}))
    .filter(m => !githubEntry(m)?.archived)
    .map((m, i) => [m, i]).sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j).map(([m]) => m);
  renderArchived();
  const list = $('module-list');
  $('no-active-modules').hidden = modules.length > 0 || !archived.length;
  if (!modules.length) {
    list.innerHTML = archived.length ? '' : '<li class="empty-modules" style="grid-column:1/-1">モジュールはまだありません。<div class="settings-actions"><button type="button" class="add-button" id="empty-add-module">＋ モジュール追加</button></div></li>';
    $('empty-add-module')?.addEventListener('click', () => $('add-module').click());
    return;
  }
  // A heading per type (in the order the types first come in the list; a module whose type is not known goes last).
  const types = [...new Set(modules.map(m => m.type || ''))].sort((a, b) => (a === '') - (b === ''));
  const card = (m, i) => `<li class="${m.exists ? '' : 'missing'}" data-index="${i}" data-type="${esc(m.type || '')}" draggable="true" title="${esc(m.path)}">
    <a role="link" tabindex="0" data-open="${i}"><span class="module-icon c${hueOf(m.name)}" aria-hidden="true">${esc(initialsOf(m.name))}</span>
    <span class="module-text"><span class="module-name">${esc(m.name)}${!m.exists ? '<span class="module-state">フォルダが見つかりません</span>' : m.notClone ? '<span class="module-state">gitのcloneではありません</span>' : ''}</span>
    <span class="module-path">${esc(m.repository || m.path)}</span></span><span class="module-go" aria-hidden="true">↗</span></a>
    <button type="button" class="module-menu" data-menu="${i}" aria-label="${esc(m.name)} の操作" title="操作">⋯</button></li>`;
  list.innerHTML = types.map(type => {
    const members = modules.map((m, i) => [m, i]).filter(([m]) => (m.type || '') === type);
    return `<li class="module-type-head" role="presentation"><h3>${esc(type ? typeLabel(type) : '型が分からないもの')}</h3><span>${members.length}</span></li>${members.map(([m, i]) => card(m, i)).join('')}`;
  }).join('');
}
// The card's icon: a colour from the name (stays when the list is reordered) and two letters after the prefix many
// modules share (ECOSTL・ECOCppLogger → ST・CL, not E・E).
const hueOf = name => [...name].reduce((h, c) => (h * 33 + c.charCodeAt(0)) >>> 0, 5381) % 6;
function initialsOf(name) {
  const lower = name.toLowerCase();
  let rest = name;
  for (const other of modules) {
    if (other.name === name) continue;
    let n = 0; const o = other.name.toLowerCase();
    while (n < lower.length && lower[n] === o[n]) n++;
    // Cut only at a word boundary (ECO|Bot, not ECOB|ot) and keep something after it.
    while (n >= 2 && !(n < name.length && /[A-Z0-9_\-. ]/.test(name[n]))) n--;
    if (n >= 2 && name.length - n < rest.length) rest = name.slice(n);
  }
  rest = rest.replace(/^[_\-. ]+/, '') || name;
  const second = rest.slice(1).match(/[A-Z0-9]/)?.[0] || rest[1] || '';
  return (rest[0] || '?').toUpperCase() + second;
}
// The workspaces the previous version made (clones of their own): shown apart, to be closed (workspace close; it stops
// when something there is not on GitHub). Work is now done in workspaces inside the module (.ecobuild/w/).
function renderLegacy() {
  const box = $('legacy-workspaces'); if (!box) return;
  box.hidden = !legacy.length;
  $('legacy-count').textContent = legacy.length;
  $('legacy-list').innerHTML = legacy.map((c, i) => `<li><div><strong>${esc(cloneRepository(c) || '（GitHubのリポジトリなし）')}${!c.exists ? '・フォルダが見つかりません' : c.task != null ? `・タスク #${c.task}` : c.branch ? '・' + esc(c.branch) : ''}</strong><small class="legacy-path">${esc(c.path)}${c.task != null && c.branch ? `（${esc(c.branch)}）` : ''}</small></div>
      <span class="archived-actions">${c.exists ? `<button type="button" data-legacy="folder" data-i="${i}">フォルダを開く</button><button type="button" class="danger-text" data-legacy="close" data-i="${i}">閉じる…</button>` : `<button type="button" data-legacy="forget" data-i="${i}">一覧から外す</button>`}</span></li>`).join('');
}
$('legacy-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-legacy]'); if (!button) return;
  const c = legacy[Number(button.dataset.i)];
  if (button.dataset.legacy === 'folder') { ECO.action('folder', {dir: c.path}).catch(e => ECO.toast(e.message, 'bad')); return; }
  if (button.dataset.legacy === 'forget') { if (await ECO.run(null, ['workspace', 'forget', c.path], {success: `${c.path} を一覧から外しました。`})) loadModules(); return; }
  const doc = await ECO.run(null, ['workspace', 'close', c.path], {title: '前の作業空間を閉じる', busy: `${c.path} を閉じています…`, success: r => r.removed ? `${c.path} を閉じました。` : `${c.path} を閉じましたが、一部が残りました（${(r.left || []).join('、')}）。使っているプログラムを閉じてから消してください。`,
    confirm: `前の版の作業空間 ${c.path} をフォルダごと消します。ビルドの出力なども消えます。\nGitHubにない作業（未コミットの変更・未Pushのコミット・退避）があるときは消しません。続きの作業は、モジュールの窓のタスク管理で「作業を再開」すると、モジュールの中の作業空間でできます。`});
  if (doc) loadModules();
});
const TYPE_LABELS = {cpp: 'C++', python: 'Python', generic: 'その他（generic）'};
const typeLabel = type => TYPE_LABELS[type] ? `${TYPE_LABELS[type]}` : type;
// 一覧から外す: ecobuild workspace forget (the folder and the GitHub repository stay). With a reason: the module cannot be
// opened or put away (its folder is gone, its GitHub repository is gone, or the folder is no longer a clone).
async function forgetModule(m, reason = '') {
  const note = !m.exists ? 'フォルダはもうありません。' : `フォルダ（${m.path}）とGitHubのリポジトリはそのまま残ります。${reason ? '不要なら「フォルダを開く」から削除してください。' : 'なお、このフォルダで ecobuild を使うと（開発環境を開くなど）、再び一覧に表示されます。'}`;
  const choice = await ECO.dialog({title: reason ? `${m.name} は使えません` : '一覧から外す', body: `${reason ? `<p>${esc(reason)}</p>` : ''}<p>このPCの一覧から外します。${esc(note)}</p>`,
    buttons: [['キャンセル', '', false], ...(reason && m.exists ? [['フォルダを開く', '', 'folder']] : []), ['一覧から外す', 'primary', 'forget']]});
  if (choice === 'folder') { try { await ECO.action('folder', {dir: m.path}); } catch (e) { ECO.toast(e.message, 'bad'); } return; }
  if (choice === 'forget' && await ECO.run(null, ['workspace', 'forget', m.path], {success: `${m.name} を一覧から外しました。`})) loadModules();
}
$('module-list').addEventListener('click', async event => {
  const more = event.target.closest('[data-menu]');
  if (more) { const r = more.getBoundingClientRect(); moduleMenu(modules[Number(more.dataset.menu)], r.right, r.bottom + 4, {right: true}); return; }
  const open = event.target.closest('[data-open]');
  if (open) { const m = modules[Number(open.dataset.open)]; if (m.notClone) putAwayModule(m); else if (m.exists) openModule(m.path); else forgetModule(m, `フォルダ ${m.path} が見つかりません（移動・削除された等）。移動した場合は、移動先を「＋ モジュール追加」の「手元のフォルダを登録」で登録してください。`); }
});
$('module-list').addEventListener('keydown', event => { if (event.key === 'Enter' && event.target.matches('[data-open]')) event.target.click(); });

// Add a module: new / clone run the CLI; registering a local folder is done by the GUI. --------------
const addDialog = $('add-dialog'), addForm = $('add-form');
const field = name => addForm.elements.namedItem(name);
let types = [];
function defaultParent() {
  try { const saved = localStorage.getItem('ecobuild-gui-parent'); if (saved) return saved; } catch (e) { /* storage blocked */ }
  if (modules.length) return modules[0].path.replace(/[\\/][^\\/]+$/, '');
  return '';
}
function updateFields() {
  const method = addForm.querySelector('[name=method]:checked').value;
  addForm.querySelector('[type=submit]').textContent = {new: '作成する', clone: '取得する', register: '登録する', adopt: 'モジュールにする…'}[method];
  if (method === 'clone') { if (!githubModules && !githubModulesLoading) loadGithubModules(); renderCloneCandidates(); }
  for (const [id, on] of [['new-fields', method === 'new'], ['new-more', method === 'new'], ['clone-fields', method === 'clone'], ['register-fields', method === 'register'], ['adopt-fields', method === 'adopt']]) { $(id).hidden = !on; $(id).disabled = !on; }
  const local = method === 'register' || method === 'adopt';   // the folder is already on this PC
  $('parent-fields').hidden = local;
  field('directory').required = !local;
  // What to make first: the type's kinds (module types: new_kinds); a type without them takes no --kind.
  const type = field('type').value, info = types.find(t => t.name === type);
  const kinds = info ? info.new_kinds || [] : (FALLBACK_KINDS[type] || []), select = $('kind-select');
  if (select.dataset.type !== type) {
    const chosen = select.value;
    select.innerHTML = kinds.map(k => `<option value="${esc(k)}">${esc(kindText(type, k))}</option>`).join('');
    select.value = kinds.includes(chosen) ? chosen : (info?.default_new_kind || kinds[0] || '');
    select.dataset.type = type;
  }
  $('kind-fields').hidden = !kinds.length; select.disabled = !kinds.length;
  const named = kinds.length > 0 && select.value !== 'none';   // --project names what is made first
  $('project-field').hidden = !named; field('project').disabled = !named;
  field('project').placeholder = type === 'python' ? '省略時はモジュール名の小文字（パッケージ名）' : '省略時はモジュール名';
  // A library: whether its test is made too (module new --no-test when not).
  const library = kinds.length > 0 && LIBRARY_KINDS.includes(select.value);
  $('test-field').hidden = !library; field('test').disabled = !library;
  showDestination();
  $('test-label').textContent = type === 'cpp' ? `テスト用のProject（${field('project').value.trim() || field('name').value.trim() || '名前'}Test）も作る` : 'テスト（tests/）も作る';
}
// Where the new folder goes, shown before it is made (as GitHub's new repository page shows owner / name).
function showDestination() {
  const method = addForm.querySelector('[name=method]:checked').value, parent = field('directory').value.trim().replace(/[\\/]+$/, '');
  const name = method === 'new' ? field('name').value.trim() : (field('repository').value.trim().split('/').pop() || '');
  $('parent-note').textContent = parent && name ? `作成先：${parent}/${name}` : '';
}
addForm.addEventListener('input', event => { if (['directory', 'name', 'repository'].includes(event.target.name)) showDestination(); });
// module new --kind: the CLI's value and what it makes.
const FALLBACK_KINDS = {cpp: ['app', 'library', 'shared', 'none'], python: ['app', 'library', 'none']};
const LIBRARY_KINDS = ['library', 'shared'];   // made with their test (module new --no-test when not)
const KIND_TEXT = {
  cpp: {app: 'app（実行ファイル）', library: 'library（静的ライブラリ .lib）', shared: 'shared（共有ライブラリ .dll）', none: 'none（Projectを作らない）'},
  python: {app: 'app（実行できるパッケージ）', library: 'library（パッケージ）', none: 'none（パッケージを作らない）'},
};
const kindText = (type, kind) => KIND_TEXT[type]?.[kind] || kind;
$('add-module').addEventListener('click', async () => {
  addForm.reset(); addForm.querySelector('details').open = false;
  field('directory').value = defaultParent();
  $('add-error').textContent = ''; updateFields(); addDialog.showModal();
  if (!types.length) {
    const doc = await ECO.cli(null, ['module', 'types'], {quiet: true});
    if (doc.ok) {
      types = doc.result; delete $('kind-select').dataset.type;
      for (const id of ['type-select', 'adopt-type-select']) $(id).innerHTML = types.map(t => `<option value="${esc(t.name)}">${esc(typeLabel(t.name))}</option>`).join('');
      updateFields();
    }
  }
  ECO.info().then(info => { if (!field('directory').value && info.home) field('directory').value = info.home.replaceAll('\\', '/'); });
});
$('cancel-add').addEventListener('click', () => addDialog.close());
// The modules on GitHub not in the list yet: click one to fill in the repository.
function renderCloneCandidates() {
  const box = $('clone-candidates'); if (!box) return;
  if (!githubModules) { box.innerHTML = '<p class="note"><span class="eco-spinner"></span> GitHubにあるモジュールを読み込んでいます…</p>'; return; }
  const candidates = githubModules.filter(g => !g.archived && !modules.some(m => sameRepository(g.repository, m.repository || m.name)));
  box.innerHTML = candidates.length ? `<p class="note">GitHubにあるモジュール</p><ul>${candidates.map(g => `<li><button type="button" data-candidate="${esc(g.repository)}">
      <strong>${esc(g.repository)}</strong><small>${esc([g.type, g.private ? '非公開' : '公開', g.updated ? '更新 ' + ECO.localTime(g.updated) : ''].filter(Boolean).join('・'))}${g.description ? '　' + esc(g.description) : ''}</small></button></li>`).join('')}</ul>`
    : `<p class="note">${githubModules.length ? 'GitHubのモジュールは、すべて一覧に登録済みです。' : 'GitHubにモジュールが見つかりませんでした。'}</p>`;
}
$('clone-candidates').addEventListener('click', event => {
  const pick = event.target.closest('[data-candidate]'); if (!pick) return;
  field('repository').value = pick.dataset.candidate; showDestination();
  for (const b of $('clone-candidates').querySelectorAll('[data-candidate]')) b.classList.toggle('selected', b === pick);
});
addForm.addEventListener('change', updateFields);
addForm.addEventListener('input', e => { if (e.target.name === 'name' || e.target.name === 'project') updateFields(); });
addForm.addEventListener('click', async event => {
  const pick = event.target.closest('[data-pick]'); if (!pick) return;
  const input = field(pick.dataset.pick);
  try { const {path} = await ECO.call('pick-folder', {title: 'フォルダを選ぶ', initial: input.value}); if (path) { input.value = path; showDestination(); } } catch (e) { ECO.toast(e.message, 'bad'); }
});
addForm.addEventListener('submit', async event => {
  event.preventDefault();
  const data = new FormData(addForm), method = data.get('method'), error = $('add-error'), submit = addForm.querySelector('[type=submit]');
  error.textContent = '';
  if (method === 'adopt') { await adoptRepository(data.get('adopt-folder').trim(), data.get('adopt-type')); return; }
  if (method === 'register') {
    const doc = await ECO.cli(null, ['workspace', 'add', data.get('folder').trim()], {quiet: true});
    if (!doc.ok && doc.error?.code === 'not_in_module') {
      // Not a module yet: offer to make it one (module adopt) with the same folder.
      field('adopt-folder').value = data.get('folder').trim();
      addForm.querySelector('[name=method][value=adopt]').checked = true; updateFields();
      error.textContent = 'このフォルダは ECOBuild のモジュールではありません。GitHub のリポジトリの clone なら、型を選んでモジュールにできます。';
      return;
    }
    if (!doc.ok) { error.textContent = errorText(doc); return; }
    addDialog.close(); ECO.toast(baseName(doc.result.path) + ' を一覧に登録しました。'); loadModules();
    ECO.prefetch(doc.result.path).catch(() => null);   // behind: what its screens show first
    return;
  }
  const parent = data.get('directory').trim().replace(/[\\/]+$/, '');
  if (!parent) { error.textContent = '保存先の親フォルダを入力してください。'; return; }
  submit.disabled = true;
  let directory;
  try { directory = (await ECO.call('mkparent', {path: parent})).path; } catch (e) { error.textContent = e.message; submit.disabled = false; return; }
  const creating = method === 'new', name = creating ? data.get('name').trim() : data.get('repository').trim();
  const args = creating ? ['module', 'new', name, '--type', data.get('type')] : ['module', 'clone', name];
  if (creating) {
    for (const option of ['description', 'owner']) if (data.get(option).trim()) args.push('--' + option, data.get(option).trim());
    if (data.has('public')) args.push('--public');
    if (data.get('kind')) args.push('--kind', data.get('kind'));
    if (LIBRARY_KINDS.includes(data.get('kind')) && !data.has('test')) args.push('--no-test');
    if (data.get('project')?.trim()) args.push('--project', data.get('project').trim());
  }
  // Close the form and show the busy overlay ("ぐるぐる") with what the command is doing now (it reports each step).
  addDialog.close(); submit.disabled = false;
  const overlay = ECO.busy({
    title: `${name.split('/').pop()} を${creating ? '作成' : '取得'}しています…`, sub: directory + '/' + name.split('/').pop(),
  });
  let reported = [];
  const doc = await ECO.cli(directory, args, {quiet: true, onProgress: lines => { reported = lines; overlay.progress(lines); }});
  if (!doc.ok) {
    // Back to the form (the values stay) with the reason.
    overlay.end(); addDialog.showModal();
    const e = doc.error || {};
    error.textContent = [e.message, e.hint].filter(Boolean).join('\n');
    if (ECO.detailText(e.details)) ECO.showError(doc, creating ? '作成できませんでした' : '取得できませんでした');
    return;
  }
  try { localStorage.setItem('ecobuild-gui-parent', parent); } catch (e) { /* storage blocked */ }
  const made = baseName(doc.result.root);
  // While waiting anyway: read what the module's screens show first, so that it opens at once (ECO.prefetch).
  overlay.progress([...reported, 'モジュールの情報を読み込み中…']);
  await ECO.prefetch(doc.result.root).catch(() => null);
  await overlay.done(`${made} を${creating ? '作成' : '取得'}しました`);
  ECO.toast(`${made} を${creating ? '作成' : '取得'}しました。`);
  await loadModules();
});

// module adopt: show what it places (--dry-run) and where it pushes, then make the clone a module.
async function adoptRepository(folder, type) {
  const error = $('add-error'), submit = addForm.querySelector('[type=submit]');
  if (!folder) { error.textContent = 'リポジトリのフォルダを入力してください。'; return; }
  submit.disabled = true;
  const plan = await ECO.cli(folder, ['module', 'adopt', '--type', type, '--dry-run'], {quiet: true});
  submit.disabled = false;
  if (!plan.ok) { error.textContent = errorText(plan); return; }
  const r = plan.result;
  addDialog.close();
  const choice = await ECO.dialog({title: `${r.name} をモジュールにする`,
    body: `<p>${esc(r.root)} の <strong>${esc(r.branch)}</strong> を、型 ${esc(r.type)} のモジュールにします。次のファイルを置いて「ECOBuild のモジュールにする」としてコミットし、GitHub の ${esc(r.branch)} へ push します（ほかの人にも届きます）。</p>
      <ul>${r.paths.map(p => `<li><code>${esc(p)}</code></li>`).join('')}</ul>
      <p class="note">型が置くもの（C++ の Solution 等）も一緒にコミットします。タスクブランチは ${esc(r.branch)} から作ります。</p>`,
    buttons: [['戻る', '', false], ['モジュールにする', 'primary', true]]});
  if (!choice) { addDialog.showModal(); return; }
  const overlay = ECO.busy({title: `${r.name} をモジュールにしています…`, sub: r.root});
  let reported = [];
  const doc = await ECO.cli(folder, ['module', 'adopt', '--type', type], {quiet: true, onProgress: lines => { reported = lines; overlay.progress(lines); }});
  if (!doc.ok) {
    overlay.end(); addDialog.showModal();
    error.textContent = errorText(doc);
    if (ECO.detailText(doc.error?.details)) ECO.showError(doc, 'モジュールにできませんでした');
    return;
  }
  overlay.progress([...reported, 'モジュールの情報を読み込み中…']);
  await ECO.prefetch(doc.result.root).catch(() => null);
  await overlay.done(`${r.name} をモジュールにしました`);
  ECO.toast(`${r.name} をモジュールにしました（${doc.result.branch} に push 済み）。`);
  await loadModules();
}

// Settings ----------------------------------------------------------------------------------------
function ownerHint(owner) { field('owner').placeholder = owner ? '未指定なら ' + owner : '未指定ならログイン中のユーザー'; }
// The containers' images (ecobuild container image …): per module (its .ecobuild/container environment + ECOBuild), on this PC.
async function loadImages(doc = null) {
  doc = doc || await ECO.cli(null, ['container', 'image', 'list'], {quiet: true});
  const r = doc.ok ? doc.result : null, ready = !!r?.docker_ready;
  $('images-build').disabled = $('images-prune').disabled = !ready;
  if (!r) { $('images-status').textContent = doc.error?.message || 'イメージの一覧を読めませんでした。'; $('images-list').innerHTML = ''; return; }
  if (!ready) { $('images-status').textContent = `Docker が使えません（${r.docker_detail}）。環境の準備で導入できます。`; $('images-list').innerHTML = ''; return; }
  const folder = p => p.split(/[\\/]/).pop();
  const old = r.images.filter(i => !i.current && !i.used_by.length).length;
  $('images-status').textContent = [
    r.missing.length ? `まだ作っていない作業空間：${r.missing.map(folder).join('、')}（作らなくても、コンテナを動かすときに作ります）。` : '',
    old ? `どのコンテナも使っていない古いイメージが ${old} 個あります。` : ''].filter(Boolean).join(' ');
  // モジュールごとに1行：今の作り方のイメージ（環境に ECOBuild を重ねたもの）と、残っている古いもの
  const modules = [...new Set(r.images.map(i => i.module))].sort();
  $('images-list').innerHTML = modules.map(module => {
    const mine = r.images.filter(i => i.module === module), tops = mine.filter(i => !i.environment);
    const now = tops.find(i => i.current), env = mine.find(i => i.environment && i.current), older = mine.filter(i => !i.current);
    const used = mine.flatMap(i => i.used_by);
    const parts = [now ? `${esc(now.size)}・${esc(now.created)}` : '',
      env ? `環境 ${esc(env.name.split(':')[1])}` : '',
      used.length ? '使っている作業空間：' + esc(used.map(folder).join('、')) : '',
      older.length ? `古いもの ${older.length} 個（${older.map(i => esc(i.size)).join('・')}${older.some(i => i.used_by.length) ? '。使用中のものは、そのコンテナを次に動かすときに入れ替わります' : ''}）` : ''].filter(Boolean);
    // No image yet is the usual state (made when a container first runs): quiet, not a warning.
    return `<li><span class="type">${esc(module)}</span><span class="img-tag" title="${esc(now?.name || '')}">${now ? esc(now.name.split(':')[1]) : ''}</span>
      <span class="${now ? 'ok' : older.length ? 'missing' : 'muted'}">${now ? '今の作り方' : older.length ? '古いものだけ' : 'まだ作っていません'}</span>${parts.length ? `<small>${parts.join('　')}</small>` : ''}</li>`;
  }).join('');
}

// 設定の種類（全般・AI・エージェント・コンテナ・ECOBuild）
function showSettingsGroup(group) {
  const tabs = [...document.querySelectorAll('[data-settings-group]')];
  if (!tabs.some(t => t.dataset.settingsGroup === group)) group = 'general';
  for (const t of tabs) t.setAttribute('aria-selected', String(t.dataset.settingsGroup === group));
  for (const card of document.querySelectorAll('#settings .settings-card')) card.hidden = card.dataset.group !== group;
  try { localStorage.setItem('ecobuild.settingsGroup', group); } catch (e) { /* 覚えられなくてよい */ }
}
for (const t of document.querySelectorAll('[data-settings-group]')) t.addEventListener('click', () => showSettingsGroup(t.dataset.settingsGroup));
showSettingsGroup((() => { try { return localStorage.getItem('ecobuild.settingsGroup'); } catch (e) { return ''; } })() || 'general');
$('open-agents-settings').addEventListener('click', () => {
  if (window.ecobuildShell?.agents?.open) window.ecobuildShell.agents.open({settings: true});
  else ECO.toast?.('エージェントの窓は、アプリの GUI（Electron）でだけ使えます。', 'info');
});
$('images-build').addEventListener('click', async () => {
  const doc = await ECO.run(null, ['container', 'image', 'build'], {busy: 'イメージを作っています（1つ数分かかります）…', success: r => r.built.length ? `${r.built.length} 個のイメージを作りました。` : '今の作り方のイメージはすべてあります。'});
  if (doc) loadImages(doc);
});
$('images-prune').addEventListener('click', async () => {
  const doc = await ECO.run(null, ['container', 'image', 'prune'], {confirm: '今の作り方でなく、どのコンテナも使っていないイメージを消します。', title: '古いイメージを消す', success: r => r.removed.length ? `${r.removed.length} 個のイメージを消しました。` : '消す古いイメージはありません。'});
  if (doc) loadImages(doc);
});

// The token the agents inside the containers log in with (ecobuild agent token …). Never shown: only whether there is one.
async function loadToken() {
  const doc = await ECO.cli(null, ['agent', 'token', 'status'], {quiet: true});
  const saved = doc.ok && doc.result.saved;
  $('token-status').textContent = !doc.ok ? (doc.error?.message || '状態を読めませんでした。')
    : saved ? '保存済み' : '未設定';
  $('token-remove').hidden = !saved;
}
// The window it opens catches the token itself when claude setup-token ends: read the status again a few times.
$('token-login').addEventListener('click', async () => {
  if (!await ECO.run(null, ['agent', 'token', 'login'], {success: 'トークンを作る窓を開きました。ブラウザーで許可すると、出たトークンを自動で保存します。'})) return;
  for (let i = 0; i < 60 && $('token-status'); i++) { await new Promise(r => setTimeout(r, 5000)); await loadToken(); if (!$('token-remove').hidden) { ECO.toast('トークンを保存しました。'); return; } }
});
$('token-form').addEventListener('submit', async event => {
  event.preventDefault();
  const value = $('token-value').value.trim(); if (!value) return;
  const doc = await ECO.run(null, ['agent', 'token', 'set'], {stdin: value, success: 'トークンを保存しました。'});
  if (doc) { $('token-value').value = ''; loadToken(); }
});
$('token-remove').addEventListener('click', async () => {
  if (await ECO.run(null, ['agent', 'token', 'remove'], {confirm: '覚えたトークンを消します（コンテナの中で一度ログインしていれば、そのログインで使えます）。', title: 'トークンを消す', success: 'トークンを消しました。'})) loadToken();
});

// Agent presets (ecobuild agent preset …): this PC's own agents (and ECOBuild's samples), copied into a module's
// registrations from the module page エージェント. Edited with the shared AGENT_EDITOR; all the data comes from the CLI.
const presets = $('presets-editor') && AGENT_EDITOR.create($('presets-editor'), {kind: 'preset', dir: () => null});
$('presets-reload')?.addEventListener('click', () => presets?.load());

async function loadSettings() {
  if (!$('default-owner')) return;   // after "GUIを終了"
  loadImages(); loadToken(); presets?.load();
  const doc = await ECO.cli(null, ['config', 'list'], {quiet: true});
  if (doc.ok && $('default-owner')) { $('default-owner').value = doc.result.owner || ''; ownerHint(doc.result.owner); }
  const info = await ECO.info();
  $('about').innerHTML = `<dl class="about-facts"><dt>GitHub のアカウント</dt><dd>${esc(info.me || '（取得できませんでした）')}</dd><dt>使っている ecobuild</dt><dd><code>${esc((info.cli || []).join(' '))}</code></dd></dl>`
    + (info.cli_warning ? `<span class="missing">注意：${esc(info.cli_warning)}</span>` : '');
}
$('owner-form').addEventListener('submit', async event => {
  event.preventDefault();
  const owner = $('default-owner').value.trim();
  const doc = await ECO.run(null, owner ? ['config', 'set', 'owner', owner] : ['config', 'unset', 'owner']);
  if (doc) { $('owner-status').textContent = owner ? '既定の所有者を ' + owner + ' に設定しました。' : 'ログイン中のユーザーを使います。'; ownerHint(owner); }
});
$('reset-owner').addEventListener('click', async () => {
  const doc = await ECO.run(null, ['config', 'unset', 'owner']);
  if (doc) { $('default-owner').value = ''; $('owner-status').textContent = '既定に戻しました。ログイン中のユーザーを使います。'; ownerHint(''); }
});
// The fixes the screen can start (a new terminal window: they need the browser): doctor's fix → [label, GUI action, params].
const FIXES = {login: ['ログイン', 'gh-login', {switch: false}], scope: ['権限を追加', 'gh-scope', {scope: 'project'}]};
function renderDiagnosis(items) {
  $('doctor-results').innerHTML = items.map(item => `<li><div><span class="item-name">${esc(item.name)}</span><small>${esc(item.detail)}${item.ok ? '' : '<br>' + esc(item.hint)}</small></div>
    <span class="${item.ok ? 'ok' : 'missing'}">${item.ok ? '確認済み' : item.required ? '要対応' : '任意'}${!item.ok && FIXES[item.fix] ? `<button type="button" data-fix="${esc(item.fix)}">${FIXES[item.fix][0]}</button>` : ''}</span></li>`).join('');
  const missing = items.filter(i => !i.ok && i.required).length;
  $('doctor-status').textContent = missing ? `対応が必要な項目が ${missing} 件あります。` : '開発に必要な環境が整っています。';
}
$('doctor-results').addEventListener('click', event => {
  const fix = FIXES[event.target.closest('[data-fix]')?.dataset.fix];
  if (fix) ECO.call(fix[1], fix[2]).then(() => ECO.toast('ターミナルで続けてください。終わったら「チェックする」で確かめられます。'), e => ECO.toast(e.message, 'bad'));
});

// First run (installed with Setup.exe: no ecobuild init) and later: when the environment is not ready, say so above
// the list and lead to the settings (環境チェック・環境の準備).
async function checkEnvironment() {
  const doc = await ECO.cli(null, ['doctor'], {quiet: true});
  const banner = $('setup-banner'), missing = doc.ok ? doc.result.items.filter(i => !i.ok && i.required) : [];
  // 環境の準備の名前・メール：今の値を placeholder に
  const author = doc.ok && doc.result.items.find(i => i.name === 'git の名前・メール');
  const [, name = '', email = ''] = (author?.ok && /^(.*?)\s*<(.*)>$/.exec(author.detail)) || [];
  const setup = $('setup-form').elements;
  setup.namedItem('name').placeholder = name || '変更するときだけ入力';
  setup.namedItem('email').placeholder = email || '変更するときだけ入力';
  banner.hidden = !missing.length;
  if (!missing.length) return;
  banner.innerHTML = `<div><strong>はじめに：開発の環境を準備してください</strong><small>足りないもの：${missing.map(i => esc(i.name)).join('、')}</small></div>
    <button type="button" class="cancel banner-action">準備する</button>`;
  banner.querySelector('button').addEventListener('click', () => { showHubPage('settings'); showSettingsGroup('general'); renderDiagnosis(doc.result.items); $('doctor-title').scrollIntoView({block: 'start'}); });
}
checkEnvironment();
window.addEventListener('focus', () => { if (!$('setup-banner').hidden) checkEnvironment(); });
$('run-doctor').addEventListener('click', async () => {
  $('doctor-status').textContent = 'チェックしています…';
  const doc = await ECO.cli(null, ['doctor']);
  if (doc.ok) renderDiagnosis(doc.result.items); else { $('doctor-status').textContent = ''; ECO.showError(doc); }
});
$('setup-form').addEventListener('submit', async event => {
  event.preventDefault();
  const data = new FormData(event.currentTarget), args = ['setup'];
  for (const key of ['name', 'email']) if (data.get(key).trim()) args.push('--' + key, data.get(key).trim());
  if (data.has('install')) args.push('--install');
  $('setup-status').textContent = '準備しています…';
  const doc = await ECO.run(null, args);
  if (!doc) { $('setup-status').textContent = ''; return; }
  const r = doc.result;
  checkEnvironment();
  $('setup-status').innerHTML = (r.done.length ? '<p>' + r.done.map(esc).join('<br>') + '</p>' : '<p>変更はありませんでした（すでに準備できています）。</p>')
    + (r.remaining.length ? '<p>まだ足りないもの：' + r.remaining.map(i => esc(i.name)).join('、') + '</p>' : '')
    + (r.commands.length ? '<p>足りないツールのインストールコマンド：</p><pre>' + r.commands.map(esc).join('\n') + '</pre>' : '');
});

// ECOBuild itself (CLI and GUI): a newer version on GitHub is offered above the list and in the settings. The update is
// ecobuild installer update: the installer runs in another window once this ecobuild has ended, and closes the GUI.
// An ecobuild that cannot be updated this way (installed from local source, or with the bundled Setup.exe) says nothing.
const short = commit => commit ? commit.slice(0, 7) : '不明';
async function checkUpdate({quiet = true} = {}) {
  if (!quiet) $('update-status').textContent = '確かめています…';
  const doc = await ECO.cli(null, ['installer', 'update', '--check'], {quiet: true});
  const r = doc.ok ? doc.result : null, newer = !!r && !r.up_to_date;
  updateGui = !!r?.gui;
  $('run-update').hidden = !newer;
  if (!doc.ok) $('update-status').textContent = quiet ? '' : `更新を確かめられません：${doc.error.message}${doc.error.hint ? '（' + doc.error.hint + '）' : ''}`;
  else $('update-status').textContent = newer ? `新しい版があります：${short(r.current)} → ${short(r.latest)}（${r.ref}）` : `最新です：${short(r.latest)}（${r.ref}）`;
  const banner = $('update-banner');
  banner.hidden = !newer;
  if (newer) {
    banner.innerHTML = `<div><strong>ECOBuild の新しい版があります</strong><small>${esc(short(r.current))} → ${esc(short(r.latest))}（${esc(r.ref)}）。${r.gui ? 'CLI と GUI' : 'CLI'}を入れ直します。</small></div>
      <button type="button" class="cancel banner-action">更新する</button>`;
    banner.querySelector('button').addEventListener('click', runUpdate);
  }
}
// The GUI ends while the installer runs (so it can be replaced, and the new ecobuild is the one used) and opens again
// when the installer's window has closed (relaunch-after: a process of its own waits for it).
let updateGui = false;   // the installer puts the GUI in too: installer update --check says
async function runUpdate() {
  const message = `${updateGui ? 'CLI と GUI' : 'CLI（ecobuild）'}を新しい版に入れ直します。GUI はいったんすべての窓を閉じ（ビルド・実行中のものも止まります）、別の窓のインストーラーが終わったら起動し直します。`;
  if (!await ECO.confirm({title: 'ECOBuild を更新', message, ok: '更新する'})) return;
  const doc = await ECO.run(null, ['installer', 'update']);
  if (!doc) return;
  const r = doc.result;
  if (r.up_to_date) { ECO.toast('最新です。', 'ok'); return checkUpdate(); }
  try { await ECO.call('relaunch-after', {pid: r.process || 0, commit: r.latest}); }
  catch (e) {
    $('update-status').textContent = '更新を始めました。インストーラーの窓が閉じたら、GUI を起動し直してください。';
    return ECO.toast(`GUI を自動で起動し直せません：${e.message}`, 'bad', 15000);
  }
  try { await ECO.call('shutdown'); } catch (e) { /* already gone */ }
  if (window.ecobuildShell) return;
  document.body.innerHTML = '<main style="padding:48px;font:15px \'Segoe UI\', \'Yu Gothic UI\', sans-serif;color:#edf1f5">ECOBuild を更新しています。インストーラーの窓が閉じると、GUI が起動し直します。このウィンドウは閉じてかまいません。</main>';
  window.close();
}
$('check-update').addEventListener('click', () => checkUpdate({quiet: false}));
$('run-update').addEventListener('click', runUpdate);
checkUpdate();

// The hub opens small (the list and the settings only). Edge may ignore the size it is started with when it is running
// already, so the window is resized once when it first opens (an app window, not a browser tab; later the user's size).
// Electron opens it at this size.
try {
  if (!window.ecobuildShell && window.toolbar && !window.toolbar.visible && !sessionStorage.getItem('ecobuild-hub-sized')) {
    sessionStorage.setItem('ecobuild-hub-sized', '1');
    if (window.outerWidth > 1000 || window.outerHeight > 720) window.resizeTo(Math.min(window.outerWidth, 1000), Math.min(window.outerHeight, 720));
  }
} catch (e) { /* storage blocked: keep the size */ }
loadModules();
loadGithubModules();
window.addEventListener('focus', loadModules);
ECO.info().then(info => { if (info.cli_warning) ECO.toast('注意：' + info.cli_warning, 'bad', 15000); });

// Put a module away in two steps, as the CLI does: ecobuild module archive makes the GitHub repository read-only (ecobuild
// module unarchive undoes it); ecobuild module delete deletes only an archived one (GitHub can restore it within 90 days).
// Whether it is archived comes from ecobuild module show (or module list when the folder is gone).
async function putAwayModule(m) {
  if (m.notClone) return forgetModule(m, 'このフォルダは git の clone ではなくなっています（削除が途中で止まった等）。GitHub のリポジトリとはつながっていないので、アーカイブ・削除はできません。');
  const dir = m.exists ? m.path : null;
  const wait = ECO.busy({title: `${m.name} の状態を確認しています…`});
  let repository = m.repository || m.name, archived = null;
  // The list from GitHub (module list, read when the hub opened) tells it; module show asks GitHub again (seconds).
  if (!githubModules && !m.exists) await (githubModulesLoading || loadGithubModules());
  const entry = githubEntry(m);
  if (entry) { repository = entry.repository; archived = entry.archived; }
  else if (m.exists) {
    const show = await ECO.cli(dir, ['module', 'show'], {quiet: true});
    if (show.ok) { repository = show.result.repository || repository; archived = show.result.archived; }
  }
  // Deleting is checked by the CLI first (delete without --confirm changes nothing): the numbers of open issues and PRs.
  const probe = archived === false ? null : await ECO.cli(dir, ['module', 'delete', repository], {quiet: true});
  wait.end();
  const code = probe ? (probe.ok ? '' : probe.error?.code) : 'not_archived';
  if (code === 'not_archived') return archiveModule(m, repository, dir);
  if (code === 'confirmation_required') return deleteArchivedModule(m, repository, dir, probe.error.message.replace(/^確認が必要です：/, ''));
  if (code === 'github_permission') return deleteArchivedModule(m, repository, dir, '');
  if (code === 'repository_not_found') return forgetModule(m, `GitHub のリポジトリ ${repository} が見つかりません（削除済み、または見る権限がありません）。`);
  ECO.showError(probe, 'モジュールを片付けられませんでした');
}

const errorText = doc => [doc.error.message, doc.error.hint].filter(Boolean).join('\n');



// Step 1: archive (read-only).
function archiveModule(m, repository, dir) {
  return ECO.form({title: `モジュールを片付ける：${m.name}`, busy: `${repository} をアーカイブしています…`, ok: 'アーカイブする',
    intro: `<b>${esc(repository)}</b> をアーカイブ（読み取り専用）にします。解除・削除は「アーカイブ済み」から。`,
    fields: [{name: 'note', type: 'html', html: `<p class="eco-help">アーカイブ中は Push や PR・Issue の変更はできません。${m.exists ? `手元のフォルダ（${esc(m.path)}）は消しません。` : ''}</p>`}],
    submit: async () => {
      const doc = await ECO.cli(dir, ['module', 'archive', repository, '--yes']);
      if (!doc.ok) return errorText(doc);
      ECO.toast(`${doc.result.repository} をアーカイブしました（読み取り専用）。「アーカイブ済み」に移動しました。`, 'ok', 8000);
      await loadGithubModules(); loadModules();
    }});
}

// Step 2: an archived module: delete it, or undo the archive.
async function deleteArchivedModule(m, repository, dir, question) {
  const local = [...clones, ...legacy].filter(c => c.exists && sameRepository(repository, cloneRepository(c))).map(c => c.path);
  let permission = false;
  const done = await ECO.form({title: `モジュールを片付ける：${m.name}`, busy: `${repository} を処理しています…`, danger: true, ok: '実行する',
    intro: `<b>${esc(repository)}</b> はアーカイブ済みです。${question ? esc(question) : ''}<br>削除したリポジトリは、90日以内なら GitHub のアカウント設定から復元できます。タスク管理の情報は削除せずに閉じ、復元したときに引き継ぎます。`,
    fields: [
      {name: 'mode', label: 'すること', type: 'radio', inline: true, value: 'delete', options: [['delete', '削除する', 'GitHubのリポジトリを Issue・PR ごと削除'], ['unarchive', 'アーカイブを解除']]},
      ...(local.length ? [{name: 'removeClone', label: `このPCのcloneも削除する（${local.join('、')}）`, type: 'checkbox', value: true, showIf: v => v.mode === 'delete'},
        // Without it, the CLI stops when a clone has something not on GitHub (module delete --discard-local).
        {name: 'discardLocal', label: 'GitHubにない変更・コミット・退避があっても削除する（それらは失われます。チェックしなければ、ある場合は中止します）', type: 'checkbox', showIf: v => v.mode === 'delete' && v.removeClone}] : []),
      {name: 'confirmName', label: `確認のため ${repository} と入力`, placeholder: repository, showIf: v => v.mode === 'delete'}],
    submit: async v => {
      if (v.mode === 'unarchive') {
        const doc = await ECO.cli(dir, ['module', 'unarchive', repository]);
        if (!doc.ok) return errorText(doc);
        ECO.toast(`${doc.result.repository} のアーカイブを解除しました。`, 'ok', 8000);
        await loadGithubModules(); loadModules();
        return;
      }
      if (v.confirmName.trim().toLowerCase() !== repository.toLowerCase()) return `削除するには、${repository} と入力してください。`;
      const doc = await ECO.cli(dir, ['module', 'delete', repository, '--confirm', repository, ...(v.removeClone ? ['--remove-workspaces', ...(v.discardLocal ? ['--discard-local'] : [])] : [])]);
      if (!doc.ok && doc.error?.code === 'github_permission') { permission = true; return; }
      if (!doc.ok) return errorText(doc);
      const r = doc.result;
      ECO.toast(`${r.repository} を削除しました（90日以内なら GitHub のアカウント設定から復元できます）。`, 'ok', 10000);
      const left = v.removeClone ? (r.workspaces || []).filter(c => !(r.removed || []).includes(c)) : [];
      if (left.length) ECO.toast(`手元のフォルダ ${left.join('、')} は他のプログラムが使用中のため削除できませんでした。プログラムを閉じてから削除してください。`, 'bad', 15000);
      await loadGithubModules(); loadModules();
    }});
  if (permission) {
    const add = await ECO.dialog({title: 'GitHubの権限が足りません', body: '<p>ログイン中の GitHub アカウントに、リポジトリを削除する権限（delete_repo）がありません。</p><p class="eco-help">「権限を追加する」を押すとターミナルが開き、ブラウザで承認できます。承認したら、もう一度「片付ける」から削除してください。</p>',
      buttons: [['閉じる', '', false], ['権限を追加する', 'primary', true]]});
    if (add) ECO.call('gh-scope', {scope: 'delete_repo'}).catch(e => ECO.toast(e.message, 'bad'));
  }
  return done;
}

// A module card's menu: the same one from right-clicking the card and from its ⋯ button.
function moduleMenu(m, x, y, options) {
  const gone = m.exists ? '' : `フォルダが見つかりません（${m.path}）`;
  ECO.menu([
    ['開発環境を開く', () => openModule(m.path), m.exists, gone],
    ['エクスプローラーでフォルダを開く', () => ECO.action('folder', {dir: m.path}).catch(e => ECO.toast(e.message, 'bad')), m.exists, gone],
    // Only the types with a solution (C++): the others never have one to open.
    ...(!m.type || ECO.typeFeatures(m.type).solution ? [[`Visual Studio ${ECO.vsVersion()} で開く`, () => ECO.openInVisualStudio(m.path), m.exists, gone]] : []),
    ['ショートカットを作る…', () => makeModuleShortcut(m), m.exists, gone],
    '-',
    ['一覧から外す…', () => forgetModule(m)],
    ['片付ける（アーカイブ・削除）…', () => putAwayModule(m), true, '', {danger: true}],
  ], x, y, options);
}
$('module-list').addEventListener('contextmenu', event => {
  const item = event.target.closest('li[data-index]'); if (!item) return;
  event.preventDefault();
  moduleMenu(modules[Number(item.dataset.index)], event.clientX, event.clientY);
});
// Drag cards to reorder the list (the order is the one thing the GUI keeps: gui.json).
let draggedModule = null;
$('module-list').addEventListener('dragstart', event => { draggedModule = event.target.closest('li[data-index]'); if (draggedModule) { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', draggedModule.dataset.index); draggedModule.classList.add('dragging'); } });
$('module-list').addEventListener('dragover', event => {
  if (!draggedModule) return;
  const over = event.target.closest('li[data-index]'); event.preventDefault();
  if (!over || over === draggedModule || over.dataset.type !== draggedModule.dataset.type) return;
  const r = over.getBoundingClientRect(), before = event.clientY < r.top + r.height / 2 || (event.clientY < r.bottom && event.clientX < r.left + r.width / 2);
  $('module-list').insertBefore(draggedModule, before ? over : over.nextSibling);
});
$('module-list').addEventListener('drop', event => { if (draggedModule) event.preventDefault(); });
$('module-list').addEventListener('dragend', async () => {
  if (!draggedModule) return;
  draggedModule.classList.remove('dragging'); draggedModule = null;
  const paths = [...$('module-list').querySelectorAll('li[data-index]')].map(li => modules[Number(li.dataset.index)].path);
  try { await ECO.call('modules/order', {paths: [...paths, ...order.filter(k => !paths.some(p => pathKey(p) === k))]}); } catch (e) { ECO.toast(e.message, 'bad'); }
  loadModules();
});

// Shortcuts (desktop and Start menu) with the app icon: start the GUI without looking for ECOBuildGUI.pyw.
$('make-shortcut').addEventListener('click', async () => {
  try { const {made} = await ECO.call('shortcut'); ECO.toast('ショートカットを作りました：' + made.map(p => p.split('\\').slice(-2).join('\\')).join('、')); }
  catch (e) { ECO.toast(e.message, 'bad', 9000); }
});

// A module's shortcut opens its development environment alone, without the hub (app.py --module). It is an app of its
// own on the taskbar (pinned, it opens that module). It goes in a folder chosen each time (the last one is kept on this PC).
const SHORTCUT_PLACE_KEY = 'ecobuild.shortcutPlace';
async function makeModuleShortcut(m) {
  let last = ''; try { last = localStorage.getItem(SHORTCUT_PLACE_KEY) || ''; } catch (e) { /* storage blocked */ }
  try {
    const {path} = await ECO.call('pick-folder', {title: `${m.name} のショートカットを作るフォルダを選ぶ`, initial: last});
    if (!path) return;
    try { localStorage.setItem(SHORTCUT_PLACE_KEY, path); } catch (e) { /* storage blocked */ }
    const {made} = await ECO.call('shortcut', {module: m.path, place: path});
    ECO.toast('ショートカットを作りました：' + made.join('、'));
  }
  catch (e) { ECO.toast(e.message, 'bad', 9000); }
}

// End the background server now (otherwise it ends a while after the last window closes). In Electron the app ends with it.
$('quit-gui').addEventListener('click', async () => {
  if (!await ECO.confirm({title: 'GUIを終了', message: 'GUIを終了します。開いているモジュールのウィンドウも使えなくなります。実行中のコマンドがある場合は、完了してから終了してください。', ok: '終了する'})) return;
  try { await ECO.call('shutdown'); } catch (e) { /* already gone */ }
  if (window.ecobuildShell) return;
  document.body.innerHTML = '<main style="padding:48px;font:15px \'Segoe UI\', \'Yu Gothic UI\', sans-serif;color:#edf1f5">ECOBuild GUI を終了しました。このウィンドウを閉じてください。</main>';
  window.close();
});
window.addEventListener('eco-operator-acted', () => loadModules());   // AI に頼んだ操作で、一覧が変わったかもしれない

// リング・オペレーターのかんたんな切り替え（Electron の GUI だけ。中身はエージェントの窓の設定と同じ）
(async () => {
  const quick = window.ecobuildShell?.agents?.quick; if (!quick) return;
  $('quick-toggles').hidden = false;
  let view = null;
  const show = next => {
    view = next;
    const ring = next.ring || {}, op = next.operator || {};
    const ringOk = ring.enabled && ring.online && ring.connected && ring.calibrated;
    $('quick-ring').className = 'nav-button quick' + (ring.enabled ? (ringOk ? ' on' : ' warn') : '');
    $('quick-ring').title = !ring.enabled ? 'リング：使っていません（押すと使う）'
      : `リング：${ring.message || ''}${ring.mode === 'operator' ? '・オペレーターモード' : ''}（押すと使わない）`;
    $('quick-operator').className = 'nav-button quick' + (op.running ? (['thinking', 'waiting', 'starting'].includes(op.state) ? ' busy' : ' on') : '');
    $('quick-operator').title = op.running ? `オペレーター：動いています（${op.state}）。押すと止める` : 'オペレーター：止まっています（押すと裏で動かす）';
  };
  show(await quick.watch());
  quick.onQuick(show);
  $('quick-ring').addEventListener('click', () => quick.ring(!view?.ring?.enabled));
  $('quick-operator').addEventListener('click', () => quick.operator(!view?.operator?.running));
})();
