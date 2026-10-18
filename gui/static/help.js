'use strict';
// Hub: help. 「使い方」 is the flow of the work; 「コマンド一覧」 is what ecobuild --help --json lists (the common commands and
// each type's), grouped by purpose, searchable, with the arguments and options of the chosen one.
const HELP = (() => {
  const $ = id => document.getElementById(id);
  const {esc} = ECO;
  // The page itself (the hub and the module window both have an empty <section id="help">).
  $('help').innerHTML = `
  <div class="page-heading"><h2 id="help-title">ヘルプ</h2>
    <div class="help-tabs" role="tablist"><button type="button" role="tab" data-help-tab="guide" aria-selected="true">使い方</button><button type="button" role="tab" data-help-tab="commands" aria-selected="false">コマンド一覧</button></div></div>
  <div id="help-guide">
    <p class="note">ECOBuildの作業は、タスク（GitHubのIssue）ごとに進めます。GUIのボタンは、ecobuild のコマンドを実行しています。コマンドの名前を押すと、コマンド一覧の説明に移ります。</p>
    <ol class="help-steps">
      <li><span class="help-step-number">1</span><div><h4>モジュールを用意する</h4><p class="help-where">ハブ › ＋ モジュール追加</p><p class="note">新しく作るか、GitHubから取得するか、手元のフォルダを登録します。</p>
        <p class="help-chips"><button type="button" data-goto="module new">module new</button><button type="button" data-goto="module clone">module clone</button><button type="button" data-goto="workspace add">workspace add</button></p></div></li>
      <li><span class="help-step-number">2</span><div><h4>タスクを作る</h4><p class="help-where">モジュール › タスク管理 › ＋ 新しいタスク</p><p class="note">やることをタスク（Issue）にします。担当者・期限・見積もり・スプリントも付けられます。</p>
        <p class="help-chips"><button type="button" data-goto="task new">task new</button><button type="button" data-goto="task list">task list</button><button type="button" data-goto="task next">task next</button></p></div></li>
      <li><span class="help-step-number">3</span><div><h4>作業を開始する</h4><p class="help-where">タスク管理 › タスク › 作業を開始</p><p class="note">タスクブランチ（task/番号-名前。名前は入力します。日本語も使えます）を作り、作業空間（このPCで作業する場所）を開きます。</p>
        <p class="help-chips"><button type="button" data-goto="task start">task start</button><button type="button" data-goto="status">status</button></p></div></li>
      <li><span class="help-step-number">4</span><div><h4>作って、確かめて、コミットする</h4><p class="help-where">作業空間</p><p class="note">ファイルを編集し、ビルド・テストして、変更をコミットします。AIを起動して手伝わせることもできます。</p>
        <p class="help-chips"><button type="button" data-goto="build">build</button><button type="button" data-goto="test">test</button><button type="button" data-goto="run">run</button><button type="button" data-goto="task commit">task commit</button><button type="button" data-goto="agent start">agent start</button></p></div></li>
      <li><span class="help-step-number">5</span><div><h4>提出して、レビューを受ける</h4><p class="help-where">作業空間 › 提出 › 提出する</p><p class="note">確認（生成ファイル・ビルド・テスト）をしてから、作成元へ提出（PR）します。</p>
        <p class="help-chips"><button type="button" data-goto="check">check</button><button type="button" data-goto="task submit">task submit</button><button type="button" data-goto="task review">task review</button><button type="button" data-goto="task approve">task approve</button></p></div></li>
      <li><span class="help-step-number">6</span><div><h4>完了する</h4><p class="help-where">作業空間 › 提出 › 完了する</p><p class="note">提出を取り込み、タスクを閉じます。ほかの人の変更は同期で取り込みます。</p>
        <p class="help-chips"><button type="button" data-goto="task finish">task finish</button><button type="button" data-goto="sync">sync</button></p></div></li>
    </ol>
    <h3 class="help-terms-title">用語</h3>
    <dl class="help-terms">
      <div><dt>モジュール</dt><dd>GitHubのリポジトリ1つ。制作・リンクの単位です。</dd></div>
      <div><dt>型</dt><dd>モジュールの種類（C++・Python・汎用）。ビルドやファイルの扱いと、使えるコマンドが型で変わります。</dd></div>
      <div><dt>タスク</dt><dd>GitHubのIssue。やることの単位です。</dd></div>
      <div><dt>タスクブランチ</dt><dd>タスクの作業をするブランチ（task/番号-名前）。変更はここでコミットし、提出で作成元に入ります。</dd></div>
      <div><dt>作業空間</dt><dd>このPCでモジュールの作業をする場所（clone）。</dd></div>
      <div><dt>提出</dt><dd>タスクブランチの変更を取り込んでもらうためのPR。レビューで承認されると完了できます。</dd></div>
      <div><dt>ビルド設定（プロファイル）</dt><dd>名前を付けたビルドの設定（構成・並列数と、型ごとの項目）。</dd></div>
    </dl>
  </div>
  <div id="help-commands" hidden>
    <div class="help-toolbar">
      <label class="help-search"><span class="sr-only">コマンドを探す</span><input id="help-search" type="search" placeholder="コマンド・説明・オプションで探す（/ で移動）" autocomplete="off"><small id="help-count"></small></label>
      <div class="help-filter" id="help-type-filter" aria-label="型で絞り込む"></div>
    </div>
    <p class="note" id="help-type-note"></p>
    <div class="help-panes">
      <div class="help-list" id="help-commands-list"></div>
      <article class="help-detail" id="help-detail" aria-live="polite"></article>
    </div>
  </div>
`;
  const shown = () => !!$('help').offsetParent;   // its page is the one shown

  // The headings of the list. A command not named here goes to 「その他」 (the CLI may add commands the GUI doesn't know).
  const CATEGORIES = [
    ['タスクと作業', ['task', 'status', 'check', 'diff', 'log', 'show', 'blame', 'restore', 'stash', 'track', 'ignore']],
    ['ビルドと開発', ['build', 'test', 'run', 'clean', 'rebuild', 'file', 'project', 'template', 'deps', 'profile']],
    ['GitHubとの同期', ['sync', 'branch', 'ci', 'release']],
    ['計画', ['milestone', 'sprint']],
    ['モジュール', ['module', 'workspace']],
    ['AI', ['agent']],
    ['環境と設定', ['init', 'setup', 'doctor', 'config']],
  ];
  const TYPE_LABEL = {cpp: 'C++', python: 'Python', generic: '汎用'};
  const FILTER_KEY = 'ecobuild-gui-help-type';

  let catalog = null, loading = null, entries = new Map(), selected = '', filter = 'all', query = '';
  try { filter = localStorage.getItem(FILTER_KEY) || 'all'; } catch (e) { /* storage blocked */ }

  // One entry per command path; variants: origin ('' = common, or a type) → the CLI's node.
  function merge(nodes, origin, parent) {
    for (const node of nodes) {
      let entry = entries.get(node.path);
      if (!entry) {
        entry = {path: node.path, name: node.name, top: node.path.split(' ')[0], parent, variants: {}, children: []};
        entries.set(node.path, entry);
        if (parent) entries.get(parent).children.push(entry);
      }
      entry.variants[origin] = node;
      if (node.section && !entry.section) entry.section = node.section;
      if (node.commands) merge(node.commands, origin, node.path);
    }
  }
  const origins = entry => Object.keys(entry.variants);
  const main = entry => entry.variants[''] || Object.values(entry.variants)[0];
  // Types that have this command of their own ('' common: every type).
  const typesOf = entry => entry.variants[''] ? [] : origins(entry);
  const visible = entry => filter === 'all' || entry.variants[''] || entry.variants[filter]
    || entry.children.some(visible);

  async function load() {
    if (catalog) return render();
    if (loading) return loading;
    $('help-commands-list').innerHTML = '<p class="note"><span class="eco-spinner"></span> コマンドの一覧を読み込んでいます…</p>';
    loading = (async () => {
      const doc = await ECO.cli(null, ['--help'], {quiet: true});
      loading = null;
      if (!doc.ok) {
        $('help-commands-list').innerHTML = `<p class="note">コマンドの一覧を読めませんでした：${esc(doc.error?.message || '')}</p>`;
        return;
      }
      catalog = doc.result; entries = new Map();
      merge(catalog.commands, '', '');
      for (const [type, value] of Object.entries(catalog.types)) merge(value.commands, type, '');
      renderFilters(); render();
    })();
    return loading;
  }

  // Search -----------------------------------------------------------------------------------------
  const words = () => query.toLowerCase().split(/\s+/).filter(Boolean);
  function text(entry) {
    return Object.values(entry.variants).map(n => [n.path, n.summary, n.help,
      ...(n.options || []).flatMap(o => [...o.names, o.help]), ...(n.arguments || []).map(a => a.name + ' ' + a.help)].join(' '))
      .join(' ').toLowerCase();
  }
  const matches = entry => words().every(w => text(entry).includes(w));
  function mark(value) {
    let html = esc(value);
    for (const w of words()) {
      const pattern = new RegExp(esc(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      html = html.replace(pattern, m => `<mark>${m}</mark>`);
    }
    return html;
  }

  // The list ----------------------------------------------------------------------------------------
  function renderFilters() {
    const types = Object.keys(catalog.types);
    if (filter !== 'all' && !types.includes(filter)) filter = 'all';
    $('help-type-filter').innerHTML = [['all', 'すべて'], ...types.map(t => [t, TYPE_LABEL[t] || t])]
      .map(([value, label]) => `<button type="button" data-filter="${esc(value)}" aria-pressed="${value === filter}">${esc(label)}</button>`).join('');
    $('help-type-note').textContent = filter === 'all'
      ? '型ごとのコマンドは、その型のモジュールの中でだけ使えます（印の付いたもの）。'
      : `${TYPE_LABEL[filter] || filter}（型 ${filter}）のモジュールの中で使えるコマンドです。`;
  }
  function badges(entry) {
    return typesOf(entry).map(t => `<span class="help-type t-${esc(t)}">${esc(TYPE_LABEL[t] || t)}</span>`).join('');
  }
  function row(entry) {
    const node = main(entry);
    return `<li><button type="button" class="help-row${entry.path === selected ? ' selected' : ''}" data-command="${esc(entry.path)}">
      <code>${mark(entry.path)}</code>${badges(entry)}<span>${mark(node.summary)}</span></button></li>`;
  }
  function render() {
    if (!catalog) return;
    const tops = [...entries.values()].filter(e => !e.parent && visible(e));
    const searching = words().length > 0;
    const known = new Set(CATEGORIES.flatMap(([, names]) => names));
    const groups = [...CATEGORIES, ['その他', tops.map(e => e.name).filter(n => !known.has(n))]];
    let html = '', count = 0;
    for (const [title, names] of groups) {
      const blocks = [];
      for (const name of names) {
        const top = tops.find(e => e.name === name); if (!top) continue;
        const leaves = flatten(top).filter(e => visible(e) && (!searching || matches(e)));
        if (!leaves.length) continue;
        count += leaves.length;
        // Single commands share one box; a group has its own.
        if (leaves.length === 1 && leaves[0] === top) {
          if (Array.isArray(blocks[blocks.length - 1])) blocks[blocks.length - 1].push(row(top)); else blocks.push([row(top)]);
        } else blocks.push(block(top, leaves));
      }
      const boxes = blocks.map(b => Array.isArray(b) ? `<ul class="help-rows">${b.join('')}</ul>` : b).join('');
      if (blocks.length) html += `<section class="help-category"><h3>${esc(title)}</h3>${boxes}</section>`;
    }
    $('help-commands-list').innerHTML = html || `<p class="note help-empty">「${esc(query)}」に合うコマンドはありません。</p>`;
    $('help-count').textContent = searching ? `${count} 件` : '';
    if (!selected || !entries.has(selected)) selected = 'task start';
    if (entries.has(selected)) renderDetail();
  }
  // A command and the ones under it (a group shows itself only when it can run by itself or has nothing under it).
  function flatten(entry) {
    const below = entry.children.flatMap(flatten);
    const runnable = Object.values(entry.variants).some(n => n.runnable);
    return runnable || !entry.children.length ? [entry, ...below] : below;
  }
  function block(top, leaves) {
    const node = main(top);
    let html = `<div class="help-group"><button type="button" class="help-group-title" data-command="${esc(top.path)}"><code>${esc(top.name)}</code>${badges(top)}<span>${esc(node.summary)}</span></button>`;
    let section = null, open = false;
    for (const leaf of leaves) {
      if (leaf.section && leaf.section !== section) {
        if (open) html += '</ul>';
        html += `<h4>${esc(leaf.section)}</h4><ul class="help-rows">`; section = leaf.section; open = true;
      } else if (!open) { html += '<ul class="help-rows">'; open = true; }
      html += row(leaf);
    }
    return html + (open ? '</ul>' : '') + '</div>';
  }

  // The chosen command ------------------------------------------------------------------------------
  let shownOrigin = '';
  function renderDetail() {
    const entry = entries.get(selected); if (!entry) return;
    const list = origins(entry);
    if (!list.includes(shownOrigin)) shownOrigin = list.includes(filter) ? filter : list[0];
    const node = entry.variants[shownOrigin];
    const crumbs = entry.path.split(' ').map((name, index, all) => {
      const path = all.slice(0, index + 1).join(' ');
      return index < all.length - 1 ? `<button type="button" class="link-button" data-command="${esc(path)}">${esc(name)}</button>` : `<strong>${esc(name)}</strong>`;
    }).join('<span>›</span>');
    const tabs = list.length > 1 ? `<div class="help-variants" role="tablist">${list.map(o => `<button type="button" role="tab" data-origin="${esc(o)}" aria-selected="${o === shownOrigin}">${o ? esc(TYPE_LABEL[o] || o) : '共通'}</button>`).join('')}</div>` : '';
    const where = shownOrigin ? `<p class="help-where">型 <b>${esc(shownOrigin)}</b>（${esc(TYPE_LABEL[shownOrigin] || shownOrigin)}）のモジュールの中で使えます。</p>` : '';
    const body = paragraphs(node.help, node.summary);
    const sub = entry.children.filter(visible);
    $('help-detail').innerHTML = `<div class="help-crumbs"><span>ecobuild</span><span>›</span>${crumbs}</div>
      <h3><code>${esc(entry.path)}</code></h3>${tabs}
      <p class="help-summary">${linked(node.summary)}</p>${where}
      ${node.runnable ? usage(node) : ''}
      ${body}${node.default_help ? paragraphs(node.default_help, node.summary) : ''}
      ${node.runnable ? argumentsTable(node) + optionsList(node) : ''}
      ${sub.length ? `<h4>コマンド</h4><ul class="help-sub">${sub.map(c => `<li><button type="button" class="link-button" data-command="${esc(c.path)}"><code>${esc(c.name)}</code></button>${badges(c)}<span>${linked(main(c).summary)}</span></li>`).join('')}</ul>` : ''}
      <p class="help-common">どのコマンドにも：<code>-C &lt;パス&gt;</code> 別のフォルダのモジュールを対象にする（コマンドの前に書く）・<code>--json</code> 結果をJSONで出す・<code>--help</code> 使い方を表示する</p>`;
    for (const button of $('help-commands-list').querySelectorAll('.help-row')) button.classList.toggle('selected', button.dataset.command === selected);
  }
  function usageText(node) {
    const parts = ['ecobuild', node.path];
    if (node.options?.length) parts.push('[オプション]');
    for (const a of node.arguments || []) {
      const name = a.name + (a.multiple ? '...' : '');
      parts.push(a.required ? name : `[${name}]`);
    }
    return parts.join(' ');
  }
  function usage(node) {
    const text = usageText(node);
    return `<div class="help-usage"><code>${esc(text)}</code><button type="button" class="cancel" data-copy="${esc(text)}">コピー</button></div>`;
  }
  // The first paragraph is the summary (shown above); the rest, a paragraph each.
  function paragraphs(help, summary) {
    const parts = (help || '').split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
    if (parts[0] && parts[0].replace(/\s+/g, '') === (summary || '').replace(/\s+/g, '')) parts.shift();
    return parts.map(p => /^\s*[-・*]/m.test(p) && p.split('\n').length > 1
      ? `<ul class="help-bullets">${p.split('\n').map(l => `<li>${linked(l.replace(/^\s*[-・*]\s*/, ''))}</li>`).join('')}</ul>`
      : `<p class="help-body">${linked(p.replace(/\n(?=\S)/g, ''))}</p>`).join('');
  }
  // 「ecobuild task finish」 in the text links to that command; --options look like code.
  function linked(value) {
    return esc(value || '').replace(/ecobuild((?: [a-z][a-z-]*)+)/g, (all, rest) => {
      const names = rest.trim().split(' ');
      for (let n = names.length; n > 0; n--) {
        const path = names.slice(0, n).join(' ');
        if (entries.has(path)) return `<button type="button" class="help-ref" data-command="${esc(path)}">ecobuild ${esc(path)}</button>${esc(names.slice(n).map(s => ' ' + s).join(''))}`;
      }
      return `<code>${all}</code>`;
    }).replace(/(^|[\s（(「、・])(--[a-z][a-z-]*)/g, '$1<code>$2</code>');
  }
  function argumentsTable(node) {
    if (!node.arguments?.length) return '';
    return `<h4>引数</h4><dl class="help-params">${node.arguments.map(a => `<div><dt><code>${esc(a.name)}${a.multiple ? '...' : ''}</code>${a.required ? '<span class="tag need">必須</span>' : '<span class="tag">省略可</span>'}${a.multiple ? '<span class="tag">複数</span>' : ''}</dt><dd>${linked(a.help)}</dd></div>`).join('')}</dl>`;
  }
  function optionsList(node) {
    if (!node.options?.length) return '';
    return `<h4>オプション</h4><dl class="help-params">${node.options.map(o => {
      const tags = [o.required && '<span class="tag need">必須</span>', o.multiple && '<span class="tag">何度でも</span>',
        o.default !== undefined && `<span class="tag">既定：${esc(String(o.default))}</span>`].filter(Boolean).join('');
      const choices = o.choices ? `<div class="help-choices">${o.choices.map(c => `<code>${esc(c)}</code>`).join('')}</div>` : '';
      return `<div><dt><code>${esc(o.names.join(', '))}${o.flag ? '' : ` <i>${esc(o.value || '値')}</i>`}</code>${tags}</dt><dd>${linked(o.help)}${choices}</dd></div>`;
    }).join('')}</dl>`;
  }

  function select(path) {
    if (!entries.has(path)) return;
    selected = path; renderDetail();
    $('help-detail').scrollTop = 0;
    // Bring the row into the list's view (only the list scrolls, not the page).
    const list = $('help-commands-list'), target = list.querySelector(`.help-row[data-command="${CSS.escape(path)}"]`);
    if (target) {
      const top = target.getBoundingClientRect().top - list.getBoundingClientRect().top;
      if (top < 0 || top + target.offsetHeight > list.clientHeight) list.scrollTop += top - list.clientHeight / 3;
    }
    if (window.matchMedia('(max-width: 900px)').matches) $('help-detail').scrollIntoView({block: 'start'});
  }
  function showTab(name) {
    for (const tab of document.querySelectorAll('[data-help-tab]')) {
      const on = tab.dataset.helpTab === name;
      tab.setAttribute('aria-selected', on); $('help-' + tab.dataset.helpTab).hidden = !on;
    }
    if (name === 'commands') load();
  }

  // Events ------------------------------------------------------------------------------------------
  document.addEventListener('click', event => {
    if (!shown()) return;
    const tab = event.target.closest('[data-help-tab]'); if (tab) return showTab(tab.dataset.helpTab);
    const goto = event.target.closest('[data-goto]');
    if (goto) { showTab('commands'); load().then(() => select(goto.dataset.goto)); return; }
    const command = event.target.closest('#help [data-command]'); if (command) return select(command.dataset.command);
    const origin = event.target.closest('[data-origin]'); if (origin) { shownOrigin = origin.dataset.origin; return renderDetail(); }
    const type = event.target.closest('[data-filter]');
    if (type) {
      filter = type.dataset.filter;
      try { localStorage.setItem(FILTER_KEY, filter); } catch (e) { /* storage blocked */ }
      renderFilters(); render(); return;
    }
    const copy = event.target.closest('[data-copy]');
    if (copy) navigator.clipboard.writeText(copy.dataset.copy).then(() => ECO.toast('コピーしました：' + copy.dataset.copy), () => ECO.toast('コピーできませんでした。', 'bad'));
  });
  $('help-search').addEventListener('input', event => { query = event.target.value.trim(); render(); });
  $('help-search').addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.target.value = ''; query = ''; render(); return; }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp' && event.key !== 'Enter') return;
    const rows = [...$('help-commands-list').querySelectorAll('.help-row')];
    if (!rows.length) return;
    event.preventDefault();
    const at = rows.findIndex(r => r.dataset.command === selected);
    const next = event.key === 'Enter' ? (at < 0 ? 0 : at) : event.key === 'ArrowDown' ? Math.min(rows.length - 1, at + 1) : Math.max(0, at - 1);
    select(rows[next].dataset.command);
  });
  document.addEventListener('keydown', event => {
    if (event.key !== '/' || !shown() || $('help-commands').hidden || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) return;
    event.preventDefault(); $('help-search').focus();
  });

  // hub.html#help・#help/commands・#help/commands/task%20start opens it there.
  function show(hash = '') {
    const [, tab, command] = hash.split('/');
    showTab(tab === 'commands' ? 'commands' : tab === 'guide' ? 'guide'
      : document.querySelector('[data-help-tab][aria-selected="true"]')?.dataset.helpTab || 'guide');
    if (command) load().then(() => select(decodeURIComponent(command)));
  }
  return {show};
})();
