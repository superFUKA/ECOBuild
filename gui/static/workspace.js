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
      WS.task = t.ok ? t.result : null; renderHeader(); WS.notifyParent();
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
  document.title = `${get('module-name').textContent} — ${s.branch || ''}`;
  const parts = [];
  if (s.task) parts.push('作成元 ' + s.base);
  get('push-state').textContent = s.ahead ? `未Pushのコミット ${s.ahead}件` : 'すべてPush済み';
  if (s.behind) parts.push('GitHubより ' + s.behind + ' 遅れ');
  if (s.base_behind) parts.push('作成元より ' + s.base_behind + ' 遅れ');
  get('branch-state').textContent = (s.task ? s.branch + '　' : '') + parts.join(' · ');
  const pr = s.pull_request;
  get('pr-state').textContent = pr && !s.finished ? `このタスクブランチ：${submissionText(pr)}` : '';
}

// How the workspace's submission reads (PullRequestState). After a partial submission was taken in, none is open.
function submissionText(pr) {
  const kind = pr.partial ? '中間提出' : '提出';
  if (pr.state === 'merged') return pr.partial ? '前回の中間提出は取り込み済み（今の提出はなし）' : `${kind}は取り込み済み`;
  if (pr.state === 'closed') return `${kind}は取り下げ済み`;
  return `${pr.draft ? '下書きの' : ''}${kind}中`;
}
const submitted = () => WS.status?.pull_request?.state === 'open' && !WS.status.finished;

function banner(html, kind = '') { return `<div class="eco-banner ${kind}">${html}</div>`; }
function renderBanners(errorDoc) {
  const s = WS.status, out = [];
  if (!s) out.push(banner(`この場所の状態を取得できませんでした：${esc(errorDoc?.error?.message || '')}`, 'bad'));
  else {
    if (s.merging) out.push(banner(`取り込み中に衝突が発生しました。衝突したファイルを修正して「取り込みを完了」を押してください（直したファイルは自動で登録します）。<button data-git="sync-continue">取り込みを完了</button><button data-git="sync-abort">取り込みを中止</button>`, 'bad'));
    if (s.reviewing) out.push(banner(`#${s.reviewing_task || '?'} の提出を手元で確認しています（ビルド・テスト・実行ができます。コミットはできません）。${s.reviewing_task ? '<button data-git="approve">承認して完了</button><button data-git="reject">差し戻す</button>' : ''}<button data-git="review-done">判定せずに戻る</button>`));
    else if (!s.task) out.push(banner(`ここはタスクブランチではありません（${esc(s.branch || 'ブランチなし')}）。ファイルの変更・コミットはタスクブランチで行います。タスク管理で「作業を開始」してください。<button data-git="go-tasks">タスク管理を開く</button>`));
    if (s.archived) out.push(banner(`GitHubのリポジトリはアーカイブ（読み取り専用）されています。Push・PR・タスクの変更はできません。<button data-git="unarchive">アーカイブを解除</button>`, 'bad'));
    if (s.upstream_gone && s.finished) out.push(banner(`#${s.task} は完了しています。<button data-git="clean-finished">タスクブランチを片付ける</button>`));
    else if (s.upstream_gone) out.push(banner(`GitHub上の ${esc(s.branch)} は削除されています（別の場所で中止された可能性があります）。タスク管理の「作業をやめる」で片付けてください。`, 'bad'));
    if (s.behind || s.base_behind) out.push(banner(`最新の変更を取り込んでいません。<button data-git="sync">最新を取り込む</button>`));
  }
  get('banners').innerHTML = out.join('');
}

// The checked files are what is committed. A file staged elsewhere (git, TortoiseGit) starts checked, once.
let seen = new Set();
function renderChanges() {
  const all = WS.changes(), list = get('changes');
  for (const [path, kinds] of all) if (!seen.has(path) && kinds.includes('staged')) WS.selected.add(path);
  seen = new Set(all.keys());
  get('change-count').textContent = all.size;
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
  const open = submitted(), draft = open && s.pull_request.draft;
  get('submit-pr').disabled = !editable || (open && !draft);
  get('submit-pr').textContent = draft ? '下書きを解除' : '提出する';
  get('submit-pr').title = open && !draft ? '提出済みです（コミットしてPushすると、提出に加わります）' : '';
  get('finish').disabled = !editable || draft;
  get('finish').title = draft ? '下書きの提出は完了できません（先に下書きを解除）' : '提出していなければ提出し、CIを待って取り込み、タスクを閉じます';
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
  if (!paths.length && amend && WS.changes().size && !await ECO.confirm({title: '直前のコミットを修正', message: '印を付けたファイルがないため、変更（管理するファイル）をすべて直前のコミットに含めます。よろしいですか？', ok: '修正する'})) return;
  const doc = await WS.run(['task', 'commit', ...paths, '--message', message, ...(amend ? ['--amend'] : [])], {success: r => 'コミットしました：' + r.message + (r.outside?.length ? `（管理外のファイル ${r.outside.length} 件も含めました）` : '')});
  if (doc) { get('commit-message').value = ''; get('amend').checked = false; WS.selected.clear(); renderChanges(); if (amend && WS.status.ahead === 0) say('Push済みのコミットを修正した場合は「強制Push」でPushしてください。'); }
});
get('push').addEventListener('click', () => WS.run(['task', 'push'], {success: 'Pushしました。'}));

