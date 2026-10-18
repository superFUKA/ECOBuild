'use strict';
// One workspace on disk: changes, commit, push, PR submission.
// History is in the explorer's menu (a file, a folder, or the whole module); stashing is left to the CLI and TortoiseGit.
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

WS.refresh = async ({fetch = false} = {}) => {
  const doc = await WS.cli(['status', ...(fetch ? ['--fetch'] : [])], {quiet: !fetch});
  if (!doc.ok) { WS.status = null; renderBanners(doc); renderChanges(); return; }
  const before = WS.status?.task;
  // Whether the GitHub repository is archived is known only with --fetch: keep the last answer.
  if (doc.result.archived === null || doc.result.archived === undefined) doc.result.archived = WS.status?.archived ?? null;
  WS.status = doc.result;
  // The task (its title for the header) is read from GitHub, which takes seconds: the changes are shown first.
  if (WS.status.task && WS.status.task !== before) {
    const number = WS.status.task;
    WS.cli(['task', 'status', String(number)], {quiet: true}).then(t => {
      if (WS.status?.task !== number) return;
      WS.task = t.ok ? t.result : null; renderHeader(); WS.notifyParent(); WS.taskLoaded?.();
    });
  } else if (!WS.status.task) WS.task = null;
  const all = WS.changes();
  for (const p of [...WS.selected]) if (!all.has(p)) WS.selected.delete(p);
  renderHeader(); renderBanners(); renderChanges();
  for (const fn of WS.listeners) fn();
  WS.notifyParent();
};

function renderHeader() {
  const s = WS.status;
  const where = s.reviewing ? `#${s.reviewing_task || '?'} の提出を確認中` : s.task ? `タスクブランチ · ${s.branch}${WS.task ? '　' + WS.task.title : ''}` : `ブランチ · ${s.branch || '（なし）'}`;
  get('workspace-label').textContent = where;
  get('branch-name').textContent = s.reviewing ? `#${s.reviewing_task || '?'} の提出を確認中` : s.branch || '（ブランチなし）';
  document.title = `${get('module-name').textContent} — ${s.branch || ''}`;
  get('push-state').textContent = s.ahead ? `未Pushのコミット ${s.ahead}件` : 'すべてPush済み';
  setTabCount('share-panel', s.task && !s.reviewing ? s.ahead : 0);
}

