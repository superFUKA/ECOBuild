'use strict';
// The submission of this workspace: the task branch placed here (listed before it is submitted: it is on GitHub from
// task start, and Push sends its commits), or the submission being reviewed here. Status (reviews, comments, CI),
// diff, submit, finish, withdraw; approve/reject while reviewing. The submissions of the whole module are in the
// module's ブランチ page. Every number is a task number; the pull request behind a submission is the CLI's business.
let selectedPr = 0, prStatus = null, me = '';
// The account's role here (account show): approving and sending back are greyed for those who do not handle the base,
// and it chooses between 反映 and 提出. Not read (an older ecobuild, no GitHub): as if handling it (the CLI decides).
let access = null, accessRead = false;
ECO.info().then(info => { me = info.me || ''; });
ECO.access(WS.dir).then(a => { access = a; accessRead = true; if (prStatus) renderPrDetail(); });
const prButton = ECO.submissionButton;

// The task branch here, while it is worked on (not finished, not reviewing someone's submission).
const currentTask = () => { const s = WS.status; return s && s.task && !s.reviewing && !s.finished && !s.upstream_gone ? s.task : 0; };
// The task this tab is about: the one being reviewed here, else the task branch here.
const hereTask = () => (WS.status?.reviewing && WS.status.reviewing_task) || currentTask();
WS.refreshPrs = async () => {
  await WS.ready;
  const n = hereTask();
  if (!n) { selectedPr = 0; prStatus = null; renderPrDetail(); return; }
  await loadPr(n);
};
async function loadPr(number) {
  if (selectedPr !== number) { selectedPr = number; prStatus = null; get('pr-tools').replaceChildren(); get('pr-detail').innerHTML = ECO.loading(); }
  const doc = await ECO.query(WS.dir, ['task', 'status', String(number)], fresh => {
    if (selectedPr === number && fresh.ok) { prStatus = fresh.result; renderPrDetail(); }
  });
  if (selectedPr !== number) return;
  prStatus = doc.ok ? doc.result : null;
  if (!doc.ok) get('pr-detail').innerHTML = `<p class="muted">${esc(doc.error.message)}</p>`;
  else renderPrDetail();
}
function renderPrDetail() {
  const t = prStatus, tools = get('pr-tools');
  tools.replaceChildren();
  // The commits going into the submission (not in the base yet), like the counts of the other tabs.
  WS.setTabCount?.('prs', selectedPr && t && t.number === selectedPr ? t.commits?.length || 0 : 0);
  if (!selectedPr) { get('pr-note').hidden = true; get('pr-commits').hidden = true; get('pr-detail').innerHTML = '<p class="muted">この作業空間に、提出するタスクブランチはありません。モジュールに届いている提出は、モジュールの「ブランチ」で見られます。</p>'; return; }
  if (!t || t.number !== selectedPr) { get('pr-note').hidden = true; get('pr-commits').hidden = true; return; }
  const sub = t.pull_request, open = sub?.state === 'open', draft = open && sub.draft;
  const s = WS.status || {}, reviewing = !!s.reviewing && s.reviewing_task === t.number, own = me ? t.assignees.includes(me) : !reviewing;
  // Left: looking at the submission (small). Right: what to do with it. Someone's submission being reviewed here is
  // approved or sent back; the task branch here is submitted, finished or withdrawn.
  const head = document.createElement('div'), title = document.createElement('div'), metaRow = document.createElement('div'), meta = document.createElement('div');
  const look = document.createElement('div'), act = document.createElement('div');
  head.className = 'pr-head'; title.className = 'pr-title'; metaRow.className = 'pr-meta-row'; meta.className = 'pr-meta';
  look.className = 'pr-look'; act.className = 'pr-act';
  const applies = !reviewing && accessRead && !!t.base && ECO.canTakeIn(access, t.base);
  const state = !sub ? 'none' : sub.state === 'open' ? (draft ? 'draft' : 'open') : sub.state;
  title.innerHTML = `<strong title="${esc(t.title)}">#${t.number} ${esc(t.title)}</strong><span class="pr-state ${state}">${esc(ECO.submissionText(sub))}</span>`;
  const a = t.activity || {checks: [], mergeable: ''};
  const mergeable = open ? {MERGEABLE: '取り込めます', CONFLICTING: '衝突があります（タスクブランチで最新を取り込んで解決してください）', UNKNOWN: '取り込めるか確認中'}[a.mergeable] || a.mergeable : '';
  meta.innerHTML = [`${esc(t.branch || 'task/' + t.number)}${t.base ? ` → ${esc(t.base)}` : ''}`, `担当 ${esc(t.assignees.join(', ') || 'なし')}${own ? '（自分）' : ''}`,
    `CI ${a.checks.length ? a.checks.map(c => `${esc(c.name)} ${ECO.checkMark(c)}`).join('、') : 'なし'}`, ...(mergeable ? [esc(mergeable)] : [])].join('<span class="sep">·</span>');
  look.append(prButton('diff', '差分'), prButton('comment', 'コメント'), prButton('task', 'タスク'), prButton('refresh', '更新'));
  if (reviewing) {
    act.append(prButton('review-done', '判定せずに終える'));
    const why = ECO.canTakeIn(access, t.base) ? '' : ECO.takeInNote(access, t.base);
    if (open) act.append(prButton('reject', '差し戻す', {enabled: !why, note: why}), prButton('approve', '承認して取り込む', {enabled: !draft && !why, kind: 'primary', note: draft ? '下書きの提出は承認できません' : why}));
  } else {
    // One way in: those who handle the base (its creator: a subtask's parent task branch too; admins) apply it
    // (task apply: no submission, as nobody else would take theirs in); the others submit (whether the task is closed
    // when it is taken in is chosen in the dialog) and the base's handler takes it in. Nothing until the role is read.
    if (open) act.append(prButton('withdraw', '提出を取り下げる', {kind: 'danger-text'}));
    if (applies) act.append(prButton('apply', '反映', {kind: 'primary'}));
    else if (accessRead) {
      if (draft) act.append(prButton('ready', '下書きを解除', {kind: 'primary'}));
      act.append(prButton('submit', '提出', {kind: draft ? '' : 'primary'}));
    }
  }
  head.append(title, act); metaRow.append(meta, look); tools.append(head, metaRow);
  const note = get('pr-note');
  note.hidden = !(!reviewing && s.ahead);
  note.textContent = note.hidden ? '' : `未Pushのコミット ${s.ahead}件：${applies ? '反映すると一緒に入ります' : open ? 'Pushすると提出に加わります' : '提出するとPushします'}。`;
  renderPrCommits();
  get('pr-detail').innerHTML = ECO.submissionConversation(t);
}

