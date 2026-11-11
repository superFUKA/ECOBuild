// eco_gui の部品の間で共有するコード（見せ方だけ。処理を呼ばない・通信しない・部品の外に触らない）。
// 部品には道具 lib として渡る。要素を作る関数には、部品が h を渡す。
// 範囲ごとに1つの入れ物にまとめる（タスク管理は task）。

// --- タスク管理（task） ---------------------------------------------------------------
const STAGES = [['planned', '計画中', 'backlog'], ['todo', '未着手', 'todo'], ['in_progress', '作業中', 'in_progress'], ['in_review', 'レビュー待ち', 'in_review'], ['done', '完了', 'done']];
const STAGE = Object.fromEntries(STAGES.map((s) => [s[0], s]));
const PRIORITIES = ['High', 'Middle', 'Low'];
// 今日（この PC の時計で YYYY-MM-DD）・日付の短い書き方（M/D）・今日を含むスプリントの名前
function taskToday() {
  const clock = new Date();
  return new Date(clock.getTime() - clock.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
const taskMd = (d) => (d ? Number(d.slice(5, 7)) + '/' + Number(d.slice(8, 10)) : '');
function taskCurrentSprint(sprints) {
  const today = taskToday();
  return ((sprints || []).find((s) => s.start <= today && today < s.end) || {}).name || '';
}
// 印を作る道具。sprints：スプリントの一覧（今のスプリントを色で分ける）。me：自分のアカウント。
function taskMarks(h, emit, menu, sprints, me) {
  const today = taskToday(), md = taskMd;
  const open = (t) => (t.state || 'open') === 'open';
  const deleted = (t) => !open(t) && t.closed_reason === 'not_planned';
  // 画面に出す段階：閉じていれば完了（か削除済み）。開いていれば、届いた段階のまま（記録がないときにどうみなすかは、ecobuild が
  // 決めて入れる）。届いていなければ ''（印を出さない）
  const stageOf = (t) => (deleted(t) ? 'deleted' : !open(t) ? 'done' : STAGE[t.stage] ? t.stage : '');
  const sprintName = (t) => (typeof t.sprint === 'string' ? t.sprint : (t.sprint && t.sprint.name) || '');
  const currentSprint = taskCurrentSprint(sprints);
  const isAgent = (who) => /agent|bot/i.test(who);
  const span = (cls, text, title) => h('span', title ? { class: cls, title } : { class: cls }, text);
  const stageMark = (key, text) => (key === 'deleted' ? span('tk-stage not_planned', text || '削除済み') : STAGE[key] ? span('tk-stage ' + STAGE[key][2], text || STAGE[key][1]) : '');
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

// --- 入力の窓（form） ------------------------------------------------------------------
// 入力の窓を描く所は、ここ1つ（部品 form と、欄を読んだ情報から組む部品 task-form・hub-add-form が使う）。
// 今までの GUI のダイアログ（static/common.js の ECO.form）と同じ見た目・同じ欄の種類。見た目（CSS）も、ここ1つに持つ
// （部品の間で part.css を共有する口がないので、描くときに一緒に入れる。値は common.css の .eco-dialog のフォームと同じ。
// theme.css より後に効くよう、全部を .eco-form の中に入れてある）。
const FORM_CSS = `
:host { display: block; font-size: 14px; }
.eco-form {
display: block; margin: 0;
[hidden] { display: none !important; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
h2 { margin: 0 0 12px; font-size: 18px; font-weight: 600; }
p { margin: 8px 0; line-height: 1.7; }
.intro { margin: 8px 0; color: var(--gf-muted); font-size: 13px; line-height: 1.7; white-space: pre-wrap; }
.intro:empty { display: none; }
.outcome { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin: 4px 0 10px; padding: 8px 12px; border: 1px solid var(--eco-line); border-radius: 7px; background: #1b2128; }
.outcome dt { color: #8d98a6; font-size: 12px; padding-top: 2px; white-space: nowrap; }
.outcome dd { margin: 0; color: var(--gf-fg); font-size: 13px; line-height: 1.6; }
.field { display: grid; gap: 6px; margin: 12px 0; font-size: 13px; }
.req { margin-left: 3px; color: #f3a5a5; }
label.check { display: flex; gap: 8px; align-items: center; margin: 10px 0; font-size: 13px; cursor: pointer; }
label.check.strong { font-weight: 600; }
.help { display: block; margin: 0; color: var(--gf-muted); font-size: 12px; }
input:not([type=checkbox]):not([type=radio]), select, textarea { width: 100%; padding: 8px 10px; border-radius: 6px; }
input[type=radio], input[type=checkbox] { width: auto; flex: none; margin: 2px 0 0; padding: 0; }
label.check input { margin: 0; }
fieldset { border: 0; padding: 0; margin: 12px 0; display: grid; gap: 8px; min-width: 0; }
fieldset legend { font-size: 13px; margin-bottom: 6px; padding: 0; }
fieldset label { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border: 1px solid var(--gf-border); border-radius: 8px; cursor: pointer; font-size: 13px; }
fieldset label:has(input:checked) { border-color: #8bd7c2; background: #253c36; }
fieldset label:has(input:focus-visible) { outline: 2px solid #8bd7c2; outline-offset: 3px; }
fieldset label strong { font-weight: 400; }
fieldset label small { display: block; color: #b4bec9; font-size: 11px; margin-top: 3px; }
fieldset.inline { grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); }
fieldset.cols { grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); margin-top: 0; }
fieldset.inline > legend, fieldset.cols > legend { grid-column: 1 / -1; }
fieldset.strong label { align-items: center; padding: 12px; border-radius: 10px; }
fieldset.strong label strong { font-size: 14px; font-weight: 600; }
fieldset.strong label input { margin: 0; }
fieldset.checks > div { display: flex; flex-wrap: wrap; gap: 6px; }
fieldset.checks label { padding: 5px 10px; border-radius: 16px; align-items: center; gap: 6px; }
fieldset.checks input { margin: 0; }
.more::after { content: '候補を読み込んでいます…'; display: block; color: #a5aeba; font-size: 12px; margin-top: 2px; }
.multi { display: grid; gap: 6px; }
.multi-item { display: flex; gap: 6px; }
.multi-item button { flex: none; width: 34px; padding: 0; font-size: 15px; }
.candidates { margin: -4px 0 12px; }
.candidates > p { margin: 0; color: var(--gf-muted); font-size: 13px; line-height: 1.8; }
.candidates ul { list-style: none; margin: 6px 0 0; padding: 0; max-height: 220px; overflow: auto; border: 1px solid #2c333c; border-radius: 8px; }
.candidates li + li { border-top: 1px solid #262c34; }
.candidates button { display: block; width: 100%; text-align: left; background: none; border: 0; border-radius: 0; padding: 8px 10px; color: inherit; white-space: normal; }
.candidates button:hover:not(:disabled) { background: #ffffff0a; }
.candidates button.selected { background: #213a33; }
.candidates strong { display: block; font-size: 13px; font-weight: 600; }
.candidates small { display: block; font-size: 11px; color: #9aa4af; margin-top: 2px; }
.row { display: grid; grid-template-columns: var(--widths, repeat(var(--cols), minmax(0, 1fr))); gap: 0 12px; align-items: start; }
.row .field { margin: 8px 0; }
.section { margin: 16px 0 4px; padding-top: 12px; border-top: 1px solid #343c46; }
.section > h3 { margin: 0 0 4px; font-size: 12px; font-weight: 600; color: #b4bec9; letter-spacing: .04em; }
.section small { margin-left: 8px; font-weight: 400; color: var(--eco-dim); letter-spacing: 0; font-size: 12px; }
details.section > summary { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border: 1px solid #343c46; border-radius: 6px; background: #191e24;
  font-size: 13px; color: #cdd5df; cursor: pointer; list-style: none; }
details.section > summary::-webkit-details-marker { display: none; }
details.section > summary::before { content: '▸'; color: var(--gf-accent); }
details.section[open] > summary::before { content: '▾'; }
details.section[open] > summary { margin-bottom: 6px; }
details.section > summary:hover { color: var(--gf-fg); }
div.intro ul, .banner ul { margin: 4px 0 0; padding-left: 20px; line-height: 1.7; }
.banner { margin: 10px 0; align-items: flex-start; }
.banner ul { font-family: var(--eco-code); font-size: 12px; }
.commits { margin: 8px 0 10px; padding: 8px 10px; border: 1px solid #333b45; border-radius: 7px; background: #1b2027; }
.commits > div { font-size: 12px; color: #a5aeba; }
.commits ul { margin: 6px 0 0; padding-left: 18px; max-height: 180px; overflow: auto; font-size: 12px; line-height: 1.7; }
.commits code { color: #8fb8ff; margin-right: 6px; font-family: var(--eco-code); }
.commits-none { margin: 8px 0; font-size: 12px; color: #a5aeba; }
.error { margin: 8px 0 0; color: var(--eco-bad); font-size: 13px; white-space: pre-wrap; }
.error:empty { display: none; }
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; padding-top: 16px; border-top: 1px solid #343c46; flex-wrap: wrap; }
.actions .side { margin-right: auto; }
.actions.sticky { position: sticky; bottom: -24px; margin-bottom: -24px; padding-bottom: 24px; background: var(--eco-panel); z-index: 2; }
@media (max-width: 600px) { .row { grid-template-columns: 1fr; } }
}
`;
const formLookup = (data, path) => String(path || '').split('.').filter(Boolean)
  .reduce((at, key) => (at === null || at === undefined ? undefined : at[key]), data);
const formBlank = (value) => value === undefined || value === null || value === '';
const formSame = (a, b) => (a ?? null) === (b ?? null);
const FORM_LAYOUT = new Set(['section', 'note']);
const formLists = (f) => f.type === 'checks' || Boolean(f.multiple);
// [値, 見せる文字, 小さな説明] の並びを、選べるもの（{value, label, help}）に
const formOptions = (pairs) => (pairs || []).map(([value, label, help]) => ({ value: String(value ?? ''), label: String(label ?? value ?? ''), help: help || '' }));

// 入力の窓を描く。ここでするのは見せ方だけ：欄の出し分け・初めの値・必須の確かめ・値の形。打った値は state に持つ
// （読んだ値が後から届いて描き直しても、打ったものは消えない）。props は、部品 form の要る情報（parts/form/part.py）と同じ。
//
// 欄を読んだ情報から組む部品（task-form・hub-add-form）は、欄を組んで、これを呼ぶ。そのときだけ使えるもの：
// - extra.submit(今の値)：決めたとき。文字を返せば、誤りとして窓の中に出す（返さなければ、部品が自分の出力を出している）。
//   なければ、出ている欄の値を submitted で出す。extra.cancel()：やめたとき（なければ cancelled を出す）。
// - extra.changed(欄の名前, 今の値)：欄の値が変わるたび。
// - props.plain：文の中の {道筋} を置き換えない（読んだ題名などを、そのまま出す）。props.bare：題とボタンの行を出さない。
//   props.waiting：決めるボタンを出さない（要る情報を待っている）。
// - 欄の derive(get)：手で変えるまで、ほかの欄の値から決まる値。欄・ボタンの label／ok に関数(get)：ほかの欄の値で変わる文。
// 返すもの：{raw}（今の値。名前 → 値。出ていない欄も入る）
function formRender(root, props, { h, emit, state }, extra = {}) {
  const lookup = formLookup, blank = formBlank, same = formSame;
  const fields = props.fields || [];
  state.touched = state.touched || {};   // 触った欄（読んだ値が後から届いても、打ったものを残す）
  state.values = state.values || {};
  state.open = state.open || {};         // 畳める節の開閉

  // 読んだ今の値のある場所：at がなければ values そのもの。あれば、その名前をたどった先（なければ、今の値はない）
  const at = props.at === null || props.at === undefined ? [] : [].concat(props.at);
  const base = at.some((key) => key === '') ? undefined
    : at.reduce((data, key) => (data === null || data === undefined ? undefined : data[key]), props.values);
  // 道筋の値：vars（画面が渡す値）→ values（読んだ値）→ also（もう1つの読んだ値）
  const known = (path) => {
    for (const from of [props.vars || {}, base, props.also]) { const found = lookup(from, path); if (found !== undefined) return found; }
    return undefined;
  };
  // 文の中の {道筋} を、その値に（空なら、中身のないかっこごと消す）
  const fill = (text) => (props.plain ? String(text ?? '') : String(text ?? '').replace(/\{([\w.]+)\}/g, (_, path) => {
    const value = known(path);
    return blank(value) ? '' : Array.isArray(value) ? value.join('、') : String(value);
  }).replace(/（）|\(\)/g, ''));

  // 読んだ一覧（rows・more）から、選べるもの・候補を作る
  const fromRows = (from) => {
    const key = from.value || 'name', where = from.where || {};
    const source = (from.source === 'more' ? props.more : props.rows) || [];
    return source.filter((row) => Object.keys(where).every((name) => same(row[name], where[name]))).map((row) => {
      const value = String(row[key] ?? ''), label = String(row[from.label || key] ?? '');
      const notes = [].concat(from.note || []).map((name) => {
        const raw = row[name], text = Array.isArray(raw) ? raw.join('→') : String(raw ?? '');
        return (from.note_labels || {})[text] || text;
      }).filter((text) => text && text !== label);
      return { value, label: notes.length ? `${label}（${notes.join('・')}）` : label, help: '' };
    });
  };
  const normal = (list) => (list || []).map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? o.value ?? ''), help: o.help || '' }));
  const optionsOf = (f) => (f.options_from ? fromRows(f.options_from) : normal(f.options));
  const suggestionsOf = (f) => (f.suggestions_from ? fromRows(f.suggestions_from) : normal(f.suggestions));
  // 候補がまだ届いていない欄（窓は待たせず、届いたら足す）
  const pending = (f) => Boolean(f.pending) || (Boolean(props.loading) && Boolean(f.options_from || f.suggestions_from));
  const listOf = (f, raw) => (Array.isArray(raw) ? raw.map(String)
    : typeof raw === 'string' && raw !== '' ? raw.split(f.join || ',').map((item) => item.trim()).filter(Boolean) : []);
  // 初めの値：読んだ今の値 → initial → 欄の value → その種類の既定
  const first = (f) => {
    const read = f.value_from ? known(f.value_from) : base && typeof base === 'object' ? base[f.name] : undefined;
    if (f.type === 'checkbox') {
      if (f.on_value !== undefined) return read === f.on_value;
      if (f.off_value !== undefined) return read !== f.off_value;
    }
    const raw = !blank(read) ? read : !blank((props.initial || {})[f.name]) ? props.initial[f.name] : f.value;
    if (f.type === 'checkbox') return raw === true || (f.on !== undefined && raw === f.on);
    if (formLists(f)) return listOf(f, raw);
    if (Array.isArray(raw)) return raw.join(f.join || ', ');
    return blank(raw) ? '' : raw;
  };
  const named = fields.filter((f) => f.name && !FORM_LAYOUT.has(f.type));
  const byName = Object.fromEntries(named.map((f) => [f.name, f]));
  const valueOf = (f) => {
    if (state.touched[f.name]) return state.values[f.name];
    if (typeof f.derive === 'function') return f.derive(get);
    const value = first(f);
    if (f.type !== 'select' && f.type !== 'radio') return value;
    const options = optionsOf(f), text = String(value);
    if (options.some((option) => option.value === text)) return text;
    // 選べるものにない値：読んだ一覧から選ぶ欄・空の値は、見えているもの（「選ばない」か先頭）。決まった選択肢の欄は、今の値のまま見せる
    if (f.options_from || text === '') return f.type === 'select' && f.none_label !== undefined ? '' : options.length ? options[0].value : '';
    return text;
  };
  function get(name) { return byName[name] ? valueOf(byName[name]) : known(name); }
  const all = () => Object.fromEntries(named.map((f) => [f.name, valueOf(f)]));
  const textOf = (text) => (typeof text === 'function' ? String(text(get) ?? '') : fill(text));
  const matches = (map) => Object.entries(map).every(([name, want]) => {
    const now = get(name);
    return Array.isArray(want) ? want.some((one) => same(now, one)) : same(now, want);
  });
  const listed = (f) => (f.list_from ? [].concat(known(f.list_from) || []) : []);
  // 並べるもの（list_from）のある文は、並びが空なら出さない（衝突するファイルがないときの警告など）。
  // empty_text があれば、読み終えてから、代わりにその文を出す
  const visible = (item) => (!item.show_if || matches(item.show_if)) && !(item.hide_if && matches(item.hide_if))
    && !(item.type === 'note' && item.list_from && !listed(item).length && !(item.empty_text && !props.loading && known(item.list_from) !== undefined));
  const empty = (f) => { const value = valueOf(f); return Array.isArray(value) ? value.every((item) => !String(item).trim()) : String(value ?? '').trim() === ''; };
  const lacking = () => named.find((f) => f.required && visible(f) && empty(f) && !(f.empty_uses && byName[f.empty_uses] && visible(byName[f.empty_uses])));

  const holders = [];   // {item, nodes}：出し分けのために覚える（欄・節・表の行・ボタン）
  const rows = [];      // 横に並べた行（中の欄が全部隠れたら、行も隠す）
  const live = [];      // ほかの欄の値で変わる所（値が変わるたびに直す）
  const error = h('p', { class: 'error', role: 'alert' }, state.error || props.problem || props.error || '');
  const refresh = () => {
    for (const update of live) update();
    for (const { item, nodes } of holders) for (const node of nodes) node.hidden = !visible(item);
    for (const row of rows) row.hidden = [...row.children].every((child) => child.hidden);
  };
  const set = (f, value) => {
    state.touched[f.name] = true;
    state.values[f.name] = value;
    if (state.error) { state.error = ''; error.textContent = props.problem || props.error || ''; }
    refresh();
    if (extra.changed) extra.changed(f.name, all());
  };
  // 文（関数なら、値が変わるたびに直す）を入れた要素
  const text = (tag, attrs, source) => {
    const node = h(tag, attrs, textOf(source));
    if (typeof source === 'function') live.push(() => { node.textContent = textOf(source); });
    return node;
  };

  const control = (f) => {
    const now = valueOf(f);
    const help = f.help ? h('small', { class: 'help' }, fill(f.help)) : '';
    const title = f.required ? h('span', {}, fill(f.label), h('span', { class: 'req', 'aria-hidden': 'true' }, '*')) : fill(f.label);
    const more = pending(f) ? ' more' : '';
    if (f.type === 'checkbox') {
      const input = h('input', { type: 'checkbox' });
      input.checked = now === true;
      input.addEventListener('change', () => set(f, input.checked));
      return h('div', { class: 'f' }, h('label', { class: f.strong ? 'check strong' : 'check' }, input, text('span', {}, f.label)), help);
    }
    if (f.type === 'radio') {
      const box = h('fieldset', { class: ['f', f.inline ? 'inline' : '', f.columns ? 'cols' : '', f.strong ? 'strong' : ''].filter(Boolean).join(' ') },
        h('legend', f.label_hidden ? { class: 'sr-only' } : {}, title));
      if (f.columns) box.style.setProperty('--cols', String(f.columns));
      for (const option of optionsOf(f)) {
        const input = h('input', { type: 'radio', name: f.name, value: option.value });
        input.checked = option.value === now;
        input.addEventListener('change', () => { if (input.checked) set(f, option.value); });
        box.append(h('label', {}, input, h('span', {}, h('strong', {}, option.label), option.help ? h('small', {}, option.help) : '')));
      }
      if (help) box.append(help);
      return box;
    }
    if (f.type === 'checks') {
      const options = optionsOf(f), list = h('div', {});
      for (const option of options) {
        const input = h('input', { type: 'checkbox', value: option.value });
        input.checked = now.includes(option.value);
        input.addEventListener('change', () => {
          const picked = valueOf(f).filter((item) => item !== option.value);
          if (input.checked) picked.push(option.value);
          set(f, options.map((o) => o.value).filter((item) => picked.includes(item)));   // 選べるものの順に（手順の順・一覧の順）
        });
        list.append(h('label', {}, input, h('span', {}, option.label)));
      }
      if (!options.length && !more) list.append(h('small', { class: 'help' }, props.loading ? '読み込み中…' : f.empty_text || '選べるものがありません。'));
      const box = h('fieldset', { class: 'f checks' + more }, h('legend', {}, title), list);
      if (help) box.append(help);
      return box;
    }
    if (f.multiple) {   // いくつも入れる欄：＋ で足し、× で消す
      const list = h('div', { class: 'multi' });
      const items = now.length ? [...now] : [''];
      const draw = (focus) => {
        list.replaceChildren(...items.map((value, index) => {
          const input = h('input', { type: 'text', placeholder: fill(f.placeholder), autocomplete: 'off', 'aria-label': fill(f.label) });
          input.value = value;
          input.addEventListener('input', () => { items[index] = input.value; set(f, [...items]); });
          const button = index === 0 ? h('button', { type: 'button', title: `${fill(f.label)}の欄を足す`, 'aria-label': `${fill(f.label)}の欄を足す` }, '＋')
            : h('button', { type: 'button', title: 'この欄を消す', 'aria-label': 'この欄を消す' }, '×');
          button.addEventListener('click', () => {
            if (index === 0) items.push(''); else items.splice(index, 1);
            set(f, [...items]);
            draw(index === 0 ? items.length - 1 : Math.min(index, items.length - 1));
          });
          return h('div', { class: 'multi-item' }, input, button);
        }));
        if (focus !== undefined) list.children[focus].querySelector('input').focus();
      };
      draw();
      return h('div', { class: 'f field' }, title, list, help);
    }
    let input, extras = [];
    if (f.type === 'select') {
      const options = optionsOf(f);
      if (String(now) !== '' && !options.some((option) => option.value === String(now))) options.push({ value: String(now), label: String(now) });
      input = h('select', {});
      if (f.none_label !== undefined) input.append(h('option', { value: '' }, fill(f.none_label)));
      for (const option of options) input.append(h('option', { value: option.value }, option.label));
      if (!options.length && f.none_label === undefined) input.append(h('option', { value: '' }, props.loading ? '読み込み中…' : f.empty_text || '（選べるものがありません）'));
      input.value = String(now);
      input.addEventListener('change', () => set(f, input.value));
    } else if (f.type === 'textarea') {
      input = h('textarea', { rows: String(f.rows || 4), placeholder: fill(f.placeholder), spellcheck: 'false' });
      input.value = String(now);
      input.addEventListener('input', () => set(f, input.value));
    } else {
      input = h('input', { type: f.type === 'number' || f.type === 'date' ? f.type : 'text', placeholder: fill(f.placeholder), autocomplete: 'off', spellcheck: 'false' });
      if (f.hint) input.title = fill(f.hint);
      if (f.type === 'number') { input.min = String(f.min ?? 0); if (f.step !== undefined) input.step = String(f.step); }
      input.value = String(now);
      input.addEventListener('input', () => set(f, input.value));
      // 手で変えるまで、ほかの欄の値から決まる値
      if (typeof f.derive === 'function') live.push(() => { if (!state.touched[f.name]) input.value = String(valueOf(f)); });
      const suggestions = suggestionsOf(f);   // 打つときの候補（選ぶと、その値が入る）
      if (suggestions.length) {
        const id = 'suggest-' + f.name;
        input.setAttribute('list', id);
        extras = [h('datalist', { id }, ...suggestions.map((s) => h('option', s.label !== s.value ? { value: s.value, label: s.label } : { value: s.value })))];
      }
    }
    return h('label', { class: 'f field' + (f.type !== 'textarea' && more ? ' more' : '') }, title, input, ...extras, help);
  };
  // 欄の下に並べる候補（押すと、その欄に入る）。candidates が null なら、まだ届いていない
  const candidates = (f, target) => {
    const box = h('div', { class: 'f candidates', 'aria-live': 'polite' });
    if (!f.candidates) {
      box.append(h('p', {}, h('span', { class: 'spinner' }), ' ' + (f.candidates_loading || '候補を読み込んでいます…')));
      return box;
    }
    if (!f.candidates.length) { box.append(h('p', {}, f.candidates_empty || '候補はありません。')); return box; }
    const list = h('ul', {});
    for (const one of normal(f.candidates)) {
      const pick = h('button', { type: 'button', class: valueOf(f) === one.value ? 'selected' : '' }, h('strong', {}, one.label), h('small', {}, one.help));
      pick.addEventListener('click', () => {
        target.value = one.value;
        for (const other of list.querySelectorAll('button')) other.classList.toggle('selected', other === pick);
        set(f, one.value);
      });
      list.append(h('li', {}, pick));
    }
    box.append(h('p', {}, f.candidates_title || '候補'), list);
    return box;
  };
  const note = (f) => {
    const names = listed(f);
    if (f.list_as === 'commits') {   // 入るコミットの一覧（「sha 件名」の並び。先頭の語を符号の字で）
      if (!names.length) return h('p', { class: 'f commits-none' }, fill(f.empty_text));
      return h('div', { class: 'f commits' }, h('div', {}, fill(f.label)), h('ul', {}, ...names.map((line) => {
        const [sha, ...subject] = String(line).split(' ');
        return h('li', {}, h('code', {}, sha), ' ' + subject.join(' '));
      })));
    }
    if (f.list_from && !names.length) return h('div', { class: 'f intro' }, fill(f.empty_text));
    const list = names.length ? h('ul', {}, ...names.map((name) => h('li', {}, String(name)))) : '';
    if (!f.tone && !list) return text('div', { class: 'f intro' }, f.label);   // 文だけ（空なら出ない）
    return f.tone ? h('div', { class: `f banner ${f.tone === 'warn' ? '' : f.tone}`.trim(), role: f.tone === 'bad' ? 'alert' : 'note' }, h('div', {}, text('span', {}, f.label), list))
      : h('div', { class: 'f intro' }, text('span', {}, f.label), list);
  };

  const form = h('form', { class: 'eco-form', novalidate: '' });
  const heading = fill(props.title) + (props.subject ? '：' + props.subject : '');
  if (heading && !props.bare) form.append(h('h2', {}, heading));
  if (props.intro) form.append(h('p', { class: 'intro' }, fill(props.intro)));
  if (props.detail) form.append(h('p', { class: 'intro' }, fill(props.detail)));
  if (props.loading && !props.bare) form.append(h('p', { class: 'intro', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…'));
  if ((props.outcome || []).length) {
    const table = h('dl', { class: 'outcome' });
    for (const row of props.outcome) {
      const nodes = [h('dt', {}, fill(row.label)), h('dd', {}, fill(row.text))];
      table.append(...nodes);
      holders.push({ item: row, nodes });
    }
    form.append(table);
  }
  let into = form, row = null, rowName = '';
  for (const f of fields) {
    if (f.type === 'section') {
      row = null; rowName = '';
      if (f.end) { into = form; continue; }
      const title = [fill(f.label), f.note ? h('small', {}, fill(f.note)) : ''];
      if (f.collapsed === undefined) {
        into = h('div', { class: 'section' }, h('h3', {}, ...title));
      } else {
        const key = String(f.label), section = h('details', { class: 'section' }, h('summary', {}, ...title));
        section.open = key in state.open ? state.open[key] : f.open === true || !f.collapsed;
        section.addEventListener('toggle', () => { state.open[key] = section.open; });
        into = section;
      }
      if (f.help) into.append(h('p', { class: 'help' }, fill(f.help)));
      form.append(into);
      holders.push({ item: f, nodes: [into] });
      continue;
    }
    const node = f.type === 'note' ? note(f) : control(f);
    const nodes = [node];
    if ('candidates' in f && f.type !== 'note') nodes.push(candidates(f, node.querySelector('input')));
    holders.push({ item: f, nodes });
    if (f.row) {
      if (f.row !== rowName) { row = h('div', { class: 'row' }); rowName = f.row; rows.push(row); into.append(row); row.widths = []; }
      row.append(node);
      row.widths.push(Number(f.width) || 1);
      row.style.setProperty('--cols', String(row.children.length));
      if (row.widths.some((width) => width !== 1)) row.style.setProperty('--widths', row.widths.map((width) => `minmax(0, ${width}fr)`).join(' '));
    } else {
      row = null; rowName = '';
      into.append(...nodes);
    }
  }

  // 出す値（出ている欄だけ。値の形を整える）
  const collect = () => {
    const values = {};
    for (const f of named) {
      if (!visible(f)) continue;
      let value = valueOf(f);
      if (f.type === 'checkbox') {
        if (f.inverse) values[f.inverse] = !value;
        if (f.on !== undefined) value = value ? f.on : f.off;
      } else if (formLists(f)) {
        value = value.map((item) => String(item).trim()).filter(Boolean);
        if (f.join !== undefined) value = value.length ? value.join(f.join) : f.empty || '';
      } else {
        value = String(value ?? '').trim();
        if (value === '' && f.empty_uses && byName[f.empty_uses] && visible(byName[f.empty_uses])) value = String(valueOf(byName[f.empty_uses]) ?? '');
        if (f.type === 'number' && value !== '') value = Number(value);
      }
      values[f.name] = value;
    }
    return values;
  };
  const fail = (message) => { state.error = message; error.textContent = message; };
  const submit = () => {
    const missing = lacking();
    if (missing) {   // 誤りは窓の中に出す（入れた値は残る）
      const label = fill(missing.label).replace(/（[^（）]*）$/, '');
      return fail(missing.type === 'checks' ? `${label}を、1つ以上選んでください。` : `${label}を入力してください。`);
    }
    if (!extra.submit) return emit('submitted', { values: collect() });
    const problem = extra.submit(all());
    fail(typeof problem === 'string' ? problem : '');
  };
  form.append(error);
  if (!props.bare) {
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => (extra.cancel ? extra.cancel() : emit('cancelled', {})));
    const buttons = h('div', { class: props.sticky ? 'actions sticky' : 'actions' });
    // 決めるほかにできること（左に置くボタン。今の値と一緒に、名前を出す）
    for (const action of props.actions || []) {
      const button = h('button', { type: 'button', class: action.primary ? 'side primary' : 'side', title: fill(action.hint) }, fill(action.label));
      button.addEventListener('click', () => emit('action', { name: action.name, values: collect() }));
      buttons.append(button);
      holders.push({ item: action, nodes: [button] });
    }
    buttons.append(cancel);
    if (!props.waiting) buttons.append(text('button', { type: 'submit', class: props.danger ? 'danger' : 'primary' }, typeof props.ok === 'function' ? props.ok : fill(props.ok) || 'OK'));
    form.append(buttons);
  }
  form.addEventListener('submit', (event) => { event.preventDefault(); if (!props.bare && !props.waiting) submit(); });
  form.addEventListener('keydown', (event) => {   // Ctrl+Enter：どの欄にいても決める（本文の欄の中でも）
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !props.bare && !props.waiting) { event.preventDefault(); submit(); }
  });
  refresh();
  root.replaceChildren(h('style', {}, FORM_CSS), form);
  return { raw: all() };
}

export default {
  form: { render: formRender, options: formOptions },
  task: { STAGES, STAGE, PRIORITIES, marks: taskMarks, filter: taskFilter, today: taskToday, md: taskMd, currentSprint: taskCurrentSprint },
};
