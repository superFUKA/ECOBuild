// 部品「ヘルプ」。今までの GUI の help.js と同じ並び・同じ見た目（使い方の手順とコマンド一覧）。
// タブ・絞り込みの文字と型・選んでいるコマンドは、この部品の中だけの状態。何も実行しない（読んだ一覧を見せるだけ）。

// コマンドの道筋ごとに1件。variants：どこのコマンドか（'' は共通、ほかは型の名前）→ 一覧の1件
function collect(catalog) {
  const entries = new Map();
  const merge = (nodes, origin, parent) => {
    for (const node of nodes || []) {
      let entry = entries.get(node.path);
      if (!entry) {
        entry = { path: node.path, name: node.name, parent, variants: {}, children: [], section: '' };
        entries.set(node.path, entry);
        if (parent) entries.get(parent).children.push(entry);
      }
      entry.variants[origin] = node;
      if (node.section && !entry.section) entry.section = node.section;
      merge(node.commands, origin, node.path);
    }
  };
  merge(catalog.commands, '', '');
  for (const [type, value] of Object.entries(catalog.types || {})) merge(value.commands, type, '');
  return entries;
}
const main = (entry) => entry.variants[''] || Object.values(entry.variants)[0];
const typesOf = (entry) => (entry.variants[''] ? [] : Object.keys(entry.variants));   // 型だけにあるコマンドの、型
const usageText = (node) => {
  const parts = ['ecobuild', node.path];
  if ((node.options || []).length) parts.push('[オプション]');
  for (const argument of node.arguments || []) {
    const name = argument.name + (argument.multiple ? '...' : '');
    parts.push(argument.required ? name : `[${name}]`);
  }
  return parts.join(' ');
};