// The commits going into the submission, as in the log (log --not-in <base>: here, so the commits not pushed yet are
// in it too): author, date, a double-click (Enter) shows a commit's changes, the right click its menu (WS.commitMenu).
// 「すべてのログ」 opens the whole log in a window of its own (the base's commits too).
let prCommitCount = 30, prCommitsRead = 0, prCommitsShown = '';
const prCommitsView = LOG.view(get('pr-commits-view'), {dir: WS.dir, menu: (c, x, y) => WS.commitMenu(prCommitsView, c, x, y), detail: false, search: false,
  empty: '提出に入るコミットはありません（作成元と同じです）。', onMore: () => { prCommitCount += 30; loadPrCommits(); }});
get('pr-commits-view').classList.add('log-short');
get('pr-full-log').addEventListener('click', () => WS.showLog());
function renderPrCommits() {
  const t = prStatus, box = get('pr-commits');
  box.hidden = !t?.base;
  if (box.hidden) return;
  const count = t.commits?.length;
  get('pr-commits-title').textContent = `提出に入るコミット${count ? `（${count}件、新しい順）` : ''}`;
  // Read again when what it is about changed (another task, another base, other commits).
  const key = [t.number, t.base, ...(t.commits || [])].join(' ');
  if (key !== prCommitsShown) { prCommitsShown = key; loadPrCommits(); }
}
async function loadPrCommits() {
  const t = prStatus;
  if (!t?.base) return;
  const mine = ++prCommitsRead, args = ['log', '--not-in', t.base, '--count', String(prCommitCount)];
  const shown = doc => { if (mine === prCommitsRead && prStatus?.number === t.number) prCommitsView.show(doc.result, doc.result.length >= prCommitCount); };
  const doc = await ECO.query(WS.dir, args, fresh => { if (fresh.ok) shown(fresh); });
  if (doc.ok) shown(doc); else if (mine === prCommitsRead) prCommitsView.error(doc.error.message);
}

