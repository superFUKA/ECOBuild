// 部品「ハブのモジュールの一覧」。今までの GUI（static/hub.js の renderModules・renderArchived・renderLegacy）と同じ見せ方。
// ここでするのは見せ方だけ：型ごとに分ける・アーカイブ済みを別に出す・頭文字と色・並べ替え（この PC に覚える）。
// 開く・外す・片付けるは、出力（action・archived・legacy・add）で出す。
const TYPE_LABELS = { cpp: 'C++', python: 'Python', generic: 'その他（generic）' };
const ARCHIVED = 'archived';  // 前に GitHub から聞いた「アーカイブ済み」（GitHub の答えを待つあいだ、一覧に混ぜないため）
const ORDER = 'order';        // 並べ替えた順（フォルダーの並び）

const pathKey = (path) => String(path).replaceAll('\\', '/').toLowerCase();
const baseName = (path) => String(path).split(/[\\/]/).filter(Boolean).pop() || String(path);
// 所有者/名前 がどちらにもあればそれで、なければ名前で比べる（origin が GitHub でないモジュールは名前だけ）
const sameRepository = (a, b) => {
  if (!a || !b) return false;
  const full = a.includes('/') && b.includes('/');
  const key = (x) => (full ? x : x.split('/').pop()).toLowerCase();
  return key(a) === key(b);
};
const cloneRepository = (clone) => clone.repository || (clone.url ? baseName(clone.url).replace(/\.git$/, '') : '');
// カードの色：名前から決める（並べ替えても変わらない）
const hueOf = (name) => [...name].reduce((hue, c) => (hue * 33 + c.charCodeAt(0)) >>> 0, 5381) % 6;
// 頭文字：多くのモジュールに共通の接頭辞を飛ばした2文字（ECOSTL・ECOCppLogger → ST・CL）
function initialsOf(name, modules) {
  const lower = name.toLowerCase();
  let rest = name;
  for (const other of modules) {
    if (other.name === name) continue;
    let n = 0;
    const o = other.name.toLowerCase();
    while (n < lower.length && lower[n] === o[n]) n++;
    while (n >= 2 && !(n < name.length && /[A-Z0-9_\-. ]/.test(name[n]))) n--;  // 語の切れ目でだけ切る
    if (n >= 2 && name.length - n < rest.length) rest = name.slice(n);
  }
  rest = rest.replace(/^[_\-. ]+/, '') || name;
  const second = (rest.slice(1).match(/[A-Z0-9]/) || [])[0] || rest[1] || '';
  return (rest[0] || '?').toUpperCase() + second;
}

