'use strict';
// One workspace on disk: changes, commit, push, PR submission.
// History is in the explorer's menu (a file, a folder, or the whole module).
const WS = {
  dir: ECO.params.get('dir') || '', module: ECO.params.get('module') || '',
  status: null, task: null, selected: new Set(), listeners: [],
};
const get = id => document.getElementById(id);
const {esc} = ECO;
if (ECO.params.get('embedded') === '1') document.body.classList.add('embedded');
get('module-name').textContent = WS.module.split(/[\\/]/).pop();
const say = message => { get('operation-status').textContent = message; };

// Runs a command here, then refreshes everything this screen shows.
WS.run = async (args, options = {}) => {
  const doc = await ECO.run(WS.dir, args, options);
  if (doc) say(typeof options.success === 'function' ? options.success(doc.result) : options.success || '');
  if (options.refresh !== false) await WS.refresh();
  return doc;
};
WS.cli = (args, options) => ECO.cli(WS.dir, args, options);
WS.onRefresh = fn => WS.listeners.push(fn);
WS.notifyParent = () => { if (window.parent !== window) window.parent.postMessage({type: 'workspace-changed', dir: WS.dir, status: WS.status, title: WS.task?.title || ''}, location.origin); };

const changeKinds = s => {
  // path -> list of kinds, in the order shown.
  const map = new Map(), add = (path, kind) => { if (!map.has(path)) map.set(path, []); map.get(path).push(kind); };
  for (const p of s.conflicted) add(p, 'conflicted');
  for (const p of s.staged) add(p, 'staged');
  for (const p of s.unstaged) add(p, 'unstaged');
  for (const p of s.untracked) add(p, 'untracked');
  return map;
};
WS.changes = () => WS.status ? changeKinds(WS.status) : new Map();
const KIND_LABEL = {conflicted: '衝突', staged: 'ステージ済み', unstaged: '変更', untracked: '追加'};

// What only status --fetch knows (GitHub's latest: how far behind the base, the files taking it in would conflict on,
// archived). It is read when the screen is shown and then every few minutes while it is (WS.fetchedAt: when); the
// plain status in between reads only this PC and keeps the last answer while the branch here stays as it was.
const FETCH_EVERY = 3 * 60 * 1000;
WS.fetchedAt = 0;
let fetched = null;   // {key, base_behind, base_conflicts}
const fetchKey = s => [s.branch, s.task, s.base, s.ahead, s.behind, s.merging].join('|');
WS.refresh = async ({fetch = false, quiet = !fetch} = {}) => {
  if (fetch) get('status-fetched').textContent = '確認中…';
  const doc = await WS.cli(['status', ...(fetch ? ['--fetch'] : [])], {quiet});
  // A look at GitHub of its own accord that failed (offline etc.): what this PC knows is read instead.
  if (!doc.ok && fetch && quiet) { WS.fetchedAt = Date.now(); return WS.refresh(); }
  // Not readable (also when a task operation removed this workspace): the module window reads its list again.
  if (!doc.ok) { WS.status = null; renderBanners(doc); renderChanges(); WS.notifyParent(); return; }
  const before = WS.status?.task;
  // Whether the GitHub repository is archived is known only with --fetch: keep the last answer.
  if (doc.result.archived === null || doc.result.archived === undefined) doc.result.archived = WS.status?.archived ?? null;
  if (fetch) { WS.fetchedAt = Date.now(); fetched = {key: fetchKey(doc.result), base_behind: doc.result.base_behind, base_conflicts: doc.result.base_conflicts}; }
  else if (fetched && fetched.key === fetchKey(doc.result)) Object.assign(doc.result, {base_behind: fetched.base_behind, base_conflicts: fetched.base_conflicts});
  // The branch moved (a commit, taking in, a reset): the last answer no longer holds, GitHub is looked at again soon.
  else if (fetched) { fetched = null; WS.fetchedAt = 0; }
  WS.status = doc.result;
  // The task (its title for the header) is read from GitHub, which takes seconds: the changes are shown first.
  if (WS.status.task && WS.status.task !== before) {
    // ECO.query: the same read as the submission tab's (prs.js), so the two share one run and what was kept shows at once
    const number = WS.status.task;
    const show = t => {
      if (WS.status?.task !== number) return;
      WS.task = t.ok ? t.result : null; renderHeader(); WS.notifyParent();
    };
    ECO.query(WS.dir, ['task', 'status', String(number)], fresh => { if (fresh.ok) show(fresh); }).then(show);
  } else if (!WS.status.task) WS.task = null;
  const all = WS.changes();
  for (const p of [...WS.selected]) if (!all.has(p)) WS.selected.delete(p);
  renderHeader(); renderBanners(); renderChanges();
  for (const fn of WS.listeners) fn();
  WS.notifyParent();
};

// The GitHub account this workspace works as (account show / account use): bound to the workspace (an AI's account
// etc.: its ecobuild, git push and the agent in its container work as it, the commits' author too) or gh's active one.
let wsAccess = null;
async function loadAccount() {
  wsAccess = await ECO.access(WS.dir);
  const button = get('account-button'); if (!button) return;
  const bound = wsAccess?.workspace_account;
  button.classList.toggle('on', !!bound);
  get('account-label').textContent = wsAccess ? wsAccess.login : '?';
  button.dataset.tip = !wsAccess ? 'アカウントを読めませんでした' : bound
    ? `${bound}（この作業空間だけ）・役割：${ECO.roleNames[wsAccess.role] || wsAccess.role}`
    : `${wsAccess.login}（gh の使用中）・役割：${ECO.roleNames[wsAccess.role] || wsAccess.role}`;
}
async function useAccount(account) {
  const doc = await WS.run(['account', 'use', ...(account ? [account] : ['--clear'])],
    {success: account ? `この作業空間を ${account} として動かします。` : '結び付けを外しました（gh の使用中のアカウントで動きます）。'});
  if (doc) await loadAccount();
}
get('account-button')?.addEventListener('click', async () => {
  const r = get('account-button').getBoundingClientRect();
  const doc = await ECO.cli(null, ['account', 'list'], {quiet: true}), accounts = doc.ok ? doc.result : [];
  const bound = wsAccess?.workspace_account || '';
  ECO.menu([
    [bound ? `この作業空間のアカウント：${bound}` : `gh の使用中のアカウント：${wsAccess?.login || '?'}`, null],
    '-',
    ...accounts.filter(a => a.login !== bound).map(a => [`${a.login} として動かす${a.active ? '（gh の使用中）' : ''}`, () => useAccount(a.login)]),
    ['ほかのアカウント…', () => ECO.form({title: 'この作業空間のアカウント', intro: '先にそのアカウントで gh auth login しておきます。',
      fields: [{name: 'account', label: 'GitHub のアカウント', required: true, placeholder: '例：my-ai-account'}], ok: '結び付ける',
      submit: v => useAccount(v.account.trim())})],
    ...(bound ? ['-', ['結び付けを外す（gh の使用中のアカウントに戻す）', () => useAccount(null)]] : []),
  ], r.left, r.bottom + 4);
});
loadAccount();


