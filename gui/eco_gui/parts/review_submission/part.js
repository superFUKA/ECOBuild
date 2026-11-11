// 部品「提出の詳細」。題・状態の文・取り込めるか・タスクブランチ → 作成元・担当・CI（名前ごとに 成功／実行中／失敗）・URL、
// 提出に入るコミット（sha と件名）、レビューとコメントの1本の流れ、下に操作のボタン（左：見る、右：する）。
// 処理できるか（承認・差し戻し・取り込み）は account show の答え（take_in）を引くだけ。できない人には説明と、灰色のボタンと理由。
const HELP = {
  finish: '取り込む：CIの結果を待って、提出（PR）を作成元へ取り込みます。タスクは提出のとおり、閉じるか続けます。',
  apply: '反映：提出（PR）を作らずに、作成元の最新へ1つのコミットにまとめて入れます。',
  withdraw: '取り下げ：提出をやめて作業中に戻します（タスクブランチはそのまま。もう一度提出できます）。',
  review: '手元で確認：提出された変更を手元に取り出し、ビルド・テスト・実行で確かめます（確かめたら承認か差し戻し）。',
  review_done: '確認をやめて、確認用の作業空間を消します（承認も差し戻しもしません）。',
  open_review: '確認用の作業空間を開きます。',
  approve: '承認して取り込む：提出を承認し、そのまま作成元へ取り込みます。タスクは提出のとおり、閉じるか続けます。',
  reject: '差し戻し：直してほしいことを書いて、担当者へ戻します（タスクは作業中に戻ります）。',
  merge: '取り込む：ブランチ同士の提出を、マージコミットで取り込み先へ取り込みます。',
};
const REVIEW = { APPROVED: '承認', CHANGES_REQUESTED: '差し戻し', COMMENTED: 'コメント' };
const MERGEABLE = { MERGEABLE: '取り込めます', CONFLICTING: '衝突があります（タスクブランチで最新を取り込んで解決してください）', UNKNOWN: '確認中' };
const stateText = (s) => (!s ? '未提出' : s.state === 'merged' ? (s.partial ? '中間提出は取り込み済み' : '取り込み済み')
  : s.state === 'closed' ? '取り下げ済み' : `${s.draft ? '下書きの' : ''}${s.partial ? '中間提出' : '提出'}中`);
