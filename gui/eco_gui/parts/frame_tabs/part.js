// 部品「作業空間のタブ」。今までの GUI（module.js の Workspace tabs・shell.css の .workspace-tab-bar）と同じ：
// タブ（題と小さく #n・×）、右の ▼（作業空間の一覧）、右クリックのメニュー、1つもないときの案内。
const DOWN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
const FOLDER = '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
const keyOf = (path) => String(path || '').replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();

export default {
  render(root, props, { h, emit, state, memory, menu, redraw }) {
    const loaded = Array.isArray(props.workspaces);
    const places = loaded ? props.workspaces : [];
    const titles = new Map((props.tasks || []).map((task) => [task.number, task.title]));
    const closed = new Set((props.closed || []).map(keyOf));
    const current = keyOf(props.current);
    const visible = places.filter((place) => !closed.has(keyOf(place.path)));
    const shown = visible.find((place) => keyOf(place.path) === current) || null;
    const label = (place) => {
      const branch = place.review ? `#${place.review} の提出を確認中` : place.branch || '（ブランチなし）';
      const title = place.task ? titles.get(place.task) || '' : '';
      return { branch, title, where: place.task ? '#' + place.task : String(place.path).replace(/[\\/]+$/, '').split(/[\\/]/).pop() };
    };
    // 閉じたタブの並び（場所は、作業空間の一覧にある書き方で渡す。なくなった作業空間は外す）
    const closedWith = (change) => {
      const next = new Set(closed);
      change(next);
      return places.map((place) => place.path).filter((path) => next.has(keyOf(path)));
    };
    const show = (place) => {
      memory.set('last', place.path);
      emit('selected', { path: place.path, closed: closedWith((set) => set.delete(keyOf(place.path))) });
    };
    const close = (targets) => {
      const gone = new Set(targets.map((place) => keyOf(place.path)));
      const left = visible.filter((place) => !gone.has(keyOf(place.path)));
      const list = closedWith((set) => { for (const key of gone) set.add(key); });
      if (shown && !gone.has(current)) emit('selected', { path: shown.path, closed: list });
      else if (left.length) {  // 今のタブを閉じた：隣（右、なければ左）を出す
        const at = visible.indexOf(shown);
        const next = visible.slice(at + 1).find((place) => !gone.has(keyOf(place.path))) || left[left.length - 1];
        memory.set('last', next.path);
        emit('selected', { path: next.path, closed: list });
      } else emit('emptied', { closed: list });
    };

    // 選んでいるタブがない・なくなった：出ているタブの1つを選んだことにする（なければ、案内のページへ）
    if (loaded && !props.loading && !shown) {
      const kept = keyOf(memory.get('last', ''));
      const next = visible.find((place) => keyOf(place.path) === kept) || visible[0];
      const key = `${current}>${next ? keyOf(next.path) : ''}|${[...closed].join(',')}`;
      if ((next || current) && state.sent !== key) {
        state.sent = key;
        if (next) emit('selected', { path: next.path, closed: closedWith(() => {}) });
        else emit('emptied', { closed: closedWith(() => {}) });
      }
    }

    const box = h('div', { class: 'frame-tabs' });
    // タブの行（出ているタブが1つもなければ、行を出さない）
    if (visible.length) {
      const strip = h('nav', { class: 'tabs', role: 'tablist', 'aria-label': '作業空間' });
      for (const place of visible) {
        const { branch, title, where } = label(place);
        const on = place === shown;
        const tab = h('button', { type: 'button', role: 'tab', 'aria-selected': String(on), tabindex: on ? '0' : '-1', title: `${branch}　${place.path}` },
          title || branch, where ? h('small', { class: 'where' }, where) : '');
        tab.addEventListener('click', () => { if (!on) show(place); });
        tab.addEventListener('keydown', (event) => {
          if (event.key === 'Delete') { event.preventDefault(); close([place]); return; }
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const at = visible.indexOf(place);
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? visible.length - 1 : (at + (event.key === 'ArrowRight' ? 1 : -1) + visible.length) % visible.length;
          if (visible[next] !== shown) show(visible[next]);
        });
        const cross = h('button', { type: 'button', class: 'close-tab', title: 'タブを閉じる（作業空間は残ります）', 'aria-label': `${title || branch} のタブを閉じる` }, '×');
        cross.addEventListener('click', () => close([place]));
        const group = h('div', { class: 'tab-group' + (on ? ' on' : ''), role: 'presentation' }, tab, cross);
        group.addEventListener('contextmenu', async (event) => {
          event.preventDefault();
          const others = visible.filter((other) => other !== place);
          const studio = (version, can) => ({ id: 'vs:' + version, label: `Visual Studio ${version} で開く`, disabled: can.can === false, reason: can.reason || '' });
          const id = await menu(event, [
            { id: 'close', label: 'タブを閉じる（作業空間は残ります）' },
            { id: 'others', label: '他のタブを閉じる', disabled: others.length === 0, reason: 'ほかに出ているタブはありません。' },
            { separator: true },
            { id: 'explorer', label: 'エクスプローラーでフォルダを開く' },
            studio('2026', props.vs2026 || {}), studio('2022', props.vs2022 || {}),
            { id: 'reload', label: '状態を更新' },
            ...(place.name ? [{ id: 'remove', label: '作業空間を削除…', danger: true }] : []),
            ...(place.task ? [{ separator: true }, { id: 'task', label: `タスク #${place.task} を表示` }] : []),
          ]);
          if (id === 'close') close([place]);
          else if (id === 'others') close(others);
          else if (id === 'task') emit('action', { name: 'task', path: place.path, task: place.task });
          else if (id && id.startsWith('vs:')) emit('action', { name: 'vs', path: place.path, version: id.slice(3) });
          else if (id) emit('action', { name: id, path: place.path });
        });
        strip.append(group);
      }
      const more = h('button', { type: 'button', class: 'add-tab', title: '作業空間の一覧（閉じたタブを再表示）', 'aria-label': '作業空間の一覧（閉じたタブを再表示）',
        'aria-expanded': String(Boolean(state.list)) });
      more.innerHTML = DOWN;
      more.addEventListener('click', () => { state.list = !state.list; redraw(); });
      box.append(h('div', { class: 'tab-bar' }, strip, more));
    }

    // ▼：作業空間の一覧（閉じたタブをまた出す・作業空間を削除）
    if (state.list) {
      const shut = () => { state.list = false; redraw(); };
      const rows = h('div', { class: 'rows' });
      for (const place of places) {
        const { branch, title, where } = label(place);
        const open = h('button', { type: 'button', class: 'pick' }, title || branch,
          !closed.has(keyOf(place.path)) ? h('span', { class: 'picker-shown' }, '表示中') : '',
          h('small', {}, ...(title ? [branch, h('br')] : []), `${where}：${place.path}`));
        open.addEventListener('click', () => { state.list = false; if (place === shown) redraw(); else show(place); });
        const row = h('div', { class: 'picker-row' }, open);
        if (place.name) {
          const remove = h('button', { type: 'button', class: 'picker-remove', title: '作業空間を削除（フォルダごと。タスクブランチは残ります）' }, '削除…');
          remove.addEventListener('click', () => { state.list = false; redraw(); emit('action', { name: 'remove', path: place.path }); });
          row.append(remove);
        }
        rows.append(row);
      }
      if (!places.length) rows.append(h('p', { class: 'help' }, '作業空間はまだありません。タスク管理でタスクの「作業を開始」すると作られます。'));
      const tasks = h('button', { type: 'button' }, 'タスク管理を開く');
      tasks.addEventListener('click', () => { state.list = false; emit('action', { name: 'tasks' }); });
      const done = h('button', { type: 'button' }, '閉じる');
      done.addEventListener('click', shut);
      const picker = h('div', { class: 'picker', role: 'dialog', 'aria-label': '作業空間' }, h('h2', {}, '作業空間'), rows, h('div', { class: 'picker-actions' }, tasks, done));
      picker.addEventListener('keydown', (event) => { if (event.key === 'Escape') { event.stopPropagation(); shut(); } });
      const veil = h('div', { class: 'veil' }, picker);
      veil.addEventListener('click', (event) => { if (event.target === veil) shut(); });
      box.append(veil);
    }

    // 出しているタブがない：案内のページ
    if (!shown && !current) {
      if (props.error) box.append(h('p', { class: 'problem', role: 'alert' }, props.error));
      else if (!loaded || (visible.length && !state.list)) box.append(h('p', { class: 'waiting muted' }, '読み込み中…'));
      else if (!visible.length) {
        const icon = h('div', { class: 'empty-icon', 'aria-hidden': 'true' });
        icon.innerHTML = FOLDER;
        const tasks = h('button', { type: 'button', class: 'primary' }, 'タスク管理を開く');
        tasks.addEventListener('click', () => emit('action', { name: 'tasks' }));
        const actions = h('div', { class: 'empty-actions' }, tasks);
        if (places.length) {
          const list = h('button', { type: 'button' }, '作業空間の一覧');
          list.addEventListener('click', () => { state.list = true; redraw(); });
          actions.append(list);
        }
        box.append(h('div', { class: 'empty-workspaces' }, icon, h('h2', {}, '表示中の作業空間はありません'),
          h('p', {}, 'タスク管理でタスクの「作業を開始」すると、ここにタブで開きます。'), actions));
      }
    }
    root.replaceChildren(box);
    const on = box.querySelector('.tab-group.on');  // タブが多いとき：今のタブを、見える所まで寄せる
    if (on) on.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (state.list) { const first = box.querySelector('.picker button'); if (first) first.focus(); }
  },
};