function renderHeader() {
  const s = WS.status;
  const where = s.reviewing ? `#${s.reviewing_task || '?'} の提出を確認中` : s.task ? `タスクブランチ · ${s.branch}${WS.task ? '　' + WS.task.title : ''}` : `ブランチ · ${s.branch || '（なし）'}`;
  get('workspace-label').textContent = where;
  renderSync();
  document.title = `${get('module-name').textContent} — ${s.branch || ''}`;
  get('push-state').textContent = s.ahead ? `未Pushのコミット ${s.ahead}件` : 'すべてPush済み';
  setTabCount('share-panel', s.task && !s.reviewing ? s.ahead : 0);
  renderStatusBar();
}

// The footer bar (as VS Code's status bar): the panels to show or hide on the left (出力: build.js), the workspace's
// state on the right — what Push sends, how far behind the base (GitHub's latest: status --fetch) and when GitHub was
// last looked at (a click looks again).
function renderStatusBar() {
  const s = WS.status, onTask = !!(s && s.task && !s.reviewing);
  const push = get('status-push');
  push.hidden = !onTask;
  push.textContent = onTask ? (s.ahead ? `↑ 未Push ${s.ahead}` : '↑ Push済み') : '';
  push.title = onTask ? (s.ahead ? `Push していないコミットが ${s.ahead} 件あります` : 'コミットはすべて Push してあります') : '';
  const behind = s ? s.base_behind || 0 : 0, clashes = s?.base_conflicts?.length || 0, base = get('status-base');
  base.hidden = !onTask || !behind;
  base.classList.toggle('bad', clashes > 0);
  base.textContent = behind ? `↓ ${s.base} より ${behind} 遅れ${clashes ? `・衝突 ${clashes}` : ''}` : '';
  base.title = behind ? `作成元 ${s.base} の新しいコミット ${behind} 件を取り込んでいません` + (clashes ? `（取り込むと衝突するファイル：${s.base_conflicts.join('、')}）` : '') : '';
  const at = WS.fetchedAt ? new Date(WS.fetchedAt) : null;
  get('status-fetched').textContent = at ? `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')} に確認` : '未確認';
  get('status-fetch').disabled = !s;
}

// コミット・Push・提出 (and ログ off a task branch) are tabs (the one shown is kept on this PC). A tab whose panel is not
// shown here is hidden.
const TAB_KEY = 'ecobuild-gui-work-tab', TABS = ['commit-panel', 'share-panel', 'prs-panel', 'history-panel'];
let workTab = 'commit-panel';
try { workTab = TABS.includes(localStorage.getItem(TAB_KEY)) ? localStorage.getItem(TAB_KEY) : workTab; } catch (e) { /* storage blocked */ }
function setTabCount(tab, count) {
  const badge = get(tab + '-count');
  badge.textContent = count; badge.classList.toggle('zero', !count);
}
WS.setTabCount = (name, count) => setTabCount(name === 'prs' ? 'prs-panel' : name, count);
function renderTabs() {
  const shown = TABS.filter(id => !get(id).hidden), current = shown.includes(workTab) ? workTab : shown[0];
  get('work-tabs').hidden = shown.length < 2;
  for (const b of get('work-tabs').querySelectorAll('[data-tab]')) {
    b.hidden = !shown.includes(b.dataset.tab);
    b.setAttribute('aria-selected', String(b.dataset.tab === current)); b.tabIndex = b.dataset.tab === current ? 0 : -1;
  }
  for (const id of TABS) get(id).classList.toggle('tab-off', id !== current);
}
WS.showTab = tab => { workTab = tab; try { localStorage.setItem(TAB_KEY, tab); } catch (e) { /* storage blocked */ } renderTabs(); };
renderTabs();   // before the first status: only the kept tab's panel
get('work-tabs').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) WS.showTab(b.dataset.tab); });
get('work-tabs').addEventListener('keydown', e => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  const tabs = [...get('work-tabs').querySelectorAll('[data-tab]:not([hidden])')], i = tabs.findIndex(b => b.dataset.tab === workTab);
  const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
  if (next) { WS.showTab(next.dataset.tab); next.focus(); }
});

function banner(html, kind = '') { return `<div class="eco-banner ${kind}">${html}</div>`; }
// What stopped on a conflict (status stopped) and its two sides (sync take --side current／incoming).
const STOPPED = {merge: '取り込み', rebase: 'タスクブランチの作り直し', revert: '取り消し', stash: '退避した変更の戻し'};
const SIDES = {merge: ['このタスクブランチの側', '取り込む側'], rebase: ['作成元の側', '自分のコミットの側'],
  revert: ['今の内容', '取り消した内容'], stash: ['今の内容', '退避した変更']};
