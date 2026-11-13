// 部品「提出のタブ」。今までの GUI（gui/static/prs.js の renderPrDetail）と同じ並び：
// 1行目は「#番号 題」と状態の印、右にすること。2行目はタスクブランチ → 作成元・担当・CI・取り込めるかと、見るボタン。
// 処理できるか（反映・承認・差し戻し）は account show の答え（take_in）を引くだけ。
const HELP = {
  submit: '提出の前のパイプライン → Push → PR', ready: '下書きをやめて、見てもらえる提出にします',
  apply: '提出（PR）を作らずに、作成元の最新へ1つのコミットにまとめて入れます',
  withdraw: '提出をやめて作業中に戻します（タスクブランチはそのまま。もう一度提出できます）',
  review_done: '確認をやめて、確認用の作業空間を消します（承認も差し戻しもしません）',
  approve: '提出を承認し、そのまま作成元へ取り込みます', reject: '直してほしいことを書いて、担当者へ戻します',
  full_log: '作成元のコミットも含めた、すべてのログを別の窓で開きます',
};
const MERGEABLE = { MERGEABLE: '取り込めます', CONFLICTING: '衝突があります（タスクブランチで最新を取り込んで解決してください）', UNKNOWN: '取り込めるか確認中' };
const REVIEW = { APPROVED: '承認', CHANGES_REQUESTED: '差し戻し', COMMENTED: 'コメント' };
const stateText = (s) => (!s ? '未提出' : s.state === 'merged' ? (s.partial ? '中間提出は取り込み済み' : '取り込み済み')
  : s.state === 'closed' ? '取り下げ済み' : `${s.draft ? '下書きの' : ''}${s.partial ? '中間提出' : '提出'}中`);

