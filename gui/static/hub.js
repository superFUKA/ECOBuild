'use strict';
// Hub: the list of modules (the clones on this PC: ecobuild module clones) and the settings shared by every module.
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
// The modules on GitHub (ecobuild module list --all): the archived ones are listed in 「アーカイブ済み」 below the list,
// and the others not in the list are offered to clone.
// Read once (it asks GitHub about every repository) and again after archiving or deleting one.
let githubModules = null, githubModulesLoading = null;
function loadGithubModules() {
  githubModulesLoading = ECO.cli(null, ['module', 'list', '--all'], {quiet: true}).then(doc => {
    githubModules = doc.ok ? doc.result : [];
    githubModulesLoading = null; renderModules(); renderCloneCandidates();
  });
  return githubModulesLoading;
}
// 所有者/名前 when both have it, otherwise the names (a module whose origin is not on GitHub has only its name).
const sameRepository = (a, b) => {
  if (!a || !b) return false;
  const full = a.includes('/') && b.includes('/'), key = x => (full ? x : x.split('/').pop()).toLowerCase();
  return key(a) === key(b);
};
const githubEntry = m => (githubModules || []).find(g => sameRepository(g.repository, m.repository || m.name));
// 「アーカイブ済み」 is what the CLI says (module list). The clones of an archived module stay recorded (module clones)
// but leave the list: they are shown under the archived module, and deleting it can remove them (--remove-clone).
let archived = [];
function renderArchived() {
  archived = (githubModules || []).filter(g => g.archived).map(g => {
    const local = clones.filter(c => c.exists && sameRepository(g.repository, cloneRepository(c)));
    return {name: g.repository.split('/').pop(), repository: g.repository, description: g.description, clones: local,
            path: local[0]?.path || '', exists: local.length > 0};
  });
  $('archived-modules').hidden = !archived.length;
  $('archived-count').textContent = `（${archived.length}）`;
  $('archived-list').innerHTML = archived.map((m, i) => `<li><div><strong>${esc(m.repository)}</strong>${m.description ? `<small>${esc(m.description)}</small>` : ''}
      ${m.clones.map(c => `<small>このPC：${esc(c.path)}</small>`).join('')}</div>
      <span class="archived-actions">${m.exists ? `<button type="button" data-archived="folder" data-i="${i}">フォルダを開く</button>` : ''}<button type="button" data-archived="unarchive" data-i="${i}">戻す</button><button type="button" class="danger-text" data-archived="delete" data-i="${i}">削除…</button></span></li>`).join('');
}
$('archived-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-archived]'); if (!button) return;
  const m = archived[Number(button.dataset.i)];
  if (button.dataset.archived === 'delete') { putAwayModule(m); return; }
  if (button.dataset.archived === 'folder') { ECO.call('open', {dir: m.path, path: ''}).catch(e => ECO.toast(e.message, 'bad')); return; }
  const doc = await ECO.run(m.exists ? m.path : null, ['module', 'unarchive', m.repository],
    {success: r => `${r.repository} のアーカイブを戻しました。` + (m.exists ? '一覧に戻しました。' : '使うには「＋ モジュール追加」の「GitHubから取得」で取得してください。'), busy: `${m.repository} を戻しています…`});
  if (doc) { await loadGithubModules(); loadModules(); }
});
// A module opens in its own app window (like the hub), not in a browser tab: the server starts it.
const openModule = path => ECO.call('open-window', {page: 'module.html?path=' + encodeURIComponent(path)})
  .catch(() => window.open('module.html?path=' + encodeURIComponent(path), '_blank'));