WS.sides = () => SIDES[WS.status?.stopped] || ['今の側', '入ってくる側'];
// A conflicted file resolved with one side's content (the explorer's menu); 続ける finishes what stopped.
WS.takeSide = async (path, incoming) => {
  const doc = await WS.run(['sync', 'take', path, '--side', incoming ? 'incoming' : 'current'], {success: `${path} を${WS.sides()[incoming ? 1 : 0]}で解決しました。`});
  await WS.reloadFiles?.();
  return doc;
};
// 「あとで」 hides the old-format banner while this screen is open (it comes back when reopened).
let upgradeLater = false;
function renderBanners(errorDoc) {
  const s = WS.status, out = [];
  if (!s) out.push(banner(`この場所の状態を取得できませんでした：${esc(errorDoc?.error?.message || '')}`, 'bad'));
  else {
    if (s.merging) out.push(banner(`${STOPPED[s.stopped] || '取り込み'}の途中で衝突しました。衝突したファイルを直して（右クリックで片方の側を採る・「差分」で TortoiseGit の衝突の画面）、「続ける」を押してください。<button data-git="sync-continue">続ける</button><button data-git="sync-abort">やめる</button>`, 'bad'));
    if (s.reviewing) out.push(banner(`#${s.reviewing_task || '?'} の提出を手元で確認しています（コミットはできません）。${s.reviewing_task ? '<button data-git="approve">承認して取り込む</button><button data-git="reject">差し戻す</button>' : ''}<button data-git="review-done">判定せずに終える</button>`));
    else if (!s.task) out.push(banner(`タスクブランチではありません（${esc(s.branch || 'ブランチなし')}）。コミットはタスクブランチで。<button data-git="go-tasks" class="primary">タスク管理を開く</button>`));
    if (s.archived) out.push(banner(`GitHubのリポジトリはアーカイブ（読み取り専用）されています。Push・PR・タスクの変更はできません。<button data-git="unarchive">アーカイブを解除</button>`, 'bad'));
    if (s.upstream_gone && s.finished) out.push(banner(`#${s.task} は完了しています。<button data-git="clean-finished">タスクブランチを片付ける</button>`));
    else if (s.upstream_gone) out.push(banner(`GitHub上の ${esc(s.branch)} は削除されています（別の場所で中止された可能性があります）。タスク管理の「作業を捨てる」で片付けてください。`, 'bad'));
    // Before taking the base in: the files it would conflict on (fixed here after taking it in; better before submitting).
    const clashes = s.base_conflicts || [];
    if (s.behind || s.base_behind) out.push(banner(`最新の変更を取り込んでいません。` + (clashes.length ? `取り込むと ${clashes.length} 件のファイルが衝突します（${clashes.map(esc).join('、')}）。取り込んで直してから提出してください。` : '') + `<button data-git="sync">最新を取り込む</button>`, clashes.length ? 'bad' : ''));
    // Changes left where nothing is committed (main etc.): they can only be thrown away here.
    const left = !s.task && !s.reviewing && !s.merging ? WS.changes().size : 0;
    if (left) out.push(banner(`未コミットの変更が ${left} 件あります。<button data-git="discard-left">変更を捨てる…</button>`));
    // ECOBuild commits its own update (any branch; off a task branch it is pushed too).
    if (s.format < s.latest_format && !upgradeLater) out.push(banner(`ECOBuild の仕様が古くなっています（版 ${s.format} → ${s.latest_format}）。` +
      (s.reviewing || s.merging ? '' : '<button data-git="upgrade">最新の仕様にする</button>') + '<button data-git="upgrade-later">あとで</button>'));
  }
  get('banners').innerHTML = out.join('');
  // Not on a task branch (main etc.): nothing is committed, pushed or submitted here, so those panels are not shown
  // (while a merge is under way the commit panel stays: its files are staged there).
  const working = !s || s.task || s.reviewing;
  get('commit-panel').hidden = !working && !s.merging;
  // Checking someone's submission here: nothing of it is pushed from here (its changes stay to look at, 提出 judges it).
  get('share-panel').hidden = !working || !!s?.reviewing;
  get('prs-panel').hidden = !working;
  // On a task branch 提出 lists the task's commits (the whole log is the explorer's 「ログ」, or 提出's すべてのログ);
  // elsewhere (main etc.) the log is what there is to see here.
  get('history-panel').hidden = working;
  // The tabs (コミット・Push・提出) or the banners say what this is: the heading is only for screen readers.
  get('changes-title').textContent = working ? 'コミット・Push・提出' : 'ログ';
  get('changes-title').classList.add('visually-hidden');
  renderTabs();
}

// The checked files are what is committed. A file staged elsewhere (git, TortoiseGit) starts checked, once.
let seen = new Set();
function renderChanges() {
  const all = WS.changes(), list = get('changes');
  for (const [path, kinds] of all) if (!seen.has(path) && kinds.includes('staged')) WS.selected.add(path);
  seen = new Set(all.keys());
  get('change-count').textContent = all.size;
  setTabCount('commit-panel', all.size);
  const scroll = list.scrollTop;
  list.replaceChildren();
  // Per Project (C++: the Project's name and kind above its files, the path from the Project's folder; a check there
  // takes all its files). One group (or a type without Projects): the list as it is.
  const groups = new Map();
  for (const [path, kinds] of all) {
    const project = WS.projectOf?.(path) || null, key = project ? project.name : '';
    if (!groups.has(key)) groups.set(key, {project, rows: []});
    groups.get(key).rows.push([path, kinds]);
  }
  const order = WS.projectOrder?.() || [];
  const keys = [...groups.keys()].sort((a, b) => (a === '' ? 1e9 : order.indexOf(a)) - (b === '' ? 1e9 : order.indexOf(b)));
  const grouped = keys.length > 1 || (keys.length === 1 && keys[0] !== '');
  for (const key of keys) {
    const {project, rows} = groups.get(key), top = grouped && project?.top ? project.top + '/' : '';
    if (grouped) list.append(changeGroup(project, rows.map(([path]) => path)));
    const root = {dirs: new Map(), files: []};
    for (const [path, kinds] of rows) {
      const parts = path.slice(top.length).split('/');
      let node = root;
      for (const part of parts.slice(0, -1)) { if (!node.dirs.has(part)) node.dirs.set(part, {dirs: new Map(), files: []}); node = node.dirs.get(part); }
      node.files.push([path, kinds, parts.at(-1)]);
    }
    appendChangeTree(list, root, top, grouped ? 1 : 0);
  }
  if (!all.size) list.innerHTML = '<p class="muted">変更はありません。</p>';
  list.scrollTop = scroll;
  get('select-all').checked = all.size > 0 && bulkOf([...all.keys()]).every(p => WS.selected.has(p));
  updateButtons();
}
WS.renderChanges = renderChanges;