// コミット・Push・提出・ログ are tabs (the one shown is kept on this PC). A tab whose panel is not shown here is hidden.
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
// 「あとで」 hides the old-format banner while this screen is open (it comes back when reopened).
let upgradeLater = false;
function renderBanners(errorDoc) {
  const s = WS.status, out = [];
  if (!s) out.push(banner(`この場所の状態を取得できませんでした：${esc(errorDoc?.error?.message || '')}`, 'bad'));
  else {
    if (s.merging) out.push(banner(`取り込み中に衝突が発生しました。衝突したファイルを修正して「取り込みを完了」を押してください（直したファイルは自動で登録します）。<button data-git="sync-continue">取り込みを完了</button><button data-git="sync-abort">取り込みを中止</button>`, 'bad'));
    if (s.reviewing) out.push(banner(`#${s.reviewing_task || '?'} の提出を手元で確認しています（ビルド・テスト・実行ができます。コミットはできません）。${s.reviewing_task ? '<button data-git="approve">承認して完了</button><button data-git="reject">差し戻す</button>' : ''}<button data-git="review-done">判定せずに戻る</button>`));
    else if (!s.task) out.push(banner(`ここはタスクブランチではありません（${esc(s.branch || 'ブランチなし')}）。ファイルの変更・コミットはタスクブランチで行います。始めているタスクなら見出しの横のブランチから切り替え、新しいタスクはタスク管理で「作業を開始」してください。<button data-git="go-tasks">タスク管理を開く</button>`));
    if (s.archived) out.push(banner(`GitHubのリポジトリはアーカイブ（読み取り専用）されています。Push・PR・タスクの変更はできません。<button data-git="unarchive">アーカイブを解除</button>`, 'bad'));
    if (s.upstream_gone && s.finished) out.push(banner(`#${s.task} は完了しています。<button data-git="clean-finished">タスクブランチを片付ける</button>`));
    else if (s.upstream_gone) out.push(banner(`GitHub上の ${esc(s.branch)} は削除されています（別の場所で中止された可能性があります）。タスク管理の「作業をやめる」で片付けてください。`, 'bad'));
    if (s.behind || s.base_behind) out.push(banner(`最新の変更を取り込んでいません。<button data-git="sync">最新を取り込む</button>`));
    // Changes left where nothing is committed (main etc.): they can only be thrown away here.
    const left = !s.task && !s.reviewing && !s.merging ? WS.changes().size : 0;
    if (left) out.push(banner(`未コミットの変更が ${left} 件残っています。タスクブランチではないので、ここではコミットできません。<button data-git="discard-left">変更を捨てる…</button>`));
    // ECOBuild commits its own update (any branch; off a task branch it is pushed too).
    if (s.format < s.latest_format && !upgradeLater) out.push(banner(`このモジュールは以前の ECOBuild の仕様（版 ${s.format}）です。今の版 ${s.latest_format} に合わせられます（.gitignore・AGENTS.md・CI 等を今の中身に。README は変えません。変えたファイルは「ECOBuild の更新」として自動でコミットします）。` +
      (s.reviewing || s.merging ? '' : '<button data-git="upgrade">最新の仕様にする</button>') + '<button data-git="upgrade-later">あとで</button>'));
  }
  get('banners').innerHTML = out.join('');
  // Not on a task branch (main etc.): nothing is committed, pushed or submitted here, so those panels are not shown
  // (while a merge is under way the commit panel stays: its files are staged there).
  const working = !s || s.task || s.reviewing;
  get('commit-panel').hidden = !working && !s.merging;
  get('share-panel').hidden = !working;
  get('prs-panel').hidden = !working;
  // On a task branch the tabs (コミット・Push・提出) say what this is: the heading is only for screen readers then.
  get('changes-title').textContent = working ? 'コミット・Push・提出・ログ' : '作業空間';
  get('changes-title').classList.toggle('visually-hidden', !!working);
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
  list.replaceChildren();
  for (const [path, kinds] of all) {
    const label = document.createElement('label'), box = document.createElement('input'), name = document.createElement('span'), kind = document.createElement('small');
    const deleted = WS.files && WS.files.missing.includes(path);
    label.className = 'change' + (WS.activeFile === path ? ' focused' : ''); label.dataset.path = path;
    box.type = 'checkbox'; box.checked = WS.selected.has(path);
    box.addEventListener('change', () => { if (box.checked) WS.selected.add(path); else WS.selected.delete(path); updateButtons(); });
    name.textContent = path; name.tabIndex = 0; name.setAttribute('role', 'button'); name.title = 'ダブルクリックで差分';
    name.addEventListener('click', e => { e.preventDefault(); WS.activeFile = path; renderChanges(); WS.selectInTree?.(path); });
    name.addEventListener('dblclick', e => { e.preventDefault(); WS.openDiff(path, kinds); });
    kind.className = 'kind ' + (deleted ? 'deleted' : kinds[0]); kind.textContent = (deleted ? '削除' : '') + (deleted && kinds[0] !== 'staged' ? '' : kinds.map(k => KIND_LABEL[k]).join(' · '));
    if (WS.files?.generated?.includes(path)) { const tag = document.createElement('span'); tag.className = 'generated-tag'; tag.textContent = '生成'; tag.title = 'CppBuild が作り直すファイル（Projectやファイルを足した結果）。そのままコミットしてください。'; name.append(tag); }
    if (WS.status?.excluded?.includes(path)) { const tag = document.createElement('span'); tag.className = 'generated-tag'; tag.textContent = '管理外'; tag.title = '管理するファイル（ecobuild track）の対象外です。印を付ければコミットに含めます。'; name.append(tag); }
    label.append(box, name, kind); list.append(label);
  }
  if (!all.size) list.innerHTML = '<p class="muted">変更はありません。</p>';
  get('select-all').checked = all.size > 0 && WS.selected.size === all.size;
  updateButtons();
}
WS.renderChanges = renderChanges;

