// 部品「コマンドの一覧」。ecobuild help --json の結果（共通のコマンドと、型ごとのコマンド）を、1つの一覧にして見せる。
// 絞り込みの文字・型・選んでいるコマンドは、この部品の中だけの状態（描く先ごとに覚える）。何も実行しない。
const STATE = new WeakMap();  // 描く先 → { query, type, selected, origin }

// コマンドの道筋ごとに1件。variants：どこのコマンドか（'' は共通、ほかは型の名前）→ 一覧の1件
function collect(catalog) {
  const entries = new Map();
  const merge = (nodes, origin, parent) => {
    for (const node of nodes || []) {
      let entry = entries.get(node.path);
      if (!entry) {
        entry = { path: node.path, name: node.name, parent, variants: {}, children: [] };
        entries.set(node.path, entry);
        if (parent) entries.get(parent).children.push(entry);
      }
      entry.variants[origin] = node;
      merge(node.commands, origin, node.path);
    }
  };
  merge(catalog.commands, '', '');
  for (const [type, value] of Object.entries(catalog.types || {})) merge(value.commands, type, '');
  return entries;
}

const main = (entry) => entry.variants[''] || Object.values(entry.variants)[0];
const typesOf = (entry) => (entry.variants[''] ? [] : Object.keys(entry.variants));  // 型だけにあるコマンドの、型
const runnable = (entry) => Object.values(entry.variants).some((node) => node.runnable);

function usage(node) {
  const parts = ['ecobuild', node.path];
  if ((node.options || []).length) parts.push('[オプション]');
  for (const argument of node.arguments || []) {
    const name = argument.name + (argument.multiple ? '...' : '');
    parts.push(argument.required ? name : `[${name}]`);
  }
  return parts.join(' ');
}