// A file whose change is only its line endings (CRLF／LF: status eol_only) is left out of what a check over several
// files takes (all, a Project, a folder), as task commit leaves it out by itself; its own check takes it.
const eolOnly = path => !!WS.status?.eol_only?.includes(path);
const bulkOf = paths => { const some = paths.filter(p => !eolOnly(p)); return some.length ? some : paths; };
WS.bulkOf = bulkOf;
const PROJECT_KIND_LABEL = {static_library: '静的ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', executable: '実行ファイル', test: 'テスト', benchmark: '性能測定'};
function changeGroup(project, paths) {
  const head = document.createElement('label'), box = document.createElement('input'), name = document.createElement('span'), count = document.createElement('small');
  head.className = 'change-group';
  box.type = 'checkbox';
  setGroupBox(box, paths);
  name.textContent = project ? project.name : 'Project の外';
  if (project?.kind) { const kind = document.createElement('span'); kind.className = 'change-group-kind'; kind.textContent = PROJECT_KIND_LABEL[project.kind] || project.kind; name.append(kind); }
  count.textContent = `${paths.length}件`;
  head.title = project ? `${project.top || '（モジュールの一番上）'}` : 'どの Project にも入らないファイル（モジュールの設定・CI 等）';
  head.append(box, name, count);
  return head;
}

// Inside a group, as in the explorer: at each level the folders (by name) before the files (the name only, by name),
// each level indented. A folder's heading takes a check for the files under it; a folder holding only one folder is
// shown with it as one heading (src/foo/bar).
function appendChangeTree(list, node, prefix, depth) {
  const pathsOf = n => [...n.files.map(([path]) => path), ...[...n.dirs.values()].flatMap(pathsOf)];
  for (let [name, child] of [...node.dirs].sort(([a], [b]) => a.localeCompare(b))) {
    while (!child.files.length && child.dirs.size === 1) { const [[sub, next]] = child.dirs; name += '/' + sub; child = next; }
    list.append(changeFolder(prefix + name, name, pathsOf(child), depth));
    appendChangeTree(list, child, prefix + name + '/', depth + 1);
  }
  for (const [path, kinds, name] of node.files.sort((a, b) => a[2].localeCompare(b[2]))) list.append(changeRow(path, kinds, name, depth));
}

function changeFolder(dir, shown, paths, depth) {
  const head = document.createElement('label'), box = document.createElement('input'), name = document.createElement('span'), count = document.createElement('small');
  head.className = 'change-folder'; head.style.paddingLeft = depth * 14 + 'px';
  box.type = 'checkbox';
  setGroupBox(box, paths);
  name.innerHTML = `<span class="change-folder-icon" aria-hidden="true">${CHANGE_FOLDER_ICON}</span>`;
  name.append(shown);
  count.textContent = `${paths.length}件`;
  head.title = dir;
  head.append(box, name, count);
  return head;
}
const CHANGE_FOLDER_ICON = '<svg viewBox="0 0 16 16" width="13" height="13"><path d="M1.5 3.5h4.2l1.5 1.5h7.3v8.5h-13z" fill="currentColor" fill-opacity=".25" stroke="currentColor" stroke-linejoin="round"/></svg>';
// A Project's or a folder's check: on when what it takes (bulkOf) is all checked; it checks that, unchecks everything.
function setGroupBox(box, paths) {
  const taken = bulkOf(paths), chosen = paths.filter(p => WS.selected.has(p)).length;
  box.checked = taken.every(p => WS.selected.has(p)); box.indeterminate = !box.checked && chosen > 0;
  box.addEventListener('change', () => {
    for (const p of paths) WS.selected.delete(p);
    if (box.checked) for (const p of taken) WS.selected.add(p);
    renderChanges();
  });
}

function changeRow(path, kinds, shown, depth = 0) {
  const label = document.createElement('label'), box = document.createElement('input'), name = document.createElement('span'), kind = document.createElement('small');
  const deleted = WS.files && WS.files.missing.includes(path);
  label.className = 'change' + (WS.activeFile === path ? ' focused' : ''); label.dataset.path = path; label.style.paddingLeft = depth * 14 + 'px';
  box.type = 'checkbox'; box.checked = WS.selected.has(path);
  box.addEventListener('change', () => { if (box.checked) WS.selected.add(path); else WS.selected.delete(path); renderChanges(); });
  name.textContent = shown; name.tabIndex = 0; name.setAttribute('role', 'button'); name.title = (shown !== path ? path + '\n' : '') + 'ダブルクリックで差分（開くのは右クリックのメニュー）';
  name.addEventListener('click', e => { e.preventDefault(); WS.activeFile = path; renderChanges(); WS.selectInTree?.(path); });
  // A double click shows the diff; opening the file is in the file menu (explorer.js) on the right click.
  name.addEventListener('dblclick', e => { e.preventDefault(); WS.openDiff(path, kinds); });
  kind.className = 'kind ' + (deleted ? 'deleted' : kinds[0]); kind.textContent = (deleted ? '削除' : '') + (deleted && kinds[0] !== 'staged' ? '' : kinds.map(k => KIND_LABEL[k]).join(' · '));
  if (WS.files?.generated?.includes(path)) { const tag = document.createElement('span'); tag.className = 'generated-tag'; tag.textContent = '生成'; tag.title = 'CppBuild が作り直すファイル（Projectやファイルを足した結果）。そのままコミットしてください。'; name.append(tag); }
  if (eolOnly(path)) { const tag = document.createElement('span'); tag.className = 'generated-tag'; tag.textContent = '改行のみ'; tag.title = '改行コード（CRLF／LF）だけが変わっています。まとめて選んでもコミットに含めません（含めるならこのファイルに印を付けます）。'; name.append(tag); }
  if (WS.status?.excluded?.includes(path)) { const tag = document.createElement('span'); tag.className = 'generated-tag'; tag.textContent = '管理外'; tag.title = '管理するファイル（ecobuild track）の対象外です。印を付ければコミットに含めます。'; name.append(tag); }
  label.append(box, name, kind);
  return label;
}

