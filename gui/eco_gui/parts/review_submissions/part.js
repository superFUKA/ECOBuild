// 部品「届いている提出」。届け先のブランチごとにまとめ（見せ方だけ）、見出しに件数、行に状態の文と担当。↑↓ で行を移れる。
const stateText = (s) => (!s ? '未提出' : s.state === 'merged' ? (s.partial ? '中間提出は取り込み済み' : '取り込み済み')
  : s.state === 'closed' ? '取り下げ済み' : `${s.draft ? '下書きの' : ''}${s.partial ? '中間提出' : '提出'}中`);

export default {
  render(root, props, { h, emit, state, redraw }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const open = (s) => s && s.state === 'open';
    const tasks = (props.tasks || []).filter((t) => open(t.submission));
    const branches = (props.branches || []).filter((b) => open(b.submission) && b.submitted_to);
    if (props.loading && !tasks.length && !branches.length) {
      return root.replaceChildren(h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…'));
    }
    if (!tasks.length && !branches.length) return root.replaceChildren(h('p', { class: 'none' }, '届いている提出はありません。'));
    const access = props.access, me = (access?.login || '').toLowerCase();
    const asked = new Set((props.to_review || []).map((t) => t.number));
    const groups = new Map();
    const group = (base) => { if (!groups.has(base)) groups.set(base, []); return groups.get(base); };
    for (const t of tasks) group(t.submission.base || '').push({ kind: 'task', id: String(t.number), task: t });
    for (const b of branches) group(b.submitted_to).push({ kind: 'branch', id: b.name, branch: b });
    const out = [], rows = [];
    for (const base of [...groups.keys()].sort()) {
      const items = groups.get(base);
      const rule = access ? (access.take_in || {})[base] || access.take_in_other || null : null;
      const section = h('section', { 'aria-label': `${base} への提出` },
        h('h3', {}, h('span', { class: 'to' }, '→'), h('span', { class: 'mono' }, base), h('span', { class: 'count' }, String(items.length))));
      if (rule && rule.allowed === false) {
        section.append(h('p', { class: 'note' }, `${base} への提出を処理できるのは、${rule.owners}だけです（見る・手元で確認・コメントはできます）。`));
      }
      const list = h('div', { class: 'list', role: 'listbox', 'aria-label': `${base} への提出` });
      for (const item of items) {
        const key = item.kind + ':' + item.id;
        let row;
        if (item.kind === 'branch') {
          row = h('button', { type: 'button', role: 'option' }, h('span', { class: 'what' }, h('span', { class: 'pill' }, 'ブランチ'), ' ', item.branch.name),
            h('span', { class: 'state' }, stateText(item.branch.submission)));
        } else {
          const t = item.task, people = t.assignees || [], mine = !!me && people.some((name) => name.toLowerCase() === me);
          row = h('button', { type: 'button', role: 'option' },
            h('span', { class: 'what' }, h('span', { class: 'number' }, `#${t.number}`), ' ', t.title,
              asked.has(t.number) ? h('span', { class: 'pill warn' }, '見るように頼まれています') : ''),
            h('span', { class: 'state' }, stateText(t.submission) + (people.length ? ' · ' + people.join(', ') : '') + (mine ? '（自分）' : '')));
        }
        row.setAttribute('aria-selected', String(state.selected === key));
        row.addEventListener('click', () => { state.selected = key; redraw(); emit('selected', { kind: item.kind, id: item.id }); });
        rows.push(row);
        list.append(row);
      }
      section.append(list);
      out.push(section);
    }
    rows.forEach((row, index) => row.addEventListener('keydown', (event) => {
      const next = event.key === 'ArrowDown' ? rows[index + 1] : event.key === 'ArrowUp' ? rows[index - 1] : null;
      if (next) { event.preventDefault(); next.focus(); }
    }));
    root.replaceChildren(...out);
  },
};
