// 部品「C++ のモジュールのページ」。今までの GUI（static/modinfo.js の renderProjects・renderDeps・renderTree・renderGeneral・renderTemplates）と
// 同じ並び・同じ文言。受け取ったものを見せ、押した操作を action で出すだけ。
const KIND = { static_library: 'ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', shared: '共有ライブラリ', interface: 'ヘッダーだけ',
  executable: '実行ファイル', app: '実行ファイル', test: 'テスト', bench: '性能測定', benchmark: '性能測定' };
const DEP_STATE = { aligned: ['記録の版', 'ok'], differs: ['記録と別の版', 'warn'], modified: ['未コミットの変更あり', 'warn'], working: ['作業版', ''], missing: ['cloneなし', 'bad'] };
const DEP_REMOTE = { ok: ['GitHubにある', 'ok'], archived: ['アーカイブ済み（更新されない）', 'warn'], moved: ['名前が変わった', 'warn'], gone: ['GitHubにない', 'bad'], unknown: ['確認できない', ''] };
const ATTACHED = ['test', 'bench', 'benchmark'];
const short = (sha) => (sha ? String(sha).slice(0, 8) : '-');
const two = (n) => String(n).padStart(2, '0');
const localTime = (iso) => {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return String(iso || '').slice(0, 16).replace('T', ' ');
  return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ' + two(d.getHours()) + ':' + two(d.getMinutes());
};
// 管理ファイル（ecobuild.toml・CMake）を変える操作（作業空間がないあいだは灰色）
const MANAGED = ['project_add', 'project_settings', 'project_link', 'project_unlink', 'project_pch', 'project_move', 'project_remove',
  'deps_update', 'dep_update', 'dep_versions', 'dep_use', 'dep_add', 'dep_remove', 'module_settings', 'template_add', 'template_replace', 'template_remove'];
const NO_WS = 'タスクブランチの作業空間がありません（タスク管理で「作業を開始」してください）';
// Project のリンクは「<依存先>/<Project>」か、名前だけ
const linksTo = (link, dep) => link === dep || String(link).startsWith(dep + '/');

// Project の木：テスト・性能測定は、リンクする（このモジュールの）最初の Project の下。ライブラリ・実行ファイルは上の段のまま、main が先
function projectTree(projects, main) {
  const names = new Set(projects.map((p) => p.name)), parent = new Map();
  for (const p of projects) {
    if (!ATTACHED.includes(p.kind)) continue;
    const first = (p.links || []).find((l) => names.has(l) && l !== p.name);
    if (first) parent.set(p.name, first);
  }
  for (const p of projects) {  // 輪（起きないはず）：切って、どの Project も出す
    const seen = new Set([p.name]);
    for (let at = parent.get(p.name); at; at = parent.get(at)) { if (seen.has(at)) { parent.delete(p.name); break; } seen.add(at); }
  }
  const rows = [];
  const visit = (p, depth, last) => {
    rows.push({ p, depth, last, parent: parent.get(p.name) });
    const kids = projects.filter((x) => parent.get(x.name) === p.name);
    kids.forEach((k, i) => visit(k, depth + 1, i === kids.length - 1));
  };
  const roots = projects.filter((p) => !parent.has(p.name)).sort((a, b) => (b.name === main) - (a.name === main));
  roots.forEach((r) => visit(r, 0, true));
  return rows;
}