function updateButtons() {
  const s = WS.status, editable = !!(s && s.task && !s.reviewing), all = WS.changes();
  const hasMessage = !!get('commit-message').value.trim();
  get('commit').disabled = !editable || !hasMessage || (!WS.selected.size && !get('amend').checked);
  get('commit').textContent = WS.selected.size ? `コミット（${WS.selected.size}件）` : 'コミット';
  get('push').disabled = !editable || !s.ahead;
  document.querySelector('[data-git=force-push]').disabled = !editable;
  get('sync-button').disabled = !s || !!s.merging;
  for (const b of document.querySelectorAll('[data-git=stage],[data-git=unstage],[data-git=discard]')) b.disabled = !editable || !WS.selected.size;
  document.querySelector('[data-git=diff]').disabled = !all.size;
  get('stash-menu').disabled = !s || !!s.reviewing || !!s.merging;
  // Staging is needed only to finish a merge that stopped on a conflict (sync continue); a commit stages what is checked.
  get('stage-tools').hidden = !(s && (s.merging || s.conflicted?.length));
}
WS.updateButtons = updateButtons;
for (const id of ['commit-message', 'amend']) get(id).addEventListener('input', updateButtons);
get('select-all').addEventListener('change', e => { WS.selected = new Set(e.target.checked ? bulkOf([...WS.changes().keys()]) : []); renderChanges(); });

async function showDiff(path, kinds) {
  if (kinds.includes('untracked')) {
    const r = await ECO.call('read', {dir: WS.dir, path}).catch(() => null);
    return ECO.output('新しいファイル', r ? (r.binary ? '（バイナリのファイル）' : r.text) : '', {sub: path});
  }
  const args = ['diff', path, ...(kinds.includes('unstaged') || kinds.includes('conflicted') ? [] : ['--staged'])];
  const doc = await WS.cli(args, {quiet: true});
  if (!doc.ok) return ECO.showError(doc);
  ECO.output('差分', doc.result || '差分はありません。', {diff: true, sub: path + (args.includes('--staged') ? '（ステージ済み）' : '')});
}
WS.showDiff = showDiff;
// Looking at git (history, line history, diffs) is TortoiseGit's job (ECO.inTortoiseGit: as text without it).
WS.inTortoiseGit = (args, asText) => ECO.inTortoiseGit(WS.dir, args, asText);
// A changed file's diff (a new file has none: its content is shown here).
WS.openDiff = (path, kinds) => kinds.includes('untracked') ? showDiff(path, kinds)
  : WS.inTortoiseGit(['diff', path, ...(kinds.includes('unstaged') || kinds.includes('conflicted') ? [] : ['--staged'])], () => showDiff(path, kinds));

// Commit: the checked files are exactly what is committed (TortoiseGit style): task commit <paths>.
get('commit').addEventListener('click', async () => {
  const message = get('commit-message').value.trim(), amend = get('amend').checked;
  if (!message) return;
  const paths = [...WS.selected];
  if (!paths.length && amend && WS.changes().size && !await ECO.confirm({title: '直前のコミットを修正', message: 'ファイルを選んでいないので、すべての変更を直前のコミットに含めます。よろしいですか？', ok: '修正する'})) return;
  const doc = await WS.run(['task', 'commit', ...paths, '--message', message, ...(amend ? ['--amend'] : [])], {success: r => 'コミットしました：' + r.message + (r.outside?.length ? `（管理外のファイル ${r.outside.length} 件も含めました）` : '')});
  if (doc) {
    get('commit-message').value = ''; get('amend').checked = false; WS.selected.clear(); renderChanges();
    await WS.reloadFiles?.();   // deleted・moved files leave the explorer only when the list is read again
    if (amend && WS.status.ahead === 0) say('Push済みのコミットを修正した場合は「強制Push」でPushしてください。');
    else if (!WS.changes().size) WS.showTab('share-panel');
  }
});
// After a Push the task is in 提出 (submit or finish it there).
get('push').addEventListener('click', async () => { if (await WS.run(['task', 'push'], {success: 'Pushしました。'})) { WS.showTab('prs-panel'); WS.refreshPrs?.(); } });

// The commits Push sends (log --unpushed: local and quick), listed under 「Push」 while there are any, as in the log:
// a double-click (Enter) shows a commit's changes, the right click its menu.
// 閉じる folds the list (kept on this PC); 「一覧」 next to the count opens it again.
const PUSH_LIST_KEY = 'ecobuild-gui-push-list-closed';
let pushListClosed = false, pushListRead = 0, pushCount = 30;
try { pushListClosed = localStorage.getItem(PUSH_LIST_KEY) === '1'; } catch (e) { /* storage blocked */ }
async function renderPushList() {
  const s = WS.status, box = get('push-commits'), ahead = s && s.task && !s.reviewing ? s.ahead : 0;
  get('push-commits-open')?.remove();
  if (!ahead) { box.hidden = true; return; }
  if (pushListClosed) {
    box.hidden = true;
    get('push-state').insertAdjacentHTML('afterend', '<button type="button" id="push-commits-open" class="link-button">一覧</button>');
    return;
  }
  const mine = ++pushListRead, doc = await WS.cli(['log', '--unpushed', '--count', String(pushCount)], {quiet: true});
  if (mine !== pushListRead) return;   // a newer status came meanwhile
  if (!doc.ok) { box.hidden = false; pushView.error(doc.error.message); return; }
  box.hidden = !doc.result.length;
  pushView.show(doc.result, doc.result.length >= pushCount);
}
// Not pushed yet, so a commit can still be undone: task reset --keep to the one before (the changes stay, to commit
// again) or task reset to it without --keep (the changes go: ecobuild asks first, listing the commits).
function pushCommitMenu(c, x, y) {
  const sha = c.sha.slice(0, 8), index = pushView.entries().findIndex(e => e.sha === c.sha);
  const later = index === 0 ? 'このコミット' : `このコミットから後（${index + 1}件）`;
  const reload = () => WS.reloadFiles?.();
  ECO.menu([
    ['変更を見る', () => pushView.showChanges(c.sha)],
    ['SHAをコピー', () => ECO.copyText(c.sha)],
    '-',
    [`${later}を取り消す（変更は残す）`, () => WS.run(['task', 'reset', `${c.sha}~1`, '--keep', '--yes'],
      {success: r => `コミット ${r.dropped.length} 件を取り消しました。変更は「コミット」に残っています。`}).then(reload)],
    [`${later}を捨てる…`, () => WS.run(['task', 'reset', `${c.sha}~1`], {title: 'コミットを捨てる',
      success: r => `コミット ${r.dropped.length} 件を捨てました。`}).then(reload), true,
      `${sha}「${c.subject}」${index ? 'から後' : ''}のコミットと、その変更を捨てます（元に戻せません）`],
  ], x, y);
}
const pushView = LOG.view(get('push-commits-view'), {dir: WS.dir, menu: pushCommitMenu, detail: false, search: false,
  empty: 'Pushするコミットはありません。', onMore: () => { pushCount += 30; renderPushList(); }});