function updateButtons() {
  const s = WS.status, editable = !!(s && s.task && !s.reviewing), all = WS.changes();
  const hasMessage = !!get('commit-message').value.trim();
  get('commit').disabled = !editable || !hasMessage || (!WS.selected.size && !get('amend').checked);
  get('commit').textContent = WS.selected.size ? `コミット（${WS.selected.size}件）` : 'コミット';
  get('push').disabled = !editable || !s.ahead;
  document.querySelector('[data-git=force-push]').disabled = !editable;
  for (const b of document.querySelectorAll('[data-git=stage],[data-git=unstage],[data-git=discard]')) b.disabled = !editable || !WS.selected.size;
  document.querySelector('[data-git=diff]').disabled = !all.size;
  // Staging is needed only to finish a merge that stopped on a conflict (sync continue); a commit stages what is checked.
  get('stage-tools').hidden = !(s && (s.merging || s.conflicted?.length));
  get('stage-status').textContent = all.size ? `${all.size}件の変更のうち ${WS.selected.size}件をコミット` : '';
}
WS.updateButtons = updateButtons;
for (const id of ['commit-message', 'amend']) get(id).addEventListener('input', updateButtons);
get('select-all').addEventListener('change', e => { WS.selected = new Set(e.target.checked ? WS.changes().keys() : []); renderChanges(); });

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
// Looking at git (history, line history, diffs) is TortoiseGit's job: ecobuild … --gui opens it there, which shows it
// better than text here. Without TortoiseGit, it is shown here as text (asText).
let noTortoiseGit = false;
WS.inTortoiseGit = async (args, asText) => {
  if (!noTortoiseGit) {
    const doc = await WS.cli([...args, '--gui'], {quiet: true});
    if (doc.ok) return;
    if (doc.error?.code !== 'tool_missing') return ECO.showError(doc);
    noTortoiseGit = true;
    say('TortoiseGit が見つからないため、この画面に文字で表示します（TortoiseGit を入れると、そちらで開きます）。');
  }
  return asText();
};
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
    if (amend && WS.status.ahead === 0) say('Push済みのコミットを修正した場合は「強制Push」でPushしてください。');
    else if (!WS.changes().size) WS.showTab('share-panel');
  }
});
// After a Push the task is in 提出 (submit or finish it there).
get('push').addEventListener('click', async () => { if (await WS.run(['task', 'push'], {success: 'Pushしました。提出・完了は「提出」で。'})) { WS.showTab('prs-panel'); WS.refreshPrs?.(); } });

// The commits Push sends (task push --dry-run: local and quick), listed under 「共有」 while there are any.
// 閉じる folds the list (kept on this PC); 「一覧」 next to the count opens it again.
const PUSH_LIST_KEY = 'ecobuild-gui-push-list-closed';
let pushListClosed = false, pushListRead = 0;
try { pushListClosed = localStorage.getItem(PUSH_LIST_KEY) === '1'; } catch (e) { /* storage blocked */ }
async function renderPushList() {
  const s = WS.status, box = get('push-commits'), ahead = s && s.task && !s.reviewing ? s.ahead : 0;
  get('push-commits-open')?.remove();
  if (!ahead) { box.hidden = true; return; }
  if (pushListClosed) {
    box.hidden = true;
    get('push-state').insertAdjacentHTML('afterend', '<button type="button" id="push-commits-open" class="link-button" title="Pushするコミットの一覧を開く">一覧</button>');
    return;
  }
  const mine = ++pushListRead, doc = await WS.cli(['task', 'push', '--dry-run'], {quiet: true});
  if (mine !== pushListRead) return;   // a newer status came meanwhile
  const commits = doc.ok ? doc.result.commits : [];
  box.hidden = !commits.length;
  get('push-commits-title').textContent = `Pushするコミット（${commits.length}件、新しい順）`;
  get('push-commits-list').innerHTML = commits.map(c => { const [sha, ...subject] = c.split(' '); return `<li><code>${esc(sha)}</code> ${esc(subject.join(' '))}</li>`; }).join('');
}
const setPushListClosed = closed => { pushListClosed = closed; try { localStorage.setItem(PUSH_LIST_KEY, closed ? '1' : '0'); } catch (e) { /* storage blocked */ } renderPushList(); };
get('push-commits-close').addEventListener('click', () => setPushListClosed(true));
document.querySelector('.share .heading').addEventListener('click', e => { if (e.target.id === 'push-commits-open') setPushListClosed(false); });
WS.onRefresh(renderPushList);