// Approve (and take in) or reject. Also used from the banner while reviewing a submission here.
WS.judge = async (approve, number) => {
  if (!number) return;
  const v = await ECO.form(approve
    ? {title: `承認して取り込む：#${number}`, intro: 'CIが終わるのを待ちます。タスクは提出のとおり閉じるか続けます。手元で確認していたなら、確認する前のブランチに戻ります。', fields: [{name: 'message', label: 'コメント（任意）', type: 'textarea'}], ok: '承認して取り込む'}
    : {title: `差し戻す：#${number}`, intro: 'タスクは作業中に戻ります。手元で確認していたなら、確認する前のブランチに戻ります。', fields: [{name: 'message', label: '直してほしいこと', type: 'textarea', required: true}], ok: '差し戻す', danger: true});
  if (!v) return;
  const doc = await WS.run(['task', approve ? 'approve' : 'reject', String(number), ...(v.message ? ['--message', v.message] : [])],
    {success: approve ? r => `#${number} を承認して取り込みました。` + (r.partial ? 'タスクは続きます。' : 'タスクを完了しました。') : `#${number} を差し戻しました。`});
  if (doc) { if (approve) ECO.workspaceKept(doc.result, number); WS.reloadFiles?.(); await WS.refreshPrs(); }
};

// Submitting the task branch here (task submit): a new submission, or again (the commits pushed, whether the task is
// closed when it is taken in, draft or not). 下書きを解除 makes a draft ready without asking.
function submitDialog(t, ready = false) {
  const sub = t.pull_request, submitted = sub?.state === 'open';
  if (ready) return WS.run(['task', 'submit', '--no-check'], {success: '下書きを解除しました。'}).then(doc => doc && WS.refreshPrs());
  const complete = submitted ? !sub.partial : true;
  return ECO.form({
    title: `提出：#${t.number}`, intro: ECO.submitOutcome(t.base, {submitted, complete}) + ECO.submissionCommits(t.commits),
    fields: [
      {name: 'complete', label: '取り込まれたらタスクを完了する', type: 'checkbox', value: complete},
      {name: 'title', label: '題名', value: t.title || '', placeholder: '空欄ならタスクの題名'},
      {name: 'draft', label: '下書きとして提出する', type: 'checkbox', value: submitted && sub.draft},
      {name: 'reviewer', label: '見てもらう人（カンマ区切り、任意）'},
      {name: 'check', label: '提出の前・後のパイプラインを走らせる（モジュール › パイプラインで当てたもの。なければ何もしません）', type: 'checkbox', value: true},
    ], ok: '提出',
    onChange: (values, formEl) => ECO.setTaskOutcome(formEl, values.complete),
    submit: async v => {
      const args = ['task', 'submit', v.complete ? '--complete' : '--partial', ...(v.title && v.title !== t.title ? ['--title', v.title] : []), ...(v.draft ? ['--draft'] : []), ...(v.reviewer ? ['--reviewer', v.reviewer] : []), ...(v.check ? [] : ['--no-check'])];
      const doc = await WS.run(args, {success: r => `${r.partial ? '中間提出' : '提出'}しました（取り込まれたら${r.partial ? '閉じずに続けます' : 'タスクを完了します'}）。`});
      if (!doc) return '提出できませんでした。';
      await WS.refreshPrs();
    },
  });
}

