'use strict';
// The submission of this workspace: the task branch placed here (listed before it is submitted: it is on GitHub from
// task start, and Push sends its commits), or the submission being reviewed here. Status (reviews, comments, CI),
// diff, submit, finish, withdraw; approve/reject while reviewing. The submissions of the whole module are in the
// module's ブランチ page. Every number is a task number; the pull request behind a submission is the CLI's business.
let selectedPr = 0, prStatus = null, me = '';
ECO.info().then(info => { me = info.me || ''; });
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
  if (!selectedPr) { get('pr-detail').innerHTML = '<p class="muted">この作業空間に、提出するタスクブランチはありません。モジュールに届いている提出は「ブランチ」で見られます。</p>'; return; }
  if (!t || t.number !== selectedPr) return;
  const sub = t.pull_request, open = sub?.state === 'open', draft = open && sub.draft;
  const s = WS.status || {}, reviewing = !!s.reviewing && s.reviewing_task === t.number, own = me ? t.assignees.includes(me) : !reviewing;
  // Left: looking at the submission (small). Right: what to do with it. Someone's submission being reviewed here is
  // approved or sent back; the task branch here is submitted, finished or withdrawn.
  const head = document.createElement('div'), title = document.createElement('div'), metaRow = document.createElement('div'), meta = document.createElement('div');
  const look = document.createElement('div'), act = document.createElement('div');
  head.className = 'pr-head'; title.className = 'pr-title'; metaRow.className = 'pr-meta-row'; meta.className = 'pr-meta';
  look.className = 'pr-look'; act.className = 'pr-act';
  const state = !sub ? 'none' : sub.state === 'open' ? (draft ? 'draft' : 'open') : sub.state;
  title.innerHTML = `<strong title="${esc(t.title)}">#${t.number} ${esc(t.title)}</strong><span class="pr-state ${state}">${esc(ECO.submissionText(sub))}</span>`;
  const a = t.activity || {checks: [], mergeable: ''};
  const mergeable = open ? {MERGEABLE: '取り込めます', CONFLICTING: '衝突があります（タスクブランチで最新を取り込んで解決してください）', UNKNOWN: '取り込めるか確認中'}[a.mergeable] || a.mergeable : '';
  meta.innerHTML = [`task/${t.number}${t.base ? ` → ${esc(t.base)}` : ''}`, `担当 ${esc(t.assignees.join(', ') || 'なし')}${own ? '（自分）' : ''}`,
    `CI ${a.checks.length ? a.checks.map(c => `${esc(c.name)} ${ECO.checkMark(c)}`).join('、') : 'なし'}`, ...(mergeable ? [esc(mergeable)] : [])].join('<span class="sep">·</span>');
  look.append(prButton('diff', '差分'), prButton('comment', 'コメント'), prButton('task', 'タスク'), prButton('refresh', '更新'));
  if (reviewing) {
    act.append(prButton('review-done', '判定せずに戻る'));
    if (open) act.append(prButton('reject', '差し戻す'), prButton('approve', '承認して完了', {enabled: !draft, kind: 'primary', note: draft ? '下書きの提出は承認できません' : ''}));
  } else {
    if (open) act.append(prButton('withdraw', '取り下げ', {kind: 'quiet-danger'}));
    if (!open) act.append(prButton('submit', '提出', {kind: 'primary'}));
    if (draft) act.append(prButton('ready', '下書きを解除', {kind: 'primary'}));
    act.append(prButton('finish', '完了', {enabled: !draft, kind: open && !draft ? 'primary' : '', note: draft ? '下書きの提出は完了できません。先に下書きを解除します' : ''}));
  }
  head.append(title, act); metaRow.append(meta, look); tools.append(head, metaRow);
  const note = !reviewing && s.ahead ? `<p class="pr-note">未Pushのコミット ${s.ahead}件：${open ? 'Pushすると提出に加わります' : '提出するとPushします'}。</p>` : '';
  const entries = ECO.submissionDetail(t, {own}).split('</dl>').slice(1).join('</dl>');   // the commits and the conversation
  get('pr-detail').innerHTML = note + entries;
}

