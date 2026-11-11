// 部品「コミットの一覧」。ブランチの選択と、コミットの行（選べる）。
const two = (n) => String(n).padStart(2, '0');
const localTime = (iso) => {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return String(iso || '').slice(0, 16).replace('T', ' ');
  return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ' + two(d.getHours()) + ':' + two(d.getMinutes());
};

export default {
  render(root, props, { h, emit }) {
    const branch = props.branch || '';
    const select = h('select', { 'aria-label': 'ブランチ' }, h('option', { value: '' }, '今いるブランチ'));
    const names = props.branches.filter((b) => !b.is_task_branch).map((b) => b.name);
    if (branch && !names.includes(branch)) names.push(branch);
    for (const name of names) {
      const item = h('option', { value: name }, name);
      if (name === branch) item.selected = true;
      select.append(item);
    }
    select.addEventListener('change', () => emit('branch', { name: select.value }));
    const out = [h('div', { class: 'bar' }, h('span', { class: 'dim' }, 'ブランチ'), select, props.loading ? h('span', { class: 'spinner' }) : '',
      h('span', { class: 'dim count' }, props.rows.length ? props.rows.length + ' 件' : ''))];
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      out.push(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    } else if (props.rows.length === 0) {
      out.push(h('p', { class: 'note', role: 'status' }, props.loading ? '読み込み中…' : 'コミットはまだありません。'));
    } else {
      const list = h('div', { class: 'commits', role: 'listbox', 'aria-label': 'コミット' });
      for (const c of props.rows) {
        const on = c.sha === props.selected;
        const marks = h('span', { class: 'marks' });
        if (c.pull_request) marks.append(h('span', { class: 'pill purple', title: '提出（PR）' }, 'PR #' + c.pull_request));
        if (c.issue) marks.append(h('span', { class: 'pill info', title: 'タスク（Issue）' }, 'タスク #' + c.issue));
        const row = h('button', { type: 'button', role: 'option', class: 'commit', 'aria-selected': String(on), title: c.subject || '' },
          h('span', { class: 'subject' }, c.subject || ''), marks,
          h('span', { class: 'meta' }, h('code', {}, String(c.sha || '').slice(0, 7)), ' ', c.author || '', '・', localTime(c.date)));
        row.addEventListener('click', () => emit('selected', { sha: c.sha }));
        list.append(row);
      }
      out.push(list);
    }
    root.replaceChildren(...out);
  },
};