get('push-commits-view').classList.add('log-short');
const setPushListClosed = closed => { pushListClosed = closed; try { localStorage.setItem(PUSH_LIST_KEY, closed ? '1' : '0'); } catch (e) { /* storage blocked */ } renderPushList(); };
get('push-commits-close').addEventListener('click', () => setPushListClosed(true));
document.querySelector('.share .heading').addEventListener('click', e => { if (e.target.id === 'push-commits-open') setPushListClosed(false); });
WS.onRefresh(renderPushList);

// A commit's menu in a log view here (提出's commits, the ログ tab): its changes, or going back to it — the files as
// they were (restore --source: a change to commit, the history stays) or the task branch itself (task reset: the later
// commits, not pushed, go).
WS.commitMenu = (view, c, x, y) => {
  const s = WS.status, onTask = !!(s && s.task && !s.reviewing), short = c.sha.slice(0, 8);
  const why = 'タスクブランチでだけ使えます';   // the reason a greyed item gives on hover
  ECO.menu([
    ['変更を見る', () => view.showChanges(c.sha)],
    ['SHAをコピー', () => ECO.copyText(c.sha)],
    '-',
    ['この版の状態に戻す…', () => WS.run(['restore', '--source', c.sha],
      {confirm: `ファイルを ${short}「${c.subject}」のときの状態に戻します。これまでのコミットは消さず、戻した結果はコミットする変更になります。`, title: 'この版の状態に戻す',
       success: `${short} の状態に戻しました。内容を確かめてコミットしてください。`}).then(() => WS.reloadFiles?.()), onTask,
      onTask ? '' : why],
    ['ここまで戻す…', () => WS.run(['task', 'reset', c.sha],
      {title: 'ここまで戻す', success: r => r.dropped.length ? `${short} まで戻しました（捨てたコミット ${r.dropped.length} 件）。` : '捨てるコミットはありません。'})
      .then(() => WS.reloadFiles?.()), onTask, onTask ? 'この版より後のコミットを捨てます' : why],
  ], x, y);
};
// ログ (ecobuild log), off a task branch (main etc.: on one, 提出 lists the task's commits): the tab is a log view
// (logview.js). It reads 30 commits; 「さらに読み込む」 reads 30 more.
let historyCount = 30;
const historyView = LOG.view(get('history-view'), {dir: WS.dir, menu: (c, x, y) => WS.commitMenu(historyView, c, x, y), detail: false, onMore: () => { historyCount += 30; loadHistory(); }});
// ブランチ：既定は今のブランチ。管理用のブランチ（GitHub にあるもの）を選ぶと、取り出さずにその履歴を読む（元の clone が
// 古いブランチのままでも、作成元に入った取り込みが見える）
let historyBranches = false;
async function fillHistoryBranches() {
  const select = get('history-branch'), here = WS.status?.branch || '';
  select.options[0].textContent = here ? `今のブランチ（${here}）` : '今のブランチ';
  if (historyBranches) return;
  historyBranches = true;
  const doc = await ECO.query(WS.dir, ['branch', 'list']);
  if (!doc.ok) return;
  const names = doc.result.filter(b => !b.is_task_branch && b.remote && !b.unusable).map(b => b.name).filter(n => n !== here);
  for (const name of names) select.add(new Option(name, name));
}
async function loadHistory() {
  if (get('history-panel').hidden) return;
  fillHistoryBranches();
  const branch = get('history-branch').value;
  const shown = doc => historyView.show(doc.result, doc.result.length >= historyCount);
  const doc = await ECO.query(WS.dir, ['log', '--count', String(historyCount), ...(branch ? ['--branch', branch] : [])], shown);
  if (doc.ok) shown(doc); else historyView.error(doc.error.message);
}
get('history-branch').addEventListener('change', () => { historyCount = 30; loadHistory(); });
WS.onRefresh(loadHistory);