// Applying the task branch here without a submission (task apply): squashed onto the latest base, the task closed and
// its task branch and workspace cleaned up, as a finish; or, unticked, the task goes on (--partial: the task branch is
// made again from the latest base, the workspace stays). An open submission is closed without taking it in.
async function applyDialog(t) {
  const submitted = t.pull_request?.state === 'open';
  let conflict = null;   // stopped on a conflict with the base: offered to take the base in here and fix it (sync)
  await ECO.form({
    title: `反映：#${t.number}`,
    intro: ECO.applyOutcome(t.base) + `<p>${submitted ? '開いている提出は取り込まずに閉じます。' : ''}衝突したら何もせずに止まります。</p>` + ECO.submissionCommits(t.commits),
    fields: [
      {name: 'complete', label: '反映したらタスクを完了する', type: 'checkbox', value: true},
      {name: 'subject', label: 'コミットの件名', value: t.title || '', placeholder: '空欄ならタスクの題名'},
      {name: 'pipelines', label: '取り込みの前のパイプラインを走らせる（モジュール › パイプラインで当てたもの。なければ何もしません）', type: 'checkbox', value: true},
    ], ok: '反映',
    onChange: (values, formEl) => ECO.setTaskOutcome(formEl, values.complete),
    submit: async v => {
      const args = ['task', 'apply', String(t.number), ...(v.complete ? [] : ['--partial']), ...(v.subject && v.subject !== t.title ? ['--subject', v.subject] : []), ...(v.pipelines ? [] : ['--no-pipelines'])];
      const tried = await WS.cli(args);
      if (!tried.ok && tried.error?.code === 'merge_conflict') { conflict = tried.error; return; }
      if (!tried.ok) { ECO.showError(tried); return '反映できませんでした。'; }
      const r = tried.result;
      ECO.toast(r.partial ? (!r.commit ? `#${t.number} の変更はすでに ${r.base} に入っていました（タスクは続きます）。` : `#${t.number} を ${r.base} へ反映しました（タスクは続きます）。`)
        : !r.commit ? `#${t.number} の変更はすでに ${r.base} に入っていたので、入れずに完了しました。` : `#${t.number} を ${r.base} へ反映し、完了しました。`);
      for (const notice of tried.notices || []) ECO.toast('お知らせ：' + notice, 'info', 9000);
      ECO.workspaceKept(tried.result, t.number); await WS.refresh(); WS.reloadFiles?.(); await WS.refreshPrs();
    },
  });
  if (!conflict) return;
  const files = (conflict.details || []).join('、');
  if (!await ECO.confirm({title: `反映：#${t.number}`, ok: '取り込んで直す', message: `${t.base} と衝突するので、反映しませんでした（何も変えていません）。${files ? `\n衝突するファイル：${files}` : ''}\n`
    + `このタスクブランチへ ${t.base} の最新を取り込みます。衝突したファイルを直して「取り込みを完了」を押してから、もう一度「反映」してください。`})) return;
  await WS.run(['sync'], {success: '取り込みました（衝突しませんでした）。もう一度「反映」できます。'});
  WS.reloadFiles?.(); await WS.refreshPrs();
}

async function prAction(action) {
  const t = prStatus, n = String(t.number);
  const after = async doc => { if (doc) await WS.refreshPrs(); };
  switch (action) {
    case 'refresh': return loadPr(t.number);
    case 'diff': return WS.inTortoiseGit(['task', 'diff', n], async () => { const doc = await WS.cli(['task', 'diff', n]); return doc.ok ? ECO.output(`#${n} の差分`, doc.result || '差分はありません。', {diff: true}) : ECO.showError(doc); });
    case 'comment': return ECO.form({title: `#${n} にコメント`, fields: [{name: 'message', label: '内容', type: 'textarea', required: true}], ok: 'コメントする',
      submit: async v => { const doc = await WS.run(['task', 'comment', n, '--message', v.message], {success: 'コメントしました。', refresh: false}); if (!doc) return 'コメントできませんでした。'; await after(doc); }});
    case 'approve': return WS.judge(true, t.number);
    case 'reject': return WS.judge(false, t.number);
    case 'submit': return submitDialog(t);
    case 'apply': return applyDialog(t);
    case 'ready': return submitDialog(t, true);
    case 'withdraw': return after(await WS.run(['task', 'withdraw', n], {success: '提出を取り下げました。', confirm: `#${n} の提出を取り下げて、作業中に戻します。タスクブランチは残るので、あとでもう一度提出できます。`, title: '提出を取り下げる', refresh: false}));
    case 'local-review': {   // 判定せずに終える (the button for review-done)
      const doc = await WS.run(['task', 'review', '--done'], {success: '確認を終え、確認用の作業空間を消しました。'});
      await after(doc); if (doc) WS.reloadFiles?.(); return;
    }
    case 'task': if (window.parent !== window) window.parent.postMessage({type: 'show-task', n: t.number}, location.origin); return;
  }
}
get('pr-tools').addEventListener('click', e => { const b = e.target.closest('[data-pr-action]'); if (b && !b.disabled && prStatus) prAction(b.dataset.prAction); });
WS.refreshPrs();
// The task here comes and goes with the status (switched, reviewing, finished): the tab follows it.
// A commit or a Push changes the commits to submit (and the count): read it again when the unpushed count changes.
let seenAhead = null;
WS.onRefresh(() => {
  const ahead = WS.status?.ahead ?? null, moved = seenAhead !== null && ahead !== seenAhead;
  seenAhead = ahead;
  if (hereTask() !== selectedPr || moved) WS.refreshPrs();
  else if (prStatus) renderPrDetail();
});
