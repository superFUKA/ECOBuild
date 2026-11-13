// 部品「タスクの入力の窓」。読んだ情報（タスク・スプリント・ブランチ・アカウント）から欄を組むだけ。
// 描くのは共有のコード（lib.js の form）。決めると、入れた値を出力する（入れていない欄は出さない。コマンドは、つなぎが呼ぶ）。
const commaList = (text) => String(text || '').split(',').map((s) => s.trim()).filter(Boolean);
// タスクブランチの名前（task/<番号>-<名前>）。日本語はそのまま。git と Windows が受けない字は - にする（ecobuild と同じ直し方）
const branchLabel = (title) => {
  let label = String(title || '').replace(/[\s~^:?*[\]\\/"<>|\x00-\x1f\x7f]+|\.{2,}|@\{/g, '-').replace(/-{2,}/g, '-').replace(/^[-.]+|[-.]+$/g, '');
  while (label.endsWith('.lock')) label = label.slice(0, -5).replace(/[-.]+$/, '');
  return label;
};
const branchNameError = (name) => (!name.trim() ? 'タスクブランチの名前を入力してください。'
  : branchLabel(name.trim()) !== name.trim() ? 'タスクブランチの名前に使えない文字があります（空白と ~ ^ : ? * [ ] \\ / " < > | と「..」）。' : '');
const taskOfBranch = (name) => { const m = /^task\/(\d+)(?:-.+)?$/.exec(name || ''); return m ? Number(m[1]) : null; };
const BRANCH_HELP = '日本語も使えます（空白と ~ ^ : ? * [ ] \\ / " < > | は使えません）。';
const END = { type: 'section', end: true };

// 窓ごとの欄。返すもの：{title, intro, fields, ok, sticky, wait, submit(x) → 誤りの文 か [出力, 中身]}（x：今入っている値）
function specOf(props, lib) {
  const options = lib.form.options, md = lib.task.md;
  const id = String(props.issue), d = props.status, me = (props.account && props.account.login) || '';
  const currentSprint = lib.task.currentSprint(props.sprints);
  const sprintOptions = options(props.sprints.map((s) => [s.name, s.name + '（' + md(s.start) + '〜' + md(s.end) + '）' + (s.name === currentSprint ? ' ・今' : '')]));
  // 担当者の候補：自分、タスクの担当者、GitHub のメンバー（後から届く）
  const known = [...new Set([...props.tasks.flatMap((t) => t.assignees || []), ...props.members.map((m) => m.login)].filter((m) => m && m !== me))].sort((a, b) => a.localeCompare(b));
  const members = [...(me ? [me] : []), ...known];
  const memberOptions = (list) => options(list.map((m) => [m, m === me ? m + '（自分）' : m]));
  const byNumber = (n) => props.tasks.find((t) => t.number === n);
  const parentOptions = (self, current) => options([...props.tasks.filter((t) => t.number !== self && ((t.state || 'open') === 'open' || t.number === current))
    .sort((a, b) => a.number - b.number).map((t) => [String(t.number), '#' + t.number + ' ' + t.title]),
  ...(current && !byNumber(current) ? [[String(current), '#' + current]] : [])]);
  const some = (payload) => Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== '' && value !== false && value !== null && value !== undefined));
  const needStatus = { wait: true, title: '#' + id, fields: [], submit: () => '' };

  if (props.kind === 'new') {
    const parent = /^\d+$/.test(props.text) && props.text !== '0' ? props.text : '';
    return { title: '新しいタスク', ok: '作成', sticky: true, fields: [
      { name: 'title', label: '題名', required: true },
      { name: 'body', label: '本文', type: 'textarea', rows: 3, placeholder: '背景・完了の条件など（任意）' },
      { name: 'stage', label: '段階', type: 'radio', inline: true, value: 'todo', hide_if: { start: true },
        options: options([['todo', '未着手'], ['planned', '計画中', 'まだ着手しない（内容・時期を詰めている）']]) },
      { name: 'assignees', label: '担当者', type: 'checks', options: memberOptions(members), pending: props.loading,
        empty_text: 'まだ候補がありません（下の「候補にいない担当者」で入力できます）' },
      { type: 'section', label: '＋ 候補にいない担当者', collapsed: true },
      { name: 'otherAssignees', label: 'GitHubのアカウント', placeholder: 'カンマ区切り（任意）' },
      END,
      { type: 'section', label: '計画' },
      { name: 'priority', label: '優先度', type: 'select', row: 'plan', none_label: 'なし', options: options(lib.task.PRIORITIES.map((p) => [p, p])) },
      { name: 'estimate', label: '見積もり', type: 'number', step: 0.5, row: 'plan' },
      { name: 'sprint', label: 'スプリント', type: 'select', row: 'plan', none_label: 'なし', options: sprintOptions },
      { name: 'plannedStart', label: '開始予定日', type: 'date', row: 'dates' }, { name: 'plannedEnd', label: '終了予定日', type: 'date', row: 'dates' },
      { name: 'due', label: '期限', type: 'date', row: 'dates' },
      { type: 'section', label: '分類・つながり', note: 'ラベル・マイルストーン・親タスク・先に終わるべきタスク', collapsed: true, open: Boolean(parent) },
      { name: 'label', label: 'ラベル', row: 'tags', placeholder: 'カンマ区切り。なければ作ります' },
      { name: 'milestone', label: 'マイルストーン', type: 'select', row: 'tags', none_label: 'なし',
        options: options(props.milestones.map((m) => [m.title, m.title + (m.due ? '（' + m.due + '）' : '')])) },
      { name: 'parent', label: '親タスク', type: 'select', row: 'links', value: parent, none_label: 'なし', options: parentOptions(0, Number(parent) || 0) },
      { name: 'blockedBy', label: '先に終わるべきタスク', row: 'links', placeholder: '番号（カンマ区切り）' },
      END,
      { name: 'start', label: '作成したら、作業空間を作って作業を開始する（担当者を選ばなければ自分になります）', type: 'checkbox', strong: true },
      // タスクブランチの名前は、手で変えるまで題名に合わせる
      { name: 'name', label: 'タスクブランチの名前', required: true, show_if: { start: true }, derive: (get) => branchLabel(get('title')),
        help: 'task/〈番号〉-〈名前〉のブランチになります（既定は題名）。' + BRANCH_HELP },
    ], submit: (x) => {
      if (x.start) { const error = branchNameError(x.name || ''); if (error) return error; }
      const assignees = [...new Set([...x.assignees, ...commaList(x.otherAssignees)])];
      return ['new', some({ title: x.title.trim(), body: x.body, stage: !x.start && x.stage === 'planned' ? 'planned' : '', assignee: assignees.join(','),
        priority: x.priority, estimate: String(x.estimate || ''), sprint: x.sprint, planned_start: x.plannedStart, planned_end: x.plannedEnd, due: x.due,
        label: x.label, milestone: x.milestone, parent: x.parent, blocked_by: x.blockedBy, start: x.start, name: x.start ? x.name.trim() : '' })];
    } };
  }

  if (props.kind === 'start') {
    if (!d) return needStatus;
    const t = byNumber(d.number) || {}, title = d.title || t.title || '';
    const parent = (d.parent && d.parent.number) || t.parent || 0;
    const existing = d.branch || t.branch || null;  // 既にタスクブランチがある（手元か GitHub）：名前はそのまま
    // 既定の作成元：子タスクは親のタスクブランチ、GitHub にあるものは記録された作成元、ほかはモジュールの既定
    const parentTask = parent ? byNumber(parent) : null;
    const parentBranch = parent ? (parentTask && parentTask.branch) || 'task/' + parent + (parentTask && branchLabel(parentTask.title) ? '-' + branchLabel(parentTask.title) : '') : '';
    const fallback = (props.account && props.account.default_base) || '';
    const base = parent ? parentBranch : d.remote && d.base ? d.base : fallback;
    const usable = props.branches.filter((b) => !b.unusable);
    const choices = parent || d.remote ? [] : [...usable.filter((b) => !b.is_task_branch), ...usable.filter((b) => b.is_task_branch && taskOfBranch(b.name) !== d.number)]
      .filter((b) => b.name !== base).map((b) => {
        const task = b.is_task_branch ? byNumber(taskOfBranch(b.name)) : null;
        return [b.name, b.is_task_branch ? b.name + '（タスクブランチ' + (task ? '：' + task.title : '') + '）' : b.name + (b.local ? '' : '（GitHubだけ）')];
      });
    const active = (props.accounts.find((a) => a.active) || {}).login || '?';
    const others = me && !(d.assignees || []).includes(me) ? d.assignees || [] : [];
    const notNone = { place: 'none' };
    return { title: (d.remote ? '作業を再開' : '作業を開始') + '：#' + id, intro: title, ok: '開始', fields: [
      { name: 'place', label: '作業の場所', type: 'radio', value: 'workspace', options: options([
        ['workspace', '作業空間を作る', 'タスクブランチの作業空間をモジュールの中（.ecobuild/w/' + id + '）に作ります。完了する・作業を捨てると消えます'],
        ['none', 'タスクブランチを作らない', '調査・設計など、コードを変えないタスク（状態を作業中にするだけ）']]) },
      ...(props.accounts.length > 1 ? [{ name: 'account', label: '作業空間で使う GitHub のアカウント（AI 用のアカウント等。push・提出・コミットの作者がそのアカウントになります）', type: 'select', hide_if: notNone,
        none_label: 'gh の使用中のアカウント（' + active + '）', options: options(props.accounts.filter((a) => !a.active).map((a) => [a.login, a.login])) }] : []),
      ...(existing ? [] : [{ name: 'name', label: 'タスクブランチの名前', required: true, value: branchLabel(title), hide_if: notNone,
        help: 'task/' + id + '-〈名前〉のブランチになります。' + BRANCH_HELP }]),
      // 作成元の候補（ブランチの一覧）は、後から届く
      { name: 'base', label: '作成元のブランチ', type: 'select', hide_if: notNone, none_label: base + (base && base === fallback ? '（既定）' : ''), options: options(choices),
        pending: props.loading && !parent && !d.remote,
        help: parent ? '子タスクは親タスクのタスクブランチ（' + parentBranch + '）から作ります。' : d.remote ? 'GitHubにあるタスクブランチから再開します（作成元は記録されているものを使います）。' : '' },
      ...((d.blocked_by || []).some((b) => (b.state || 'open') === 'open') ? [{ name: 'ignoreBlocked', label: '先に終わるべきタスクが開いていても始める', type: 'checkbox' }] : []),
      ...(others.length ? [{ name: 'takeOver', label: others.join('、') + ' から引き継ぐ（担当者を自分にし、タスクに残します）', type: 'checkbox',
        help: 'ほかの人が担当しています。重ねて作業しないよう、相談してから引き継いでください。' }] : []),
    ], submit: (x) => {
      if (others.length && !x.takeOver) return others.join('、') + ' が担当しています。引き継ぐ場合は「引き継ぐ」に印を付けてください。';
      const none = x.place === 'none';
      if (!none && !existing) { const error = branchNameError(x.name || ''); if (error) return error; }
      return ['start', some({ id, no_branch: none, name: !none && !existing ? x.name.trim() : '', base: none ? '' : x.base, account: none ? '' : x.account,
        ignore_blocked: x.ignoreBlocked, take_over: x.takeOver })];
    } };
  }

  if (props.kind === 'edit') {
    if (!d) return needStatus;
    const current = (d.parent && d.parent.number) || 0, blocked = d.blocked_by || [];
    return { title: 'タスク #' + id + ' を編集', ok: '保存', fields: [
      { name: 'title', label: '題名', value: d.title || '', required: true }, { name: 'body', label: '本文', type: 'textarea', value: d.body || '', rows: 6 },
      { type: 'section', label: 'つながり' },
      { name: 'parent', label: '親タスク', type: 'select', value: current ? String(current) : '', none_label: 'なし', options: parentOptions(d.number, current) },
      { name: 'addBlocked', label: '先に終わるべきタスクを追加', row: 'blocked', placeholder: '番号（カンマ区切り）' },
      { name: 'removeBlocked', label: '先に終わるべきタスクから外す', row: 'blocked', placeholder: '番号（カンマ区切り）',
        help: blocked.length ? '今：' + blocked.map((b) => '#' + b.number).join('、') : '今はありません。' },
      END,
    ], submit: (x) => {
      const parent = Number(x.parent) || 0;
      // 別の親へ移す：今の親から外して付ける（ecobuild task edit --clear-parent --parent <番号> の1回で）
      const moved = parent !== current;
      const payload = some({ title: x.title !== (d.title || '') ? x.title : '', body: x.body !== (d.body || '') ? x.body : '',
        parent: moved && parent ? String(parent) : '', clear_parent: moved && Boolean(current), add_blocked_by: x.addBlocked, remove_blocked_by: x.removeBlocked });
      if (!Object.keys(payload).length) return '変更する内容がありません。';
      return ['edit', { id, ...payload }];
    } };
  }

  // 担当者を追加
  const already = (d && d.assignees) || (byNumber(props.issue) || {}).assignees || [];
  return { title: '担当者を追加：#' + id, ok: '追加', fields: [
    { name: 'who', label: '担当者', type: 'checks', options: memberOptions(members.filter((m) => !already.includes(m))), pending: props.loading,
      empty_text: '候補者はすべて担当済みです（下の欄に入力できます）' },
    { name: 'other', label: '候補にいない担当者（GitHubのアカウント、カンマ区切り。任意）' }],
  submit: (x) => {
    const who = [...new Set([...x.who, ...commaList(x.other)])];
    return who.length ? ['edit', { id, add_assignee: who.join(',') }] : '担当者を選んでください。';
  } };
}

export default {
  render(root, props, tools) {
    const spec = specOf(props, tools.lib);
    tools.lib.form.render(root, {
      plain: true, title: spec.title, intro: spec.intro || '', fields: spec.fields, ok: spec.ok, sticky: spec.sticky,
      waiting: spec.wait, loading: spec.wait, problem: props.error,
    }, tools, {
      submit: (x) => {
        const result = spec.submit(x);
        if (typeof result === 'string') return result;
        tools.emit(result[0], result[1]);
        return undefined;
      },
      cancel: () => tools.emit('cancel', {}),
    });
  },
};