// The commits Push sends (task push --dry-run: local and quick), listed under 「GitHubへ共有」 while there are any.
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
get('submit-pr').addEventListener('click', () => submitted() ? WS.run(['task', 'submit', '--no-check'], {success: '下書きを解除しました。'}).then(() => WS.refreshPrs?.()) : ECO.form({
  title: '提出する', intro: '確認（ビルド・テスト等）してからタスクブランチをPushし、作成元' + (WS.status?.base ? `（${esc(WS.status.base)}）` : '') + 'へ提出します。',
  fields: [
    {name: 'title', label: '題名', value: WS.task?.title || '', placeholder: '空欄ならタスクの題名'},
    {name: 'draft', label: '下書きとして提出する（準備ができたら「下書きを解除」）', type: 'checkbox'},
    {name: 'partial', label: '中間提出（取り込んでもタスクを閉じず、タスクブランチを作り直して続ける）', type: 'checkbox'},
    {name: 'reviewer', label: '見てもらう人（カンマ区切り、任意）'},
    {name: 'check', label: '提出前にビルド・テストを確認する', type: 'checkbox', value: true},
  ], ok: '提出する',
  submit: async v => {
    const args = ['task', 'submit', ...(v.title ? ['--title', v.title] : []), ...(v.draft ? ['--draft'] : []), ...(v.partial ? ['--partial'] : []), ...(v.reviewer ? ['--reviewer', v.reviewer] : []), ...(v.check ? [] : ['--no-check'])];
    const doc = await WS.run(args, {success: r => `${r.partial ? '中間提出' : '提出'}しました。`});
    if (!doc) return '提出できませんでした。';
    WS.refreshPrs?.();
  },
}));
get('finish').addEventListener('click', () => ECO.form({
  title: '完了する', intro: (submitted() ? '' : '提出していないので、提出してから取り込みます。') + 'CIを待って取り込み、タスクを閉じて、このタスクブランチを片付けます（中間提出なら、取り込んだ後にタスクブランチを作り直して続けます）。',
  fields: [{name: 'subject', label: '取り込むコミットの件名', value: WS.task?.title || '', placeholder: '空欄ならタスクの題名'}, {name: 'ignore', label: 'CIが失敗していても完了する', type: 'checkbox'}], ok: '完了する',
  submit: async v => {
    const doc = await WS.run(['task', 'finish', ...(v.subject && v.subject !== WS.task?.title ? ['--subject', v.subject] : []), ...(v.ignore ? ['--ignore-checks'] : [])],
      {success: r => r.partial ? '中間提出を取り込み、タスクブランチを作り直しました。' : `#${r.task} を完了しました。` + (r.next ? `次の候補：#${r.next.number} ${r.next.title}` : '')});
    if (!doc) return '完了できませんでした。';
    WS.reloadFiles?.(); WS.refreshPrs?.();
  },
}));

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
      const tracked = sel.filter(p => !WS.status.untracked.includes(p)), untracked = sel.filter(p => WS.status.untracked.includes(p));
      if (!tracked.length) return say('未追跡のファイルは「元に戻す」の対象ではありません。不要ならエクスプローラーから削除してください。');
      if (!await ECO.confirm({title: '変更を元に戻す', message: `${tracked.length}件のファイルの未コミットの変更を破棄します。この操作は元に戻せません。` + (untracked.length ? `（未追跡の ${untracked.length} 件はそのままです）` : ''), ok: '元に戻す', danger: true})) return;
      return WS.run(['restore', ...tracked], {success: '変更を元に戻しました。'});
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

function showLog(entries, path) {
  const text = entries.map(e => `${e.sha.slice(0, 8)}  ${ECO.localTime(e.date, true)}  ${e.author}\n    ${e.subject}${e.issue ? `  (タスク #${e.issue})` : ''}`).join('\n');
  ECO.output('コミット履歴', text || '履歴はありません。', {sub: path || ''});
}
WS.showLog = showLog;

WS.ready = WS.refresh();
// After the archive was undone (from an error, or the banner), read the state again.
window.addEventListener('eco-unarchived', () => WS.refresh({fetch: true}));