export default {
  render(root, props, { h }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const entries = collect(props.catalog);
    if (entries.size === 0) return root.replaceChildren(h('p', { role: 'status' }, props.loading ? 'コマンドの一覧を読み込んでいます…' : 'コマンドはありません'));
    if (!STATE.has(root)) STATE.set(root, { query: '', type: '', selected: props.first, origin: '' });
    const state = STATE.get(root);
    const label = (type) => props.type_labels[type] || type;
    const types = Object.keys(props.catalog.types || {});
    const muted = 'color:var(--gf-muted)';
    const code = 'font-family:ui-monospace,Consolas,monospace';
    const badge = (type) => h('small', { style: 'border:1px solid var(--gf-border);border-radius:var(--gf-radius);padding:0 .3rem;margin-left:.3rem' }, label(type));

    const inType = (entry) => !state.type || entry.variants[''] || entry.variants[state.type];
    const text = (entry) => Object.values(entry.variants).map((node) => [node.path, node.summary, node.help,
      ...(node.options || []).flatMap((option) => [...option.names, option.help]),
      ...(node.arguments || []).map((argument) => `${argument.name} ${argument.help}`)].join(' ')).join(' ').toLowerCase();
    const matches = (entry) => state.query.toLowerCase().split(/\s+/).filter(Boolean).every((word) => text(entry).includes(word));
    // 一覧に出すもの：実行できるコマンドと、下にコマンドのないもの（グループの名前だけのものは、見出しにする）
    const listed = () => [...entries.values()].filter((entry) => (runnable(entry) || !entry.children.length) && inType(entry) && matches(entry));

    const search = h('input', { type: 'search', value: state.query, placeholder: 'コマンド・説明・オプションで探す', 'aria-label': 'コマンドを探す', style: 'flex:1' });
    const count = h('small', {}, '');
    const filters = h('div', { class: 'row', role: 'group', 'aria-label': '型で絞る' });
    const list = h('div', { style: 'flex:0 0 19rem;max-height:30rem;overflow:auto;border:1px solid var(--gf-border);border-radius:var(--gf-radius)' });
    const detail = h('div', { style: 'flex:1;min-width:0;max-height:30rem;overflow:auto;display:grid;gap:.5rem;align-content:start' });

    const select = (path) => { state.selected = path; state.origin = ''; drawList(); drawDetail(); };
    const link = (path, words) => {
      const button = h('button', { type: 'button', style: `${code};border:0;background:transparent;padding:0;color:var(--gf-accent)` }, words);
      button.addEventListener('click', () => select(path));
      return button;
    };

    const drawFilters = () => {
      filters.replaceChildren(...[['', 'すべて'], ...types.map((type) => [type, label(type)])].map(([type, words]) => {
        const button = h('button', { type: 'button', 'aria-pressed': String(state.type === type), 'aria-selected': String(state.type === type) }, words);
        button.addEventListener('click', () => { state.type = type; drawFilters(); drawList(); drawDetail(); });
        return button;
      }));
    };

    const drawList = () => {
      const found = listed().sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
      count.textContent = `${found.length} 件`;
      if (!found.length) return list.replaceChildren(h('p', { role: 'status', style: `${muted};margin:.5rem .6rem` }, '当てはまるコマンドはありません'));
      const rows = h('ul', { role: 'listbox', style: 'gap:0' });
      let group = null;
      for (const entry of found) {
        const top = entry.path.split(' ')[0];
        if (top !== group && entry.path !== top) rows.append(h('li', { style: `${muted};padding:.4rem .6rem .1rem;font-size:.85em` }, top));
        group = top;
        const on = entry.path === state.selected;
        const row = h('button', { type: 'button', role: 'option', 'aria-selected': String(on),
          style: 'display:block;width:100%;text-align:left;border:0;border-radius:0;background:transparent;padding:.25rem .6rem' },
          h('span', { style: code + (on ? ';font-weight:600' : '') }, entry.path), ...typesOf(entry).map(badge),
          h('small', { style: 'display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis' }, main(entry).summary || ''));
        if (on) row.style.background = 'var(--gf-surface)';
        row.addEventListener('click', () => select(entry.path));
        rows.append(h('li', {}, row));
      }
      list.replaceChildren(rows);
    };

    const params = (title, items, name) => {
      const box = h('dl', { style: 'display:grid;grid-template-columns:max-content 1fr;gap:.3rem 1rem;margin:0' });
      for (const item of items) {
        const notes = [item.required ? '必須' : '', item.multiple ? 'いくつでも' : '',
          item.default !== undefined && item.default !== null && item.default !== '' && item.default !== false ? `既定：${item.default}` : '',
          item.choices ? `選べる値：${item.choices.join('・')}` : ''].filter(Boolean).join('、');
        box.append(h('dt', { style: code }, name(item)), h('dd', { style: 'margin:0' }, item.help || '', ...(notes ? [h('small', { style: 'display:block' }, notes)] : [])));
      }
      return [h('strong', {}, title), box];
    };

    const drawDetail = () => {
      const entry = entries.get(state.selected) || listed()[0];
      if (!entry) return detail.replaceChildren(h('p', { role: 'status', style: muted }, 'コマンドを選ぶと、使い方が出ます'));
      const origins = Object.keys(entry.variants);
      if (!origins.includes(state.origin)) state.origin = origins.includes(state.type) ? state.type : origins[0];
      const node = entry.variants[state.origin];
      const parts = [h('div', { style: `${code};font-size:1.15em;font-weight:600` }, `ecobuild ${entry.path}`)];
      if (origins.length > 1) {  // 同じ名前のコマンドが、型ごとにある（build・test 等）
        parts.push(h('div', { class: 'row', role: 'group', 'aria-label': 'どの型のコマンドか' }, ...origins.map((origin) => {
          const button = h('button', { type: 'button', 'aria-selected': String(origin === state.origin) }, origin ? label(origin) : '共通');
          button.addEventListener('click', () => { state.origin = origin; drawDetail(); });
          return button;
        })));
      }
      if (state.origin) parts.push(h('small', {}, `型 ${state.origin}（${label(state.origin)}）のモジュールの中で使えます。`));
      if (node.runnable) parts.push(h('pre', { style: `${code};margin:0;padding:.4rem .6rem;white-space:pre-wrap;border:1px solid var(--gf-border);border-radius:var(--gf-radius)` }, usage(node)));
      for (const words of [node.help || node.summary || '', node.default_help || '']) {
        for (const paragraph of words.split(/\n\s*\n/).map((one) => one.trim()).filter(Boolean)) {
          parts.push(h('p', { style: 'margin:0;white-space:pre-wrap' }, paragraph));
        }
      }
      if (node.runnable && (node.arguments || []).length) parts.push(...params('引数', node.arguments, (item) => item.name + (item.multiple ? '...' : '')));
      if (node.runnable && (node.options || []).length) {
        parts.push(...params('オプション', node.options, (item) => item.names.join(', ') + (item.flag ? '' : ` ${item.value || '値'}`)));
      }
      const below = entry.children.filter(inType);
      if (below.length) {
        const box = h('ul', {});
        for (const child of below) box.append(h('li', {}, link(child.path, child.name), ...typesOf(child).map(badge), h('small', { style: 'margin-left:.5rem' }, main(child).summary || '')));
        parts.push(h('strong', {}, 'コマンド'), box);
      }
      if (entry.parent) parts.push(h('div', {}, h('small', {}, '上のコマンド：'), link(entry.parent, entry.parent)));
      parts.push(h('small', {}, 'どのコマンドにも：-C <パス>（別のフォルダーのモジュールを相手にする。コマンドの前に書く）・--json（結果を JSON で出す）・--help（使い方）'));
      detail.replaceChildren(...parts);
    };

    search.addEventListener('input', () => { state.query = search.value; drawList(); });
    drawFilters();
    drawList();
    drawDetail();
    root.replaceChildren(h('div', { style: 'display:grid;gap:.5rem' },
      h('div', { style: 'display:flex;gap:.5rem;align-items:center' }, search, count), filters,
      h('small', {}, '型の印の付いたコマンドは、その型のモジュールの中でだけ使えます。'),
      h('div', { style: 'display:flex;gap:1rem;align-items:flex-start' }, list, detail)));
  },
};
