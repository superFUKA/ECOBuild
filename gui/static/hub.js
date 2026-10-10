'use strict';
// Hub: the list of modules (kept by the GUI) and the settings shared by every module.
const $ = id => document.getElementById(id);
const {esc} = ECO;

// Navigation ------------------------------------------------------------------------------------
const navigation = document.querySelectorAll('[data-page]');
navigation.forEach(button => button.addEventListener('click', () => {
  navigation.forEach(item => {
    const selected = item === button;
    if (selected) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
    $(item.dataset.page).hidden = !selected;
  });
  if (button.dataset.page === 'settings') loadSettings();
}));

// Module list -----------------------------------------------------------------------------------
let modules = [];
// A module opens in its own app window (like the hub), not in a browser tab: the server starts it.
const openModule = path => ECO.call('open-window', {page: 'module.html?path=' + encodeURIComponent(path)})
  .catch(() => window.open('module.html?path=' + encodeURIComponent(path), '_blank'));

async function loadModules() {
  if (!$('module-list')) return;   // after "GUIを終了"
  try { modules = await ECO.call('modules'); } catch (e) { ECO.toast(e.message, 'bad'); modules = []; }
  const list = $('module-list');
  if (!modules.length) {
    list.innerHTML = '';
    list.insertAdjacentHTML('afterend', '');
    list.innerHTML = '<li class="empty-modules" style="grid-column:1/-1">モジュールはまだありません。「＋ モジュール追加」から、新しく作る・GitHubから取得する・手元のフォルダを登録するのどれかで追加してください。</li>';
    return;
  }
  list.innerHTML = modules.map((m, i) => `<li class="${m.exists ? '' : 'missing'}" data-index="${i}" draggable="true" title="右クリックで操作、ドラッグで並び替え">
    <a role="link" tabindex="0" data-open="${i}"><span class="module-icon" aria-hidden="true">${esc((m.name[0] || '?').toUpperCase())}</span><span class="module-name">${esc(m.name)}</span><span class="module-path">${esc(m.path)}</span>
    ${m.exists ? '' : '<span class="module-state">フォルダが見つかりません</span>'}<span class="module-open">開発環境を開く<span aria-hidden="true">↗</span></span></a>
    <details class="module-menu"><summary aria-label="${esc(m.name)} の操作">⋯</summary><div>
      <button type="button" data-action="folder" data-index="${i}">フォルダを開く</button>
      <button type="button" data-action="remove" data-index="${i}">一覧から外す</button></div></details></li>`).join('');
}
$('module-list').addEventListener('click', async event => {
  const action = event.target.closest('[data-action]');
  if (action) {
    action.closest('details').removeAttribute('open');
    const m = modules[Number(action.dataset.index)];
    if (action.dataset.action === 'folder') { try { await ECO.call('open', {dir: m.path, path: ''}); } catch (e) { ECO.toast(e.message, 'bad'); } }
    if (action.dataset.action === 'remove' && await ECO.confirm({title: '一覧から外す', message: `${m.name} をこの一覧から外します。フォルダやGitHubのリポジトリは消しません。`, ok: '外す'})) {
      await ECO.call('modules/remove', {path: m.path}); loadModules();
    }
    return;
  }
  const open = event.target.closest('[data-open]');
  if (open) { const m = modules[Number(open.dataset.open)]; if (m.exists) openModule(m.path); else ECO.toast('フォルダが見つかりません：' + m.path, 'bad'); }
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
  addForm.querySelector('[type=submit]').textContent = {new: '作成する', clone: '取得する', register: '登録する'}[method];
  for (const [id, on] of [['new-fields', method === 'new'], ['clone-fields', method === 'clone'], ['register-fields', method === 'register']]) { $(id).hidden = !on; $(id).disabled = !on; }
  $('parent-fields').hidden = method === 'register';
  field('directory').required = method !== 'register';
  const type = field('type').value;
  $('app-field').hidden = type !== 'cpp';
  $('type-description').textContent = types.find(t => t.name === type)?.description || '';
}
$('add-module').addEventListener('click', async () => {
  addForm.reset(); addForm.querySelector('details').open = false;
  field('directory').value = defaultParent();
  $('add-error').textContent = ''; updateFields(); addDialog.showModal();
  if (!types.length) {
    const doc = await ECO.cli(null, ['types'], {quiet: true});
    if (doc.ok) { types = doc.result; $('type-select').innerHTML = types.map(t => `<option value="${esc(t.name)}">${esc(t.name)}</option>`).join(''); updateFields(); }
  }
  ECO.info().then(info => { if (!field('directory').value && info.home) field('directory').value = info.home.replaceAll('\\', '/'); });
});
$('cancel-add').addEventListener('click', () => addDialog.close());
addForm.addEventListener('change', updateFields);
addForm.addEventListener('click', async event => {
  const pick = event.target.closest('[data-pick]'); if (!pick) return;
  const input = field(pick.dataset.pick);
  try { const {path} = await ECO.call('pick-folder', {title: 'フォルダを選ぶ', initial: input.value}); if (path) input.value = path; } catch (e) { ECO.toast(e.message, 'bad'); }
});
addForm.addEventListener('submit', async event => {
  event.preventDefault();
  const data = new FormData(addForm), method = data.get('method'), error = $('add-error'), submit = addForm.querySelector('[type=submit]');
  error.textContent = '';
  if (method === 'register') {
    try { const m = await ECO.call('modules/add', {path: data.get('folder').trim()}); addDialog.close(); ECO.toast(m.name + ' を一覧に登録しました。'); loadModules(); }
    catch (e) { error.textContent = e.message; }
    return;
  }
  const parent = data.get('directory').trim().replace(/[\\/]+$/, '');
  if (!parent) { error.textContent = '保存先の親フォルダを入力してください。'; return; }
  submit.disabled = true;
  let directory;
  try { directory = (await ECO.call('mkparent', {path: parent})).path; } catch (e) { error.textContent = e.message; submit.disabled = false; return; }
  const creating = method === 'new', name = creating ? data.get('name').trim() : data.get('repository').trim();
  const args = creating ? ['new', name, '--type', data.get('type')] : ['clone', name];
  if (creating) {
    for (const option of ['description', 'owner']) if (data.get(option).trim()) args.push('--' + option, data.get(option).trim());
    if (data.has('public')) args.push('--public');
    if (data.has('app') && data.get('type') === 'cpp') args.push('--app');
  }
  // Close the form and show the busy overlay ("ぐるぐる"). The CLI reports no progress until it ends, so the steps are
  // what the command does (not live progress); the elapsed seconds show it is still working.
  addDialog.close(); submit.disabled = false;
  const overlay = ECO.busy({
    title: `${name.split('/').pop()} を${creating ? '作成' : '取得'}しています…`, sub: directory + '/' + name.split('/').pop(),
    steps: creating ? ['GitHubにリポジトリを作る', 'ライブラリ・テスト用のProjectを用意する', '初回のコミットをPushする']
      : ['GitHubからcloneする', '依存先をcloneする', '生成ファイルを用意する'],
  });
  const doc = await ECO.cli(directory, args, {quiet: true});
  if (!doc.ok) {
    // Back to the form (the values stay) with the reason.
    overlay.end(); addDialog.showModal();
    const e = doc.error || {};
    error.textContent = [e.message, e.hint].filter(Boolean).join('\n');
    if (ECO.detailText(e.details)) ECO.showError(doc, creating ? '作成できませんでした' : '取得できませんでした');
    return;
  }
  try { localStorage.setItem('ecobuild-gui-parent', parent); } catch (e) { /* storage blocked */ }
  const m = await ECO.call('modules/add', {path: doc.result.root}).catch(() => ({name, path: doc.result.root}));
  await overlay.done(`${m.name} を${creating ? '作成' : '取得'}しました`);
  ECO.toast(`${m.name} を${creating ? '作成' : '取得'}しました。`);
  await loadModules();
});

// Settings ----------------------------------------------------------------------------------------
function ownerHint(owner) { field('owner').placeholder = owner ? '未指定なら ' + owner : '未指定ならログイン中のユーザー'; }
async function loadSettings() {
  if (!$('default-owner')) return;   // after "GUIを終了"
  const doc = await ECO.cli(null, ['config', 'list'], {quiet: true});
  if (doc.ok && $('default-owner')) { $('default-owner').value = doc.result.owner || ''; ownerHint(doc.result.owner); }
  const info = await ECO.info();
  $('about').innerHTML = `ログイン中のGitHubアカウント：${esc(info.me || '（取得できませんでした）')}<br>使っている ecobuild：${esc((info.cli || []).join(' '))}`
    + (info.cli_warning ? `<br><span class="missing">注意：${esc(info.cli_warning)}</span>` : '');
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
function renderDiagnosis(items) {
  $('doctor-results').innerHTML = items.map(item => `<li><div><span class="item-name">${esc(item.name)}</span><small>${esc(item.detail)}${item.ok ? '' : '<br>' + esc(item.hint)}</small></div>
    <span class="${item.ok ? 'ok' : 'missing'}">${item.ok ? '確認済み' : item.required ? '要対応' : '任意'}</span></li>`).join('');
  const missing = items.filter(i => !i.ok && i.required).length;
  $('doctor-status').textContent = missing ? missing + '件の対応が必要です。' : '開発に必要な環境が整っています。';
}
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
  $('setup-status').innerHTML = (r.done.length ? '<p>' + r.done.map(esc).join('<br>') + '</p>' : '<p>変えることはありませんでした。</p>')
    + (r.remaining.length ? '<p>まだ足りないもの：' + r.remaining.map(i => esc(i.name)).join('、') + '</p>' : '')
    + (r.commands.length ? '<p>足りないツールの導入コマンド：</p><pre>' + r.commands.map(esc).join('\n') + '</pre>' : '');
});

