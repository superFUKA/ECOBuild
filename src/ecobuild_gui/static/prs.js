'use strict';
// Pull requests of the module: list, status (reviews, comments, CI), edit, review, merge, local review, revert.
let prs = [], selectedPr = 0, prStatus = null, me = '';
ECO.info().then(info => { me = info.me || ''; });
const PR_STATE = {open: '開いている', closed: '閉じた', merged: 'マージ済み', OPEN: '開いている', CLOSED: '閉じた', MERGED: 'マージ済み'};
const prState = pr => pr.draft && pr.state.toLowerCase() === 'open' ? '下書き' : PR_STATE[pr.state] || pr.state;

WS.refreshPrs = async select => {
  const doc = await WS.cli(['pr', 'list', ...(get('pr-all').checked ? ['--all'] : [])], {quiet: true});
  if (!doc.ok) { get('pr-list').innerHTML = `<p class="muted">${esc(doc.error.message)}</p>`; return; }
  prs = doc.result;
  if (select) selectedPr = select;
  if (!selectedPr && WS.status?.pull_request) selectedPr = WS.status.pull_request.number;
  renderPrList();
  if (selectedPr) await loadPr(selectedPr); else renderPrDetail();
};
function renderPrList() {
  get('pr-list').innerHTML = prs.map(pr => `<button type="button" data-select-pr="${pr.number}" aria-pressed="${pr.number === selectedPr}"><span>#${pr.number} ${esc(pr.title)}</span><span class="pr-state">${esc(pr.head)} → ${esc(pr.base)} · ${esc(prState(pr))}${pr.author ? ' · ' + esc(pr.author) : ''}</span></button>`).join('') || '<p class="muted">プルリクエストはありません。</p>';
}
async function loadPr(number) {
  selectedPr = number; renderPrList();
  get('pr-detail').innerHTML = ECO.loading();
  const doc = await WS.cli(['pr', 'status', String(number)], {quiet: true});
  prStatus = doc.ok ? doc.result : null;
  if (!doc.ok) get('pr-detail').innerHTML = `<p class="muted">${esc(doc.error.message)}</p>`;
  else renderPrDetail();
}
const checkMark = c => c.status !== 'completed' ? '<span class="check-wait">実行中</span>' : ['success', 'skipped', 'neutral'].includes(c.conclusion) ? '<span class="check-ok">成功</span>' : `<span class="check-bad">${esc(c.conclusion || '失敗')}</span>`;
function renderPrDetail() {
  const pr = prStatus, tools = get('pr-tools');
  tools.replaceChildren();
  if (!pr || pr.number !== selectedPr) { get('pr-detail').innerHTML = ''; return; }
  const state = pr.state.toLowerCase(), open = state === 'open', merged = state === 'merged', own = me && pr.author === me;
  const s = WS.status || {}, reviewingThis = s.reviewing === pr.number, workspacePr = pr.head.startsWith('task/');
  const buttons = [
    ['refresh', '状態を更新'], ['diff', '差分'], ['edit', '編集', !merged], ['comment', 'コメント'],
    ['review', 'レビュー', open && !own], [pr.draft ? 'ready' : 'draft', pr.draft ? '下書きを解除' : '下書きに戻す', open],
    [state === 'closed' ? 'reopen' : 'close', state === 'closed' ? '開き直す' : '閉じる', !merged],
    ['merge', 'マージ', open && !pr.draft], ['local-review', reviewingThis ? '手元の確認を終える' : '手元で確認', reviewingThis || (open && !own)],
    ['revert', 'マージを取り消す', merged && workspacePr], ['task', 'タスクを見る', !!pr.task],
  ];
  for (const [action, label, enabled = true] of buttons) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.disabled = !enabled; b.dataset.prAction = action; tools.append(b);
  }
  const a = pr.activity || {reviews: [], comments: [], checks: [], mergeable: ''};
  const mergeable = {MERGEABLE: 'マージできます', CONFLICTING: '衝突があります（作業空間で最新を取り込んで解決）', UNKNOWN: '確認中'}[a.mergeable] || a.mergeable;
  get('pr-detail').innerHTML = `<dl>
      <dt>PR</dt><dd><strong>#${pr.number} ${esc(pr.title)}</strong></dd>
      <dt>状態</dt><dd>${esc(prState(pr))}${open ? ' · ' + esc(mergeable) : ''}</dd>
      <dt>向き</dt><dd>${esc(pr.head)} → ${esc(pr.base)}</dd>
      <dt>作成者</dt><dd>${esc(pr.author)}${own ? '（自分）' : ''}</dd>
      ${pr.task ? `<dt>タスク</dt><dd>#${pr.task}</dd>` : ''}
      <dt>CI</dt><dd>${a.checks.length ? a.checks.map(c => `${esc(c.name)}：${checkMark(c)}`).join('<br>') : 'なし'}</dd>
      <dt>URL</dt><dd>${esc(pr.url)}</dd></dl>
    ${pr.body ? `<div class="pr-body">${esc(pr.body)}</div>` : ''}
    ${a.reviews.map(r => `<div class="entry"><b>${esc(r.author)}</b> · ${esc({APPROVED: '承認', CHANGES_REQUESTED: '修正の依頼', COMMENTED: 'コメント'}[r.state] || r.state)}${r.body ? '\n' + esc(r.body) : ''}</div>`).join('')}
    ${a.comments.map(c => `<div class="entry"><b>${esc(c.author)}</b>\n${esc(c.body)}</div>`).join('')}`;
}

async function prAction(action) {
  const pr = prStatus, n = String(pr.number);
  const after = async doc => { if (doc) { await WS.refreshPrs(pr.number); } };
  switch (action) {
    case 'refresh': return loadPr(pr.number);
    case 'diff': { const doc = await WS.cli(['pr', 'diff', n]); return doc.ok ? ECO.output(`PR #${n} の差分`, doc.result || '差分はありません。', {diff: true}) : ECO.showError(doc); }
    case 'ready': return after(await WS.run(['pr', 'ready', n], {success: '下書きを解除しました。', refresh: false}));
    case 'draft': return after(await WS.run(['pr', 'draft', n], {success: '下書きに戻しました。', refresh: false}));
    case 'close': return after(await WS.run(['pr', 'close', n], {success: 'PRを閉じました。', confirm: `PR #${n} を閉じます（ブランチ・作業空間・タスクはそのまま）。作業をやめるならタスク管理の「作業をやめる」を使います。`, title: 'PRを閉じる', refresh: false}));
    case 'reopen': return after(await WS.run(['pr', 'reopen', n], {success: 'PRを開き直しました。', refresh: false}));
    case 'comment': return ECO.form({title: `PR #${n} にコメント`, fields: [{name: 'message', label: '内容', type: 'textarea', required: true}], ok: 'コメントする',
      submit: async v => { const doc = await WS.run(['pr', 'comment', n, '--message', v.message], {success: 'コメントしました。', refresh: false}); if (!doc) return 'コメントできませんでした。'; await after(doc); }});
    case 'review': return ECO.form({title: `PR #${n} をレビュー`, fields: [
      {name: 'kind', label: '結果', type: 'radio', value: 'approve', options: [['approve', '承認する'], ['request-changes', '修正を依頼する', '内容が必要です'], ['comment', 'コメントだけ', '内容が必要です']]},
      {name: 'message', label: '内容', type: 'textarea'}], ok: '送る',
      submit: async v => {
        if (v.kind !== 'approve' && !v.message) return '内容を入力してください。';
        const doc = await WS.run(['pr', 'review', n, '--' + v.kind, ...(v.message ? ['--message', v.message] : [])], {success: 'レビューを送りました。', refresh: false});
        if (!doc) return 'レビューを送れませんでした。'; await after(doc);
      }});
    case 'edit': return ECO.form({title: `PR #${n} を編集`, fields: [
      {name: 'title', label: '題名', value: pr.title}, {name: 'body', label: '本文', type: 'textarea', value: pr.body.replace(/^(Closes|Refs) #\d+\s*$/gm, '').trim(), rows: 5, help: '作業空間のPRでは、タスクとのつながり（Closes／Refs #番号）は残ります。'},
      {name: 'clearBody', label: '本文を消す', type: 'checkbox'}, {name: 'base', label: '向き先のブランチ', value: pr.base, help: '作業空間のPRなら、作業空間の作成元も変わります。'},
      {name: 'addReviewer', label: 'レビューを頼む人（カンマ区切り）'}, {name: 'removeReviewer', label: 'レビューの依頼を外す人（カンマ区切り）'},
      {name: 'addLabel', label: '付けるラベル（カンマ区切り）'}, {name: 'removeLabel', label: '外すラベル（カンマ区切り）'}], ok: '保存',
      submit: async v => {
        if (v.clearBody && v.body) return '本文を消す場合は、本文の欄を空にしてください。';
        const args = ['pr', 'edit', n];
        if (v.title && v.title !== pr.title) args.push('--title', v.title);
        const oldBody = pr.body.replace(/^(Closes|Refs) #\d+\s*$/gm, '').trim();
        if (v.body && v.body !== oldBody) args.push('--body', v.body);
        if (v.clearBody) args.push('--clear-body');
        if (v.base && v.base !== pr.base) args.push('--base', v.base);
        for (const [key, option] of [['addReviewer', '--add-reviewer'], ['removeReviewer', '--remove-reviewer'], ['addLabel', '--add-label'], ['removeLabel', '--remove-label']]) if (v[key]) args.push(option, v[key]);
        if (args.length === 3) return '変える内容がありません。';
        const doc = await WS.run(args, {success: 'PRを変更しました。', refresh: false}); if (!doc) return '変更できませんでした。'; await after(doc);
      }});
    case 'merge': {
      const workspacePr = pr.head.startsWith('task/');
      const v = await ECO.form({title: `PR #${n} をマージ`, intro: workspacePr ? '作業空間のPRをsquashでマージし、タスクを閉じます（途中の反映なら作業空間を作り直します）。' : 'ブランチ同士のPRを、マージコミットでマージします。',
        fields: [{name: 'ignore', label: 'CIが失敗していてもマージする', type: 'checkbox'}], ok: 'マージ'});
      if (!v) return;
      const doc = await WS.run([...(workspacePr ? ['task', 'merge', n] : ['branch', 'merge', n]), ...(v.ignore ? ['--ignore-checks'] : [])], {success: r => `PR #${r.number} をマージしました。` + (r.closed_issue ? `タスク #${r.closed_issue} を閉じました。` : '') + (r.workspace_rebuilt ? '作業空間を作り直しました。' : '')});
      await after(doc); if (doc) WS.reloadFiles(); return;
    }
    case 'local-review': {
      const done = WS.status?.reviewing === pr.number;
      const doc = await WS.run(['task', 'review', ...(done ? ['--done'] : [n])], {success: done ? '確認を終えて戻りました。' : `PR #${n} を手元に取り出しました。ビルド・テスト・実行で確かめられます。`});
      await after(doc); if (doc) WS.reloadFiles(); return;
    }
    case 'revert': {
      const doc = await WS.run(['task', 'revert', n], {success: r => `PR #${r.pull_request} を取り消す作業空間 ${r.branch} を作りました。PRを提出してください。`, confirm: `マージ済みの PR #${n} を取り消す作業空間を作ります（タスクを作り、取り消しのコミットを用意します）。`, title: 'マージを取り消す'});
      await after(doc); if (doc) WS.reloadFiles(); return;
    }
    case 'task': if (window.parent !== window) window.parent.postMessage({type: 'show-task', n: pr.task}, location.origin); return;
  }
}
get('pr-list').addEventListener('click', e => { const b = e.target.closest('[data-select-pr]'); if (b) loadPr(Number(b.dataset.selectPr)); });
get('pr-tools').addEventListener('click', e => { const b = e.target.closest('[data-pr-action]'); if (b && !b.disabled && prStatus) prAction(b.dataset.prAction); });
get('pr-all').addEventListener('change', () => WS.refreshPrs());
get('pr-state').addEventListener('click', e => { const a = e.target.closest('[data-pr]'); if (a) { e.preventDefault(); loadPr(Number(a.dataset.pr)); } });
WS.ready.then(() => WS.refreshPrs());
