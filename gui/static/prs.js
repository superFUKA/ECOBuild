'use strict';
// Submissions of the module (task list --submitted): status (reviews, comments, CI), diff, local review, approve/reject,
// finish, withdraw. Every number is a task number; the pull request behind a submission is the CLI's business.
let prs = [], selectedPr = 0, prStatus = null, me = '';
ECO.info().then(info => { me = info.me || ''; });
const SUBMISSION = s => !s ? 'なし' : s.state === 'merged' ? (s.partial ? '中間提出は取り込み済み' : '取り込み済み') : s.state === 'closed' ? '取り下げ済み' : `${s.draft ? '下書きの' : ''}${s.partial ? '中間提出' : '提出'}中`;

WS.refreshPrs = async select => {
  const [doc] = await Promise.all([WS.cli(['task', 'list', get('pr-all').checked ? '--to-review' : '--submitted'], {quiet: true}), WS.ready]);
  if (!doc.ok) { get('pr-list').innerHTML = `<p class="muted">${esc(doc.error.message)}</p>`; return; }
  prs = doc.result;
  if (select) selectedPr = select;
  if (!selectedPr && WS.status?.workspace && WS.status?.pull_request?.state === 'open') selectedPr = WS.status.workspace;
  if (selectedPr && !prs.some(t => t.number === selectedPr)) selectedPr = 0;
  renderPrList();
  if (selectedPr) await loadPr(selectedPr); else { prStatus = null; renderPrDetail(); }
};
function renderPrList() {
  get('pr-list').innerHTML = prs.map(t => `<button type="button" data-select-pr="${t.number}" aria-pressed="${t.number === selectedPr}"><span>#${t.number} ${esc(t.title)}</span><span class="pr-state">${esc(SUBMISSION(t.submission))}${t.assignees.length ? ' · ' + esc(t.assignees.join(', ')) : ''}</span></button>`).join('')
    || `<p class="muted">${get('pr-all').checked ? '見るように頼まれた提出はありません。' : '提出中のタスクはありません。'}</p>`;
}
async function loadPr(number) {
  selectedPr = number; renderPrList();
  get('pr-detail').innerHTML = ECO.loading();
  const doc = await WS.cli(['task', 'status', String(number)], {quiet: true});
  prStatus = doc.ok ? doc.result : null;
  if (!doc.ok) get('pr-detail').innerHTML = `<p class="muted">${esc(doc.error.message)}</p>`;
  else renderPrDetail();
}
const checkMark = c => c.status !== 'completed' ? '<span class="check-wait">実行中</span>' : ['success', 'skipped', 'neutral'].includes(c.conclusion) ? '<span class="check-ok">成功</span>' : `<span class="check-bad">${esc(c.conclusion || '失敗')}</span>`;
function renderPrDetail() {
  const t = prStatus, tools = get('pr-tools');
  tools.replaceChildren();
  if (!t || t.number !== selectedPr) { get('pr-detail').innerHTML = ''; return; }
  const sub = t.pull_request, open = sub?.state === 'open', own = me && t.assignees.includes(me);
  const s = WS.status || {}, reviewingThis = !!s.reviewing && s.reviewing_task === t.number;
  const buttons = [
    ['refresh', '状態を更新'], ['diff', '差分'], ['comment', 'コメント'],
    ['local-review', reviewingThis ? '判定せずに戻る' : '手元で確認', reviewingThis || (open && !own)],
    ['approve', '承認して完了', open && !own && !sub.draft], ['reject', '差し戻す', open && !own],
    ['finish', '完了する', open && !sub.draft], ['withdraw', '取り下げる', open],
    ['task', 'タスクを見る'],
  ];
  for (const [action, label, enabled = true] of buttons) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.disabled = !enabled; b.dataset.prAction = action; tools.append(b);
  }
  const a = t.activity || {reviews: [], comments: [], checks: [], mergeable: ''};
  const mergeable = {MERGEABLE: '取り込めます', CONFLICTING: '衝突があります（作業空間で最新を取り込んで解決してください）', UNKNOWN: '確認中'}[a.mergeable] || a.mergeable;
  get('pr-detail').innerHTML = `<dl>
      <dt>タスク</dt><dd><strong>#${t.number} ${esc(t.title)}</strong></dd>
      <dt>提出</dt><dd>${esc(SUBMISSION(sub))}${open ? ' · ' + esc(mergeable) : ''}</dd>
      <dt>作業空間</dt><dd>task/${t.number}${t.base ? ` → ${esc(t.base)}` : ''}</dd>
      <dt>担当者</dt><dd>${esc(t.assignees.join(', ') || 'なし')}${own ? '（自分）' : ''}</dd>
      <dt>CI</dt><dd>${a.checks.length ? a.checks.map(c => `${esc(c.name)}：${checkMark(c)}`).join('<br>') : 'なし'}</dd>
      ${sub ? `<dt>URL</dt><dd>${esc(sub.url)}</dd>` : ''}</dl>
    ${a.reviews.map(r => `<div class="entry"><b>${esc(r.author)}</b> · ${esc({APPROVED: '承認', CHANGES_REQUESTED: '差し戻し', COMMENTED: 'コメント'}[r.state] || r.state)}${r.body ? '\n' + esc(r.body) : ''}</div>`).join('')}
    ${a.comments.map(c => `<div class="entry"><b>${esc(c.author)}</b>\n${esc(c.body)}</div>`).join('')}
    ${(t.comments || []).map(c => `<div class="entry"><b>${esc(c.author)}</b>（タスク）\n${esc(c.body)}</div>`).join('')}`;
}