// ログ (ecobuild log): a commit's menu shows its changes, or goes back to it — the files as they were (restore --source:
// a change to commit, the history stays) or the task branch itself (task reset: the later commits, not pushed, go).
// The tab shows 30 commits; 「さらに読み込む」 reads 30 more, the search box narrows them (subject, author, SHA, #task).
let history = [], historyCount = 30;
const matchesCommit = (c, query) => !query || [c.sha, c.subject, c.author, c.issue ? '#' + c.issue : ''].some(v => String(v).toLowerCase().includes(query));
async function loadHistory() {
  const doc = await ECO.query(WS.dir, ['log', '--count', String(historyCount)], fresh => { history = fresh.result; renderHistory(); });
  history = doc.ok ? doc.result : []; renderHistory();
}
function renderHistory() {
  const box = get('history-list'); if (!box) return;
  const query = get('history-search').value.trim().toLowerCase();
  box.innerHTML = history.map((c, i) => matchesCommit(c, query) ? `<li><button type="button" data-history="${i}" title="${esc(c.sha)}　右クリック・押すと操作">
    <code>${esc(c.sha.slice(0, 8))}</code><span class="history-subject">${esc(c.subject)}</span>
    <small>${esc(c.author)}・${esc(ECO.localTime(c.date, true))}${c.issue ? `・#${c.issue}` : ''}</small></button></li>` : '').join('')
    || `<li class="muted">${query ? '一致するコミットはありません。' : 'ログはありません。'}</li>`;
  get('history-more').hidden = history.length < historyCount;
}
get('history-search').addEventListener('input', renderHistory);
get('history-more').addEventListener('click', () => { historyCount += 30; loadHistory(); });
get('history-open').addEventListener('click', () => showLog());
function historyMenu(index, x, y) {
  const c = history[index], s = WS.status, onTask = !!(s && s.task && !s.reviewing), short = c.sha.slice(0, 8);
  ECO.menu([
    ['差分を見る', () => showLog('', c.sha)],
    ['SHAをコピー', () => ECO.copyText(c.sha)],
    '-',
    [onTask ? 'この版の状態に戻す（変更としてコミットする）…' : 'この版の状態に戻す（タスクブランチで）', () => WS.run(['restore', '--source', c.sha],
      {confirm: `ファイルを ${short}「${c.subject}」のときの状態に戻します。これまでのコミットは消さず、戻した結果はコミットする変更になります。`, title: 'この版の状態に戻す',
       success: `${short} の状態に戻しました。内容を確かめてコミットしてください。`}).then(() => WS.reloadFiles?.()), onTask],
    [onTask ? 'ここまで戻す（後のコミットを捨てる）…' : 'ここまで戻す（タスクブランチで）', () => WS.run(['task', 'reset', c.sha],
      {title: 'ここまで戻す', success: r => r.dropped.length ? `${short} まで戻しました（捨てたコミット ${r.dropped.length} 件）。` : '捨てるコミットはありません。'})
      .then(() => WS.reloadFiles?.()), onTask],
  ], x, y);
}
get('history-list')?.addEventListener('click', e => { const b = e.target.closest('[data-history]'); if (b) { const r = b.getBoundingClientRect(); historyMenu(Number(b.dataset.history), r.left + 40, r.bottom); } });
get('history-list')?.addEventListener('contextmenu', e => { const b = e.target.closest('[data-history]'); if (b) { e.preventDefault(); historyMenu(Number(b.dataset.history), e.clientX, e.clientY); } });
WS.onRefresh(loadHistory);
// Switching the task branch placed here (task start <n>: one already started, here or on GitHub). A new task is
// started from タスク管理 (its dialog chooses the base and the place). A task branch placed in another workspace is
// not placed here too: its tab is shown instead (one task branch, one place).
const keyOf = dir => dir.replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();
ECO.info().then(info => { WS.me = info.me || ''; }).catch(() => {});
function whyNotSwitch(s) {
  if (!s) return 'この場所の状態を読めません。';
  if (s.merging) return '取り込みの途中です（完了するか中止してから切り替えます）。';
  if (s.reviewing) return '提出を確認中です（「判定せずに戻る」で戻ってから切り替えます）。';
  const excluded = new Set(s.excluded || []);
  if (s.staged.length || s.unstaged.length || s.conflicted.length || s.untracked.some(p => !excluded.has(p))) return '未コミットの変更があります（コミットするか退避してから切り替えます）。';
  return '';
}
get('switch-branch').addEventListener('click', async () => {
  const button = get('switch-branch'), r = button.getBoundingClientRect(), s = WS.status;
  const doc = await ECO.query(WS.dir, ['task', 'list']);
  if (!doc.ok) return ECO.showError(doc);
  const why = whyNotSwitch(s), here = keyOf(WS.dir);
  const started = doc.result.filter(t => t.state === 'open' && (t.current || t.task_branch || t.remote || t.workspace));
  const items = started.map(t => {
    const label = `#${t.number} ${t.title}`;
    if (t.current) return [`✓ ${label}（ここに置いています）`, () => {}, false];
    if (t.workspace && keyOf(t.workspace) !== here) {
      return [`${label}（作業空間 ${t.workspace.split(/[\\/]/).pop()}）`, () => window.parent.postMessage({type: 'open-place', dir: t.workspace}, location.origin),
        window.parent !== window, `別の作業空間に置いてあります。そのタブを表示します（${t.workspace}）`];
    }
    const others = WS.me && t.assignees?.length && !t.assignees.includes(WS.me) ? t.assignees : [];
    if (others.length) return [`${label}（担当：${others.join('、')}）`, () => {}, false, 'ほかの人が担当しています。引き継ぐなら、タスク管理の「作業を開始」から'];
    return [label + (t.task_branch ? '' : '（GitHubから再開）'), () => WS.run(['task', 'start', String(t.number)],
      {success: `タスクブランチ task/${t.number} に切り替えました。`}).then(d => d && WS.reloadFiles?.()), !why, why];
  });
  ECO.menu([
    [why || 'この作業空間に置くタスクブランチ', null],
    ...items,
    ...(started.some(t => !t.current) ? [] : [['ほかに始めているタスクはありません', () => {}, false]]),
    ...(window.parent !== window ? ['-', ['新しいタスクを始める（タスク管理）', () => gitAction('go-tasks')]] : []),
  ], r.left, r.bottom + 4);
});

// Toolbar actions.
async function gitAction(action) {
  const sel = [...WS.selected];
  switch (action) {
    case 'stage': return WS.run(['task', 'add', ...sel], {success: sel.length + '件をステージしました。'});
    case 'approve': case 'reject': return WS.judge?.(action === 'approve', WS.status.reviewing_task);
    case 'clean-finished': return WS.run(['task', 'prune', String(WS.status.task)], {success: r => '片付けました。' + (r.switched_to ? `${r.switched_to} に移りました。` : '')}).then(() => WS.reloadFiles?.());
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
    case 'sync-continue': return WS.run(['sync', 'continue'], {success: '取り込みを完了しました。'});
    case 'sync-abort': return WS.run(['sync', 'abort'], {success: '取り込みを中止し、取り込む前の状態に戻しました。', confirm: '止まっている取り込みを中止し、取り込む前の状態に戻します。', title: '取り込みを中止'}).then(() => WS.reloadFiles?.());
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
    case 'review-done': return WS.run(['task', 'review', '--done'], {success: '判定せずに確認を終えて戻りました。'}).then(() => WS.reloadFiles?.());
    case 'go-tasks': if (window.parent !== window) window.parent.document.getElementById('tasks-menu')?.click(); return;
    case 'pr-refresh': return WS.refreshPrs?.();
  }
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-git]');
  if (b && !b.disabled) { e.preventDefault(); gitAction(b.dataset.git); }
});