const statePill = (s) => (!s ? '' : s.state === 'merged' ? 'ok' : s.state === 'closed' ? 'dim' : s.draft ? 'warn' : 'purple');

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const t = props.task, access = props.access;
    const b = props.branch || (props.name ? (props.branches || []).find((one) => one.name === props.name) : null) || null;
    if (!t && !b) {
      return root.replaceChildren(props.loading ? h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…')
        : h('p', { role: 'status' }, '提出を選ぶと、ここに詳しく出ます。'));
    }
    const row = (name, ...value) => [h('dt', {}, name), h('dd', {}, ...value)];
    // 処理できるか：取り込み先のブランチで引く。分からなければ（古い ecobuild・オフライン）灰色にしない（実行のときに ecobuild が確かめる）
    const base = t ? (t.pull_request?.base || t.base || '') : (b.submitted_to || '');
    const rule = access ? (access.take_in || {})[base] || access.take_in_other || null : null;
    const handles = !rule || rule.allowed !== false;
    const why = handles ? '' : `${base} への提出を処理できるのは、${rule.owners}だけです`;
    const id = t ? String(t.number) : b.name;
    const button = (action, label, { enabled = true, kind = '', note = '', extra = {} } = {}) => {
      const item = h('button', { type: 'button', class: kind, title: [HELP[action], note && `（${note}）`].filter(Boolean).join('\n') }, label);
      item.disabled = !enabled;
      item.addEventListener('click', () => emit('action', { action, id, base, partial: false, workspace: '', ...extra }));
      return item;
    };
    const look = h('div', { class: 'look' }), act = h('div', { class: 'act' }), out = [];

    if (!t) {  // ブランチ同士の提出
      const s = b.submission || {};
      out.push(h('dl', {}, ...row('ブランチ', h('strong', {}, b.name), ` → ${b.submitted_to || ''}`),
        ...row('提出', h('span', { class: 'pill ' + statePill(s) }, stateText(s)), ' ', h('span', { class: 'pill' }, 'ブランチ同士')),
        ...(s.url ? row('URL', h('span', { class: 'url' }, s.url)) : [])));
      act.append(button('merge', '取り込む', { kind: 'primary', enabled: !s.draft && handles, note: s.draft ? '下書きの提出は取り込めません' : why }));
    } else {
      const sub = t.pull_request, open = sub?.state === 'open', draft = open && sub.draft;
      const a = t.activity || { reviews: [], comments: [], checks: [], mergeable: '' };
      const me = (access?.login || '').toLowerCase();
      const own = !!me && (t.assignees || []).some((name) => name.toLowerCase() === me);
      const conflicting = a.mergeable === 'CONFLICTING';
      const reviewing = (props.spaces || []).find((space) => sub && space.review === sub.number) || null;
      const check = (c) => (c.status !== 'completed' ? h('span', { class: 'check wait' }, '実行中')
        : ['success', 'skipped', 'neutral'].includes(c.conclusion) ? h('span', { class: 'check ok' }, '成功')
          : h('span', { class: 'check bad' }, c.conclusion || '失敗'));
      const checks = (a.checks || []).length ? a.checks.flatMap((c, i) => [...(i ? [h('br')] : []), `${c.name}：`, check(c)]) : ['なし'];
      out.push(h('dl', {},
        ...row('タスク', h('strong', {}, `#${t.number} ${t.title}`)),
        ...row('提出', h('span', { class: 'pill ' + statePill(sub) }, stateText(sub)),
          ...(open ? [' ', h('span', { class: conflicting ? 'merge bad' : a.mergeable === 'MERGEABLE' ? 'merge ok' : 'merge' }, MERGEABLE[a.mergeable] || a.mergeable || '')] : [])),
        ...row('タスクブランチ', h('span', { class: 'mono' }, t.branch || `task/${t.number}`), t.base ? ` → ${t.base}` : ''),
        ...row('担当者', (t.assignees || []).join(', ') || 'なし', own ? '（自分）' : ''),
        ...row('CI', ...checks),
        ...(sub ? row('URL', h('span', { class: 'url' }, sub.url)) : [])));
      // 提出に入るコミット（新しい順。「短いID 件名」）
      if (Array.isArray(t.commits)) {
        out.push(t.commits.length ? h('div', { class: 'commits' }, h('div', { class: 'commits-head' }, `提出に入るコミット（${t.commits.length}件、新しい順）`),
          h('ul', {}, ...t.commits.map((line) => { const at = line.indexOf(' '); return h('li', {}, h('code', {}, at < 0 ? line : line.slice(0, at)), at < 0 ? '' : line.slice(at + 1)); })))
          : h('p', { class: 'commits-none' }, '提出に入るコミットはありません（作成元と同じです）。'));
      }
      // レビュー・提出へのコメント・タスクへのコメントを、1本の流れで
      const entry = (author, mark, body) => h('div', { class: 'entry' }, h('b', {}, author), mark ? h('span', { class: 'mark' }, mark) : '', body ? h('div', { class: 'body' }, body) : '');
      const talk = [...(a.reviews || []).map((r) => entry(r.author, ' · ' + (REVIEW[r.state] || r.state), r.body)),
        ...(a.comments || []).map((c) => entry(c.author, '', c.body)), ...(t.comments || []).map((c) => entry(c.author, '（タスク）', c.body))];
      if (talk.length) out.push(h('div', { class: 'talk' }, ...talk));
      if (open && !handles) out.push(h('p', { class: 'note' }, `${why}（見る・手元で確認・コメントはできます）。`));

      look.append(button('diff', '差分', { kind: 'quiet small' }), button('comment', 'コメント', { kind: 'quiet small' }),
        button('task', 'タスク', { kind: 'quiet small' }), button('refresh', '更新', { kind: 'quiet small' }));
      const extra = { partial: !!sub?.partial, workspace: reviewing ? String(reviewing.path) : '' };
      if (reviewing) act.append(button('open_review', '確認用の作業空間を開く', { extra }), button('review_done', '判定せずに終える', { extra }));
      if (open && !own) {
        if (!reviewing) act.append(button('review', '手元で確認', { extra }));
        act.append(button('reject', '差し戻す', { enabled: handles, note: why, extra }),
          button('approve', '承認して取り込む', { kind: 'primary', enabled: !draft && handles && !conflicting, extra,
            note: draft ? '下書きの提出は承認できません' : why || (conflicting ? '作成元と衝突しています。差し戻して、担当者に最新を取り込んでもらいます' : '') }));
      } else if (open) {
        act.append(button('withdraw', '提出を取り下げる', { kind: 'quiet danger-text', extra }),
          button('finish', '取り込む', { kind: 'primary', enabled: !draft && handles && !conflicting, extra,
            note: draft ? '下書きの提出は取り込めません。タスクブランチの作業空間で下書きを解除します'
              : why || (conflicting ? '作成元と衝突しています。タスクブランチで最新を取り込んで直してから取り込みます' : '') }));
      } else if (own && t.task_branch && t.state === 'open') {
        act.append(button('apply', '反映…', { extra, enabled: handles, note: why }));
      }
    }
    root.replaceChildren(...out, h('div', { class: 'tools' }, look, act));
  },
};
