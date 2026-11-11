// 部品「ブランチの詳細」。今までの GUI のブランチの右側（見出し・事実の並び・タスクブランチの一覧）と同じに描く。
const isOpen = (s) => !!s && s.state === 'open';

export default {
  render(root, props, { h, emit, state, redraw }) {
    const shared = props.branches.filter((b) => !b.is_task_branch);
    const out = [];
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      out.push(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    const def = props.default_base || '';
    const b = shared.find((x) => x.name === props.selected) || shared.find((x) => x.name === def) || shared[0];
    if (!b) {
      if (!props.error) out.push(h('p', { role: 'status' }, props.loading ? '読み込み中…' : 'ブランチを選んでください。'));
      return root.replaceChildren(...out);
    }
    const isDefault = b.name === def;
    const creator = (props.creators || {})[b.name] || '';
    const button = (action, label, cls, title, more) => {
      const item = h('button', { type: 'button', class: cls || '' }, label);
      if (title) item.title = title;
      item.addEventListener('click', () => emit('action', { action, name: b.name, ...(more || {}) }));
      return item;
    };

    // 見出し：名前と、どこにあるか・作成元・作った人・出ている提出
    const where = [b.local ? '手元' : '', b.remote ? 'GitHub' : ''].filter(Boolean).join('・')
      + (b.remote ? '' : b.merged ? '（既定の作成元に取り込み済み）' : b.merged === false ? '（既定の作成元に取り込んでいない）' : '');
    const line = h('p', { class: 'note' });
    if (isDefault) line.append(h('span', { class: 'pill ok' }, '既定'), ' ');
    if (b.unusable) line.append(h('span', { class: 'pill' }, 'モジュールではない'), ' ');
    line.append(where);
    if (b.base) line.append('　作成元：', h('span', { class: 'mono' }, b.base));
    if (creator && !isDefault) line.append('　作った人：' + creator);
    if (isOpen(b.submission)) line.append('　', h('span', { class: 'pill purple' }, (b.submission.draft ? '下書きの' : '') + '提出 → ' + b.submitted_to));
    const actions = h('div', { class: 'actions' }, button('merge', '取り込み・提出…', '', 'このブランチを、別のブランチへ取り込む・提出する'));
    if (!isDefault) actions.append(button('delete', '削除…', 'danger-text', 'このブランチを、手元と GitHub から削除します（タスクブランチの作成元・今いるブランチは消せません）。'));
    out.push(h('div', { class: 'head' }, h('div', {}, h('h3', {}, b.name), line), actions));

    // 事実の並び：作業・仕様・保護
    const facts = h('dl', { class: 'facts' });
    const fact = (name, ...value) => facts.append(h('dt', {}, name), h('dd', {}, ...value));
    if (b.unusable) fact('作業', b.unusable + '。タスクブランチの作成元にはできません');
    if (b.format != null && b.latest_format != null && b.format < b.latest_format) {
      fact('仕様', '以前の ECOBuild の仕様（版 ' + b.format + '。今の版は ' + b.latest_format + '）',
        h('span', { class: 'dim' }, '　最新にするには：ecobuild module upgrade --branch ' + b.name));
    }
    if (isDefault) {
      const p = props.protection;
      const set = button('protect', '設定…', 'link', '設定の画面の「ブランチの保護」を開きます');
      if (!p) fact('保護', 'なし（提出以外でも変更できます）　', set);
      else {
        fact('保護', '取り込みは提出だけ・承認 ' + (p.approvals ? p.approvals + ' 人' : 'は不要')
          + (p.checks && p.checks.length ? '・CI（' + p.checks.join(', ') + '）' : '') + '　', set, ' ', button('unprotect', '外す', 'link'));
      }
    }
    if (facts.children.length) out.push(facts);

    // このブランチから作ったタスクブランチ（畳める。開閉は、窓を開いているあいだ覚える）
    const tasks = props.branches.filter((t) => t.is_task_branch && t.base === b.name);
    if (tasks.length) {
      const list = h('ul', {});
      for (const t of tasks) {
        const number = (/^task\/(\d+)/.exec(t.name) || [])[1];
        const item = h('li', {}, h('span', { class: 'branch-name' }, t.name), ' ', h('span', { class: 'pill ok' }, 'タスクブランチ'), ' ',
          h('span', { class: 'where' }, [t.local ? '手元' : '', t.remote ? 'GitHub' : ''].filter(Boolean).join('・')));
        if (isOpen(t.submission)) item.append(' ', h('span', { class: 'pill purple' }, '提出中'));
        if (number) item.append(' ', button('task', 'タスクを開く', 'small', '', { task: Number(number) }));
        list.append(item);
      }
      const box = h('details', { class: 'task-branches' }, h('summary', {}, 'このブランチから作ったタスクブランチ（' + tasks.length + '）'), list);
      box.open = state.tasksOpen === true;
      box.addEventListener('toggle', () => { state.tasksOpen = box.open; });
      out.push(box);
    }
    root.replaceChildren(...out);
  },
};