// Approve (and finish) or reject. Also used from the banner while reviewing a submission here.
WS.judge = async (approve, number) => {
  if (!number) return;
  const v = await ECO.form(approve
    ? {title: `承認して完了：#${number}`, intro: '提出を承認し、そのまま完了します（CIを待って取り込み、タスクを閉じます）。確認中なら、確認の前の場所へ戻ります。', fields: [{name: 'message', label: 'コメント（任意）', type: 'textarea'}], ok: '承認して完了'}
    : {title: `差し戻す：#${number}`, intro: '直してほしいことを書いて差し戻します。タスクは作業中に戻ります。確認中なら、確認の前の場所へ戻ります。', fields: [{name: 'message', label: '直してほしいこと', type: 'textarea', required: true}], ok: '差し戻す', danger: true});
  if (!v) return;
  const doc = await WS.run(['task', approve ? 'approve' : 'reject', String(number), ...(v.message ? ['--message', v.message] : [])],
    {success: approve ? `#${number} を承認して完了しました。` : `#${number} を差し戻しました。`});
  if (doc) { WS.reloadFiles?.(); await WS.refreshPrs(); }
};

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
    case 'finish': {
      const v = await ECO.form({title: `完了する：#${n}`, intro: 'CIを待って取り込み、タスクを閉じて作業空間を片付けます（中間提出なら、取り込んだ後に作業空間を作り直して続けます）。',
        fields: [{name: 'subject', label: '取り込むコミットの件名（空ならタスクの題名）'}, {name: 'ignore', label: 'CIが失敗していても完了する', type: 'checkbox'}], ok: '完了する'});
      if (!v) return;
      const doc = await WS.run(['task', 'finish', n, ...(v.subject ? ['--subject', v.subject] : []), ...(v.ignore ? ['--ignore-checks'] : [])], {success: r => r.partial ? '中間提出を取り込みました。' : `#${n} を完了しました。`});
      await after(doc); if (doc) WS.reloadFiles?.(); return;
    }
    case 'withdraw': return after(await WS.run(['task', 'withdraw', n], {success: '提出を取り下げました。', confirm: `#${n} の提出を取り下げて作業中に戻します（作業空間はそのまま。もう一度提出できます）。`, title: '提出を取り下げる', refresh: false}));
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

// Right-click a submission in the list: the same actions as the buttons under the list.
get('pr-list').addEventListener('contextmenu', async e => {
  const b = e.target.closest('[data-select-pr]'); if (!b) return;
  e.preventDefault();
  const x = e.clientX, y = e.clientY, number = Number(b.dataset.selectPr);
  if (!prStatus || prStatus.number !== number) await loadPr(number);
  const items = [...get('pr-tools').querySelectorAll('[data-pr-action]')].map(t => [t.textContent, () => prAction(t.dataset.prAction), !t.disabled]);
  if (items.length) ECO.menu(items, x, y);
});
