// 部品「左のメニュー」。上に窓の題（モジュールの名前）、まとまりごとの項目（アイコン付き）、下にアカウント。
// 折りたたむとアイコンだけになる（この PC に覚える）。今の項目に印を付ける。
// 上の項目は、ドラッグ（キーボードなら Alt+↑／↓）で並べ替えられる（この PC に覚える。下の設定・ヘルプは動かさない）。
const ICONS = {
  module: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  tasks: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/>',
  board: '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="10" rx="1"/><rect x="17" y="4" width="4" height="13" rx="1"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  submit: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  branch: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 7v10"/><path d="M18 10c0 4-6 3-11.2 7.5"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  members: '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.700 6 6"/><circle cx="17" cy="9" r="2.500"/><path d="M16 14.200c2.900.300 5 2.700 5 5.800"/>',
  flow: '<rect x="3" y="9" width="5" height="6" rx="1"/><rect x="16" y="9" width="5" height="6" rx="1"/><path d="M8 12h8M13 9l3 3-3 3"/>',
  ci: '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
  agent: '<rect x="5" y="8" width="14" height="11" rx="2"/><path d="M12 4v4M9 13h.01M15 13h.01M9 16h6"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.700 1.700 0 0 0 .3 1.800l.1.100a2 2 0 1 1-2.800 2.800l-.1-.100a1.700 1.700 0 0 0-1.800-.300 1.700 1.700 0 0 0-1 1.500V21a2 2 0 1 1-4 0v-.100a1.700 1.700 0 0 0-1.100-1.500 1.700 1.700 0 0 0-1.800.300l-.1.100a2 2 0 1 1-2.800-2.800l.1-.100a1.700 1.700 0 0 0 .3-1.800 1.700 1.700 0 0 0-1.500-1H3a2 2 0 1 1 0-4h.1a1.700 1.700 0 0 0 1.500-1.100 1.700 1.700 0 0 0-.3-1.800l-.1-.100a2 2 0 1 1 2.800-2.800l.1.100a1.700 1.700 0 0 0 1.800.300H9a1.700 1.700 0 0 0 1-1.500V3a2 2 0 1 1 4 0v.100a1.700 1.700 0 0 0 1 1.500 1.700 1.700 0 0 0 1.800-.300l.1-.100a2 2 0 1 1 2.800 2.800l-.1.100a1.700 1.700 0 0 0-.3 1.800V9a1.700 1.700 0 0 0 1.500 1H21a2 2 0 1 1 0 4h-.1a1.700 1.700 0 0 0-1.500 1z"/>',
  container: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.500 9a2.500 2.500 0 1 1 3.500 2.300c-.6.300-1 .900-1 1.600v.600"/><path d="M12 17h.01"/>',
  home: '<path d="M4 11l8-7 8 7"/><path d="M6 10v10h12V10"/>',
  operator: '<path d="M4 5h16v11H9l-5 4z"/>',
  collapse: '<path d="M15 6l-6 6 6 6"/>',
};
const ROLES = { admin: '管理者', maintain: '管理', write: '書き込み', triage: '整理', read: '読み取り' };

export default {
  render(root, props, { h, emit, memory, state, redraw }) {
    const icon = (name) => {
      const box = h('span', { class: 'icon', 'aria-hidden': 'true' });
      box.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        + (ICONS[name] || ICONS.module) + '</svg>';
      return box;
    };
    const collapsed = memory.shared.get('collapsed', false) === true;  // どの画面でも同じ（部品の種類ごとに覚える）
    const nav = h('nav', { class: collapsed ? 'side collapsed' : 'side', 'aria-label': 'メニュー' });

    const toggle = h('button', { type: 'button', class: 'toggle', title: collapsed ? 'メニューを広げる' : 'メニューを折りたたむ' }, icon('collapse'));
    toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.addEventListener('click', () => { memory.shared.set('collapsed', !collapsed); redraw(); });
    const top = h('div', { class: 'top' }, toggle);
    if (props.title) top.append(h('strong', { title: props.title }, props.title));
    nav.append(top);

    // 並べ替えた順は、項目の組（ハブ・モジュールの窓）ごとに覚える（どの画面に置いても同じ）
    const tops = props.items.filter((item) => !item.bottom);
    const orderKey = 'order:' + tops.map((item) => item.id).sort().join(',');
    const saved = memory.shared.get(orderKey, []) || [];
    const rank = (item) => { const at = saved.indexOf(item.id); return at < 0 ? saved.length : at; };
    const ordered = tops.map((item, i) => [item, i]).sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j).map(([item]) => item);
    const keep = (ids) => { memory.shared.set(orderKey, ids); redraw(); };

    let group = null;
    const list = h('div', { class: 'items' });
    for (const item of ordered) {
      if (item.group && item.group !== group) {
        group = item.group;
        list.append(h('div', { class: 'group' }, group));
      }
      list.append(movable(entry(item), item));
    }
    nav.append(list);

    const bottom = h('div', { class: 'bottom' });
    for (const item of props.items) if (item.bottom) bottom.append(entry(item));
    const account = props.account || {};
    if (account.login) {
      const role = ROLES[account.role] || account.role || '';
      const who = h('button', { type: 'button', class: 'account', title: 'ログイン中の GitHub アカウント' + (role ? '（' + role + '）' : '') },
        h('span', { class: 'avatar' }, String(account.login).slice(0, 1).toUpperCase()),
        h('span', { class: 'name' }, account.login));
      if (role) who.append(h('span', { class: 'role' }, role));
      who.addEventListener('click', () => emit('account', {}));
      bottom.append(who);
    }
    nav.append(bottom);
    root.replaceChildren(nav);
    if (state.refocus) { state.refocus.focus(); state.refocus = null; }  // Alt+↑／↓ で動かした項目に、フォーカスを残す

    // ドラッグで並べ替え・Alt+↑／↓ で1つ動かす
    function movable(button, item) {
      button.draggable = true;
      button.addEventListener('dragstart', (event) => {
        state.dragged = item.id;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', item.id);
        button.classList.add('dragging');
      });
      button.addEventListener('dragend', () => { state.dragged = null; button.classList.remove('dragging'); });
      button.addEventListener('dragover', (event) => { if (state.dragged && state.dragged !== item.id) event.preventDefault(); });
      button.addEventListener('drop', (event) => {
        if (!state.dragged || state.dragged === item.id) return;
        event.preventDefault();
        const box = button.getBoundingClientRect();
        const ids = ordered.map((x) => x.id).filter((id) => id !== state.dragged);
        ids.splice(ids.indexOf(item.id) + (event.clientY < box.top + box.height / 2 ? 0 : 1), 0, state.dragged);
        state.dragged = null;
        keep(ids);
      });
      button.addEventListener('keydown', (event) => {
        if (!event.altKey || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        const ids = ordered.map((x) => x.id);
        const at = ids.indexOf(item.id);
        const to = at + (event.key === 'ArrowUp' ? -1 : 1);
        if (to < 0 || to >= ids.length) return;
        ids.splice(at, 1);
        ids.splice(to, 0, item.id);
        state.focus = item.id;
        keep(ids);
      });
      if (state.focus === item.id) { state.focus = null; state.refocus = button; }
      return button;
    }

    function entry(item) {
      const button = h('button', { type: 'button', class: 'item', title: item.bottom ? item.label : item.label + '（ドラッグか Alt+↑／↓ で並べ替え）' }, icon(item.icon), h('span', {}, item.label));
      if (item.id === props.current) button.setAttribute('aria-current', 'page');
      button.addEventListener('click', () => emit('selected', { id: item.id }));
      return button;
    }
  },
};