// Stashing (ecobuild stash): the stash is shared by every workspace of the module, and pop and drop take this branch's
// latest one only, so the menu counts and lists this branch's entries ("On <branch>: …" / "WIP on <branch>: …").
const stashBranch = entry => entry.match(/^(?:WIP )?[Oo]n (.+?): /)?.[1] ?? null;
// 取り込む (the toolbar, where the branch's name was: a workspace holds one task branch, so what it belongs to — its
// base — is what there is to take in; the opposite way of Push). The button takes the base's latest in (sync) any time,
// not only from the 最新 banner; it names the base, counts how far behind it is (GitHub's latest: status --fetch) and
// turns red when taking it in would conflict. ▾: another branch (into a task branch only) and looking at GitHub again.
// Checking someone's submission here there is nothing to take in: not shown.
function renderSync() {
  const s = WS.status, group = get('sync-group');
  group.hidden = !s || !!s.reviewing;
  if (group.hidden) return;
  const behind = s.base_behind || s.behind || 0, clashes = s.base_conflicts?.length || 0;
  get('sync-label').textContent = s.task && s.base ? s.base : '取り込む';
  const count = get('sync-count');
  count.hidden = !behind; count.textContent = behind;
  group.classList.toggle('due', behind > 0); group.classList.toggle('bad', clashes > 0);
  get('sync-button').dataset.tip = s.merging ? '止まっている操作を、帯の「続ける」か「やめる」で終えてから取り込めます'
    : (s.task ? `作成元 ${s.base || ''} の最新を取り込む` : 'GitHub の最新を取り込む')
      + (behind ? `（新しいコミット ${behind} 件${clashes ? `・取り込むと衝突するファイル ${clashes} 件：${s.base_conflicts.join('、')}` : ''}）` : '');
}
get('sync-button').addEventListener('click', () => gitAction('sync'));
get('sync-more').addEventListener('click', e => {
  const r = e.currentTarget.getBoundingClientRect(), s = WS.status || {}, stopped = !!s.merging;
  const why = '止まっている操作を、帯の「続ける」か「やめる」で終えてから取り込めます';
  ECO.menu([
    ['最新を取り込む', () => gitAction('sync'), !stopped, stopped ? why : s.task ? `GitHub の作成元（${s.base || ''}）の最新を取り込みます` : 'GitHub の最新を取り込みます'],
    ['ほかのブランチから取り込む…', () => gitAction('sync-from'), !!s.task && !stopped, stopped ? why : s.task ? '別の管理ブランチ・別のタスクブランチの変更を取り込みます' : 'タスクブランチでだけ取り込めます'],
    '-',
    ['GitHub の最新を確認', () => gitAction('fetch'), true, '作成元の遅れ・取り込むと衝突するファイルを確かめます（取り込みはしません）'],
  ], r.left, r.bottom + 4);
});
get('stash-menu').addEventListener('click', async e => {
  const r = e.currentTarget.getBoundingClientRect();
  const doc = await WS.cli(['stash', 'list'], {quiet: true});
  if (!doc.ok) return ECO.showError(doc);
  const branch = WS.status?.branch, own = doc.result.filter(entry => stashBranch(entry) === branch);
  const others = doc.result.length - own.length, changed = WS.changes().size > 0;
  ECO.menu([
    ['変更を退避', () => WS.run(['stash'], {success: r => r.stashed ? '変更を退避しました。' : '退避する変更はありません。'}).then(() => WS.reloadFiles?.()),
      changed, changed ? '未コミットの変更（新しいファイルも）をしまい、最後のコミットの状態にします' : '未コミットの変更はありません'],
    ['退避を戻す', () => WS.run(['stash', 'pop'], {success: '退避した変更を戻しました。'}).then(() => WS.reloadFiles?.()),
      own.length > 0, own.length ? `このブランチで最後に退避した変更を戻します：${own[0]}` : 'このブランチで退避した変更はありません'],
    ['退避の一覧', () => ECO.output('退避の一覧', own.map((entry, i) => `${i + 1}: ${entry}`).join('\n') || 'このブランチで退避した変更はありません。',
      {sub: others ? `${branch}（ほかのブランチの退避 ${others} 件は、それぞれの作業空間で扱います）` : branch})],
    '-',
    ['退避を削除…', async () => {
      if (!await ECO.confirm({title: '退避を削除', message: `このブランチで最後に退避した変更を捨てます。\nこの操作は元に戻せません。`, detail: own[0], ok: '削除', danger: true})) return;
      return WS.run(['stash', 'drop'], {success: '退避した変更を削除しました。'});
    }, own.length > 0, '', {danger: true}],
  ], r.left, r.bottom + 4);
});