export default {
  render(root, props, { h, state, memory, keys }) {
    if (props.error) return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, `読めませんでした：${props.error}`)));
    const entries = collect(props.catalog || {});
    const types = Object.keys((props.catalog || {}).types || {});
    const label = (type) => (props.type_labels || {})[type] || type;
    if (state.tab === undefined) {
      state.tab = memory.get('tab', 'guide') === 'commands' ? 'commands' : 'guide';
      state.filter = memory.get('type', 'all');
      state.query = '';
      state.selected = props.first || '';
      state.origin = '';
    }
    if (state.filter !== 'all' && !types.includes(state.filter)) state.filter = 'all';

    // --- 探す：文字に合うか・合った文字に印 ---
    const words = () => state.query.toLowerCase().split(/\s+/).filter(Boolean);
    const textOf = (entry) => Object.values(entry.variants).map((node) => [node.path, node.summary, node.help,
      ...(node.options || []).flatMap((option) => [...(option.names || []), option.help]),
      ...(node.arguments || []).map((argument) => `${argument.name} ${argument.help}`)].join(' ')).join(' ').toLowerCase();
    const matches = (entry) => { const text = textOf(entry); return words().every((word) => text.includes(word)); };
    const marked = (value) => {   // 探した文字のところを <mark> にした並び
      const text = String(value || '');
      const found = words();
      if (!found.length) return [text];
      const lower = text.toLowerCase();
      const out = [];
      let at = 0;
      while (at < text.length) {
        let next = -1, length = 0;
        for (const word of found) {
          const index = lower.indexOf(word, at);
          if (index >= 0 && (next < 0 || index < next)) { next = index; length = word.length; }
        }
        if (next < 0) break;
        if (next > at) out.push(text.slice(at, next));
        out.push(h('mark', {}, text.slice(next, next + length)));
        at = next + length;
      }
      if (at < text.length) out.push(text.slice(at));
      return out;
    };
    const visible = (entry) => state.filter === 'all' || entry.variants[''] || entry.variants[state.filter] || entry.children.some(visible);
    // コマンドと、その下のコマンド（まとまりの名前だけのものは、それ自身は出さない）
    const flatten = (entry) => {
      const below = entry.children.flatMap(flatten);
      return Object.values(entry.variants).some((node) => node.runnable) || !entry.children.length ? [entry, ...below] : below;
    };
    const badges = (entry) => typesOf(entry).map((type) => h('span', { class: `type t-${type}` }, label(type)));

    // --- 骨組み ---
    const tabGuide = h('button', { type: 'button', role: 'tab' }, '使い方');
    const tabCommands = h('button', { type: 'button', role: 'tab' }, 'コマンド一覧');
    const guide = h('div', { class: 'guide' });
    const commands = h('div', { class: 'commands' });
    const search = h('input', { type: 'search', value: state.query, placeholder: 'コマンド・説明・オプションで探す（/ で移動）', autocomplete: 'off', 'aria-label': 'コマンドを探す' });
    const count = h('small', {});
    const filters = h('div', { class: 'filter', role: 'group', 'aria-label': '型で絞り込む' });
    const typeNote = h('p', { class: 'note' });
    const list = h('div', { class: 'list' });
    const detail = h('article', { class: 'detail', 'aria-live': 'polite' });

    const showTab = (name) => {
      state.tab = name;
      memory.set('tab', name);
      tabGuide.setAttribute('aria-selected', String(name === 'guide'));
      tabCommands.setAttribute('aria-selected', String(name === 'commands'));
      guide.hidden = name !== 'guide';
      commands.hidden = name !== 'commands';
    };
    tabGuide.addEventListener('click', () => showTab('guide'));
    tabCommands.addEventListener('click', () => showTab('commands'));

    const select = (path, reveal) => {
      if (!entries.has(path)) return;
      state.selected = path;
      drawDetail();
      detail.scrollTop = 0;
      for (const [rowPath, row] of rows) {
        row.className = rowPath === path ? 'row selected' : 'row';
        if (rowPath === path && reveal) row.scrollIntoView({ block: 'nearest' });
      }
    };
    const refTo = (path, cls, ...children) => {
      const button = h('button', { type: 'button', class: cls }, ...children);
      button.addEventListener('click', () => select(path, true));
      return button;
    };
    // 説明の中の「ecobuild task finish」は、そのコマンドへの飛び先に。--option はコードの見た目に
    const linked = (value) => {
      const out = [];
      const text = String(value || '');
      const pattern = /ecobuild((?: [a-z][a-z-]*)+)|(^|[\s（(「、・])(--[a-z][a-z-]*)/g;
      let at = 0;
      for (let found = pattern.exec(text); found; found = pattern.exec(text)) {
        if (found.index > at) out.push(text.slice(at, found.index));
        if (found[1]) {
          const names = found[1].trim().split(' ');
          let done = false;
          for (let n = names.length; n > 0 && !done; n -= 1) {
            const path = names.slice(0, n).join(' ');
            if (entries.has(path)) {
              out.push(refTo(path, 'ref', `ecobuild ${path}`), names.slice(n).map((name) => ` ${name}`).join(''));
              done = true;
            }
          }
          if (!done) out.push(h('code', {}, found[0]));
        } else {
          out.push(found[2], h('code', {}, found[3]));
        }
        at = found.index + found[0].length;
      }
      if (at < text.length) out.push(text.slice(at));
      return out;
    };

    // --- 使い方 ---
    if (props.intro) guide.append(h('p', { class: 'note' }, props.intro));
    const steps = h('ol', { class: 'steps' });
    (props.steps || []).forEach((step, index) => {
      const chips = h('p', { class: 'chips' });
      for (const command of step.commands || []) {
        const chip = h('button', { type: 'button', title: `コマンド一覧の ${command} へ` }, command);
        chip.addEventListener('click', () => { showTab('commands'); select(command, true); });
        chips.append(chip);
      }
      steps.append(h('li', {}, h('span', { class: 'step-number' }, String(index + 1)),
        h('div', {}, h('h4', {}, step.title || ''), h('p', { class: 'where' }, step.where || ''), h('p', { class: 'note' }, step.text || ''), chips)));
    });
    guide.append(steps);
    if ((props.terms || []).length) {
      const terms = h('dl', { class: 'terms' });
      for (const term of props.terms) terms.append(h('div', {}, h('dt', {}, term.term || ''), h('dd', {}, term.text || '')));
      guide.append(h('h3', { class: 'terms-title' }, '用語'), terms);
    }

    // --- コマンド一覧 ---
    let rows = [];   // [道筋, 行のボタン]
    const drawFilters = () => {
      filters.replaceChildren(...[['all', 'すべて'], ...types.map((type) => [type, label(type)])].map(([value, text]) => {
        const button = h('button', { type: 'button' }, text);
        button.setAttribute('aria-pressed', String(value === state.filter));
        button.addEventListener('click', () => { state.filter = value; memory.set('type', value); drawFilters(); drawList(); });
        return button;
      }));
      typeNote.textContent = state.filter === 'all'
        ? '型ごとのコマンドは、その型のモジュールの中でだけ使えます（印の付いたもの）。'
        : `${label(state.filter)}（型 ${state.filter}）のモジュールの中で使えるコマンドです。`;
    };
    const row = (entry) => {
      const button = h('button', { type: 'button', class: entry.path === state.selected ? 'row selected' : 'row' },
        h('code', {}, ...marked(entry.path)), ...badges(entry), h('span', { class: 'summary' }, ...marked(main(entry).summary)));
      button.addEventListener('click', () => select(entry.path));
      rows.push([entry.path, button]);
      return h('li', {}, button);
    };
    const block = (top, leaves) => {
      const title = refTo(top.path, 'group-title', h('code', {}, top.name), ...badges(top), h('span', { class: 'summary' }, main(top).summary || ''));
      const box = h('div', { class: 'group' }, title);
      let section = null, ul = null;
      for (const leaf of leaves) {
        if (leaf.section && leaf.section !== section) {
          section = leaf.section;
          ul = h('ul', { class: 'rows' });
          box.append(h('h4', {}, section), ul);
        } else if (!ul) {
          ul = h('ul', { class: 'rows' });
          box.append(ul);
        }
        ul.append(row(leaf));
      }
      return box;
    };
    const drawList = () => {
      rows = [];
      if (!entries.size) {
        count.textContent = '';
        return list.replaceChildren(h('p', { class: 'note', role: 'status' }, ...(props.loading ? [h('span', { class: 'spinner' }), ' コマンドの一覧を読み込んでいます…'] : ['コマンドはありません'])));
      }
      const tops = [...entries.values()].filter((entry) => !entry.parent && visible(entry));
      const searching = words().length > 0;
      const known = new Set((props.categories || []).flatMap((category) => category.commands || []));
      const groups = [...(props.categories || []), { title: 'その他', commands: tops.map((entry) => entry.name).filter((name) => !known.has(name)) }];
      const out = [];
      let total = 0;
      for (const group of groups) {
        const boxes = [];
        let singles = null;   // 1つだけのコマンドは、同じ箱にまとめる
        for (const name of group.commands || []) {
          const top = tops.find((entry) => entry.name === name);
          if (!top) continue;
          const leaves = flatten(top).filter((entry) => visible(entry) && (!searching || matches(entry)));
          if (!leaves.length) continue;
          total += leaves.length;
          if (leaves.length === 1 && leaves[0] === top) {
            if (!singles) { singles = h('ul', { class: 'rows single' }); boxes.push(singles); }
            singles.append(row(top));
          } else {
            singles = null;
            boxes.push(block(top, leaves));
          }
        }
        if (boxes.length) out.push(h('section', { class: 'category' }, h('h3', {}, group.title || ''), ...boxes));
      }
      count.textContent = searching ? `${total} 件` : '';
      if (!out.length) out.push(h('p', { class: 'note empty' }, `「${state.query}」に合うコマンドはありません。`));
      list.replaceChildren(...out);
      if (!state.selected || !entries.has(state.selected)) state.selected = entries.has(props.first) ? props.first : (rows[0] || [''])[0];
      drawDetail();
    };

    // --- 選んだコマンド ---
    const paragraphs = (help, summary) => {   // 初めの段落は要約（上に出している）。残りを、段落ごとに
      const parts = String(help || '').split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
      if (parts[0] && parts[0].replace(/\s+/g, '') === String(summary || '').replace(/\s+/g, '')) parts.shift();
      // 箇条書き：行の頭が「- 」「* 」「・」（「--option」で始まる行は、箇条書きではない）
      return parts.map((part) => (/^\s*(?:[-*]\s|・)/m.test(part) && part.split('\n').length > 1
        ? h('ul', { class: 'bullets' }, ...part.split('\n').map((line) => h('li', {}, ...linked(line.replace(/^\s*(?:[-*]\s+|・\s*)/, '')))))
        : h('p', { class: 'body' }, ...linked(part.replace(/\n(?=\S)/g, '')))));
    };
    const tag = (text, need) => h('span', { class: need ? 'tag need' : 'tag' }, text);
    const drawDetail = () => {
      const entry = entries.get(state.selected);
      if (!entry) return detail.replaceChildren();
      const origins = Object.keys(entry.variants);
      if (!origins.includes(state.origin)) state.origin = origins.includes(state.filter) ? state.filter : origins[0];
      const node = entry.variants[state.origin];
      const crumbs = h('div', { class: 'crumbs' }, h('span', {}, 'ecobuild'));
      entry.path.split(' ').forEach((name, index, all) => {
        crumbs.append(h('span', {}, '›'));
        crumbs.append(index < all.length - 1 ? refTo(all.slice(0, index + 1).join(' '), 'link', name) : h('strong', {}, name));
      });
      const out = [crumbs, h('h3', {}, h('code', {}, entry.path))];
      if (origins.length > 1) {   // 同じ名前のコマンドが、型ごとにある（build・test 等）
        out.push(h('div', { class: 'variants', role: 'tablist' }, ...origins.map((origin) => {
          const button = h('button', { type: 'button', role: 'tab' }, origin ? label(origin) : '共通');
          button.setAttribute('aria-selected', String(origin === state.origin));
          button.addEventListener('click', () => { state.origin = origin; drawDetail(); });
          return button;
        })));
      }
      out.push(h('p', { class: 'summary-line' }, ...linked(node.summary)));
      if (state.origin) out.push(h('p', { class: 'where' }, '型 ', h('b', {}, state.origin), `（${label(state.origin)}）のモジュールの中で使えます。`));
      if (node.runnable) {
        const text = usageText(node);
        const copy = h('button', { type: 'button', class: 'copy' }, 'コピー');
        copy.addEventListener('click', () => {
          const done = (words) => { copy.textContent = words; setTimeout(() => { copy.textContent = 'コピー'; }, 1500); };
          try {
            navigator.clipboard.writeText(text).then(() => done('コピーしました'), () => done('コピーできませんでした'));
          } catch (error) {
            done('コピーできませんでした');
          }
        });
        out.push(h('div', { class: 'usage' }, h('code', {}, text), copy));
      }
      out.push(...paragraphs(node.help, node.summary));
      if (node.default_help) out.push(...paragraphs(node.default_help, node.summary));
      if (node.runnable && (node.arguments || []).length) {
        out.push(h('h4', {}, '引数'), h('dl', { class: 'params' }, ...node.arguments.map((argument) => h('div', {},
          h('dt', {}, h('code', {}, argument.name + (argument.multiple ? '...' : '')), argument.required ? tag('必須', true) : tag('省略可'),
            ...(argument.multiple ? [tag('複数')] : [])),
          h('dd', {}, ...linked(argument.help))))));
      }
      if (node.runnable && (node.options || []).length) {
        out.push(h('h4', {}, 'オプション'), h('dl', { class: 'params' }, ...node.options.map((option) => {
          const name = h('code', {}, (option.names || []).join(', '));
          if (!option.flag) name.append(' ', h('i', {}, option.value || '値'));
          const tags = [];
          if (option.required) tags.push(tag('必須', true));
          if (option.multiple) tags.push(tag('何度でも'));
          if (option.default !== undefined && option.default !== null && option.default !== '' && option.default !== false) tags.push(tag(`既定：${option.default}`));
          const text = h('dd', {}, ...linked(option.help));
          if (option.choices) text.append(h('div', { class: 'choices' }, ...option.choices.map((choice) => h('code', {}, String(choice)))));
          return h('div', {}, h('dt', {}, name, ...tags), text);
        })));
      }
      const below = entry.children.filter(visible);
      if (below.length) {
        out.push(h('h4', {}, 'コマンド'), h('ul', { class: 'sub' }, ...below.map((child) => h('li', {},
          refTo(child.path, 'link', h('code', {}, child.name)), ...badges(child), h('span', { class: 'summary' }, ...linked(main(child).summary))))));
      }
      out.push(h('p', { class: 'common' }, 'どのコマンドにも：', h('code', {}, '-C <パス>'), ' 別のフォルダのモジュールを対象にする（コマンドの前に書く）・',
        h('code', {}, '--json'), ' 結果をJSONで出す・', h('code', {}, '--help'), ' 使い方を表示する'));
      detail.replaceChildren(...out);
    };

    search.addEventListener('input', () => { state.query = search.value.trim(); drawList(); });
    search.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { search.value = ''; state.query = ''; drawList(); return; }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp' && event.key !== 'Enter') return;
      if (!rows.length) return;
      event.preventDefault();
      const at = rows.findIndex(([path]) => path === state.selected);
      const next = event.key === 'Enter' ? Math.max(at, 0) : event.key === 'ArrowDown' ? Math.min(rows.length - 1, at + 1) : Math.max(0, at - 1);
      select(rows[next][0], true);
    });
    commands.append(h('div', { class: 'toolbar' }, h('label', { class: 'search' }, search, count), filters), typeNote, h('div', { class: 'panes' }, list, detail));
    const page = h('div', { class: 'help' },
      h('div', { class: 'heading' }, h('h2', {}, 'ヘルプ'), h('div', { class: 'tabs', role: 'tablist' }, tabGuide, tabCommands)), guide, commands);
    // 「/」で、窓のどこからでも探す欄へ（keys。欄に打っているときは、その欄に「/」を入れる）
    page.addEventListener('focusin', (event) => { state.typing = /^(INPUT|TEXTAREA)$/.test(event.target.tagName) ? event.target : null; });
    page.addEventListener('focusout', () => { state.typing = null; });
    keys('/', () => {
      const field = state.typing;
      if (field && field.isConnected && typeof field.setRangeText === 'function') {
        field.setRangeText('/', field.selectionStart, field.selectionEnd, 'end');
        field.dispatchEvent(new Event('input'));
        return;
      }
      if (commands.hidden) showTab('commands');
      search.focus();
    });
    drawFilters();
    drawList();
    showTab(state.tab);
    root.replaceChildren(page);
  },
};
