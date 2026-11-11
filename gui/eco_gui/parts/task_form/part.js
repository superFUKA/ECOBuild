// 部品「タスクの入力の窓」。欄を描き、入れた値を出力するだけ（入れていない欄は出さない。コマンドは、つなぎが呼ぶ）。
// 入れている途中の値は、この部品が持つ（state）。欄の出し分け（「作ったら始める」で名前の欄が出る 等）は見せ方。
const PRIORITIES = ['High', 'Middle', 'Low'];
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
const md = (d) => (d ? Number(d.slice(5, 7)) + '/' + Number(d.slice(8, 10)) : '');
const BRANCH_HELP = '日本語も使えます（空白と ~ ^ : ? * [ ] \\ / " < > | は使えません）。';

// 窓ごとの欄。v：今入っている値。返すもの：{title, intro, fields, ok, danger, wait, submit(v) → 誤りの文 か [出力, 中身]}
function specOf(props, v) {
  const id = String(props.issue), d = props.status, me = (props.account && props.account.login) || '';
  const today = (() => { const c = new Date(); return new Date(c.getTime() - c.getTimezoneOffset() * 60000).toISOString().slice(0, 10); })();
  const currentSprint = (props.sprints.find((s) => s.start <= today && today < s.end) || {}).name || '';
  const sprintOptions = [['', 'なし'], ...props.sprints.map((s) => [s.name, s.name + '（' + md(s.start) + '〜' + md(s.end) + '）' + (s.name === currentSprint ? ' ・今' : '')])];
  const known = [...new Set(props.tasks.flatMap((t) => t.assignees || []).filter((m) => m !== me))].sort((a, b) => a.localeCompare(b));
  const members = [...(me ? [me] : []), ...known];
  const memberOptions = (list) => list.map((m) => [m, m === me ? m + '（自分）' : m]);
  const byNumber = (n) => props.tasks.find((t) => t.number === n);
  const parentOptions = (self, current) => [['', 'なし'], ...props.tasks.filter((t) => t.number !== self && ((t.state || 'open') === 'open' || t.number === current))
    .sort((a, b) => a.number - b.number).map((t) => [String(t.number), '#' + t.number + ' ' + t.title]),
  ...(current && !byNumber(current) ? [[String(current), '#' + current]] : [])];
  const some = (payload) => Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== '' && value !== false && value !== null && value !== undefined));
  const needStatus = { wait: true, title: '#' + id, fields: [], ok: '', submit: () => '' };

  if (props.kind === 'new') {
    const parent = /^\d+$/.test(props.text) && props.text !== '0' ? props.text : '';
    return { title: '新しいタスク', ok: '作成', sticky: true, fields: [
      { name: 'title', label: '題名', required: true, follow: 'name' },
      { name: 'body', label: '本文', type: 'textarea', rows: 3, placeholder: '背景・完了の条件など（任意）' },
      { name: 'stage', label: '段階', type: 'radio', inline: true, value: 'todo', showIf: (x) => !x.start, options: [['todo', '未着手'], ['planned', '計画中', 'まだ着手しない（内容・時期を詰めている）']] },
      { name: 'assignees', label: '担当者', type: 'checks', options: memberOptions(members), empty: 'まだ候補がありません（下の「候補にいない担当者」で入力できます）' },
      { section: '＋ 候補にいない担当者', collapsed: true },
      { name: 'otherAssignees', label: 'GitHubのアカウント', placeholder: 'カンマ区切り（任意）' },
      { end: true },
      { section: '計画' },
      { name: 'priority', label: '優先度', type: 'select', row: 'plan', options: [['', 'なし'], ...PRIORITIES.map((p) => [p, p])] },
      { name: 'estimate', label: '見積もり', type: 'number', row: 'plan' },
      { name: 'sprint', label: 'スプリント', type: 'select', row: 'plan', options: sprintOptions },
      { name: 'plannedStart', label: '開始予定日', type: 'date', row: 'dates' }, { name: 'plannedEnd', label: '終了予定日', type: 'date', row: 'dates' },
      { name: 'due', label: '期限', type: 'date', row: 'dates' },
      { section: '分類・つながり', note: 'ラベル・マイルストーン・親タスク・先に終わるべきタスク', collapsed: true, open: Boolean(parent) },
      { name: 'label', label: 'ラベル', row: 'tags', placeholder: 'カンマ区切り。なければ作ります' },
      { name: 'milestone', label: 'マイルストーン', type: 'select', row: 'tags', options: [['', 'なし'], ...props.milestones.map((m) => [m.title, m.title + (m.due ? '（' + m.due + '）' : '')])] },
      { name: 'parent', label: '親タスク', type: 'select', row: 'links', value: parent, options: parentOptions(0, Number(parent) || 0) },
      { name: 'blockedBy', label: '先に終わるべきタスク', row: 'links', placeholder: '番号（カンマ区切り）' },
      { end: true },
      { name: 'start', label: '作成したら、作業空間を作って作業を開始する（担当者を選ばなければ自分になります）', type: 'checkbox', strong: true },
      { name: 'name', label: 'タスクブランチの名前', required: true, showIf: (x) => x.start, help: 'task/〈番号〉-〈名前〉のブランチになります（既定は題名）。' + BRANCH_HELP },
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
    const notNone = (x) => x.place !== 'none';
    return { title: (d.remote ? '作業を再開' : '作業を開始') + '：#' + id, intro: title, ok: '開始', fields: [
      { name: 'place', label: '作業の場所', type: 'radio', value: 'workspace', options: [
        ['workspace', '作業空間を作る', 'タスクブランチの作業空間をモジュールの中（.ecobuild/w/' + id + '）に作ります。完了する・作業を捨てると消えます'],
        ['none', 'タスクブランチを作らない', '調査・設計など、コードを変えないタスク（状態を作業中にするだけ）']] },
      ...(props.accounts.length > 1 ? [{ name: 'account', label: '作業空間で使う GitHub のアカウント（AI 用のアカウント等。push・提出・コミットの作者がそのアカウントになります）', type: 'select', showIf: notNone,
        options: [['', 'gh の使用中のアカウント（' + active + '）'], ...props.accounts.filter((a) => !a.active).map((a) => [a.login, a.login])] }] : []),
      ...(existing ? [] : [{ name: 'name', label: 'タスクブランチの名前', required: true, value: branchLabel(title), showIf: notNone,
        help: 'task/' + id + '-〈名前〉のブランチになります。' + BRANCH_HELP }]),
      { name: 'base', label: '作成元のブランチ', type: 'select', showIf: notNone, options: [['', base + (base && base === fallback ? '（既定）' : '')], ...choices],
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
      { section: 'つながり' },
      { name: 'parent', label: '親タスク', type: 'select', value: current ? String(current) : '', options: parentOptions(d.number, current) },
      { name: 'addBlocked', label: '先に終わるべきタスクを追加', row: 'blocked', placeholder: '番号（カンマ区切り）' },
      { name: 'removeBlocked', label: '先に終わるべきタスクから外す', row: 'blocked', placeholder: '番号（カンマ区切り）',
        help: blocked.length ? '今：' + blocked.map((b) => '#' + b.number).join('、') : '今はありません。' },
      { end: true },
    ], submit: (x) => {
      const parent = Number(x.parent) || 0;
      // 別の親へ移す：ecobuild は、今の親から外してからでないと付けない（2回に分ける）
      if (parent && current && parent !== current) return '親タスクを変えるには、先に「なし」にして保存し、もう一度開いて新しい親を選んでください。';
      const payload = some({ title: x.title !== (d.title || '') ? x.title : '', body: x.body !== (d.body || '') ? x.body : '',
        parent: parent && !current ? String(parent) : '', clear_parent: !parent && Boolean(current), add_blocked_by: x.addBlocked, remove_blocked_by: x.removeBlocked });
      if (!Object.keys(payload).length) return '変更する内容がありません。';
      return ['edit', { id, ...payload }];
    } };
  }

  // 担当者を追加
  const already = (d && d.assignees) || (byNumber(props.issue) || {}).assignees || [];
  return { title: '担当者を追加：#' + id, ok: '追加', fields: [
    { name: 'who', label: '担当者', type: 'checks', options: memberOptions(members.filter((m) => !already.includes(m))), empty: '候補者はすべて担当済みです（下の欄に入力できます）' },
    { name: 'other', label: '候補にいない担当者（GitHubのアカウント、カンマ区切り。任意）' }],
  submit: (x) => {
    const who = [...new Set([...x.who, ...commaList(x.other)])];
    return who.length ? ['edit', { id, add_assignee: who.join(',') }] : '担当者を選んでください。';
  } };
}

export default {
  render(root, props, { h, emit, state }) {
    const v = state.v || (state.v = {});
    const spec = specOf(props, v);
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => emit('cancel', {}));
    if (spec.wait) {
      return root.replaceChildren(h('h2', {}, spec.title), h('p', { class: 'intro', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…'), h('div', { class: 'actions' }, cancel));
    }
    for (const f of spec.fields) {
      if (f.name && !(f.name in v)) v[f.name] = f.value !== undefined ? f.value : f.type === 'checkbox' ? false : f.type === 'checks' ? [] : '';
    }
    state.open = state.open || {};
    const inputs = {};
    const wraps = [];
    const sync = () => { for (const [f, node] of wraps) node.hidden = Boolean(f.showIf) && !f.showIf(v); };
    const changed = () => sync();
    const help = (f) => (f.help ? [h('small', { class: 'help' }, f.help)] : []);
    const field = (f) => {
      if (f.type === 'checkbox') {
        const box = h('input', { type: 'checkbox' });
        box.checked = v[f.name] === true;
        box.addEventListener('change', () => { v[f.name] = box.checked; changed(f); });
        return h('div', { class: 'f' }, h('label', { class: f.strong ? 'check strong' : 'check' }, box, f.label), ...help(f));
      }
      if (f.type === 'radio') {
        const set = h('fieldset', { class: f.inline ? 'f inline' : 'f' }, h('legend', {}, f.label));
        for (const [value, label, note] of f.options) {
          const radio = h('input', { type: 'radio', name: f.name, value });
          radio.checked = v[f.name] === value;
          radio.addEventListener('change', () => { v[f.name] = value; changed(f); });
          set.append(h('label', {}, radio, h('span', {}, label, ...(note ? [h('small', {}, note)] : []))));
        }
        return set;
      }
      if (f.type === 'checks') {
        const list = h('div', {});
        for (const [value, label] of f.options) {
          const box = h('input', { type: 'checkbox', value });
          box.checked = v[f.name].includes(value);
          box.addEventListener('change', () => { v[f.name] = box.checked ? [...new Set([...v[f.name], value])] : v[f.name].filter((x) => x !== value); });
          list.append(h('label', {}, box, label));
        }
        if (!f.options.length) list.append(h('small', {}, f.empty || ''));
        return h('fieldset', { class: 'f checks' }, h('legend', {}, f.label), list);
      }
      let input;
      if (f.type === 'select') {
        input = h('select', {});
        for (const [value, label] of f.options) {
          const option = h('option', { value }, label);
          if (value === v[f.name]) option.selected = true;
          input.append(option);
        }
        input.addEventListener('change', () => { v[f.name] = input.value; changed(f); });
      } else {
        input = f.type === 'textarea' ? h('textarea', { rows: String(f.rows || 4) }) : h('input', { type: f.type || 'text' });
        if (f.type === 'number') { input.min = '0'; input.step = '0.5'; }
        if (f.placeholder) input.placeholder = f.placeholder;
        input.value = v[f.name];
        input.addEventListener('input', () => {
          v[f.name] = input.value;
          // タスクブランチの名前は、手で変えるまで題名に合わせる
          if (f.follow && inputs[f.follow] && (v[f.follow] || '') === (state.auto || '')) { state.auto = v[f.follow] = branchLabel(input.value); inputs[f.follow].value = state.auto; }
        });
      }
      inputs[f.name] = input;
      return h('label', { class: 'f field' }, f.label, input, ...help(f));
    };

    const form = h('form', {});
    let into = form, row = null, rowName = '';
    for (const f of spec.fields) {
      if (f.section !== undefined) {
        const title = [f.section, ...(f.note ? [h('small', {}, f.note)] : [])];
        if (f.collapsed) {
          into = h('details', { class: 'section' }, h('summary', {}, ...title));
          into.open = f.section in state.open ? state.open[f.section] : f.open === true;
          const box = into;
          box.addEventListener('toggle', () => { state.open[f.section] = box.open; });
        } else {
          into = h('div', { class: 'section' }, h('h3', {}, ...title));
        }
        form.append(into);
        row = null; rowName = '';
        continue;
      }
      if (f.end) { into = form; row = null; rowName = ''; continue; }
      const node = field(f);
      wraps.push([f, node]);
      if (f.row) {
        if (f.row !== rowName) { row = h('div', { class: 'row' }); rowName = f.row; into.append(row); }
        row.append(node);
        row.style.setProperty('--cols', String(row.children.length));
      } else {
        row = null; rowName = '';
        into.append(node);
      }
    }
    sync();
    const error = h('p', { class: 'error', role: 'alert' }, state.error || '');
    const ok = h('button', { type: 'submit', class: spec.danger ? 'danger' : 'primary' }, spec.ok);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const missing = spec.fields.find((f) => f.name && f.required && !(f.showIf && !f.showIf(v)) && !String(v[f.name] || '').trim());
      const result = missing ? missing.label + 'を入力してください。' : spec.submit(v);
      state.error = typeof result === 'string' ? result : '';
      error.textContent = state.error;
      if (typeof result !== 'string') emit(result[0], result[1]);
    });
    form.append(error, h('div', { class: spec.sticky ? 'actions sticky' : 'actions' }, cancel, ok));
    const top = [h('h2', {}, spec.title)];
    if (spec.intro) top.push(h('p', { class: 'intro' }, spec.intro));
    root.replaceChildren(...top, form);
  },
};
