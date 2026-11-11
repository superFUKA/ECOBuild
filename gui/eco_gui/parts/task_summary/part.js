// 部品「タスク管理の概要」。数は届いたまま（数えるのは ecobuild）。タイル・バーの幅と色は見せ方だけ。押すと、その表示へ（go）。
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

export default {
  render(root, props, { h, emit, menu }) {
    const marks = taskMarks(h, emit, menu, props.sprints, props.me);
    const { md, open, deleted } = marks;
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    if (props.loading && props.tasks.length === 0) return root.replaceChildren(marks.loading('集計しています…'));
    const go = (screen, more) => () => emit('go', { screen, ...(more || {}) });
    const opened = props.tasks.filter(open), count = (stage) => opened.filter((t) => marks.stageOf(t) === stage).length;
    const late = props.overdue.overdue || [], soon = props.overdue.soon || [];
    const clock = new Date(Date.now() - 7 * 86400000);
    const weekAgo = new Date(clock.getTime() - clock.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const finished = props.tasks.filter((t) => !open(t) && !deleted(t) && t.finished).sort((a, b) => String(b.finished).localeCompare(String(a.finished)));
    const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
    const width = (node, value) => { node.setAttribute('style', 'width:' + value + '%'); return node; };
    const none = (text) => h('p', { class: 'tk-muted' }, text);
    const card = (title, body, options) => {
      const o = options || {};
      const head = h('div', { class: 'tk-section-head' }, h('h3', {}, title, ...(o.sub ? [h('span', { class: 'tk-muted' }, o.sub)] : [])));
      if (o.go) { const link = h('button', { type: 'button', class: 'tk-link' }, '開く ›'); link.addEventListener('click', go(o.go)); head.append(link); }
      return h('section', { class: 'tk-card dash-card' }, head, ...body);
    };
    // 表示を開くタイルは、押せる形（›）。ほかは平ら
    const big = (label, value, cls, screen) => {
      const inner = [h('b', {}, String(value)), h('span', {}, label)];
      if (!screen) return h('div', { class: 'stat ' + cls }, ...inner);
      const tile = h('button', { type: 'button', class: 'stat go ' + cls }, ...inner);
      tile.addEventListener('click', go(screen));
      return tile;
    };
    const row = (t, ...extra) => {
      const line = h('div', { class: 'tk-next-row', tabindex: '0' }, marks.num(t), h('span', { class: 'tk-grow' }, t.title), ...extra, marks.prio(t), marks.due(t), marks.est(t), ...marks.avatars(t));
      line.setAttribute('aria-selected', String(String(t.number) === String(props.selected || '')));
      return marks.pick(line, t);
    };

    // 段階：開いているタスクを、1本のバーで
    const bar = h('div', { class: 'stagebar' });
    for (const [key, label, cls] of STAGES.slice(0, 4)) {
      if (!count(key)) continue;
      const seg = h('button', { type: 'button', class: 'seg ' + cls, title: label + ' ' + count(key) });
      seg.setAttribute('style', 'flex:' + count(key));
      seg.setAttribute('aria-label', label + ' ' + count(key));
      seg.addEventListener('click', go('board'));
      bar.append(seg);
    }
    const keys = h('div', { class: 'tk-stagekeys' }, ...STAGES.slice(0, 4).map(([key, label]) => marks.stageMark(key, label + ' ' + count(key))));

    const s = props.sprint;
    const sprintBody = !s ? [none(props.sprints.length ? '今日を含むスプリントはありません。' : 'スプリントはまだありません。')] : [
      h('div', { class: 'dash-sprint' }, h('div', {}, h('b', {}, s.done + ' / ' + s.total), h('span', {}, '完了')), h('div', {}, h('b', {}, String(s.estimate_remaining)), h('span', {}, '見積もりの残り')),
        h('div', {}, h('b', {}, String(s.days_left)), h('span', {}, '残り日数'))),
      h('div', { class: 'tk-progress', title: '完了 ' + pct(s.done, s.total) + '%' }, width(h('span', {}), pct(s.estimate_done, s.estimate_total) || pct(s.done, s.total))),
      ...((s.unestimated || []).length ? [h('p', { class: 'tk-note' }, '見積もりのないタスク ' + s.unestimated.length + ' 件')] : []),
      ...((s.carried_over || []).length ? [h('p', { class: 'tk-note' }, '持ち越し ' + s.carried_over.length + ' 件')] : [])];

    const ms = props.milestones.map((m) => {
      const line = h('button', { type: 'button', class: 'dash-row' },
        h('span', { class: 'tk-grow' }, m.title, ...(m.due ? [h('small', { class: m.late ? 'tk-due overdue' : 'tk-muted' }, ' ' + md(m.due) + (m.late ? ' 期日超過' : ''))] : [])),
        h('span', { class: 'minibar' }, width(h('span', {}), pct(m.done, m.total))), h('span', { class: 'tk-muted' }, m.done + '/' + m.total),
        ...((m.overdue_tasks || []).length ? [h('span', { class: 'tk-reason' }, '期限切れ ' + m.overdue_tasks.length)] : []));
      line.addEventListener('click', go('tasks', { milestone: m.title }));
      return line;
    });
    const people = props.workload.filter((w) => w.open), most = Math.max(1, ...people.map((w) => w.open));
    const wl = people.map((w) => {
      const line = h('button', { type: 'button', class: 'dash-row' }, marks.avatarMark(w.assignee),
        h('span', { class: 'dash-name' }, (w.assignee || '担当なし') + (w.assignee && w.assignee === props.me ? '（自分）' : '')),
        h('span', { class: 'minibar' }, width(h('span', {}), pct(w.open, most)), width(h('span', { class: 'doing' }), pct(w.in_progress, most))),
        h('span', { class: 'tk-muted' }, w.open + ' 件・作業中 ' + w.in_progress + (w.estimate_remaining ? '・残り ' + w.estimate_remaining : '')),
        ...(w.overdue ? [h('span', { class: 'tk-reason' }, '期限切れ ' + w.overdue)] : []));
      line.addEventListener('click', w.assignee ? () => emit('dialog', { screen: 'task-person', id: '0', text: w.assignee }) : go('tasks', { assignee: '-' }));
      return line;
    });
    const prRow = (t) => {
      const line = h('div', { class: 'tk-next-row', tabindex: '0' }, marks.num(t), h('span', { class: 'tk-grow' }, t.title), marks.submissionPill(t.submission || {}), ...marks.avatars(t));
      return marks.pick(line, t);
    };
    const asked = props.reviews, openPrs = props.tasks.filter((t) => open(t) && t.submission);
    const h4 = (text) => h('h4', { class: 'dash-h' }, text);

    root.replaceChildren(h('div', { class: 'dash' },
      h('div', { class: 'stats wide' }, big('開いているタスク', opened.length, '', 'tasks'), big('作業中', count('in_progress'), '', 'board'), big('レビュー待ち', count('in_review'), '', 'board'),
        big('期限切れ', late.length, late.length ? 'bad' : '', 'task-next'), big('この1週間に完了', finished.filter((t) => t.finished >= weekAgo).length, ''),
        big('レビューの依頼', asked.length, asked.length ? 'warn' : '')),
      card('段階', [bar, keys], { go: 'board', sub: '開いている ' + opened.length + ' 件' }),
      card(s ? '今のスプリント：' + s.sprint.name : '今のスプリント', sprintBody, { go: 'task-sprint', sub: s ? md(s.sprint.start) + '〜' + md(s.sprint.end) : '' }),
      card('自分の次のタスク', props.next.length ? props.next.map((x, i) => row(x.task, h('span', { class: 'tk-rank' }, String(i + 1)), ...(x.reasons || []).slice(0, 2).map((r) => h('span', { class: 'tk-reason' }, r))))
        : [none('自分が担当していて、着手できるタスクはありません。')], { go: 'task-next' }),
      card('期限', late.length || soon.length ? [...late.map((t) => row(t, h('span', { class: 'tk-reason bad' }, '期限切れ'))), ...soon.map((t) => row(t, h('span', { class: 'tk-reason' }, '7日以内')))]
        : [none('期限切れ・期限が近いタスクはありません。')], { go: 'task-next' }),
      card('マイルストーン', ms.length ? ms : [none('開いているマイルストーンはありません。')]),
      card('担当者ごとの量', wl.length ? wl : [none('開いているタスクはありません。')], { sub: '親タスクは数えません' }),
      card('提出', [...(asked.length ? [h4('見るように頼まれた提出'), ...asked.map(prRow)] : []),
        ...(openPrs.length ? [h4('提出中 ' + openPrs.length), ...openPrs.slice(0, 6).map(prRow)] : [none('提出中のタスクはありません。')])]),
      card('最近完了したタスク', finished.length ? finished.slice(0, 6).map((t) => row(t, h('span', { class: 'tk-muted' }, md(t.finished)))) : [none('まだありません。')])));
  },
};
