'use strict';
// Submissions of the module (task list --submitted): status (reviews, comments, CI), diff, local review, approve/reject,
// finish, withdraw. Every number is a task number; the pull request behind a submission is the CLI's business.
// The task branch placed here is listed too, before it is submitted (it is on GitHub from task start, and Push sends
// its commits): submitting and finishing it are done here, the Push tab only pushes.
let submissions = [], prs = [], selectedPr = 0, prStatus = null, me = '';
ECO.info().then(info => { me = info.me || ''; });
const SUBMISSION = ECO.submissionText, prButton = ECO.submissionButton;

// The task branch here, while it is worked on (not finished, not reviewing someone's submission).
const currentTask = () => { const s = WS.status; return s && s.task && !s.reviewing && !s.finished && !s.upstream_gone ? s.task : 0; };
function listed() {
  const n = currentTask();
  if (!n || get('pr-all').checked || submissions.some(t => t.number === n)) return submissions;
  const task = WS.task?.number === n ? WS.task : null;
  return [{number: n, title: task?.title || '', assignees: task?.assignees || [], submission: null}, ...submissions];
}
WS.refreshPrs = async select => {
  // Cached (ECO.query): the kept list shows at once; a newer one replaces it when it comes.
  const which = get('pr-all').checked ? '--to-review' : '--submitted';
  const [doc] = await Promise.all([ECO.query(WS.dir, ['task', 'list', which], fresh => {
    if ((get('pr-all').checked ? '--to-review' : '--submitted') !== which) return;
    submissions = fresh.result; prs = listed(); renderPrList();
  }), WS.ready]);
  if (!doc.ok) { get('pr-list').innerHTML = `<p class="muted">${esc(doc.error.message)}</p>`; return; }
  submissions = doc.result; prs = listed();
  if (select) selectedPr = select;
  if (!selectedPr && currentTask()) selectedPr = currentTask();
  if (selectedPr && !prs.some(t => t.number === selectedPr)) selectedPr = 0;
  renderPrList();
  if (selectedPr) await loadPr(selectedPr); else { prStatus = null; renderPrDetail(); }
};
function renderPrList() {
  WS.setTabCount?.('prs', prs.length);
  get('pr-list').innerHTML = prs.map(t => `<button type="button" data-select-pr="${t.number}" aria-pressed="${t.number === selectedPr}"><span>#${t.number} ${esc(t.title)}${t.number === currentTask() ? ' <small class="muted">（ここのタスクブランチ）</small>' : ''}</span><span class="pr-state">${esc(SUBMISSION(t.submission))}${t.assignees.length ? ' · ' + esc(t.assignees.join(', ')) : ''}</span></button>`).join('')
    || `<p class="muted">${get('pr-all').checked ? '見るように頼まれた提出はありません。' : '提出中のタスクはありません。'}</p>`;
}
async function loadPr(number) {
  selectedPr = number; renderPrList();
  get('pr-detail').innerHTML = ECO.loading();
  const doc = await ECO.query(WS.dir, ['task', 'status', String(number)], fresh => {
    if (selectedPr === number) { prStatus = fresh.result; renderPrDetail(); }
  });
  prStatus = doc.ok ? doc.result : null;
  if (!doc.ok) get('pr-detail').innerHTML = `<p class="muted">${esc(doc.error.message)}</p>`;
  else renderPrDetail();
}
function renderPrDetail() {
  const t = prStatus, tools = get('pr-tools');
  tools.replaceChildren();
  if (!t || t.number !== selectedPr) { get('pr-detail').innerHTML = ''; return; }
  const sub = t.pull_request, open = sub?.state === 'open', own = me ? t.assignees.includes(me) : t.number === currentTask();
  const s = WS.status || {}, reviewingThis = !!s.reviewing && s.reviewing_task === t.number, here = t.number === currentTask();
  const draft = open && sub.draft;
  // Left: looking at the submission (small). Right: what to do with it — only the actions that apply to this one:
  // one's own (or the one here) is submitted and finished; someone else's is checked, approved or sent back.
  const look = document.createElement('div'), act = document.createElement('div');
  look.className = 'pr-look'; act.className = 'pr-act';
  look.append(prButton('diff', '差分'), prButton('comment', 'コメント'), prButton('task', 'タスク'), prButton('refresh', '更新'));
  if (reviewingThis) act.append(prButton('review-done', '判定せずに戻る'));
  if (open && !own) {
    if (!reviewingThis) act.append(prButton('local-review', '手元で確認'));
    act.append(prButton('reject', '差し戻す'), prButton('approve', '承認して完了', {enabled: !draft, kind: 'primary', note: draft ? '下書きの提出は承認できません' : ''}));
  } else if (own || here) {
    if (open) act.append(prButton('withdraw', '取り下げ', {kind: 'quiet-danger'}));
    if (here && !open) act.append(prButton('submit', '提出', {kind: 'primary'}));
    if (draft) act.append(prButton(here ? 'ready' : 'submit', '下書きを解除', {enabled: here, kind: 'primary', note: here ? '' : 'このタスクブランチの作業空間で解除します'}));
    if (open || here) act.append(prButton('finish', '完了', {enabled: !draft, kind: open && !draft ? 'primary' : '', note: draft ? '下書きの提出は完了できません。先に下書きを解除します' : ''}));
  }
  tools.append(look, act);
  get('pr-detail').innerHTML = ECO.submissionDetail(t, {own,
    note: here && s.ahead ? `（未Pushのコミット ${s.ahead}件。${open ? 'Pushすると提出に加わります' : '提出するとPushします'}）` : ''});
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
  if (t.pull_request?.state === 'open') return WS.run(['task', 'submit', '--no-check'], {success: '下書きを解除しました。'}).then(doc => doc && WS.refreshPrs(t.number));
  return ECO.form({
    title: `提出：#${t.number}`, intro: 'ビルド・テストなどで確認してから、タスクブランチをPushして作成元' + (t.base ? `（${esc(t.base)}）` : '') + 'へ提出します。',
    fields: [
      {name: 'title', label: '題名', value: t.title || '', placeholder: '空欄ならタスクの題名'},
      {name: 'draft', label: '下書きとして提出する（準備ができたら「下書きを解除」）', type: 'checkbox'},
      {name: 'partial', label: '中間提出（取り込んでもタスクを閉じず、タスクブランチを作り直して続ける）', type: 'checkbox'},
      {name: 'reviewer', label: '見てもらう人（カンマ区切り、任意）'},
      {name: 'check', label: '提出前にビルド・テストを確認する', type: 'checkbox', value: true},
    ], ok: '提出',
    submit: async v => {
      const args = ['task', 'submit', ...(v.title && v.title !== t.title ? ['--title', v.title] : []), ...(v.draft ? ['--draft'] : []), ...(v.partial ? ['--partial'] : []), ...(v.reviewer ? ['--reviewer', v.reviewer] : []), ...(v.check ? [] : ['--no-check'])];
      const doc = await WS.run(args, {success: r => `${r.partial ? '中間提出' : '提出'}しました。`});
      if (!doc) return '提出できませんでした。';
      await WS.refreshPrs(t.number);
    },
  });
}

