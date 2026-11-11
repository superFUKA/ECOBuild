// 部品「試験を選ぶ木」。今までの GUI（build.js の chooseTests）と同じ：まとまりの木・半分の印・数「見つかった / 全部」・
// 前に流した結果の ✗ ✓ -・見つかったものを選ぶ／外す／すべて外す・「N 件を選んでいます」。
const MARK = { failed: '✗ ', passed: '✓ ', skipped: '- ' };

export default {
  render(root, props, { h, emit, state, redraw }) {
    if (!state.opened) { state.opened = new Set(); state.closed = new Set(); state.query = ''; }
    const names = props.rows.map((row) => row.name).filter(Boolean);
    // C++ の名前（サブプロジェクト.Suite.Test）か、Python の名前（フォルダー/ファイル::クラス::試験）か
    const dotted = names.length > 0 && names.every((name) => !name.includes('/') && !name.includes('::'));
    // 名前の、木を下る段：[見せる名前, まとまりの名前]。まとまりの名前を渡すと、中の全部が流れる
    const steps = (name) => {
      if (dotted) {
        const m = name.match(/^([^.]+)\.([^.]+)\.(.+)$/);
        return m ? [[m[1], m[1]], [m[2], `${m[1]}.${m[2]}.*`], [m[3], name]] : [[name, name]];
      }
      const [file, ...parts] = name.split('::'), dirs = file.split('/');
      return [...dirs.map((d, i) => [d, dirs.slice(0, i + 1).join('/')]), ...parts.map((p, i) => [p, [file, ...parts.slice(0, i + 1)].join('::')])];
    };
    const top = { key: '', children: new Map(), leaves: [] }, known = new Set(), above = new Map();
    for (const name of names) {
      if (known.has(name)) continue;
      known.add(name);
      let node = top;
      const path = steps(name);
      above.set(name, path.map(([, key]) => key));
      for (const [label, key] of path) {
        node.leaves.push(name);
        if (!node.children.has(key)) node.children.set(key, { key, label, children: new Map(), leaves: [] });
        node = node.children.get(key);
      }
      node.leaves.push(name); node.leaf = name;
    }
    // 選んでいるもの：試験の名前そのものか、それを含むまとまりの名前
    const given = new Set(props.checked || []);
    const picked = new Set(names.filter((name) => above.get(name).some((key) => given.has(key))));
    const status = new Map(((props.last && props.last.cases) || []).map((c) => [c.name, c.status]));
    const query = state.query.toLowerCase().split(/\s+/).filter(Boolean);
    const shown = (name) => query.every((word) => name.toLowerCase().includes(word));
    // 出すもの：全部チェックしたまとまりは名前1つ（全部なら、いちばん上のまとまりごと）。木にない名前（前に選んだもの）は残す
    const values = (set) => {
      const walk = (node) => (!node.leaf && node.key && node.leaves.length > 1 && node.leaves.every((n) => set.has(n)) ? [node.key]
        : node.leaf ? (set.has(node.leaf) ? [node.leaf] : []) : [...node.children.values()].flatMap(walk));
      const loose = [...given].filter((value) => !known.has(value) && ![...above.values()].some((keys) => keys.includes(value)));
      return [...walk(top), ...loose];
    };
    const tick = (leaves, on) => {
      const next = new Set(picked);
      for (const name of leaves) { if (on) next.add(name); else next.delete(name); }
      emit('changed', { values: values(next) });
    };

    const box = h('div', { class: 'pick' });
    const search = h('input', { type: 'search', placeholder: dotted ? '名前で探す（空白で区切ると、全部を含むもの）　例：Calc Add' : '名前で探す（空白で区切ると、全部を含むもの）　例：test_calc',
      'aria-label': '試験を名前で探す', value: state.query });
    search.addEventListener('input', () => { state.query = search.value; state.typing = true; redraw(); });
    const button = (label, action) => { const b = h('button', { type: 'button' }, label); b.addEventListener('click', action); return b; };
    const count = h('span', { class: 'tt-count' }, `${picked.size} 件を選んでいます`);
    const tools = h('p', { class: 'test-pick-tools' },
      button('見つかったものを選ぶ', () => tick(top.leaves.filter(shown), true)),
      button('見つかったものを外す', () => tick(top.leaves.filter(shown), false)),
      button('選択をすべて外す', () => emit('changed', { values: [] })), count);
    const tree = h('div', { class: 'test-tree', role: 'group', 'aria-label': 'テスト' });

    // 開いておくもの：探して当たったもの・手で開いたもの・親に1つだけのまとまり・小さな木の全部
    const isOpen = (node, single) => query.length > 0 || state.opened.has(node.key) || (!state.closed.has(node.key) && (single || top.leaves.length <= 40));
    const row = (node, depth, single) => {
      const visible = node.leaves.filter(shown);
      if (!visible.length) return null;
      const on = node.leaves.filter((n) => picked.has(n)).length, group = !node.leaf, open = group && isOpen(node, single);
      const failed = node.leaves.some((n) => status.get(n) === 'failed');
      const mark = node.leaf ? (status.has(node.leaf) ? MARK[status.get(node.leaf)] || '✗ ' : '') : failed ? '✗ ' : '';
      const check = h('input', { type: 'checkbox' });
      check.checked = on > 0 && on === node.leaves.length;
      check.indeterminate = on > 0 && on < node.leaves.length;
      check.addEventListener('change', () => tick(node.leaves.filter(shown), check.checked));  // まとまりのチェックは、見えているものに効く
      const label = h('label', node.leaf ? { title: node.leaf } : {}, check,
        h('span', {}, mark ? h('span', { class: mark.startsWith('✗') ? 'failed' : mark.startsWith('✓') ? 'passed' : '' }, mark) : '', node.label));
      if (group) label.append(h('small', {}, (query.length ? `${visible.length} / ` : '') + node.leaves.length));
      const line = h('div', { class: 'tt-row', style: `--depth:${depth}` });
      if (group) {
        const toggle = h('button', { type: 'button', class: 'tt-toggle', 'aria-expanded': String(open), 'aria-label': open ? '畳む' : '開く' }, open ? '▾' : '▸');
        toggle.addEventListener('click', () => {
          (open ? state.opened : state.closed).delete(node.key);
          (open ? state.closed : state.opened).add(node.key);
          redraw();
        });
        line.append(toggle);
      } else line.append(h('span', { class: 'tt-toggle' }));
      line.append(label);
      const item = h('li', {}, line);
      if (group && open) {
        const kids = [...node.children.values()].map((child) => row(child, depth + 1, node.children.size === 1)).filter(Boolean);
        if (kids.length) item.append(h('ul', {}, ...kids));
      }
      return item;
    };
    const rows = [...top.children.values()].map((child) => row(child, 0, top.children.size === 1)).filter(Boolean);
    if (props.error) tree.append(h('p', { class: 'help', role: 'alert' }, props.error));
    else if (rows.length) tree.append(h('ul', {}, ...rows));
    else tree.append(h('p', { class: 'help' }, props.loading ? 'テストを探しています…' : names.length ? '検索に当てはまるテストはありません' : props.empty_text));
    box.append(search, tools, tree);
    const scroll = state.scroll || 0;
    root.replaceChildren(box);
    tree.scrollTop = scroll;
    tree.addEventListener('scroll', () => { state.scroll = tree.scrollTop; });
    if (state.typing) { state.typing = false; search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
  },
};