export default {
  render(root, props, { h, emit }) {
    const s = props.status || {}, t = s.reviewing ? props.review : props.task;  // 確認中なら、確認している提出
    const box = h('div', { class: 'pr' });
    if (props.error) { box.append(h('p', { role: 'alert' }, props.error)); return root.replaceChildren(box); }
    if (!('branch' in s) && !('task' in s)) { box.append(h('p', { class: 'muted' }, '読み込んでいます…')); return root.replaceChildren(box); }
    // この作業空間のタスク：確認中の提出か、作業中のタスクブランチ
    const here = (s.reviewing && s.reviewing_task) || (s.task && !s.reviewing && !s.finished && !s.upstream_gone ? s.task : 0);
    if (!here) {
      box.append(h('p', { class: 'muted' }, 'この作業空間に、提出するタスクブランチはありません。モジュールに届いている提出は、モジュールの「ブランチ」で見られます。'));
      return root.replaceChildren(box);
    }
    if (!t || Number(t.number) !== Number(here)) { box.append(h('p', { class: 'muted' }, '読み込んでいます…')); return root.replaceChildren(box); }

    const id = String(t.number);
    const button = (action, label, { enabled = true, kind = '', note = '' } = {}) => {
      const item = h('button', { type: 'button', class: kind, title: [HELP[action], note && `（${note}）`].filter(Boolean).join('\n') }, label);
      item.disabled = !enabled;
      item.addEventListener('click', () => emit('action', { action, id }));
      return item;
    };
    const sub = t.pull_request, open = Boolean(sub) && sub.state === 'open', draft = open && Boolean(sub.draft);
    const reviewing = Boolean(s.reviewing) && Number(s.reviewing_task) === Number(t.number);
    const access = props.access, me = String((access && access.login) || '').toLowerCase();
    const own = me ? (t.assignees || []).some((name) => name.toLowerCase() === me) : !reviewing;
    // 処理できるか：取り込み先で引く。分からなければ灰色にしない（実行のときに ecobuild が確かめる）
    const base = (sub && sub.base) || t.base || '';
    const rule = access ? (access.take_in || {})[base] || access.take_in_other || null : null;
    const handles = !rule || rule.allowed !== false;
    const why = handles ? '' : `${base} への提出を処理できるのは、${rule.owners || '作成元を作った人と管理者'}だけです`;
    const applies = !reviewing && Boolean(access) && Boolean(base) && handles;

    const kind = !sub ? 'none' : sub.state === 'open' ? (draft ? 'draft' : 'open') : sub.state;
    const title = h('div', { class: 'pr-title' }, h('strong', { title: t.title || '' }, `#${t.number} ${t.title || ''}`), h('span', { class: 'pr-state ' + kind }, stateText(sub)));
    const act = h('div', { class: 'pr-act' });
    if (reviewing) {
      act.append(button('review_done', '判定せずに終える'));
      if (open) {
        act.append(button('reject', '差し戻す', { enabled: handles, note: why }),
          button('approve', '承認して取り込む', { enabled: !draft && handles, kind: 'primary', note: draft ? '下書きの提出は承認できません' : why }));
      }
    } else {
      // 作成元を処理できる人は反映（提出しない）。ほかの人は提出して、処理できる人に取り込んでもらう
      if (open) act.append(button('withdraw', '提出を取り下げる', { kind: 'quiet danger-text' }));
      if (applies) act.append(button('apply', '反映', { kind: 'primary' }));
      else {
        if (draft) act.append(button('ready', '下書きを解除', { kind: 'primary' }));
        act.append(button('submit', '提出', { kind: draft ? '' : 'primary' }));
      }
    }
    const a = t.activity || { checks: [], mergeable: '' };
    const checks = (a.checks || []).length ? a.checks.flatMap((c, i) => [i ? '、' : '', `${c.name} `,
      c.status !== 'completed' ? h('span', { class: 'check wait' }, '実行中')
        : ['success', 'skipped', 'neutral'].includes(c.conclusion) ? h('span', { class: 'check ok' }, '成功') : h('span', { class: 'check bad' }, c.conclusion || '失敗')]) : ['なし'];
    const sep = () => h('span', { class: 'sep' }, '·');
    const meta = h('div', { class: 'pr-meta' }, `${t.branch || 'task/' + t.number}${base ? ` → ${base}` : ''}`, sep(),
      `担当 ${(t.assignees || []).join(', ') || 'なし'}${own ? '（自分）' : ''}`, sep(), 'CI ', ...checks);
    if (open && a.mergeable) meta.append(sep(), h('span', { class: a.mergeable === 'CONFLICTING' ? 'merge bad' : a.mergeable === 'MERGEABLE' ? 'merge ok' : 'merge' }, MERGEABLE[a.mergeable] || a.mergeable));
    const look = h('div', { class: 'pr-look' }, button('diff', '差分', { kind: 'quiet small' }), button('comment', 'コメント', { kind: 'quiet small' }),
      button('task', 'タスク', { kind: 'quiet small' }), button('refresh', '更新', { kind: 'quiet small' }));
    box.append(h('div', { class: 'pr-head' }, title, act), h('div', { class: 'pr-meta-row' }, meta, look));
    if (!reviewing && s.ahead) {
      box.append(h('p', { class: 'pr-note' }, `未Pushのコミット ${s.ahead}件：${applies ? '反映すると一緒に入ります' : open ? 'Pushすると提出に加わります' : '提出するとPushします'}。`));
    }
    if (open && !handles) box.append(h('p', { class: 'pr-why' }, `${why}（見る・コメントはできます）。`));
    // レビュー・提出へのコメント・タスクへのコメントを、1本の流れで
    const entry = (author, mark, body) => h('div', { class: 'entry' }, h('b', {}, author), mark ? h('span', { class: 'mark' }, mark) : '', body ? h('div', { class: 'body' }, body) : '');
    const talk = [...(a.reviews || []).map((r) => entry(r.author, ' · ' + (REVIEW[r.state] || r.state), r.body)),
      ...(a.comments || []).map((c) => entry(c.author, '', c.body)), ...(t.comments || []).map((c) => entry(c.author, '（タスク）', c.body))];
    if (talk.length) box.append(h('div', { class: 'talk' }, ...talk));
    // 提出に入るコミット（一覧は下の部品。ここは見出しと「すべてのログ」）
    if (base) {
      const count = Array.isArray(t.commits) ? t.commits.length : 0;
      box.append(h('div', { class: 'pr-commits-head' }, h('span', {}, `提出に入るコミット${count ? `（${count}件、新しい順）` : ''}`),
        button('full_log', 'すべてのログ', { kind: 'link-button' })));
    }
    root.replaceChildren(box);
  },
};