// Toolbar actions.
async function gitAction(action) {
  const sel = [...WS.selected];
  switch (action) {
    case 'stage': return WS.run(['task', 'add', ...sel], {success: sel.length + '件をステージしました。'});
    case 'approve': case 'reject': return WS.judge?.(action === 'approve', WS.status.reviewing_task);
    case 'clean-finished': return WS.run(['task', 'prune', String(WS.status.task)], {success: r => '片付けました。' + (r.workspace_removed ? `作業空間 ${r.workspace_removed} を消しました。` : r.workspace_kept ? `作業空間を残しました（${r.workspace_kept}）。` : '')});
    case 'stage-all': return WS.run(['task', 'add', '--all'], {success: 'すべての変更をステージしました。'});
    case 'unstage': {
      const staged = sel.filter(p => WS.status.staged.includes(p));
      if (!staged.length) return say('選択したファイルにステージ済みのものはありません。');
      return WS.run(['restore', ...staged, '--staged'], {success: 'ステージを取り消しました。'});
    }
    case 'discard': {
      // restore: back to the last commit (staged changes too); a file added since (new, staged or not) is deleted.
      if (!await ECO.confirm({title: '変更を元に戻す', message: `${sel.length} 件のファイルの変更を捨てて、最後のコミットの状態に戻します。追加したファイルは消えます。\nこの操作は元に戻せません。`, ok: '元に戻す', danger: true})) return;
      const doc = await WS.run(['restore', ...sel], {success: '変更を元に戻しました。'});
      if (doc) { WS.selected.clear(); renderChanges(); await WS.reloadFiles?.(); }
      return doc;
    }
    case 'diff': return ECO.form({title: '差分', fields: [
      {name: 'path', label: '対象のパス（空欄ならすべて）', value: WS.activeFile || ''},
      {name: 'mode', label: '比較', type: 'radio', value: '', options: [['', 'ステージしていない変更'], ['staged', 'ステージ済みの変更'], ['base', '作成元との差分（提出で出る差分）']]},
      {name: 'gui', label: 'TortoiseGitで表示する', type: 'checkbox', value: true}], ok: '表示',
      submit: async v => {
        const doc = await WS.cli(['diff', ...(v.path ? [v.path] : []), ...(v.mode ? ['--' + v.mode] : []), ...(v.gui ? ['--gui'] : [])]);
        if (!doc.ok) return doc.error.message;
        if (!v.gui) setTimeout(() => ECO.output('差分', doc.result || '差分はありません。', {diff: true, sub: v.path}));
      }});
    case 'sync': return WS.run(['sync'], {success: r => `取り込みました（${r.branch}）` + (r.merged?.length ? '：' + r.merged.join(', ') : '')}).then(() => WS.reloadFiles?.());
    case 'sync-from': {
      // Another branch on GitHub (a management branch or another task branch) into this task branch; its commits go into the submission too.
      const doc = await ECO.query(WS.dir, ['branch', 'list']);
      if (!doc.ok) return ECO.showError(doc);
      const skip = [WS.status.branch, WS.status.base];
      const usable = doc.result.filter(b => b.remote && !b.unusable && !skip.includes(b.name));
      const options = [...usable.filter(b => !b.is_task_branch).map(b => [b.name, b.name]),
        ...usable.filter(b => b.is_task_branch).map(b => [b.name, `${b.name}（タスクブランチ）`])];
      if (!options.length) return say('取り込めるほかのブランチが GitHub にありません。');
      return ECO.form({title: 'ほかのブランチから取り込む',
        intro: `選んだブランチの変更を、このタスクブランチ（${esc(WS.status.branch)}）へ取り込みます。作成元（${esc(WS.status.base || '')}）の最新も一緒に取り込みます。取り込んだコミットは、このタスクブランチの提出にも入ります。`,
        fields: [{name: 'branch', label: '取り込むブランチ', type: 'select', value: options[0][0], options}], ok: '取り込む',
        submit: async v => {
          // A conflict stops here like 最新を取り込む: the banner then offers 続ける／やめる.
          setTimeout(async () => { await WS.run(['sync', '--from-branch', v.branch], {success: r => `取り込みました（${r.branch}）` + (r.merged?.length ? '：' + r.merged.join(', ') : '：すでに入っていました')}); await WS.reloadFiles?.(); });
        }});
    }
    case 'sync-continue': {
      const what = STOPPED[WS.status?.stopped] || '取り込み';
      return WS.run(['sync', 'continue'], {success: WS.status?.stopped === 'stash' ? '衝突を直しました（退避した変更は残っています。いらなければ「退避」から捨てます）。' : `${what}を完了しました。`}).then(() => WS.reloadFiles?.());
    }
    case 'sync-abort': {
      const what = STOPPED[WS.status?.stopped] || '取り込み';
      return WS.run(['sync', 'abort'], {success: `${what}をやめて、前の状態に戻しました。`, confirm: `止まっている${what}をやめて、前の状態に戻します。` + (WS.status?.stopped === 'stash' ? '戻した変更は捨てます（退避した変更は残っています）。' : ''), title: `${what}をやめる`}).then(() => WS.reloadFiles?.());
    }
    case 'upgrade': {
      const plan = await WS.cli(['module', 'upgrade', '--dry-run'], {quiet: true});
      if (!plan.ok) return ECO.showError(plan);
      const where = WS.status?.task ? 'このタスクブランチにコミットします（Push・提出はいつものとおり）。' : `${WS.status?.branch || 'このブランチ'} にコミットし、GitHub へ push します。`;
      if (!await ECO.confirm({title: '最新の仕様にする', message: `ECOBuild の仕様（版 ${plan.result.format} → ${plan.result.latest_format}）に合わせて、次のファイルを変えます（生成ファイルも作り直します）。変えたファイルは「ECOBuild の更新」として${where}`, detail: plan.result.paths.join('\n'), ok: '最新の仕様にする'})) return;
      return WS.run(['module', 'upgrade'], {success: r => `最新の仕様にしました（${r.paths.length}件のファイル）。` + (r.commit ? `「ECOBuild の更新」として ${r.branch} にコミット${r.pushed ? 'し、push' : ''}しました。` : '') + (r.skipped.length ? `手で編集してあるため作り直していません：${r.skipped.join('、')}` : '')}).then(() => WS.reloadFiles?.());
    }
    case 'upgrade-later': upgradeLater = true; return renderBanners();
    case 'discard-left': {
      // Off a task branch: every change shown (added files too) goes back to the last commit (restore <paths>).
      const paths = [...WS.changes().keys()];
      if (!paths.length || !await ECO.confirm({title: '変更を捨てる', message: `${WS.status.branch || 'この作業空間'} の未コミットの変更 ${paths.length} 件を捨てて、最後のコミットの状態に戻します。追加したファイルは消えます。\nこの操作は元に戻せません。`, detail: paths.join('\n'), ok: '捨てる', danger: true})) return;
      return WS.run(['restore', ...paths], {success: '変更を捨てました。'}).then(() => WS.reloadFiles?.());
    }
    case 'unarchive': return ECO.offerUnarchive(WS.dir, {error: {message: 'GitHubのリポジトリがアーカイブ（読み取り専用）されています。'}});
    case 'fetch': return WS.refresh({fetch: true}).then(() => say('GitHubの最新を確認しました。'));
    case 'review-done': return WS.run(['task', 'review', '--done'], {success: '判定せずに確認を終え、確認用の作業空間を消しました。'});
    case 'go-tasks': if (window.parent !== window) window.parent.document.getElementById('tasks-menu')?.click(); return;
  }
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-git]');
  if (b && !b.disabled) { e.preventDefault(); gitAction(b.dataset.git); }
});

// The log of a file or folder (the explorer's 「ログ」) opens in a window of its own (log.html): several can be open
// side by side and moved freely.
// module: the window is the module's (its taskbar button and icon), not the hub's.
WS.showLog = (path = '') => ECO.openPage(`log.html?dir=${encodeURIComponent(WS.dir)}&path=${encodeURIComponent(path)}&module=${encodeURIComponent(WS.module || WS.dir)}`);

WS.ready = WS.refresh();
// After the archive was undone (from an error, or the banner), read the state again.
window.addEventListener('eco-unarchived', () => WS.refresh({fetch: true}));
// GitHub's latest while this screen is shown (in the module window, its tab is the one shown): first after the quick
// read, then every few minutes. A hidden tab looks again when it is shown (within the tick).
const shownNow = () => !document.hidden && (!window.frameElement || window.frameElement.offsetParent !== null);
let fetching = false;
async function fetchIfDue() {
  if (fetching || !shownNow() || !WS.status || Date.now() - WS.fetchedAt < FETCH_EVERY) return;
  fetching = true;
  try { await WS.refresh({fetch: true, quiet: true}); } finally { fetching = false; }
}
WS.ready.then(fetchIfDue);
setInterval(fetchIfDue, 20000);
document.addEventListener('visibilitychange', fetchIfDue);
