// 部品「届いている提出」。届け先のブランチごとにまとめ（見せ方だけ）、見出しに件数、行に状態の文と担当。
// 何も選んでいなければ先頭の行を選ぶ。↑↓ で行を選び直す。行の右クリックで、詳細のボタンと同じ操作（どれを出すか・灰色は、詳細と同じ決め方）。
const stateText = (s) => (!s ? '未提出' : s.state === 'merged' ? (s.partial ? '中間提出は取り込み済み' : '取り込み済み')
  : s.state === 'closed' ? '取り下げ済み' : `${s.draft ? '下書きの' : ''}${s.partial ? '中間提出' : '提出'}中`);

export default {
  render(root, props, { h, emit, menu, state, open_url }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const open = (s) => s && s.state === 'open';
    const tasks = (props.tasks || []).filter((t) => open(t.submission));
    const branches = (props.branches || []).filter((b) => !b.is_task_branch && open(b.submission) && b.submitted_to);  // タスクブランチの提出は、タスクの行に出る
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
    const ruleOf = (base) => (access ? (access.take_in || {})[base] || access.take_in_other || null : null);
    const keyOf = (item) => item.kind + ':' + item.id;
    const chosen = props.selected_task ? 'task:' + props.selected_task : props.selected_branch ? 'branch:' + props.selected_branch : '';
    const choose = (item) => emit('selected', { kind: item.kind, id: item.id, task: item.kind === 'task' ? item.id : '', branch: item.kind === 'branch' ? item.id : '' });

    // 右クリック：詳細のボタンと同じ操作。処理できない人・下書きは灰色と理由（守りは ecobuild）
    const actionsOf = (item, base) => {
      const rule = ruleOf(base), handles = !rule || rule.allowed !== false;
      const why = handles ? '' : `${base} への提出を処理できるのは、${rule.owners}だけです`;
      const act = (id, label, more) => ({ id, label, ...(more || {}) });
      if (item.kind === 'branch') {
        const s = item.branch.submission || {};
        return [act('merge', '取り込む', { disabled: Boolean(s.draft) || !handles, reason: s.draft ? '下書きの提出は取り込めません' : why }),
          ...(s.url ? [{ separator: true }, act('github', 'GitHubで開く')] : [])];
      }
      const t = item.task, s = t.submission || {};
      const own = !!me && (t.assignees || []).some((name) => name.toLowerCase() === me);
      const items = [act('diff', '差分'), act('comment', 'コメント…'), act('task', 'タスク'), { separator: true }];
      if (own) {
        items.push(act('withdraw', '提出を取り下げる'),
          act('finish', '取り込む…', { disabled: Boolean(s.draft) || !handles, reason: s.draft ? '下書きの提出は取り込めません。タスクブランチの作業空間で下書きを解除します' : why }));
      } else {
        items.push(act('review', '手元で確認'), act('reject', '差し戻す…', { disabled: !handles, reason: why }),
          act('approve', '承認して取り込む…', { disabled: Boolean(s.draft) || !handles, reason: s.draft ? '下書きの提出は承認できません' : why }));
      }
      if (s.url || t.url) items.push({ separator: true }, act('github', 'GitHubで開く'));
      return items;
    };
    const showMenu = async (event, item, base) => {
      event.preventDefault();
      if (keyOf(item) !== chosen) choose(item);
      const picked = await menu(event, actionsOf(item, base));
      if (!picked) return;
      if (picked === 'github') {
        const s = item.kind === 'branch' ? item.branch.submission : item.task.submission;
        open_url((s && s.url) || (item.task && item.task.url));
        return;
      }
      emit('action', { action: picked, id: item.id, base, partial: Boolean(item.kind === 'task' && item.task.submission.partial), workspace: '' });
    };

    const out = [], rows = [], items = [];
    for (const base of [...groups.keys()].sort()) {
      const members = groups.get(base);
      const rule = ruleOf(base);
      const section = h('section', { 'aria-label': `${base} への提出` },
        h('h3', {}, h('span', { class: 'to' }, '→'), h('span', { class: 'mono' }, base), h('span', { class: 'count' }, String(members.length))));
      if (rule && rule.allowed === false) {
        section.append(h('p', { class: 'note' }, `${base} への提出を処理できるのは、${rule.owners}だけです（見る・手元で確認・コメントはできます）。`));
      }
      const list = h('div', { class: 'list', role: 'listbox', 'aria-label': `${base} への提出` });
      for (const item of members) {
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
        row.setAttribute('aria-selected', String(chosen === keyOf(item)));
        row.tabIndex = chosen === keyOf(item) || (!chosen && !items.length) ? 0 : -1;
        row.addEventListener('click', () => choose(item));
        row.addEventListener('contextmenu', (event) => showMenu(event, item, base));
        rows.push(row);
        items.push(item);
        list.append(row);
      }
      section.append(list);
      out.push(section);
    }
    // ↑↓：行を選び直す（右の詳細も替わる）
    rows.forEach((row, index) => row.addEventListener('keydown', (event) => {
      const next = event.key === 'ArrowDown' ? index + 1 : event.key === 'ArrowUp' ? index - 1 : -1;
      if (next < 0 || next >= rows.length) return;
      event.preventDefault();
      state.focus = keyOf(items[next]);
      choose(items[next]);
    }));
    // 何も選んでいない・選んでいた提出がなくなった：先頭を選ぶ
    if (!items.some((item) => keyOf(item) === chosen) && state.auto !== keyOf(items[0])) {
      state.auto = keyOf(items[0]);
      Promise.resolve().then(() => choose(items[0]));
    }
    root.replaceChildren(...out);
    // ↑↓ で選び直した行に、フォーカスを置いたままにする
    const focused = state.focus && rows[items.findIndex((item) => keyOf(item) === state.focus)];
    if (focused && state.focus === chosen) { state.focus = null; Promise.resolve().then(() => focused.focus()); }
  },
};
