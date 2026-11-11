// 部品「タスクの詳細」。描くのは task status の結果。変える・開くは出力を出すだけ（コマンドは、つなぎが呼ぶ）。
// 計画の値は、その場の欄を変えるとすぐ edit を出す。打っている途中のコメントは、この部品が持つ（state）。
const BODY_FOLD = 220;  // 本文を折りたたむ高さ（part.css と同じ）

export default {
  render(root, props, { h, lib, emit, menu, state, redraw }) {
    const { PRIORITIES } = lib.task;
    const d = props.status;
    const me = (props.account && props.account.login) || '';
    const marks = lib.task.marks(h, emit, menu, props.sprints, me);
    const closeButton = () => {
      const button = h('button', { type: 'button', class: 'd-close', title: '詳細を閉じる', 'aria-label': '詳細を閉じる' }, '×');
      button.addEventListener('click', () => emit('closed', {}));
      return props.closable ? button : '';
    };
    if (props.error) return root.replaceChildren(h('div', { class: 'd-head' }, closeButton()), h('p', { class: 'tk-empty', role: 'alert' }, props.error));
    // まだ届いていない・前に選んだタスクのまま（選び直した直後）：読み込み中
    if (!d || (props.number && String(d.number) !== String(props.number))) return root.replaceChildren(h('div', { class: 'd-head' }, closeButton()), marks.loading());

    const id = String(d.number), t = d.task || {}, isOpen = (d.state || 'open') === 'open';
    const view = { ...t, state: d.state, task_branch: d.task_branch, remote: d.remote };
    const hasWorkspace = Boolean(d.task_branch), pr = d.pull_request || null;
    const dialog = (screen, text) => emit('dialog', { screen, id, text: text || '' });
    const button = (label, cls, action, title) => {
      const b = h('button', cls ? { type: 'button', class: cls } : { type: 'button' }, label);
      if (title) b.title = title;
      b.addEventListener('click', action);
      return b;
    };
    const section = (title, ...children) => h('section', { class: 'd-section' }, ...(title ? [h('h4', {}, title)] : []), ...children);
    const kv = (cls, rows) => h('dl', { class: cls }, ...rows.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, ...(Array.isArray(v) ? v : [v]))]));

    // 提出を処理できるか（作成元を作った人と管理者。分からなければ灰色にしない：コマンドが必ず確かめる）
    const a = props.account || {};
    const creator = d.base && d.base !== a.default_base ? (a.creators || {})[d.base] || '' : '';
    const canTakeIn = !a.login || a.admin === true || (creator !== '' && creator.toLowerCase() === String(a.login).toLowerCase());
    const why = canTakeIn ? '' : (d.base || '取り込み先') + ' への提出を処理できるのは、' + (creator ? (d.base + ' を作った ' + creator + ' と') : '') + '管理者だけです';
    const own = Boolean(me) && (d.assignees || []).includes(me);
    const conflicting = Boolean(d.activity && d.activity.mergeable === 'CONFLICTING');
    const conflictNote = (mine) => (mine ? '作成元と衝突しています。タスクブランチの作業空間で最新を取り込んで直し、Push してから取り込みます'
      : '作成元と衝突しています。差し戻して、作業者に最新を取り込んで直してもらいます');

    // --- 見出しとボタン ---
    const head = h('div', { class: 'd-head' }, marks.num(d), marks.stageBadge(view));
    if (d.url) head.append(h('a', { class: 'd-link', href: d.url, target: '_blank', rel: 'noopener', title: 'GitHubで開く' }, 'GitHub ↗'));
    head.append(closeButton());
    const actions = h('div', { class: 'd-actions' });
    if (!isOpen) actions.append(button(marks.deleted(view) ? '元に戻す' : '開き直す', '', () => emit('reopen', { id })));
    else if (hasWorkspace && d.workspace) actions.append(button('タスクブランチを開く', 'primary', () => emit('workspace', { path: d.workspace })));
    else if (!hasWorkspace) actions.append(button(d.remote ? '作業を再開' : '作業を開始', 'primary', () => dialog('task-start')));
    if (isOpen) {
      actions.append(hasWorkspace || d.remote
        ? button('完了にする', '', () => dialog('task-complete'), 'タスクを完了にします。出している提出・まだ取り込んでいない変更があれば取り込んでから閉じ、タスクブランチを片付けます（作業をやめるなら ⋯ の「作業を捨てる」）')
        : button('完了にする', '', () => emit('close', { id })));
    }
    actions.append(button('編集', '', () => dialog('task-edit')));
    const more = button('⋯', 'more', async (event) => {
      const others = isOpen && pr && pr.state === 'open' && !own;
      const sep = { separator: true };
      const groups = [
        [!isOpen && pr && pr.state === 'merged' ? { id: 'revert', label: '取り込みを取り消す…' } : null,
          others && !pr.draft ? { id: 'finish', label: '承認せずに取り込む…', disabled: Boolean(why || conflicting), reason: why || conflictNote(false) } : null,
          others ? { id: 'withdraw', label: '提出を取り下げる…' } : null],
        [hasWorkspace ? { id: 'prune', label: 'このPCから片付ける…' } : null],
        [hasWorkspace || d.remote ? { id: 'drop', label: '作業を捨てる…', danger: true } : null, isOpen ? { id: 'delete', label: '削除…', danger: true } : null],
      ].map((g) => g.filter(Boolean)).filter((g) => g.length);
      if (!groups.length) groups.push([{ id: 'none', label: 'ほかの操作はありません', disabled: true }]);
      const chosen = await menu(event, groups.flatMap((g, i) => (i ? [sep, ...g] : g)));
      if (chosen === 'revert') emit('revert', { id });
      else if (chosen === 'finish') dialog('task-finish');
      else if (chosen === 'withdraw') emit('withdraw', { id });
      else if (chosen === 'prune') dialog('task-prune');
      else if (chosen === 'drop') dialog('task-drop');
      else if (chosen === 'delete') emit('remove', { id });
    }, 'その他の操作');
    more.setAttribute('aria-label', 'その他の操作');
    actions.append(more);

    // --- 本文（長ければ折りたたむ） ---
    const bodyOpen = state.bodyOpen === id;
    const body = h('div', { class: bodyOpen ? 'd-body open' : 'd-body' }, d.body || h('span', { class: 'tk-muted' }, '本文はありません'));
    const moreBody = button(bodyOpen ? '折りたたむ' : 'すべて表示', 'tk-link d-more', () => { state.bodyOpen = bodyOpen ? null : id; redraw(); });
    moreBody.hidden = true;

    // --- 担当・ラベル ---
    const chip = (text, onText, onRemove) => {
      const x = button('×', 'x', onRemove, '外す');
      const name = onText ? button(text, 'person-name', onText, text + ' の画面') : text;
      return h('span', { class: 'chip' }, name, x);
    };
    const people = h('div', { class: 'chips' }, ...(d.assignees || []).map((who) => chip(who + (who === me ? '（自分）' : ''),
      () => emit('dialog', { screen: 'task-person', id: '0', text: who }), () => emit('edit', { id, remove_assignee: who }))),
      button('＋', 'add', () => dialog('task-assign'), '担当者を追加'));
    const labels = h('div', { class: 'chips' }, ...(d.labels || []).map((label) => chip(label, null, () => emit('edit', { id, remove_label: label }))),
      button('＋', 'add', () => dialog('task-label'), 'ラベルを付ける'));

    // --- 計画・日程（変えるとすぐ保存） ---
    const plan = (key, value) => emit('edit', value ? { id, [key]: value } : { id, clear: key });
    const select = (options, current, onChange) => {
      const box = h('select', {});
      for (const [value, label] of options) {
        const option = h('option', { value }, label);
        if (value === current) option.selected = true;
        box.append(option);
      }
      box.disabled = !isOpen;
      box.addEventListener('change', () => onChange(box.value));
      return box;
    };
    const sprintNow = marks.sprintName(t);
    const sprintOptions = [['', 'なし'], ...props.sprints.map((s) => [s.name, s.name + '（' + marks.md(s.start) + '〜' + marks.md(s.end) + '）' + (s.name === marks.currentSprint ? ' ・今' : '')]),
      ...(sprintNow && !props.sprints.some((s) => s.name === sprintNow) ? [[sprintNow, sprintNow]] : [])];
    const milestoneOptions = [['', 'なし'], ...props.milestones.map((m) => [m.title, m.title]),
      ...(d.milestone && !props.milestones.some((m) => m.title === d.milestone) ? [[d.milestone, d.milestone]] : [])];
    const estimate = h('input', { type: 'number', min: '0', step: '0.5', placeholder: 'なし' });
    estimate.value = t.estimate === null || t.estimate === undefined ? '' : String(t.estimate);
    estimate.disabled = !isOpen;
    estimate.addEventListener('change', () => plan('estimate', estimate.value));
    const date = (key) => {
      const input = h('input', { type: 'date', class: t[key] ? '' : 'empty' });
      input.value = t[key] || '';
      input.disabled = !isOpen;
      input.addEventListener('change', () => plan(key, input.value));
      return input;
    };
    const planRows = kv('kv controls', [
      ['優先度', select([['', 'なし'], ...PRIORITIES.map((p) => [p, p])], t.priority || '', (v) => plan('priority', v))],
      ['見積もり', estimate],
      ['スプリント', select(sprintOptions, sprintNow, (v) => plan('sprint', v))],
      ['マイルストーン', select(milestoneOptions, d.milestone || '', (v) => emit('edit', v ? { id, milestone: v } : { id, clear_milestone: true }))]]);
    const dateRows = kv('kv controls', [['開始予定', date('planned_start')], ['終了予定', date('planned_end')], ['期限', date('due')],
      ['日付', h('span', { class: 'tk-muted' }, '追加 ' + (t.created || '-') + (t.started ? ' · 開始 ' + t.started : '') + (t.finished ? ' · 終了 ' + t.finished : ''))]]);

    // --- つながり ---
    const rel = (x) => {
      const row = h('div', { class: 'rel', tabindex: '0' }, marks.num(x), h('span', { class: 'tk-grow' }, x.title || ''), (x.state || 'open') === 'open' ? '' : marks.stageMark('done'));
      row.addEventListener('click', () => emit('selected', { id: String(x.number) }));
      row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); emit('selected', { id: String(x.number) }); } });
      return row;
    };
    const relations = [d.parent && ['親タスク', [d.parent]], (d.subtasks || []).length && ['子タスク', d.subtasks],
      (d.blocked_by || []).length && ['先に終わるべき', d.blocked_by], (d.blocking || []).length && ['待っているタスク', d.blocking]].filter(Boolean);

    // --- 作業と提出 ---
    const branch = hasWorkspace ? [d.branch || t.branch || 'task/' + id, ...(d.workspace ? [h('div', { class: 'tk-muted' }, d.workspace)] : [])]
      : [h('span', { class: 'tk-muted' }, d.remote ? 'GitHubだけ' : 'なし')];
    if (d.base) branch.push(h('div', { class: 'tk-muted' }, '作成元 ' + d.base));
    const kind = pr && pr.partial ? '中間提出' : '提出';
    const submission = !pr ? h('span', { class: 'tk-muted' }, 'なし')
      : pr.state === 'merged' ? (isOpen ? h('span', { class: 'tk-muted' }, 'なし（前回の中間提出は取り込み済み）') : kind + 'は取り込み済み')
        : pr.state === 'closed' ? h('span', { class: 'tk-muted' }, kind + 'は取り下げ済み') : (pr.draft ? '下書きの' : '') + kind + '中';
    const work = [kv('kv', [['タスクブランチ', branch], ['提出', submission]])];
    const submitted = Boolean(pr && pr.state === 'open');
    if (isOpen && (submitted || hasWorkspace)) {
      const off = (b, reason) => { if (reason) { b.disabled = true; b.title = reason; } return b; };
      const draft = submitted && pr.draft === true;
      const act = !submitted ? []
        : own ? [button('提出を取り下げる', 'quiet-danger', () => emit('withdraw', { id }), '取り下げ：提出をやめて作業中に戻します（タスクブランチはそのまま。もう一度提出できます）。'),
          off(button('取り込む', 'primary', () => dialog('task-finish'), '取り込む：CIの結果を待って、提出（PR）を作成元へ取り込みます。'),
            draft ? '下書きの提出は取り込めません。タスクブランチの作業空間で下書きを解除します' : why || (conflicting ? conflictNote(true) : ''))]
          : [button('手元で確認', '', () => emit('review', { id }), '手元で確認：提出された変更を手元に取り出し、ビルド・テスト・実行で確かめます（確かめたら承認か差し戻し）。'),
            off(button('差し戻す', '', () => dialog('task-reject'), '差し戻し：直してほしいことを書いて、担当者へ戻します（タスクは作業中に戻ります）。'), why),
            off(button('承認して取り込む', 'primary', () => dialog('task-approve'), '承認して取り込む：提出を承認し、そのまま作成元へ取り込みます。'),
              draft ? '下書きの提出は承認できません' : why || (conflicting ? conflictNote(false) : ''))];
      work.push(h('div', { class: 'sub-actions' }, h('div', {}, button('差分', '', () => emit('submission', { id }))), h('div', {}, ...act)));
    }

    // --- コメント ---
    if (state.commentFor !== id || !state.comment) {
      state.commentFor = id;
      state.comment = h('textarea', { placeholder: 'コメントを書く（作業の記録・申し送り）', 'aria-label': 'コメント' });
    }
    const send = button('コメント', '', () => {
      const text = state.comment.value.trim();
      if (!text) return;
      emit('comment', { id, message: text });
      state.comment.value = '';
    });
    const comments = (d.comments || []).map((c) => h('article', { class: 'comment' }, h('header', {}, c.author || ''), h('p', {}, c.body || '')));

    root.replaceChildren(head, h('h3', { class: 'd-title' }, d.title || ''), actions,
      section('', body, moreBody),
      section('担当・ラベル', kv('kv', [['担当者', people], ['ラベル', labels]])),
      section('計画', planRows), section('日程', dateRows),
      ...(relations.length ? [section('つながり', kv('kv', relations.map(([label, xs]) => [label, xs.map(rel)])))] : []),
      section('作業', ...work),
      section('コメント ' + (d.comments || []).length, ...comments, h('div', { class: 'comment-box' }, state.comment, h('div', {}, send))));
    moreBody.hidden = !bodyOpen && body.scrollHeight <= BODY_FOLD + 4;
  },
};