// Approve (and finish) or reject. Also used from the banner while reviewing a submission here.
WS.judge = async (approve, number) => {
  if (!number) return;
  const v = await ECO.form(approve
    ? {title: `承認して完了：#${number}`, intro: '提出を承認して完了します（CIが終わるのを待って取り込み、タスクを閉じます）。手元で確認していたなら、確認する前のブランチに戻ります。', fields: [{name: 'message', label: 'コメント（任意）', type: 'textarea'}], ok: '承認して完了'}
    : {title: `差し戻す：#${number}`, intro: '直してほしいことを書いて差し戻します。タスクは作業中に戻ります。手元で確認していたなら、確認する前のブランチに戻ります。', fields: [{name: 'message', label: '直してほしいこと', type: 'textarea', required: true}], ok: '差し戻す', danger: true});
  if (!v) return;
  const doc = await WS.run(['task', approve ? 'approve' : 'reject', String(number), ...(v.message ? ['--message', v.message] : [])],
    {success: approve ? `#${number} を承認して完了しました。` : `#${number} を差し戻しました。`});
  if (doc) { WS.reloadFiles?.(); await WS.refreshPrs(); }
};

// Submitting the task branch here (task submit), or making its draft submission ready.
function submitDialog(t) {
  if (t.pull_request?.state === 'open') return WS.run(['task', 'submit', '--no-check'], {success: '下書きを解除しました。'}).then(doc => doc && WS.refreshPrs());
  return ECO.form({
    title: `提出：#${t.number}`, intro: 'ビルド・テストなどで確認してから、タスクブランチをPushして作成元' + (t.base ? `（${esc(t.base)}）` : '') + 'へ提出します。' + ECO.submissionCommits(t.commits),
    fields: [
      {name: 'title', label: '題名', value: t.title || '', placeholder: '空欄ならタスクの題名'},
      {name: 'draft', label: '下書きとして提出する（準備ができたら「下書きを解除」）', type: 'checkbox'},
      {name: 'reviewer', label: '見てもらう人（カンマ区切り、任意）'},
      {name: 'check', label: '提出前にビルド・テストを確認する', type: 'checkbox', value: true},
    ], ok: '提出',
    submit: async v => {
      const args = ['task', 'submit', ...(v.title && v.title !== t.title ? ['--title', v.title] : []), ...(v.draft ? ['--draft'] : []), ...(v.reviewer ? ['--reviewer', v.reviewer] : []), ...(v.check ? [] : ['--no-check'])];
      const doc = await WS.run(args, {success: r => `${r.partial ? '中間提出' : '提出'}しました。`});
      if (!doc) return '提出できませんでした。';
      await WS.refreshPrs();
    },
  });
}

async function prAction(action) {
  const t = prStatus, n = String(t.number);
  const after = async doc => { if (doc) await WS.refreshPrs(); };
  switch (action) {
    case 'refresh': return loadPr(t.number);
    case 'diff': { const doc = await WS.cli(['task', 'diff', n]); return doc.ok ? ECO.output(`#${n} の差分`, doc.result || '差分はありません。', {diff: true}) : ECO.showError(doc); }
    case 'comment': return ECO.form({title: `#${n} にコメント`, fields: [{name: 'message', label: '内容', type: 'textarea', required: true}], ok: 'コメントする',
      submit: async v => { const doc = await WS.run(['task', 'comment', n, '--message', v.message], {success: 'コメントしました。', refresh: false}); if (!doc) return 'コメントできませんでした。'; await after(doc); }});
    case 'approve': return WS.judge(true, t.number);
    case 'reject': return WS.judge(false, t.number);
    case 'submit': case 'ready': return submitDialog(t);
    case 'finish': {
      const v = await ECO.form({title: `完了：#${n}`, intro: (t.pull_request?.state === 'open' ? '' : '提出していないので、提出してから取り込みます。') + 'CIを待って取り込み、タスクを閉じてタスクブランチを片付けます。',
        fields: [{name: 'subject', label: '取り込むコミットの件名（空ならタスクの題名）'}, {name: 'ignore', label: 'CIが失敗していても完了する', type: 'checkbox'}, {name: 'partial', label: 'タスクを閉じずに続ける（取り込んだ後、タスクブランチを作り直して作業を続ける）', type: 'checkbox'}], ok: '完了'});
      if (!v) return;
      const doc = await WS.run(['task', 'finish', n, ...(v.subject ? ['--subject', v.subject] : []), ...(v.ignore ? ['--ignore-checks'] : []), ...(v.partial ? ['--partial'] : [])], {success: r => r.partial ? '中間提出を取り込みました。' : `#${n} を完了しました。`});
      await after(doc); if (doc) WS.reloadFiles?.(); return;
    }
    case 'withdraw': return after(await WS.run(['task', 'withdraw', n], {success: '提出を取り下げました。', confirm: `#${n} の提出を取り下げて、作業中に戻します。タスクブランチは残るので、あとでもう一度提出できます。`, title: '提出を取り下げる', refresh: false}));
    case 'local-review': {   // 判定せずに戻る (the button for review-done)
      const doc = await WS.run(['task', 'review', '--done'], {success: '確認を終えて戻りました。'});
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