loadModules();
window.addEventListener('focus', loadModules);
ECO.info().then(info => { if (info.cli_warning) ECO.toast('注意：' + info.cli_warning, 'bad', 15000); });

// Right-click a module card.
$('module-list').addEventListener('contextmenu', event => {
  const item = event.target.closest('li[data-index]'); if (!item) return;
  event.preventDefault();
  const m = modules[Number(item.dataset.index)];
  ECO.menu([
    ['開発環境を開く', () => openModule(m.path), m.exists],
    ['エクスプローラーでフォルダを開く', () => ECO.call('open', {dir: m.path, path: ''}).catch(e => ECO.toast(e.message, 'bad')), m.exists],
    [`Visual Studio ${ECO.vsVersion()} で開く`, () => ECO.openInVisualStudio(m.path), m.exists],
    '-',
    ['一覧から外す…', async () => {
      if (await ECO.confirm({title: '一覧から外す', message: `${m.name} をこの一覧から外します。フォルダやGitHubのリポジトリは消しません。`, ok: '外す'})) { await ECO.call('modules/remove', {path: m.path}); loadModules(); }
    }],
  ], event.clientX, event.clientY);
});
// Drag cards to reorder the list (kept in gui.json).
let draggedModule = null;
$('module-list').addEventListener('dragstart', event => { draggedModule = event.target.closest('li[data-index]'); if (draggedModule) { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', draggedModule.dataset.index); draggedModule.classList.add('dragging'); } });
$('module-list').addEventListener('dragover', event => {
  if (!draggedModule) return;
  const over = event.target.closest('li[data-index]'); event.preventDefault();
  if (!over || over === draggedModule) return;
  const r = over.getBoundingClientRect(), before = event.clientY < r.top + r.height / 2 || (event.clientY < r.bottom && event.clientX < r.left + r.width / 2);
  $('module-list').insertBefore(draggedModule, before ? over : over.nextSibling);
});
$('module-list').addEventListener('drop', event => { if (draggedModule) event.preventDefault(); });
$('module-list').addEventListener('dragend', async () => {
  if (!draggedModule) return;
  draggedModule.classList.remove('dragging'); draggedModule = null;
  const paths = [...$('module-list').querySelectorAll('li[data-index]')].map(li => modules[Number(li.dataset.index)].path);
  try { await ECO.call('modules/order', {paths}); } catch (e) { ECO.toast(e.message, 'bad'); }
  loadModules();
});

// Shortcuts (desktop and Start menu) with the app icon: start the GUI without looking for ECOBuildGUI.pyw.
$('make-shortcut').addEventListener('click', async () => {
  try { const {made} = await ECO.call('shortcut'); ECO.toast('ショートカットを作りました：' + made.map(p => p.split('\\').slice(-2).join('\\')).join('、')); }
  catch (e) { ECO.toast(e.message, 'bad', 9000); }
});

// End the background server now (otherwise it ends a while after the last window closes).
$('quit-gui').addEventListener('click', async () => {
  if (!await ECO.confirm({title: 'GUIを終了', message: 'GUIを終了します。開いているモジュールの窓も使えなくなります。実行中のコマンドがあれば、終わるのを待ってから押してください。', ok: '終了する'})) return;
  try { await ECO.call('shutdown'); } catch (e) { /* already gone */ }
  document.body.innerHTML = '<main style="padding:48px;font:15px \'Segoe UI\', \'Yu Gothic UI\', sans-serif;color:#edf1f5">ECOBuild GUI を終了しました。この窓を閉じてください。</main>';
  window.close();
});
