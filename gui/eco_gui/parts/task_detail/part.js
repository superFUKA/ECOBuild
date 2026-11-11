// 部品「タスクの詳細」。描くのは task status の結果。変える・開くは出力を出すだけ（コマンドは、つなぎが呼ぶ）。
// 計画の値は、その場の欄を変えるとすぐ edit を出す。打っている途中のコメントは、この部品が持つ（state）。
// <<タスクの印（タスクを描く部品で同じもの。部品はほかのファイルを読めないので、それぞれに同じ文を置く）
const STAGES = [['planned', '計画中', 'backlog'], ['todo', '未着手', 'todo'], ['in_progress', '作業中', 'in_progress'], ['in_review', 'レビュー待ち', 'in_review'], ['done', '完了', 'done']];
const STAGE = Object.fromEntries(STAGES.map((s) => [s[0], s]));
const PRIORITIES = ['High', 'Middle', 'Low'];
// 印を作る道具。sprints：スプリントの一覧（今のスプリントを色で分ける）。me：自分のアカウント。
function taskMarks(h, emit, menu, sprints, me) {
  const clock = new Date();
  const today = new Date(clock.getTime() - clock.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const md = (d) => (d ? Number(d.slice(5, 7)) + '/' + Number(d.slice(8, 10)) : '');
  const open = (t) => (t.state || 'open') === 'open';
  const deleted = (t) => !open(t) && t.closed_reason === 'not_planned';
  // 画面に出す段階：閉じていれば完了（か削除済み）。段階の記録がなければ、タスクブランチがあれば作業中、なければ未着手
  const stageOf = (t) => (deleted(t) ? 'deleted' : !open(t) ? 'done' : STAGE[t.stage] ? t.stage : (t.task_branch || t.remote || t.current ? 'in_progress' : 'todo'));
  const sprintName = (t) => (typeof t.sprint === 'string' ? t.sprint : (t.sprint && t.sprint.name) || '');
  const currentSprint = ((sprints || []).find((s) => s.start <= today && today < s.end) || {}).name || '';
  const isAgent = (who) => /agent|bot/i.test(who);
  const span = (cls, text, title) => h('span', title ? { class: cls, title } : { class: cls }, text);
  const stageMark = (key, text) => span('tk-stage ' + (key === 'deleted' ? 'not_planned' : STAGE[key][2]), text || (key === 'deleted' ? '削除済み' : STAGE[key][1]));
  const avatarMark = (who) => (!who ? span('tk-avatar none', '', '担当なし') : span('tk-avatar' + (isAgent(who) ? ' agent' : ''), isAgent(who) ? 'AI' : who[0].toUpperCase(), who));
  const avatar = (who) => {
    if (!who) return avatarMark('');
    const button = h('button', { type: 'button', class: 'tk-person-link', title: who + ' の画面' }, avatarMark(who));
    button.addEventListener('click', (event) => { event.stopPropagation(); emit('dialog', { screen: 'task-person', id: '0', text: who }); });
    return button;
  };
  const marks = {
    today, md, open, deleted, stageOf, sprintName, currentSprint, span, stageMark, avatarMark, avatar,
    stageBadge: (t) => (open(t) ? stageMark(stageOf(t)) : stageMark(deleted(t) ? 'deleted' : 'done')),
    prio: (t) => (t.priority ? span('tk-prio ' + t.priority, t.priority) : ''),
    due: (t) => (t.due ? span('tk-due' + (open(t) && t.due < today ? ' overdue' : ''), md(t.due)) : ''),
    est: (t) => (t.estimate !== null && t.estimate !== undefined ? span('tk-est', String(t.estimate), '見積もり') : ''),
    sprintTag: (t) => (sprintName(t) ? span('tk-sprint' + (sprintName(t) === currentSprint ? ' now' : ''), sprintName(t), 'スプリント') : ''),
    num: (t) => span('tk-num', '#' + t.number),
    flags: (t) => [
      t.blocked_by && open(t) ? span('tk-flag blocked', '待ち ' + t.blocked_by) : '',
      t.subtasks ? span('tk-flag', '子 ' + t.subtasks_done + '/' + t.subtasks) : '',
      t.current || t.task_branch ? span('tk-flag', 'タスクブランチ') : t.remote ? span('tk-flag', 'GitHubにタスクブランチ') : '',
    ].filter(Boolean),
    avatars: (t) => ((t.assignees || []).length ? t.assignees.map(avatar) : [avatar('')]),
    submissionPill: (s) => (s ? span('tk-pill', s.draft ? '下書き' : s.partial ? '中間提出' : '提出中') : ''),
    loading: (text) => h('p', { class: 'tk-empty', role: 'status' }, h('span', { class: 'spinner' }), ' ' + (text || '読み込んでいます…')),
    failed: (text) => h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, text)),
    // 行・カードを選べるようにする（押す・Enter・Space）。右クリックでメニュー
    pick: (node, t) => {
      node.addEventListener('click', (event) => { if (!event.target.closest('button, select, input, textarea, a')) emit('selected', { id: String(t.number) }); });
      node.addEventListener('keydown', (event) => {
        if ((event.key === 'Enter' || event.key === ' ') && event.target === node) { event.preventDefault(); emit('selected', { id: String(t.number) }); }
      });
      node.addEventListener('contextmenu', (event) => { event.preventDefault(); marks.menu(event, t); });
      return node;
    },
    // 右クリックのメニュー。選んだものを出すだけ（何が起きるかは、つないだコマンドと、開く入力の窓が決める）
    menu: async (event, t) => {
      const id = String(t.number), isOpen = open(t), hasWorkspace = Boolean(t.task_branch || t.current), stage = stageOf(t);
      const mine = Boolean(me) && (t.assignees || []).includes(me);
      const sep = { separator: true };
      const items = [{ id: 'show', label: '詳細を見る' }];
      if (isOpen && hasWorkspace && t.workspace) items.push({ id: 'workspace', label: 'タスクブランチを開く' });
      if (isOpen && !hasWorkspace) items.push({ id: 'start', label: t.remote ? '作業を再開…' : '作業を開始…' });
      items.push(sep, { id: 'assign', label: '担当者を追加…' });
      if (me) items.push(mine ? { id: 'unassign-me', label: '自分を担当から外す' } : { id: 'assign-me', label: '自分を担当にする' });
      if (isOpen) {
        items.push(sep, { heading: '優先度' }, ...PRIORITIES.map((p) => ({ id: 'priority:' + p, label: (t.priority === p ? '✓ ' : '　 ') + p, disabled: t.priority === p, reason: '今の優先度です' })));
        if (t.priority) items.push({ id: 'clear:priority', label: '　 優先度を消す' });
        const sprint = [];
        if (currentSprint) sprint.push({ id: 'sprint-in', label: '今のスプリント（' + currentSprint + '）に入れる', disabled: sprintName(t) === currentSprint, reason: '今のスプリントに入っています' });
        if (sprintName(t)) sprint.push({ id: 'clear:sprint', label: 'スプリントから外す' });
        if (sprint.length) items.push(sep, ...sprint);
        if (!hasWorkspace && !t.remote && (stage === 'planned' || stage === 'todo')) items.push(stage === 'planned' ? { id: 'stage:todo', label: '未着手にする' } : { id: 'stage:planned', label: '計画中に戻す' });
      }
      items.push(sep, { id: 'child', label: '子タスクを作る…', disabled: !isOpen, reason: '閉じたタスクです' }, { id: 'edit', label: '編集…' });
      items.push(isOpen ? { id: 'complete', label: '完了にする…' } : { id: 'reopen', label: deleted(t) ? '元に戻す' : '開き直す' });
      if (hasWorkspace) items.push(sep, { id: 'prune', label: 'このPCから片付ける（GitHubには残す）…' });
      if (hasWorkspace || t.remote || isOpen) items.push(sep);
      if (hasWorkspace || t.remote) items.push({ id: 'drop', label: '作業を捨てる（GitHubからも消す）…', danger: true });
      if (isOpen) items.push({ id: 'delete', label: '削除…', danger: true });
      const chosen = await menu(event, items);
      if (!chosen) return;
      const dialog = (screen, text) => emit('dialog', { screen, id, text: text || '' });
      const [kind, value] = chosen.split(':');
      if (chosen === 'show') emit('selected', { id });
      else if (chosen === 'workspace') emit('workspace', { path: t.workspace });
      else if (chosen === 'start') dialog('task-start');
      else if (chosen === 'assign') dialog('task-assign');
      else if (chosen === 'assign-me') emit('edit', { id, add_assignee: '@me' });
      else if (chosen === 'unassign-me') emit('edit', { id, remove_assignee: '@me' });
      else if (kind === 'priority') emit('edit', { id, priority: value });
      else if (kind === 'clear') emit('edit', { id, clear: value });
      else if (chosen === 'sprint-in') emit('edit', { id, sprint: currentSprint });
      else if (kind === 'stage') emit('edit', { id, stage: value });
      else if (chosen === 'child') dialog('task-new', id);
      else if (chosen === 'edit') dialog('task-edit');
      else if (chosen === 'complete') { if (hasWorkspace || t.remote) dialog('task-complete'); else emit('close', { id }); }
      else if (chosen === 'reopen') emit('reopen', { id });
      else if (chosen === 'prune') dialog('task-prune');
      else if (chosen === 'drop') dialog('task-drop');
      else if (chosen === 'delete') emit('remove', { id });
    },
  };
  return marks;
}
// 絞り込み（task-bar の出す値）に合うタスクだけにする。見せ方だけ
function taskFilter(tasks, f, marks, me) {
  const search = String(f.search || '').trim().toLowerCase();
  const who = f.assignee || '', sprint = f.sprint || '', milestone = f.milestone || '';
  return tasks.filter((t) => (marks.open(t) || (marks.deleted(t) ? f.deleted === true : f.closed === true))
    && (who === '' || (who === '-' ? !(t.assignees || []).length : (t.assignees || []).includes(who === '@me' ? me : who)))
    && (sprint === '' || (sprint === '-' ? !marks.sprintName(t) : marks.sprintName(t) === (sprint === 'current' ? marks.currentSprint : sprint)))
    && (milestone === '' || (milestone === '-' ? !t.milestone : t.milestone === milestone))
    && (!search || String(t.title || '').toLowerCase().includes(search) || '#' + t.number === search));
}
// タスクの印>>
const BODY_FOLD = 220;  // 本文を折りたたむ高さ（part.css と同じ）

export default {
  render(root, props, { h, emit, menu, state, redraw }) {
    const d = props.status;
    const me = (props.account && props.account.login) || '';
    const marks = taskMarks(h, emit, menu, props.sprints, me);
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