async function prAction(action) {
  const t = prStatus, n = String(t.number);
  const after = async doc => { if (doc) await WS.refreshPrs(t.number); };
  switch (action) {
    case 'refresh': return loadPr(t.number);
    case 'diff': { const doc = await WS.cli(['task', 'diff', n]); return doc.ok ? ECO.output(`#${n} の差分`, doc.result || '差分はありません。', {diff: true}) : ECO.showError(doc); }
    case 'comment': return ECO.form({title: `#${n} にコメント`, fields: [{name: 'message', label: '内容', type: 'textarea', required: true}], ok: 'コメントする',
      submit: async v => { const doc = await WS.run(['task', 'comment', n, '--message', v.message], {success: 'コメントしました。', refresh: false}); if (!doc) return 'コメントできませんでした。'; await after(doc); }});
    case 'approve': return WS.judge(true, t.number);
    case 'reject': return WS.judge(false, t.number);
    case 'submit': case 'ready': return submitDialog(t);
    case 'finish': {
      const v = await ECO.form({title: `完了：#${n}`, intro: (t.pull_request?.state === 'open' ? '' : '提出していないので、提出してから取り込みます。') + 'CIを待って取り込み、タスクを閉じてタスクブランチを片付けます（中間提出なら、取り込んだ後にタスクブランチを作り直して続けます）。',
        fields: [{name: 'subject', label: '取り込むコミットの件名（空ならタスクの題名）'}, {name: 'ignore', label: 'CIが失敗していても完了する', type: 'checkbox'}], ok: '完了'});
      if (!v) return;
      const doc = await WS.run(['task', 'finish', n, ...(v.subject ? ['--subject', v.subject] : []), ...(v.ignore ? ['--ignore-checks'] : [])], {success: r => r.partial ? '中間提出を取り込みました。' : `#${n} を完了しました。`});
      await after(doc); if (doc) WS.reloadFiles?.(); return;
    }
    case 'withdraw': return after(await WS.run(['task', 'withdraw', n], {success: '提出を取り下げました。', confirm: `#${n} の提出を取り下げて、作業中に戻します。タスクブランチは残るので、あとでもう一度提出できます。`, title: '提出を取り下げる', refresh: false}));
    case 'local-review': {
      const done = !!WS.status?.reviewing && WS.status.reviewing_task === t.number;
      const doc = await WS.run(['task', 'review', ...(done ? ['--done'] : [n])], {success: done ? '確認を終えて戻りました。' : `#${n} の提出を手元に取り出しました。ビルド・テスト・実行で確認できます。`});
      await after(doc); if (doc) WS.reloadFiles?.(); return;
    }
    case 'task': if (window.parent !== window) window.parent.postMessage({type: 'show-task', n: t.number}, location.origin); return;
  }
}
get('pr-list').addEventListener('click', e => { const b = e.target.closest('[data-select-pr]'); if (b) loadPr(Number(b.dataset.selectPr)); });
get('pr-tools').addEventListener('click', e => { const b = e.target.closest('[data-pr-action]'); if (b && !b.disabled && prStatus) prAction(b.dataset.prAction); });
get('pr-all').addEventListener('change', () => WS.refreshPrs());
WS.refreshPrs();
// The task branch here comes and goes with the status (switched, finished, its title read): the list follows it.
WS.taskLoaded = () => { prs = listed(); renderPrList(); };
let shownCurrent = -1;
WS.onRefresh(() => {
  const n = currentTask();
  prs = listed(); renderPrList();
  if (n !== shownCurrent) { shownCurrent = n; if (n && !selectedPr) loadPr(n); }
  else if (prStatus && prStatus.number === n) renderPrDetail();
});

// Right-click a submission in the list: the same actions as the buttons under the list.
get('pr-list').addEventListener('contextmenu', async e => {
  const b = e.target.closest('[data-select-pr]'); if (!b) return;
  e.preventDefault();
  const x = e.clientX, y = e.clientY, number = Number(b.dataset.selectPr);
  if (!prStatus || prStatus.number !== number) await loadPr(number);
  const items = [...get('pr-tools').querySelectorAll('[data-pr-action]')].map(t => [t.textContent, () => prAction(t.dataset.prAction), !t.disabled]);
  if (items.length) ECO.menu(items, x, y);
});
