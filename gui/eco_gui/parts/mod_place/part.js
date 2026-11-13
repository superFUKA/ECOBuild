// 部品「コミットするタスクブランチを選ぶ欄」。今までの GUI（agentrules.js の「コミットする場所」）と同じ選び方。
export default {
  render(root, props, { h, emit }) {
    const spaces = (props.workspaces || []).filter((w) => w.task != null && w.review == null);
    const folder = (path) => String(path).split(/[\\/]/).pop();
    const create = h('button', { type: 'button', class: 'small' }, '新しいタスクを作る…');
    create.addEventListener('click', () => emit('new_task', {}));
    const out = [];
    if (props.workspaces === null || props.workspaces === undefined) out.push(h('span', { class: 'note', role: 'status' }, '作業空間を読み込んでいます…'));
    else if (!spaces.length) out.push(h('span', {}, `${props.title}：タスクブランチの作業空間がありません。`), create);
    else {
      const select = h('select', {}, h('option', { value: '' }, '選んでください'),
        ...spaces.map((w) => h('option', { value: w.path }, `${w.branch || ''}（${folder(w.path)}）`)));
      select.value = spaces.some((w) => w.path === props.value) ? props.value : '';
      select.addEventListener('change', () => emit('changed', { path: select.value }));
      out.push(h('label', {}, props.title, select), create);
    }
    if (props.note) out.push(h('span', { class: 'note' }, props.note));
    root.replaceChildren(h('div', { class: 'place' }, ...out));
  },
};