let clones = [], order = [];
const pathKey = p => p.replaceAll('\\', '/').toLowerCase();
const baseName = p => p.split(/[\\/]/).filter(Boolean).pop() || p;
// 所有者/名前 when the origin is on GitHub, otherwise the name in the URL (matched by name: sameRepository).
const cloneRepository = c => c.repository || (c.url ? baseName(c.url).replace(/\.git$/, '') : '');
async function loadModules() {
  if (!$('module-list')) return;   // after "GUIを終了"
  const [doc, saved] = await Promise.all([ECO.cli(null, ['module', 'clones'], {quiet: true}), ECO.call('modules/order', {}).catch(() => [])]);
  if (!doc.ok) ECO.showError(doc, 'このPCのcloneの一覧を読めませんでした');
  clones = doc.ok ? doc.result : [];
  order = saved.map(pathKey);
  renderModules();
}
function renderModules() {
  if (!$('module-list')) return;
  const rank = m => { const i = order.indexOf(pathKey(m.path)); return i < 0 ? order.length : i; };
  modules = clones.filter(c => c.kind === 'module')
    .map(c => ({path: c.path, name: baseName(c.path), exists: c.exists, repository: cloneRepository(c)}))
    .filter(m => !githubEntry(m)?.archived)
    .map((m, i) => [m, i]).sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j).map(([m]) => m);
  renderArchived();
  const list = $('module-list');
  $('no-active-modules').hidden = modules.length > 0 || !archived.length;
  if (!modules.length) {
    list.innerHTML = archived.length ? '' : '<li class="empty-modules" style="grid-column:1/-1">モジュールはまだありません。「＋ モジュール追加」から、新しく作る・GitHubから取得する・手元のフォルダを登録するのどれかで追加してください。</li>';
    return;
  }
  list.innerHTML = modules.map((m, i) => `<li class="${m.exists ? '' : 'missing'}" data-index="${i}" draggable="true" title="右クリックで操作、ドラッグで並び替え">
    <a role="link" tabindex="0" data-open="${i}"><span class="module-icon" aria-hidden="true">${esc((m.name[0] || '?').toUpperCase())}</span><span class="module-name">${esc(m.name)}</span><span class="module-path">${esc(m.path)}</span>
    ${m.exists ? '' : '<span class="module-state">フォルダが見つかりません</span>'}<span class="module-open">開発環境を開く<span aria-hidden="true">↗</span></span></a>
    <details class="module-menu"><summary aria-label="${esc(m.name)} の操作">⋯</summary><div>
      <button type="button" data-action="folder" data-index="${i}">フォルダを開く</button>
      <button type="button" data-action="remove" data-index="${i}">一覧から外す</button>
      <button type="button" class="danger-text" data-action="delete" data-index="${i}">片付ける（アーカイブ・削除）…</button></div></details></li>`).join('');
}
// 一覧から外す: ecobuild module forget (the folder and the GitHub repository stay).
async function forgetModule(m) {
  if (!await ECO.confirm({title: '一覧から外す', message: `${m.name} をこの一覧（このPCのcloneの記録）から外します。フォルダやGitHubのリポジトリは消しません。フォルダの中で ecobuild を使うと（開発環境を開く等）、また一覧に入ります。`, ok: '外す'})) return;
  if (await ECO.run(null, ['module', 'forget', m.path])) loadModules();
}
$('module-list').addEventListener('click', async event => {
  const action = event.target.closest('[data-action]');
  if (action) {
    action.closest('details').removeAttribute('open');
    const m = modules[Number(action.dataset.index)];
    if (action.dataset.action === 'folder') { try { await ECO.call('open', {dir: m.path, path: ''}); } catch (e) { ECO.toast(e.message, 'bad'); } }
    if (action.dataset.action === 'remove') forgetModule(m);
    if (action.dataset.action === 'delete') putAwayModule(m);
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
  if (method === 'clone') { if (!githubModules && !githubModulesLoading) loadGithubModules(); renderCloneCandidates(); }
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
    const doc = await ECO.cli(null, ['module', 'types'], {quiet: true});
    if (doc.ok) { types = doc.result; $('type-select').innerHTML = types.map(t => `<option value="${esc(t.name)}">${esc(t.name)}</option>`).join(''); updateFields(); }
  }
  ECO.info().then(info => { if (!field('directory').value && info.home) field('directory').value = info.home.replaceAll('\\', '/'); });
});
$('cancel-add').addEventListener('click', () => addDialog.close());
// The modules on GitHub not in the list yet: click one to fill in the repository.
function renderCloneCandidates() {
  const box = $('clone-candidates'); if (!box) return;
  if (!githubModules) { box.innerHTML = '<p class="note"><span class="eco-spinner"></span> GitHubにあるモジュールを読み込んでいます…</p>'; return; }
  const candidates = githubModules.filter(g => !g.archived && !modules.some(m => sameRepository(g.repository, m.repository || m.name)));
  box.innerHTML = candidates.length ? `<p class="note">GitHubにあるモジュール（クリックで選ぶ）</p><ul>${candidates.map(g => `<li><button type="button" data-candidate="${esc(g.repository)}">
      <strong>${esc(g.repository)}</strong><small>${esc([g.type, g.private ? '非公開' : '公開', g.updated ? '更新 ' + g.updated.slice(0, 10) : ''].filter(Boolean).join('・'))}${g.description ? '　' + esc(g.description) : ''}</small></button></li>`).join('')}</ul>`
    : `<p class="note">${githubModules.length ? 'GitHubにあるモジュールは、すべて一覧にあります。' : 'GitHubにモジュールが見つかりませんでした。'}他の所有者のものは「所有者/名前」で入力してください。</p>`;
}
$('clone-candidates').addEventListener('click', event => {
  const pick = event.target.closest('[data-candidate]'); if (!pick) return;
  field('repository').value = pick.dataset.candidate;
  for (const b of $('clone-candidates').querySelectorAll('[data-candidate]')) b.classList.toggle('selected', b === pick);
});
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
    const doc = await ECO.cli(null, ['module', 'register', data.get('folder').trim()], {quiet: true});
    if (!doc.ok) { error.textContent = errorText(doc); return; }
    addDialog.close(); ECO.toast(baseName(doc.result.path) + ' を一覧に登録しました。'); loadModules();
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
  const made = baseName(doc.result.root);
  await overlay.done(`${made} を${creating ? '作成' : '取得'}しました`);
  ECO.toast(`${made} を${creating ? '作成' : '取得'}しました。`);
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
loadGithubModules();
window.addEventListener('focus', loadModules);
ECO.info().then(info => { if (info.cli_warning) ECO.toast('注意：' + info.cli_warning, 'bad', 15000); });

