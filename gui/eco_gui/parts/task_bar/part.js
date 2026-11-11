// 部品「タスク管理の上の帯」。表示のタブと、絞り込み。選んだ値を出すだけ（絞るのは表示の部品、読み直すのは中継地点）。
// 打っている途中の文字と選んだ値は、この部品が持つ（state）。開いたときの値は start。
const VIEWS = [['board', 'ボード'], ['tasks', '一覧'], ['task-next', '次にやる'], ['schedule', '日程'], ['task-sprint', 'スプリント'], ['task-summary', '概要']];

export default {
  render(root, props, { h, emit, state }) {
    // 開いたときの値（start）が変わったら、それに合わせ直す（概要から、絞り込み付きで一覧へ来たとき等）
    const startKey = JSON.stringify(props.start || {});
    if (!state.f || state.startKey !== startKey) {
      const s = props.start || {};
      state.startKey = startKey;
      state.f = { search: s.search || '', assignee: s.assignee || '', sprint: s.sprint || '', milestone: s.milestone || '',
        ready: s.ready === true, closed: s.closed === true, deleted: s.deleted === true };
      if (state.search) state.search.value = state.f.search;
    }
    const f = state.f;
    const out = () => ({ ...f, all: f.closed || f.deleted });
    const now = new Date();
    const today = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const md = (d) => (d ? Number(d.slice(5, 7)) + '/' + Number(d.slice(8, 10)) : '');

    const tabs = h('nav', { class: 'views', role: 'tablist', 'aria-label': '表示' });
    for (const [id, label] of VIEWS) {
      const tab = h('button', { type: 'button', role: 'tab' }, label);
      tab.setAttribute('aria-selected', String(id === props.view));
      tab.addEventListener('click', () => { if (id !== props.view) emit('view', { id, ...out() }); });
      tabs.append(tab);
    }
    const parts = [tabs];

    if (props.scope !== 'none') {
      const select = (name, label, options) => {
        const box = h('select', { 'aria-label': label });
        for (const [value, text] of options) {
          const option = h('option', { value }, text);
          if (value === f[name]) option.selected = true;
          box.append(option);
        }
        if (!options.some((o) => o[0] === f[name])) f[name] = '';
        box.addEventListener('change', () => { f[name] = box.value; emit('changed', out()); });
        return box;
      };
      const accounts = [...new Set(props.tasks.flatMap((t) => t.assignees || []))].sort();
      const assignee = select('assignee', '担当者', [['', '担当者：すべて'], ['@me', '自分'],
        ...accounts.filter((a) => a !== props.me).map((a) => [a, a]), ['-', '担当なし']]);
      const bar = h('form', { class: 'filter' });
      bar.addEventListener('submit', (event) => event.preventDefault());
      if (props.scope === 'all') {
        // 検索の欄は作り直さない（打っている途中の位置が残る）
        if (!state.search) {
          state.search = h('input', { type: 'search', placeholder: '題名で絞り込む', 'aria-label': '検索', class: 'search' });
          state.search.value = f.search;
          state.search.addEventListener('input', () => { state.f.search = state.search.value; emit('changed', { ...state.f, all: state.f.closed || state.f.deleted }); });
        }
        const current = (props.sprints.find((s) => s.start <= today && today < s.end) || {}).name || '';
        const sprint = select('sprint', 'スプリント', [['', 'スプリント：すべて'], ...(current ? [['current', '今のスプリント（' + current + '）']] : []),
          ...props.sprints.map((s) => [s.name, s.name + '（' + md(s.start) + '〜）']), ['-', 'スプリントなし']]);
        const names = [...new Set([...props.milestones.map((m) => m.title), ...props.tasks.map((t) => t.milestone).filter(Boolean)])];
        const milestone = select('milestone', 'マイルストーン', [['', 'マイルストーン：すべて'], ...names.map((m) => [m, m]), ['-', 'マイルストーンなし']]);
        const check = (name, label, title) => {
          const box = h('input', { type: 'checkbox' });
          box.checked = f[name];
          box.addEventListener('change', () => { f[name] = box.checked; emit('reload', out()); });
          const line = h('label', { class: 'check' }, box, ' ' + label);
          if (title) line.title = title;
          return line;
        };
        bar.append(state.search, assignee, sprint, milestone, check('ready', '着手できるものだけ'), check('closed', '完了したタスクも表示'),
          check('deleted', '削除したタスクも表示', '削除したタスク（GitHubでは「対応しない」として閉じたもの）は、ふだんは表示しません'));
      } else {
        bar.append(assignee);
      }
      parts.push(bar);
    }
    root.replaceChildren(...parts);
  },
};