export default {
  render(root, props, { h, emit, menu, state }) {
    const act = (name, target, value) => emit('action', { name, target: target || '', value: value || '' });
    const pill = (text, tone) => h('span', { class: tone ? 'pill ' + tone : 'pill' }, text);
    const sub = (...kids) => h('div', { class: 'sub' }, ...kids);
    // 管理ファイルを変える操作は、タスクブランチの作業空間で行う（作業空間を読んで、1つもなければ灰色と理由）
    const spaces = props.workspaces;
    const readOnly = Array.isArray(spaces) && !spaces.some((w) => w.task != null && w.review == null);
    const locked = (name) => readOnly && MANAGED.includes(name);
    const button = (label, name, target, cls, title) => {
      const off = locked(name);
      const b = h('button', { type: 'button', class: cls || 'small', ...(off ? { title: NO_WS } : title ? { title } : {}) }, label);
      if (off) b.disabled = true;
      b.addEventListener('click', () => act(name, target));
      return b;
    };
    // 行の右クリック：その行のボタンと ⋯ の項目（[{id, label, danger}] か {separator}）
    const rowMenu = (row, target, items) => {
      row.addEventListener('contextmenu', async (event) => {
        event.preventDefault();
        const id = await menu(event, items.map((i) => (i.separator ? i : { ...i, ...(locked(i.id) ? { disabled: true, reason: NO_WS } : {}) })));
        if (id) act(id, target);
      });
      return row;
    };
    const banner = () => {
      if (!readOnly) return '';
      const open = h('button', { type: 'button', class: 'small' }, 'タスク管理を開く');
      open.addEventListener('click', () => act('open_tasks'));
      return h('div', { class: 'banner info' }, h('span', {}, '変更はタスクブランチの作業空間で行います。作業空間がないので、今は見るだけです。'), open);
    };
    const head = (title, ...actions) => h('div', { class: 'head' }, h('h3', {}, title), h('div', { class: 'actions' }, ...actions));
    const table = (cls, columns, rows) => h('table', { class: cls },
      columns ? h('thead', {}, h('tr', {}, ...columns.map((c) => h('th', {}, c)))) : '', h('tbody', {}, ...rows));
    const out = readOnly ? [banner()] : [];
    const failed = () => {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      return h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again);
    };
    const waiting = () => h('p', { class: 'empty', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…');
    const projects = props.projects || [], deps = props.deps || [], settings = props.settings || null;

    if (props.view === 'projects') {
      const main = settings && settings.main_project;
      out.push(head('Project', button('＋ Project', 'project_add', '', 'primary')));
      if (props.error) out.push(failed());
      else if (!projects.length) out.push(props.loading ? waiting() : h('p', { class: 'empty' }, 'Projectはありません。'));
      else {
        const rows = projectTree(projects, main);
        out.push(table('table projects', ['名前', '種類', '場所', 'リンク', h('span', { class: 'sr' }, '操作')], rows.map(({ p, depth, last, parent }, i) => {
          const name = h('span', { class: 'indent', style: '--depth:' + depth });
          if (parent) name.append(h('span', { class: 'line', 'aria-hidden': 'true' }, last ? '└' : '├'), pill(KIND[p.kind] || p.kind, 'kind'), p.name);
          else { name.append(h('strong', {}, p.name)); if (p.name === main) name.append(' ', pill('main', 'ok')); }
          const links = h('td', {});
          for (const l of (p.links || []).filter((x) => x !== parent)) links.append(pill('→ ' + l, deps.some((d) => linksTo(l, d.name)) ? 'ok' : ''), ' ');
          const more = h('button', { type: 'button', class: 'small more', 'aria-label': p.name + ' のほかの操作', title: 'ほかの操作', 'aria-haspopup': 'menu' }, '⋯');
          const others = [{ id: 'project_link', label: 'リンクを足す…' }, { id: 'project_unlink', label: 'リンクを外す…' }, { id: 'project_pch', label: 'PCH…' }, { id: 'project_move', label: '移動…' },
            { separator: true }, { id: 'project_remove', label: '削除…', danger: true }];
          const lockedItems = others.map((i) => (i.separator ? i : { ...i, ...(locked(i.id) ? { disabled: true, reason: NO_WS } : {}) }));
          more.addEventListener('click', async (event) => {
            const id = await menu(event, lockedItems);
            if (id) act(id, p.name);
          });
          const joined = rows[i + 1] && rows[i + 1].parent;
          return rowMenu(h('tr', { class: (parent ? 'attached' : '') + (joined ? ' joined' : '') },
            h('td', {}, name), h('td', {}, parent ? '' : pill(KIND[p.kind] || p.kind)), h('td', { class: 'mono' }, (p.directory || '') + '/'), links,
            h('td', { class: 'row-actions' }, button('設定…', 'project_settings', p.name), more)),
          p.name, [{ id: 'project_settings', label: '設定…' }, { separator: true }, ...others]);
        })));
        out.push(h('p', { class: 'legend' }, h('span', {}, pill('→ 依存先', 'ok'), ' 他のモジュール'), h('span', {}, pill('→ Project'), ' このモジュール内'),
          h('span', {}, pill('main', 'ok'), ' 他のモジュールからリンクされる（全般）')));
      }
    } else if (props.view === 'deps') {
      const fetched = props.fetched === true;
      out.push(head('依存先', button(fetched ? 'GitHubをもう一度確認' : 'GitHubと照らし合わせる', 'deps_fetch', '', 'small', '依存先が GitHub で消えた・名前が変わった・新しい版が出たかを確かめます'),
        button('手元を記録に合わせる', 'deps_sync', '', 'small', '手元の依存先を、記録してある版にそろえます（手元にないものは取ってきます）'),
        button('すべて更新', 'deps_update', '', 'small', '依存先の記録を GitHub の最新に更新し、手元の clone と生成ファイルも合わせます'),
        button('＋ リンク', 'dep_add', '', 'primary')));
      if (props.error) out.push(failed());
      else if (!deps.length) out.push(props.loading ? waiting() : h('p', { class: 'empty' }, '依存先はありません。'));
      else {
        const columns = ['名前', '記録の版', '手元の版', '状態', ...(fetched ? ['GitHub'] : []), '使っているProject', h('span', { class: 'sr' }, '操作')];
        out.push(table('table', columns, deps.map((d) => {
          const [label, tone] = DEP_STATE[d.state] || [d.state, ''];
          const users = h('td', {});
          for (const p of projects.filter((x) => (x.links || []).some((l) => linksTo(l, d.name)))) users.append(pill(p.name), ' ');
          const cells = [h('td', {}, h('strong', {}, d.name), sub(d.url || '')), h('td', { class: 'mono' }, short(d.recorded)),
            h('td', { class: 'mono' }, short(d.local), d.branch ? sub(d.branch) : ''), h('td', {}, pill(label, tone))];
          if (fetched) {
            const cell = h('td', {});
            if (d.remote) {
              const [text, kind] = DEP_REMOTE[d.remote] || [d.remote, ''];
              cell.append(pill(text, kind));
              if (d.remote === 'moved') cell.append(sub('現在の名前は ' + d.moved_to + '（GitHubの転送で取得できます）'));
              if (d.remote === 'gone') cell.append(sub('このモジュールを新しくcloneすると、この依存先を取得できません'));
              if (d.latest && d.latest !== d.recorded) cell.append(sub('新しい版 ', h('span', { class: 'mono' }, short(d.latest))));
            }
            cells.push(cell);
          }
          const remove = button('リンクを外す…', 'dep_remove', d.name, 'small danger-text');
          cells.push(users, h('td', { class: 'row-actions' }, button('更新', 'dep_update', d.name, 'small', 'GitHub の既定のブランチの最新にします'),
            button('版を選ぶ…', 'dep_versions', d.name, 'small', 'ブランチ・タグ・コミットから選んで記録します（前の版に戻すのにも）'), remove));
          return rowMenu(h('tr', {}, ...cells), d.name, [{ id: 'dep_update', label: '更新' }, { id: 'dep_versions', label: '版を選ぶ…' },
            { id: 'dep_remove', label: 'リンクを外す…', danger: true }]);
        })));
      }
      // 版を選ぶ（押した依存先の、タグと、ブランチのコミットの新しい順）
      const v = props.versions;
      if (v && v.name) {
        const dep = deps.find((d) => d.name === v.name);
        const branch = h('select', { 'aria-label': 'ブランチ' }, ...(v.branches || []).map((b) => {
          const option = h('option', { value: b }, b === v.default_branch ? b + '（既定）' : b);
          if (b === v.branch) option.selected = true;
          return option;
        }));
        branch.addEventListener('change', () => act('dep_versions', v.name, branch.value));
        const close = h('button', { type: 'button', class: 'small quiet' }, '閉じる');
        close.addEventListener('click', () => act('dep_versions_close', v.name));
        const mark = (sha) => (sha === v.recorded ? pill('記録の版', 'ok') : '');
        const use = (at, label) => {
          const b = h('button', { type: 'button', class: 'small', 'aria-label': label + ' を記録する' }, 'この版にする');
          b.addEventListener('click', () => act('dep_use', v.name, at));
          return b;
        };
        const rows = [
          ...(v.tags || []).map((t) => h('li', {}, pill('タグ ' + t.name, 'info'), h('code', {}, short(t.sha)), h('span', { class: 'subject' }, ''), mark(t.sha),
            h('span', { class: 'when' }, localTime(t.date)), use(t.name, 'タグ ' + t.name))),
          ...(v.commits || []).map((c, i) => h('li', {}, h('code', {}, short(c.sha)), h('span', { class: 'subject', title: c.subject || '' }, c.subject || ''),
            ...(c.tags || []).map((t) => pill(t, 'info')), i === 0 ? pill('最新') : '', mark(c.sha), h('span', { class: 'when' }, localTime(c.date)), use(c.sha, short(c.sha))))];
        out.push(h('section', { class: 'versions' },
          h('div', { class: 'head' }, h('h4', {}, '依存先 ' + v.name + ' の版を選ぶ'), h('div', { class: 'actions' }, h('label', { class: 'branch' }, 'ブランチ', branch), close)),
          h('p', { class: 'note' }, '選んだ版を依存先 ' + v.name + ' の記録にし、手元の clone と生成ファイルも合わせます。今の記録は ', h('code', {}, short((dep && dep.recorded) || v.recorded)),
            ' です。前の版に戻すのにも使えます。'),
          rows.length ? h('ol', { class: 'commits' }, ...rows) : h('p', { class: 'empty' }, 'コミットがありません')));
      }
      // 依存関係の図（依存先の依存先も。もう出したものは、開かない）
      const t = props.tree;
      if (t && (t.direct || []).length) {
        const nodes = new Map((t.nodes || []).map((n) => [n.name, n])), shown = new Set();
        const walk = (names) => h('ul', {}, ...names.map((name) => {
          const n = nodes.get(name) || { name, revision: '', present: false, depends_on: [] };
          const again = shown.has(name) && (n.depends_on || []).length > 0;
          shown.add(name);
          const note = !n.present ? pill('cloneなし（その先は不明）', 'bad') : again ? pill('上に同じ') : '';
          return h('li', {}, h('div', { class: 'branch' }, h('span', { class: 'branch-name' }, name), h('span', { class: 'mono dimmed' }, short(n.revision)), note),
            !again && (n.depends_on || []).length ? walk(n.depends_on) : '');
        }));
        out.push(h('h4', { class: 'subhead' }, '依存関係の図'),
          h('ul', { class: 'tree' }, h('li', {}, h('div', { class: 'branch own' }, h('span', { class: 'branch-name' }, t.module || ''), pill('このモジュール', 'ok')), walk(t.direct))));
      }
    } else if (props.view === 'general') {
      out.push(head('全般', button('変更…', 'module_settings', '', 'primary')));
      if (props.error) out.push(failed());
      else if (!settings) out.push(props.loading ? waiting() : h('div', { class: 'banner bad' }, h('span', {}, 'このモジュールの設定を読めませんでした。')));
      else {
        const f = settings.folders;
        const row = (label, value, note) => h('tr', {}, h('th', { scope: 'row' }, label), h('td', {}, value, note ? sub(note) : ''));
        const runtime = { dll: 'DLL（/MD）', static: '静的（/MT）' }[settings.msvc_runtime] || '既定';
        out.push(table('table settings', null, [
          row('他のモジュールからリンクされるProject（main）', settings.main_project ? h('strong', {}, settings.main_project) : h('span', { class: 'dimmed' }, 'なし（他のモジュールからリンクできない）')),
          row('MSVC のCランタイム', runtime, 'このモジュールを頂点にしたビルド全体'),
          ...(f ? [row('ソリューションフォルダー：自分のProject', f.projects || ''), row('ソリューションフォルダー：リンク先のモジュール', f.linked_projects || ''),
            row('ソリューションフォルダー：CMake・GoogleTest 等', f.external || '', 'Visual Studio のソリューションでのまとめ方')] : [])]));
      }
    } else {
      const templates = settings && settings.templates && !Array.isArray(settings.templates) ? settings.templates : null;
      out.push(head('ファイルテンプレート', button('＋ テンプレート', 'template_add', '', 'primary')));
      if (props.error) out.push(failed());
      else if (!templates) out.push(props.loading ? waiting() : h('div', { class: 'banner bad' }, h('span', {}, 'ファイルテンプレートを読めませんでした。')));
      else {
        out.push(table('table', ['名前', 'ファイル', h('span', { class: 'sr' }, '操作')], Object.keys(templates).map((name) => {
          const t = templates[name] || {};
          return rowMenu(h('tr', {}, h('td', {}, h('strong', {}, name), t.builtin ? ' ' : '', t.builtin ? pill('既定') : ''), h('td', { class: 'mono' }, t.path || ''),
            h('td', { class: 'row-actions' }, button('差し替え…', 'template_replace', name), t.builtin ? '' : button('削除…', 'template_remove', name, 'small danger-text'))),
          name, [{ id: 'template_replace', label: '差し替え…' }, ...(t.builtin ? [] : [{ id: 'template_remove', label: '削除…', danger: true }])]);
        })));
        out.push(h('p', { class: 'note' }, 'ファイルの中の {{header}}・{{name}}・{{suite}}・{{project}} は、作るときに置き換わります。'));
      }
    }
    state.view = props.view;
    root.replaceChildren(h('section', { class: 'cpp' }, ...out));
  },
};