export default {
  render(root, props, { h, emit, menu, memory, state, redraw }) {
    if (props.rows === null) {
      return root.replaceChildren(h('p', { class: 'empty', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…'));
    }
    // GitHub の答え（known）が届いたら、アーカイブ済みを覚え直す。届くまでは、前に覚えたもので分ける
    let known = props.known;
    if (known) {
      const now = known.filter((g) => g.archived).map((g) => ({ repository: g.repository, description: g.description || '', archived: true }));
      if (JSON.stringify(now) !== JSON.stringify(memory.get(ARCHIVED, []))) memory.set(ARCHIVED, now);
    } else {
      known = memory.get(ARCHIVED, []) || [];
    }
    const githubEntry = (m) => known.find((g) => sameRepository(g.repository, m.repository || m.name));
    const order = (memory.get(ORDER, []) || []).map(pathKey);
    const rank = (m) => { const i = order.indexOf(pathKey(m.path)); return i < 0 ? order.length : i; };
    const modules = props.rows
      .map((c) => {
        const repository = cloneRepository(c);
        const entry = repository ? known.find((g) => sameRepository(g.repository, repository)) : null;
        return { path: c.path, name: baseName(c.repository || '') || baseName(c.path), exists: c.exists !== false, repository,
          github: Boolean(c.repository), notClone: c.exists !== false && !c.url, type: c.type || (entry && entry.type) || '' };
      })
      .filter((m) => !(githubEntry(m) || {}).archived)
      .map((m, i) => [m, i]).sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j).map(([m]) => m);
    const archived = known.filter((g) => g.archived).map((g) => {
      const local = [...props.rows, ...props.legacy].filter((c) => c.exists !== false && sameRepository(g.repository, cloneRepository(c)));
      return { repository: g.repository, description: g.description || '', clones: local.map((c) => c.path) };
    });

    const box = h('div', { class: 'modules' });
    if (!modules.length) {
      if (archived.length) {
        box.append(h('p', { class: 'empty' }, 'アーカイブしていないモジュールはありません。'));
      } else {
        const add = h('button', { type: 'button', class: 'primary' }, '＋ モジュール追加');
        add.addEventListener('click', () => emit('add', {}));
        box.append(h('div', { class: 'empty' }, 'モジュールはまだありません。', h('div', { class: 'empty-actions' }, add)));
      }
    } else {
      const list = h('ul', { class: 'module-list', 'aria-label': 'モジュール一覧' });
      // 型ごとの見出し（型が一覧に初めて出る順。型が分からないものは最後）
      const types = [...new Set(modules.map((m) => m.type || ''))].sort((a, b) => (a === '') - (b === ''));
      for (const type of types) {
        const members = modules.filter((m) => (m.type || '') === type);
        list.append(h('li', { class: 'type-head', role: 'presentation' },
          h('h3', {}, type ? (TYPE_LABELS[type] || type) : '型が分からないもの'), h('span', {}, String(members.length))));
        for (const m of members) list.append(card(m));
      }
      box.append(list);
    }
    if (archived.length) box.append(archivedBox());
    if (props.legacy.length) box.append(legacyBox());
    root.replaceChildren(box);

    function reasonOf(m) {
      if (m.notClone) return 'このフォルダは git の clone ではなくなっています（削除が途中で止まった等）。GitHub のリポジトリとはつながっていないので、アーカイブ・削除はできません。';
      if (!m.exists) return `フォルダ ${m.path} が見つかりません（移動・削除された等）。移動した場合は、移動先を「＋ モジュール追加」の「手元のフォルダを登録」で登録してください。`;
      return '';
    }
    function act(m, action, reason) {
      emit('action', { id: m.path, action, name: m.name, repository: m.repository, reason: reason || '' });
    }
    function card(m) {
      const mark = !m.exists ? 'フォルダが見つかりません' : m.notClone ? 'gitのcloneではありません' : '';
      const name = h('span', { class: 'module-name' }, h('span', { class: 'label' }, m.name));
      if (mark) name.append(h('span', { class: 'module-state' }, mark));
      const open = h('button', { type: 'button', class: 'open' },
        h('span', { class: 'module-icon c' + hueOf(m.name), 'aria-hidden': 'true' }, initialsOf(m.name, modules)),
        h('span', { class: 'module-text' }, name, h('span', { class: 'module-path' }, m.repository || m.path)),
        h('span', { class: 'module-go', 'aria-hidden': 'true' }, '↗'));
      // 開けないモジュール（フォルダがない・clone でない）は、理由と一緒に「一覧から外す」を出す
      open.addEventListener('click', () => (reasonOf(m) ? act(m, 'forget', reasonOf(m)) : act(m, 'open')));
      const more = h('button', { type: 'button', class: 'module-menu', title: '操作', 'aria-label': m.name + ' の操作' }, '⋯');
      more.addEventListener('click', (event) => showMenu(event, m));
      const item = h('li', { class: m.exists ? 'mod' : 'mod missing', title: m.path, draggable: 'true' }, open, more);
      item.addEventListener('contextmenu', (event) => { event.preventDefault(); showMenu(event, m); });
      // 並べ替え：同じ型の中でドラッグ（順は、この PC に覚える）
      item.addEventListener('dragstart', (event) => {
        state.dragged = m.path;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', m.path);
        item.classList.add('dragging');
      });
      item.addEventListener('dragend', () => { state.dragged = null; item.classList.remove('dragging'); });
      item.addEventListener('dragover', (event) => {
        const from = modules.find((x) => x.path === state.dragged);
        if (from && from !== m && (from.type || '') === (m.type || '')) event.preventDefault();
      });
      item.addEventListener('drop', (event) => {
        const from = modules.find((x) => x.path === state.dragged);
        if (!from || from === m || (from.type || '') !== (m.type || '')) return;
        event.preventDefault();
        const box = item.getBoundingClientRect();
        const before = event.clientY < box.top + box.height / 2 || (event.clientY < box.bottom && event.clientX < box.left + box.width / 2);
        const paths = modules.map((x) => x.path).filter((p) => p !== from.path);
        paths.splice(paths.indexOf(m.path) + (before ? 0 : 1), 0, from.path);
        memory.set(ORDER, paths);
        state.dragged = null;
        redraw();
      });
      return item;
    }
    async function showMenu(event, m) {
      const gone = m.exists ? '' : `フォルダが見つかりません（${m.path}）`;
      const noAway = m.notClone ? 'git の clone ではないので、GitHub のリポジトリとつながっていません'
        : !m.github ? 'GitHub のリポジトリがありません（origin が GitHub ではありません）' : '';
      const chosen = await menu(event, [
        { id: 'open', label: '開発環境を開く', disabled: Boolean(reasonOf(m)), reason: gone || reasonOf(m) },
        { separator: true },
        { id: 'forget', label: '一覧から外す…' },
        { id: 'away', label: '片付ける（アーカイブ）…', danger: true, disabled: Boolean(noAway), reason: noAway },
      ]);
      if (chosen) act(m, chosen);
    }
    function fold(name, title, count, body) {
      const details = h('details', { class: 'fold' }, h('summary', {}, title + ' ', h('span', { class: 'count' }, String(count))), body);
      details.open = memory.get(name, false) === true;
      details.addEventListener('toggle', () => { if (details.open !== (memory.get(name, false) === true)) memory.set(name, details.open); });
      return details;
    }
    function archivedBox() {
      const list = h('ul', {});
      for (const m of archived) {
        const text = h('div', {}, h('strong', {}, m.repository));
        if (m.description) text.append(h('small', {}, m.description));
        for (const path of m.clones) text.append(h('small', {}, 'このPC：' + path));
        const undo = h('button', { type: 'button' }, '解除');
        undo.addEventListener('click', () => emit('archived', { repository: m.repository, action: 'unarchive', local: m.clones.join('、') }));
        const remove = h('button', { type: 'button', class: 'danger-text' }, '削除…');
        remove.addEventListener('click', () => emit('archived', { repository: m.repository, action: 'delete', local: m.clones.join('、') }));
        list.append(h('li', {}, text, h('span', { class: 'fold-actions' }, undo, remove)));
      }
      return fold('archived-open', 'アーカイブ済み', archived.length, list);
    }
    function legacyBox() {
      const list = h('ul', {});
      for (const c of props.legacy) {
        const exists = c.exists !== false;
        const what = !exists ? '・フォルダが見つかりません' : c.task !== null && c.task !== undefined ? `・タスク #${c.task}` : c.branch ? '・' + c.branch : '';
        const text = h('div', {}, h('strong', {}, (cloneRepository(c) || '（GitHubのリポジトリなし）') + what),
          h('small', { class: 'mono' }, c.path + (c.task !== null && c.task !== undefined && c.branch ? `（${c.branch}）` : '')));
        const actions = h('span', { class: 'fold-actions' });
        if (exists) {
          const close = h('button', { type: 'button', class: 'danger-text' }, '閉じる…');
          close.addEventListener('click', () => emit('legacy', { path: c.path, action: 'close' }));
          actions.append(close);
        } else {
          const forget = h('button', { type: 'button' }, '一覧から外す');
          forget.addEventListener('click', () => emit('legacy', { path: c.path, action: 'forget' }));
          actions.append(forget);
        }
        list.append(h('li', {}, text, actions));
      }
      return fold('legacy-open', '前の作業空間', props.legacy.length, list);
    }
  },
};