// Put a module away in two steps, as the CLI does: ecobuild module archive makes the GitHub repository read-only (ecobuild
// module unarchive undoes it); ecobuild module delete deletes only an archived one (GitHub can restore it within 90 days).
// Whether it is archived comes from ecobuild module show (or module list when the folder is gone).
async function putAwayModule(m) {
  const dir = m.exists ? m.path : null;
  const wait = ECO.busy({title: `${m.name} の状態を確かめています…`});
  let repository = m.repository || m.name, archived = null;
  if (m.exists) {
    const show = await ECO.cli(dir, ['module', 'show'], {quiet: true});
    if (show.ok) { repository = show.result.repository || repository; archived = show.result.archived; }
  } else {
    if (!githubModules) await (githubModulesLoading || loadGithubModules());
    const entry = githubEntry(m);
    if (entry) { repository = entry.repository; archived = entry.archived; }
  }
  // Deleting is checked by the CLI first (delete without --confirm changes nothing): the numbers of open issues and PRs.
  const probe = archived === false ? null : await ECO.cli(dir, ['module', 'delete', repository], {quiet: true});
  wait.end();
  const code = probe ? (probe.ok ? '' : probe.error?.code) : 'not_archived';
  if (code === 'not_archived') return archiveModule(m, repository, dir);
  if (code === 'confirmation_required') return deleteArchivedModule(m, repository, dir, probe.error.message.replace(/^確認が必要です：/, ''));
  if (code === 'github_permission') return deleteArchivedModule(m, repository, dir, '');
  ECO.showError(probe, 'モジュールを片付けられません');
}

const errorText = doc => [doc.error.message, doc.error.hint].filter(Boolean).join('\n');

// Step 1: archive (read-only).
function archiveModule(m, repository, dir) {
  return ECO.form({title: `モジュールを片付ける：${m.name}`, busy: `${repository} をアーカイブしています…`, ok: 'アーカイブする',
    intro: `モジュールの片付けは2段階です。まず GitHub のリポジトリ <b>${esc(repository)}</b> をアーカイブ（読み取り専用）にし、使っていないことを確かめてから削除します。`,
    fields: [{name: 'note', type: 'html', html: `<p class="eco-help">アーカイブしたモジュールは一覧から外れ、一覧の下の「アーカイブ済み」に出ます。そこから、いつでも戻すか、削除できます。アーカイブ中は push・PR・Issue の変更ができません。タスク管理の情報は残ります。${m.exists ? `手元のフォルダ（${esc(m.path)}）は消しません（削除するときに一緒に消せます）。` : ''}</p>`}],
    submit: async () => {
      const doc = await ECO.cli(dir, ['module', 'archive', repository, '--yes']);
      if (!doc.ok) return errorText(doc);
      ECO.toast(`${doc.result.repository} をアーカイブしました（読み取り専用）。一覧の下の「アーカイブ済み」に移しました。`, 'ok', 8000);
      await loadGithubModules(); loadModules();
    }});
}