// The log to read at length (the ログ tab's 「大きく表示」・「差分を見る」, the explorer's 「ログ」 without TortoiseGit): the
// commits on the left (search, ↑↓, read more), the chosen one's changes on the right (path: only its log, its files open).
async function showLog(path = '', selected = '') {
  let count = 50, entries = [], chosen = selected;
  const diffs = new Map();
  const load = async () => {
    const doc = await WS.cli(['log', ...(path ? [path] : []), '--count', String(count)], {quiet: true});
    if (doc.ok) entries = doc.result; else ECO.showError(doc);
    return doc.ok;
  };
  if (!await load()) return;
  chosen ||= entries[0]?.sha || '';
  return ECO.dialog({title: path ? `ログ：${path}` : 'ログ', wide: true,
    body: `<div class="log-view"><div class="log-side"><input type="search" class="log-search" placeholder="件名・作成者・SHA・#タスクで絞り込み" aria-label="ログを絞り込む">
      <ul class="log-entries" role="listbox" tabindex="0" aria-label="コミット"></ul><button type="button" class="log-more">さらに読み込む</button></div><div class="log-main"></div></div>`,
    onOpen: d => {
      d.classList.add('eco-output', 'log-dialog');
      const list = d.querySelector('.log-entries'), main = d.querySelector('.log-main'), search = d.querySelector('.log-search'), more = d.querySelector('.log-more');
      const visible = () => entries.filter(c => matchesCommit(c, search.value.trim().toLowerCase()));
      const renderList = () => {
        list.innerHTML = visible().map(c => `<li role="option" data-sha="${esc(c.sha)}" aria-selected="${c.sha === chosen}"><code>${esc(c.sha.slice(0, 8))}</code><span class="log-subject">${esc(c.subject)}</span>
          <small>${esc(c.author)}・${esc(ECO.localTime(c.date, true))}${c.issue ? `・#${c.issue}` : ''}</small></li>`).join('') || '<li class="muted">一致するコミットはありません。</li>';
        more.hidden = entries.length < count;
      };
      const choose = async sha => {
        chosen = sha; renderList();
        list.querySelector('[aria-selected=true]')?.scrollIntoView({block: 'nearest'});
        if (!sha) { main.innerHTML = '<p class="muted">ログはありません。</p>'; return; }
        if (!diffs.has(sha)) {
          main.innerHTML = '<p class="muted">読み込んでいます…</p>';
          const doc = await WS.cli(['show', sha], {quiet: true});
          diffs.set(sha, doc.ok ? doc.result : `読み込めませんでした：${doc.error.message}`);
        }
        if (chosen !== sha) return;
        const c = entries.find(x => x.sha === sha);
        main.innerHTML = `<div class="log-commit"><strong>${esc(c?.subject || sha.slice(0, 8))}</strong><button type="button" data-copy="${esc(sha)}">SHAをコピー</button>
          <button type="button" data-fold="open">すべて開く</button><button type="button" data-fold="close">すべて閉じる</button></div>${ECO.diffHtml(diffs.get(sha), {focus: path})}`;
        main.scrollTop = 0;
      };
      list.addEventListener('click', e => { const row = e.target.closest('[data-sha]'); if (row) choose(row.dataset.sha); });
      list.addEventListener('keydown', e => {
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
        e.preventDefault();
        const shown = visible(), i = shown.findIndex(c => c.sha === chosen), next = shown[Math.max(0, Math.min(shown.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))];
        if (next && next.sha !== chosen) choose(next.sha);
      });
      main.addEventListener('click', e => {
        const copy = e.target.closest('[data-copy]'), fold = e.target.closest('[data-fold]')?.dataset.fold;
        if (copy) ECO.copyText(copy.dataset.copy);
        if (fold) main.querySelectorAll('details.eco-file').forEach(f => { f.open = fold === 'open'; });
      });
      search.addEventListener('input', renderList);
      more.addEventListener('click', async () => { count += 50; if (await load()) renderList(); });
      choose(chosen);
      setTimeout(() => list.focus());   // after the dialog focuses its button
    }});
}
WS.showLog = showLog;

WS.ready = WS.refresh();
// After the archive was undone (from an error, or the banner), read the state again.
window.addEventListener('eco-unarchived', () => WS.refresh({fetch: true}));
