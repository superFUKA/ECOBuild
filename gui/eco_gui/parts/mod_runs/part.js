// 部品「CI の実行の表」。今までの GUI の CI の実行（見出しの行・表・行のボタン・右クリック）と同じに描く。
const CONCLUSIONS = { failure: '失敗', timed_out: '時間切れ', startup_failure: '起動できず', action_required: '要対応' };
const EVENTS = { push: 'push', pull_request: '提出（PR）', workflow_dispatch: '手動', schedule: '定期' };
const result = (r) => r.status !== 'completed' ? ['実行中', 'warn'] : ['success', 'skipped', 'neutral'].includes(r.conclusion) ? ['成功', 'ok']
  : r.conclusion === 'cancelled' ? ['取り消し', ''] : [CONCLUSIONS[r.conclusion] || r.conclusion || '失敗', 'bad'];
const failed = (r) => r.status === 'completed' && result(r)[1] === 'bad';
const two = (n) => String(n).padStart(2, '0');
const localTime = (iso) => {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return String(iso || '').slice(0, 16).replace('T', ' ');
  return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ' + two(d.getHours()) + ':' + two(d.getMinutes());
};

export default {
  render(root, props, { h, emit, state, redraw, menu }) {
    const branch = props.branch || '';
    const runs = branch ? props.branch_rows : props.rows;
    const out = [];

    // 見出しの行：実行・ブランチで絞る・GitHub で見る・手動で実行
    const select = h('select', { 'aria-label': 'ブランチ' }, h('option', { value: '' }, 'すべてのブランチ'));
    const names = props.branches.filter((b) => b.remote).map((b) => b.name);
    if (branch && !names.includes(branch)) names.push(branch);
    for (const name of names) {
      const item = h('option', { value: name }, name);
      if (name === branch) item.selected = true;
      select.append(item);
    }
    select.addEventListener('change', () => emit('branch', { name: select.value }));
    const end = h('span', { class: 'end' });
    if (props.url) end.append(h('a', { class: 'button', href: props.url.replace(/\.git$/, '') + '/actions', target: '_blank', rel: 'noopener' }, 'GitHub で見る ↗'));
    const run = h('button', { type: 'button', class: 'primary small' }, '▶ 手動で実行');
    run.addEventListener('click', () => emit('dispatch', { branch }));
    end.append(run);
    out.push(h('div', { class: 'section-row' }, h('h3', {}, '実行'), select, props.loading ? h('span', { class: 'spinner' }) : '', end));

    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      out.push(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    } else if (runs.length === 0) {
      out.push(h('p', { class: 'note' }, props.loading ? '読み込み中…' : (branch ? branch + ' の' : '') + 'CIの実行はありません。'));
    } else {
      const act = (action, r) => emit('action', { action, run: r.id });
      const rerun = async (event, r) => {
        if (!failed(r)) return act('rerun', r);
        const chosen = await menu(event, [{ heading: '#' + r.id + ' をもう一度実行' }, { id: 'rerun_failed', label: '失敗したジョブだけを実行する' },
          { id: 'rerun', label: 'すべてのジョブを実行する' }]);
        if (chosen) act(chosen, r);
      };
      const body = h('tbody', {});
      for (const r of runs) {
        const [text, cls] = result(r);
        const buttons = h('td', { class: 'row-actions' });
        if (failed(r)) {
          const logs = h('button', { type: 'button', class: 'small' }, 'ログ');
          logs.addEventListener('click', () => act('logs', r));
          buttons.append(logs);
        }
        const again = h('button', { type: 'button', class: 'small' }, '再実行');
        if (r.status !== 'completed') { again.setAttribute('aria-disabled', 'true'); again.title = '実行中です'; }
        again.addEventListener('click', (event) => { if (r.status === 'completed') rerun(event, r); });
        buttons.append(again);
        if (r.url) buttons.append(h('a', { class: 'button small', href: r.url, target: '_blank', rel: 'noopener', title: 'GitHubで開く', 'aria-label': 'GitHubで開く' }, '↗'));
        const row = h('tr', { class: r.id === state.run ? 'selected' : '', title: r.workflow || '' },
          h('td', {}, h('span', { class: cls ? 'pill ' + cls : 'pill' }, text)), h('td', {}, String(r.id)), h('td', { class: 'branch' }, r.branch || ''),
          h('td', {}, EVENTS[r.event] || r.event || ''), h('td', {}, localTime(r.created)), buttons);
        row.addEventListener('click', (event) => {
          if (event.target.closest('button, a') || state.run === r.id) return;
          state.run = r.id;
          redraw();
        });
        row.addEventListener('dblclick', (event) => { if (!event.target.closest('button, a') && failed(r)) act('logs', r); });
        row.addEventListener('contextmenu', async (event) => {
          event.preventDefault();
          state.run = r.id;
          const chosen = await menu(event, [
            { id: 'logs', label: '失敗した手順のログ', disabled: !failed(r), reason: '失敗した実行ではありません' },
            { id: 'rerun', label: 'もう一度実行', disabled: r.status !== 'completed', reason: '実行中です' },
            ...(failed(r) ? [{ id: 'rerun_failed', label: '失敗したジョブだけをもう一度実行' }] : []),
            { separator: true },
            { id: 'only', label: (r.branch || '') + ' の実行だけを表示', disabled: branch === r.branch || !r.branch, reason: '今、このブランチで絞っています' },
          ]);
          if (chosen === 'only') emit('branch', { name: r.branch });
          else if (chosen) act(chosen, r);
          else redraw();
        });
        body.append(row);
      }
      out.push(h('table', { class: 'runs' }, h('thead', {}, h('tr', {}, h('th', {}, '結果'), h('th', {}, '#'), h('th', {}, 'ブランチ'), h('th', {}, 'きっかけ'),
        h('th', {}, '日時'), h('th', {}, h('span', { class: 'sr-only' }, '操作')))), body));
    }
    root.replaceChildren(...out);
  },
};