// Step 2: an archived module: delete it, or undo the archive.
async function deleteArchivedModule(m, repository, dir, question) {
  const local = clones.filter(c => c.exists && sameRepository(repository, cloneRepository(c))).map(c => c.path);
  let permission = false;
  const done = await ECO.form({title: `モジュールを片付ける：${m.name}`, busy: `${repository} を処理しています…`, danger: true, ok: '実行する',
    intro: `<b>${esc(repository)}</b> はアーカイブ済みです。${question ? esc(question) : ''}<br>削除したリポジトリは、GitHub のアカウントの設定から90日以内なら元に戻せます。タスク管理の情報は消さずに閉じ、戻したときに引き継ぎます。`,
    fields: [
      {name: 'mode', label: 'すること', type: 'radio', value: 'delete', options: [['delete', '削除する', 'GitHubのリポジトリを、Issue・PRとともに消す'], ['unarchive', 'アーカイブを戻す', 'また変更できるようにする']]},
      ...(local.length ? [{name: 'removeClone', label: `このPCのcloneも削除する（${local.join('、')}）。どれかにGitHubにない変更・コミット・退避があれば止まります`, type: 'checkbox', value: true}] : []),
      {name: 'confirmName', label: `削除するときは、確認のため ${repository} と入力`, placeholder: repository}],
    submit: async v => {
      if (v.mode === 'unarchive') {
        const doc = await ECO.cli(dir, ['module', 'unarchive', repository]);
        if (!doc.ok) return errorText(doc);
        ECO.toast(`${doc.result.repository} のアーカイブを戻しました。`, 'ok', 8000);
        await loadGithubModules(); loadModules();
        return;
      }
      if (v.confirmName.trim().toLowerCase() !== repository.toLowerCase()) return `削除するには、${repository} と入力してください。`;
      const doc = await ECO.cli(dir, ['module', 'delete', repository, '--confirm', repository, ...(v.removeClone ? ['--remove-clone'] : [])]);
      if (!doc.ok && doc.error?.code === 'github_permission') { permission = true; return; }
      if (!doc.ok) return errorText(doc);
      const r = doc.result;
      ECO.toast(`${r.repository} を削除しました（GitHubのアカウントの設定から、90日以内なら元に戻せます）。`, 'ok', 10000);
      const left = v.removeClone ? (r.clones || []).filter(c => !(r.removed || []).includes(c)) : [];
      if (left.length) ECO.toast(`手元のフォルダ ${left.join('、')} は、他のプログラムが使っているため削除できませんでした。閉じてから削除してください。`, 'bad', 15000);
      await loadGithubModules(); loadModules();
    }});
  if (permission) {
    const add = await ECO.dialog({title: 'GitHubの権限が足りません', body: '<p>GitHubへのログインに、リポジトリを削除する権限（delete_repo）がありません。</p><p class="eco-help">「権限を追加する」で端末の窓が開き、ブラウザで承認します。終わったら、もう一度「片付ける」から削除してください。</p>',
      buttons: [['閉じる', '', false], ['権限を追加する', 'primary', true]]});
    if (add) ECO.call('gh-scope', {scope: 'delete_repo'}).catch(e => ECO.toast(e.message, 'bad'));
  }
  return done;
}

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
    ['一覧から外す…', () => forgetModule(m)],
    ['片付ける（アーカイブ・削除）…', () => putAwayModule(m)],
  ], event.clientX, event.clientY);
});
// Drag cards to reorder the list (the order is the one thing the GUI keeps: gui.json).
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
  try { await ECO.call('modules/order', {paths: [...paths, ...order.filter(k => !paths.some(p => pathKey(p) === k))]}); } catch (e) { ECO.toast(e.message, 'bad'); }
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
