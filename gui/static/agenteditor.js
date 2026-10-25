'use strict';
// The editor of agent registrations, shared by the module page エージェント (the module's registrations:
// ecobuild agent registry …, committed on a task branch) and the hub's settings (this PC's presets: ecobuild agent preset …).
// Left: the list (the module page puts 全エージェント共通 on top); right: one registration, edited in place in sections
// (基本・文書・最初の発言・渡すツール・起動してよい子) and saved at once. All the data comes from the CLI.
window.AGENT_EDITOR = (() => {
  const {esc} = ECO;
  const SOURCES = {sample: '見本', preset: 'このPCのプリセット', module: 'モジュールの登録'};
  // What a tool may do (its mark from the CLI): shown on each tool, and the quick choices pick by it.
  const MARKS = {read: ['見る', ''], change: ['変える', 'warn'], owner: ['ブランチを変える', 'warn'], children: ['子を扱う', 'top']};
  const QUICK = [['read', '見るだけ'], ['read,change', '見る＋作業空間を変える'], ['read,change,children', 'コミット・提出だけさせない'],
                 ['read,change,owner', '子を扱う以外すべて']];
  // The tools by what they are about (by the name; a new tool not here goes to そのほか).
  const AREAS = [
    ['状態・履歴を見る', n => /^(status|diff|log|show|blame|branch_|stash_|module_)/.test(n)],
    ['タスク', n => n.startsWith('task_')],
    ['ファイル', n => n.startsWith('file_')],
    ['ビルド・試験', n => /^(build|clean|rebuild|run|test|check|profile_)/.test(n)],
    ['取り込み（GitHub の最新）', n => n.startsWith('sync')],
    ['CI', n => n.startsWith('ci_')],
    ['子のエージェント・親への報告', n => n.startsWith('children_') || n === 'report_to_parent'],
  ];
  const TOO_MANY = 30;   // tools: past 30–50 definitions, the choice of tool tends to degrade
  const MODELS = [['', 'Claude Code の既定'], ['opus', 'Opus'], ['fable', 'Fable'], ['sonnet', 'Sonnet'], ['haiku', 'Haiku']];
  const toolsCache = new Map();   // dir → the tools (they change only with ECOBuild)
  const glob = p => new RegExp('^' + p.replace(/[.+^${}()|\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
  const matches = (name, patterns) => patterns.some(p => glob(p).test(name));
  const firstSentence = text => { const line = (text || '').split('\n')[0]; const end = line.indexOf('。'); return end > 0 ? line.slice(0, end + 1) : line; };
  // registry.stronger: child gives a tool the parent's patterns don't (unsure counts as stronger)
  const WILD = /[*?[]/;
  const covered = (pattern, allowed) => allowed.some(given => given === pattern || given === '*'
    || (!WILD.test(pattern) && glob(given).test(pattern))
    || (given.endsWith('*') && !WILD.test(given.slice(0, -1)) && pattern.startsWith(given.slice(0, -1))));
  const stronger = (child, parentTools) => child.tools.some(p => !covered(p, parentTools));
  const toolsText = tools => tools.includes('*') ? 'ツール：すべて' : `ツール：${tools.length}件の指定`;

  // opts: {kind: 'module'|'preset', dir() (the place shown), target(what) (where a change is saved: a dir, null for none, or
  //        undefined when cancelled; the module page asks for a task branch), notice() (html above), top: {key, label,
  //        render(), click(e), dirty()} | null, onChanged(dir)}
  function create(box, opts) {
    const group = opts.kind === 'module' ? 'registry' : 'preset';
    const st = {list: null, tools: null, samples: new Set(), selected: '', shown: null, dirty: false, error: ''};
    const cli = (args, extra = {}) => ECO.cli(opts.dir(), args, {quiet: true, ...extra});
    const target = what => opts.target ? opts.target(what) : Promise.resolve(opts.dir());
    // A change runs where target() says; the page then shows that place (onChanged).
    async function change(what, args, extra) {
      const dir = await target(what);
      if (dir === undefined) return null;
      const doc = await ECO.run(dir, args, extra);
      if (doc) { st.dirty = false; await opts.onChanged?.(dir); }
      return doc;
    }

    async function load(keep = true) {
      box.innerHTML = ECO.loading();
      const key = opts.dir() || '';
      const [list, tools, presets] = await Promise.all([cli(['agent', group, 'list']),
        toolsCache.has(key) ? {ok: true, result: toolsCache.get(key)} : cli(['agent', 'registry', 'tools']),
        cli(['agent', 'preset', 'list'])]);
      if (!list.ok) { box.innerHTML = `<div class="eco-banner bad">読めませんでした：${esc(list.error?.message || '')}</div>`; return; }
      if (tools.ok) toolsCache.set(key, tools.result);
      st.list = list.result; st.tools = tools.ok ? tools.result : [];
      // ECOBuild's samples: an own registration of the same name goes back to the sample when removed
      st.samples = new Set(presets.ok ? presets.result.filter(r => r.source === 'sample').map(r => r.name) : []);
      if (!keep || !(st.selected === opts.top?.key || st.list.some(r => r.name === st.selected)))
        st.selected = opts.top ? opts.top.key : (st.list.find(r => r.human_start) || st.list[0])?.name || '';
      await select(st.selected, true);
    }
    async function select(name, force = false) {
      if (!force && st.dirty && !await ECO.confirm({title: '保存していない変更', message: '保存していない変更を捨てて移りますか？', ok: '捨てて移る', danger: true})) return;
      st.selected = name; st.dirty = false; st.shown = null;
      if (name && name !== opts.top?.key) {
        const doc = await cli(['agent', group, 'show', name]);
        st.shown = doc.ok ? doc.result : null;
        st.error = doc.ok ? '' : doc.error?.message || '';
      }
      draw();
    }
    const badge = (text, cls = '') => `<span class="ae-badge ${cls}">${esc(text)}</span>`;
    function sideItem(r) {
      return `<button type="button" class="ae-item" data-ae-select="${esc(r.name)}" aria-current="${r.name === st.selected}">
        <span class="ae-item-title">${esc(r.title)}</span><span class="ae-item-name">${esc(r.name)}</span>
        <span class="ae-item-badges">${r.human_start ? badge('人が起動', 'top') : ''}${r.source === 'sample' ? badge(opts.kind === 'module' ? 'プリセットのまま' : '見本', 'quiet') : ''}${r.pending ? badge('まだ効いていない', 'warn') : ''}</span></button>`;
    }
    function side() {
      return `<nav class="ae-side" aria-label="エージェント">
        ${opts.top ? `<button type="button" class="ae-item ae-top" data-ae-select="${esc(opts.top.key)}" aria-current="${st.selected === opts.top.key}"><span class="ae-item-title">${esc(opts.top.label)}</span><span class="ae-item-name">どのエージェントにも渡す文</span></button><div class="ae-side-head">役</div>` : ''}
        ${st.list.map(sideItem).join('')}
        <button type="button" class="ae-add" data-ae-add>＋ ${opts.kind === 'module' ? 'エージェントを追加' : 'プリセットを足す'}</button>
      </nav>`;
    }
    // 渡すツール: すべて, or the tools picked, by what they are about (each with what it does and what it may change)
    function toolsSection(r) {
      const all = r.tools.includes('*');
      const exact = new Set(st.tools.map(t => t.name));
      const others = r.tools.filter(p => p !== '*' && !exact.has(p));
      const areas = [...AREAS, ['そのほか', () => true]];
      const byArea = new Map(areas.map(([label]) => [label, []]));
      for (const t of st.tools) byArea.get(areas.find(([, test]) => test(t.name))[0]).push(t);
      const row = t => { const byPattern = matches(t.name, others);   // given by a pattern below: shown, kept as the pattern
        const [kind, cls] = MARKS[t.mark] || [t.mark, ''];
        return `<label class="ae-tool" title="${esc((byPattern ? '下のパターンで渡しています\n' : '') + t.summary)}">
          <input type="checkbox" data-ae-tool="${esc(t.name)}" data-mark="${esc(t.mark)}"${byPattern ? ' data-by-pattern disabled' : ''}${byPattern || r.tools.includes(t.name) ? ' checked' : ''}>
          <span class="ae-tool-text">${esc(firstSentence(t.summary) || t.name)}</span><code>${esc(t.name)}</code>${kind && cls ? badge(kind, cls) : ''}</label>`; };
      return `<section class="ae-sec"><h4>渡すツール</h4>
        <p class="mi-note">エージェントが ECOBuild でできることは、ここで渡すツールだけです。印：${badge('変える', 'warn')} 作業空間のファイルを変える　${badge('ブランチを変える', 'warn')} コミット・push・提出（タスクの持ち主だけ）　${badge('子を扱う', 'top')} 子のエージェント</p>
        <div class="ae-radio"><label><input type="radio" name="ae-tools-mode" value="all"${all ? ' checked' : ''}> すべて（ECOBuild が増やすツールも）</label>
          <label><input type="radio" name="ae-tools-mode" value="pick"${all ? '' : ' checked'}> 選んだものだけ</label></div>
        <div class="ae-quick"><span>まとめて選ぶ：</span>${QUICK.map(([marks, label]) => `<button type="button" class="sm" data-ae-quick="${marks}">${label}</button>`).join('')}<span class="ae-count" data-ae-count></span></div>
        <div class="ae-tools"${all ? ' hidden' : ''}>
          ${[...byArea].filter(([, list]) => list.length).map(([label, list]) => `<fieldset class="ae-group"><legend>${esc(label)}<span class="ae-group-count" data-ae-group-count></span><span class="ae-group-actions"><button type="button" class="sm" data-ae-group data-on="1">すべて</button><button type="button" class="sm" data-ae-group data-on="">外す</button></span></legend>
            ${list.map(row).join('')}</fieldset>`).join('')}
          <details class="ae-more"${others.length ? ' open' : ''}><summary>名前のパターンで渡す（上級）</summary>
            <label class="ae-field">パターン（カンマ区切り。例：task_*。後で増えるツールも合えば渡します）<input type="text" data-ae-field="patterns" value="${esc(others.join(', '))}"></label></details>
        </div></section>`;
    }
    // だれが起動するか: a person (the workspace's エージェント), and the roles that have this one in 起動してよい子 (saved on
    // their registrations). An agent no role has, with no commit/submit tools, is one only a person starts and steers.
    const parentsOf = name => st.list.filter(x => x.name !== name && x.children.includes(name)).map(x => x.name);
    function startSection(r) {
      const parents = parentsOf(r.name);
      const rows = st.list.filter(x => x.name !== r.name).map(x => `<label class="ae-child"><input type="checkbox" data-ae-parent="${esc(x.name)}"${parents.includes(x.name) ? ' checked' : ''}>
          <span class="ae-child-main"><span class="ae-item-title">${esc(x.title)}</span> <span class="ae-item-name">${esc(x.name)}</span>
            <span class="ae-child-info">${esc(toolsText(x.tools))}</span></span>
          <span class="ae-child-warn" data-ae-parent-warn hidden>${badge('この役のほうが強いので子にできない', 'warn')}</span></label>`);
      return `<section class="ae-sec"><h4>だれが起動するか</h4>
        <label class="ae-check"><input type="checkbox" data-ae-field="human_start"${r.human_start ? ' checked' : ''}> 人が手で起動できる（作業空間の「エージェント」の ＋ に出る）</label>
        <p class="mi-note">子として起動できる役（それぞれの「起動してよい子」に入れます）。どれにも入れなければ、ほかのエージェントからは起動されません。</p>
        <div class="ae-children">${rows.join('') || '<span class="mi-note">ほかの役がありません</span>'}</div>
        <p class="mi-note ae-start-sum" data-ae-start-sum></p></section>`;
    }
    // 起動してよい子: chosen from the agents of this list (this module's, or the presets), this one too
    function childrenSection(r) {
      const names = new Set(st.list.map(x => x.name));
      const rows = st.list.map(x => {
        const self = x.name === r.name;
        return `<label class="ae-child" data-ae-child-row="${esc(x.name)}"><input type="checkbox" data-ae-child="${esc(x.name)}"${r.children.includes(x.name) ? ' checked' : ''}>
          <span class="ae-child-main"><span class="ae-item-title">${esc(x.title)}</span> <span class="ae-item-name">${esc(x.name)}</span>${self ? badge('この役自身', 'quiet') : ''}
            <span class="ae-child-info">${esc(MODELS.find(([v]) => v === x.model)?.[1] || x.model)}・${esc(toolsText(x.tools))}</span></span>
          <span class="ae-child-warn" data-ae-child-warn hidden>${badge('この役より強い（渡すツールが多い）', 'warn')}</span></label>`;
      });
      const missing = r.children.filter(n => !names.has(n)).map(n => `<label class="ae-child"><input type="checkbox" data-ae-child="${esc(n)}" checked>
          <span class="ae-child-main"><span class="ae-item-name">${esc(n)}</span>${badge(opts.kind === 'module' ? 'このモジュールにない' : '一覧にない', 'warn')}
            <span class="ae-child-info">${opts.kind === 'module' ? '外すか、左の「＋ エージェントを追加」で同じ名前を足してください' : '写した先のモジュールにあれば使えます'}</span></span></label>`);
      return `<section class="ae-sec"><h4>起動してよい子</h4>
        <p class="mi-note">この役が子として起動できるエージェントを、${opts.kind === 'module' ? 'このモジュールのエージェント' : 'プリセット'}から選びます（左の一覧と同じ。足すと、ここにも出ます）。この役より強い（渡すツールが多い）ものは選べません。</p>
        <div class="ae-children">${rows.concat(missing).join('')}</div>
        <label class="ae-field ae-narrow">同時に持てる子の数<input type="number" min="0" data-ae-field="max_children" value="${r.max_children}"></label></section>`;
    }
    function editor() {
      if (st.selected === opts.top?.key) return opts.top.render();
      const r = st.shown;
      if (!r) return `<div class="eco-banner bad">${esc(st.error || '選んでください')}</div>`;
      const model = MODELS.some(([v]) => v === r.model) ? r.model : 'other';
      const sampleNote = r.source === 'sample' ? `<p class="mi-note">${opts.kind === 'module'
        ? 'プリセット（ECOBuild の見本）のままです。直して保存すると、このモジュール用に上書きします（プリセットはそのまま）。'
        : 'ECOBuild の見本です。直して保存すると、このPCのプリセットとして上書きします（見本はそのまま）。'}</p>` : '';
      const removable = r.source === (opts.kind === 'module' ? 'module' : 'preset');
      return `<div class="ae-head"><div><h3>${esc(r.title)} <span class="ae-item-name">${esc(r.name)}</span></h3>
          <div class="ae-item-badges">${badge(opts.kind === 'module' && r.source === 'sample' ? 'プリセットのまま' : SOURCES[r.source] || r.source, 'quiet')}${r.human_start ? badge('人が起動', 'top') : ''}${r.pending ? badge('まだ効いていない（取り込まれると効く）', 'warn') : ''}</div>${sampleNote}</div>
        <div class="mi-actions"><button type="button" class="primary" data-ae-save disabled>${opts.kind === 'module' ? (r.source === 'sample' ? 'このモジュール用に保存' : '保存してコミット') : '保存'}</button>
          <button type="button" data-ae-revert disabled>元に戻す</button>
          ${opts.kind === 'module' ? '<button type="button" data-ae-to-preset title="この登録を、このPCのプリセットとして保存します（ほかのモジュールでも使えるように）">プリセットにする</button>' : ''}
          ${removable ? `<button type="button" class="danger-text" data-ae-remove>${st.samples.has(r.name) ? (opts.kind === 'module' ? 'プリセットに戻す' : '見本に戻す') : '消す'}</button>` : ''}</div></div>
        <section class="ae-sec"><h4>基本</h4><div class="ae-grid">
          <label class="ae-field">表示名<input type="text" data-ae-field="title" value="${esc(r.title)}"></label>
          <label class="ae-field">モデル<select data-ae-field="model">${MODELS.map(([v, l]) => `<option value="${v}"${v === model ? ' selected' : ''}>${l}</option>`).join('')}<option value="other"${model === 'other' ? ' selected' : ''}>そのほか…</option></select>
            <input type="text" data-ae-field="model-other" value="${esc(model === 'other' ? r.model : '')}" placeholder="モデルの名前"${model === 'other' ? '' : ' hidden'}></label>
        </div></section>
        ${startSection(r)}
        <section class="ae-sec"><h4>文書</h4><p class="mi-note">起動のときにエージェントに渡す、この役の文（何者か・何をするか・決まり）。</p>
          <textarea class="ae-doc" data-ae-field="document" rows="${Math.min(28, Math.max(10, r.document.split('\n').length + 2))}">${esc(r.document)}</textarea></section>
        <section class="ae-sec"><h4>最初の発言</h4><textarea data-ae-field="first_prompt" rows="2">${esc(r.first_prompt || '')}</textarea></section>
        ${loopSection(r)}
        ${toolsSection(r)}
        ${childrenSection(r)}`;
    }
    // The improvement loop (evaluate → fix → evaluate again) and when to stop: written into the briefing; the turn and cost
    // limits are kept by ECOBuild when an agent starts it (claude -p), not when a person starts it in a tab
    function loopSection(r) {
      const num = (key, label, step, help) => `<label class="ae-field ae-narrow">${label}<input type="number" min="0" step="${step}" data-ae-field="${key}" value="${r[key] || 0}"${help ? ` title="${esc(help)}"` : ''}></label>`;
      return `<section class="ae-sec"><h4>改善のループと止める条件</h4>
        <p class="mi-note">評価 → 直す → 評価し直す を回し、良くなった変更だけを残す。決めたものは起動のときの文に入ります。0 は「決めない／上限なし」。ターン数・費用の上限は、ほかのエージェントが起動したとき（画面なし）に ECOBuild が止めます。</p>
        <div class="ae-grid">
          <label class="ae-field">評価のしかた<input type="text" data-ae-field="evaluation" value="${esc(r.evaluation || '')}" placeholder="例：check（only=build,test）。空なら任された仕事に書かれたもの"></label>
          <label class="ae-field">教訓の記録先（モジュールの中のフォルダー）<input type="text" data-ae-field="lessons" value="${esc(r.lessons || '')}" placeholder="例：.ecobuild/agents/lessons。空なら報告に書くだけ"></label>
        </div>
        <div class="ae-grid">
          ${num('max_rounds', '評価し直す回数の上限', 1, 'それでも届かなければ「質問あり」か「止まっている」で返す')}
          ${num('max_turns', 'ターン数の上限', 1)}
          ${num('max_cost', '費用の上限（ドル）', 0.5)}
        </div></section>`;
    }
    function draw() {
      box.innerHTML = `${opts.notice ? opts.notice() : ''}<div class="ae">${side()}<div class="ae-main">${editor()}</div></div>`;
      if (st.shown && st.selected !== opts.top?.key) showFit(edited().v);
    }
    const field = name => box.querySelector(`[data-ae-field="${name}"]`);
    function edited() {
      const r = st.shown, v = {};
      v.title = field('title').value.trim();
      v.model = field('model').value === 'other' ? field('model-other').value.trim() : field('model').value;
      v.human_start = field('human_start').checked;
      v.document = field('document').value;
      v.first_prompt = field('first_prompt').value.trim();
      const pick = box.querySelector('[name=ae-tools-mode]:checked')?.value === 'pick';
      const patterns = (field('patterns')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
      v.tools = pick ? [...new Set([...box.querySelectorAll('[data-ae-tool]:checked:not([data-by-pattern])')].map(b => b.dataset.aeTool).concat(patterns))] : ['*'];
      v.children = [...box.querySelectorAll('[data-ae-child]:checked')].map(b => b.dataset.aeChild);
      v.max_children = Number(field('max_children').value) || 0;
      v.evaluation = field('evaluation').value.trim();
      v.lessons = field('lessons').value.trim();
      for (const key of ['max_rounds', 'max_turns', 'max_cost']) v[key] = Math.max(0, Number(field(key).value) || 0);
      const same = (a, b) => a.length === b.length && a.every(x => b.includes(x));
      const args = [];
      if (v.title !== r.title) args.push('--title', v.title);
      if (v.model !== r.model) args.push('--model', v.model);
      if (v.human_start !== r.human_start) args.push(v.human_start ? '--human-start' : '--no-human-start');
      if (!same(v.tools, r.tools)) args.push('--tools', v.tools.join(','));
      if (!same(v.children, r.children)) args.push('--children', v.children.join(','));
      if (v.max_children !== r.max_children) args.push('--max-children', String(v.max_children));
      if (v.first_prompt !== (r.first_prompt || '').trim()) args.push('--first-prompt', v.first_prompt);
      if (v.evaluation !== (r.evaluation || '')) args.push('--evaluation', v.evaluation);
      if (v.lessons !== (r.lessons || '')) args.push('--lessons', v.lessons);
      for (const key of ['max_rounds', 'max_turns', 'max_cost']) if (v[key] !== (r[key] || 0)) args.push(`--${key.replace('_', '-')}`, String(v[key]));
      const document = v.document.trim() !== r.document.trim();
      if (document) args.push('--document', '-');
      // the roles that start this one: their children change (added or taken off)
      const wanted = [...box.querySelectorAll('[data-ae-parent]:checked')].map(b => b.dataset.aeParent), had = parentsOf(r.name);
      const parents = st.list.filter(x => wanted.includes(x.name) !== had.includes(x.name))
        .map(x => [x.name, wanted.includes(x.name) ? [...x.children, r.name] : x.children.filter(n => n !== r.name)]);
      return {args, stdin: document ? v.document.trim() + '\n' : undefined, parents, v};
    }
    function markDirty() {
      if (!st.shown) return;
      const {args, parents, v} = edited();
      st.dirty = args.length > 0 || parents.length > 0;
      const save = box.querySelector('[data-ae-save]'), revert = box.querySelector('[data-ae-revert]');
      if (save) save.disabled = !st.dirty;
      if (revert) revert.disabled = !st.dirty;
      showFit(v);
    }
    // What the choices come to: which children/parents the tools picked don't allow, how many tools, who starts it.
    function showFit(v) {
      const me = {tools: v.tools};
      for (const row of box.querySelectorAll('[data-ae-child-row]')) {
        const x = st.list.find(y => y.name === row.dataset.aeChildRow), box_ = row.querySelector('input'), strong = x && x.name !== st.shown.name && stronger(x, v.tools);
        row.querySelector('[data-ae-child-warn]').hidden = !strong;
        box_.disabled = strong && !box_.checked;
        row.classList.toggle('ae-off', !!strong);
      }
      for (const b of box.querySelectorAll('[data-ae-parent]')) {
        const x = st.list.find(y => y.name === b.dataset.aeParent), strong = x && stronger(me, x.tools);
        b.closest('.ae-child').querySelector('[data-ae-parent-warn]').hidden = !strong;
        b.disabled = strong && !b.checked;
        b.closest('.ae-child').classList.toggle('ae-off', !!strong);
      }
      const count = box.querySelector('[data-ae-count]');
      if (count) {
        const given = v.tools.includes('*') ? st.tools : st.tools.filter(t => matches(t.name, v.tools));
        const owner = given.filter(t => t.mark === 'owner').length;
        count.textContent = `${given.length} / ${st.tools.length} 個を渡す${owner ? `（コミット・提出のツール ${owner} 個を含む）` : '（コミット・提出はさせない）'}`
          + (given.length > TOO_MANY ? `。多めです：ツールが ${TOO_MANY} を超えると選び方が落ちやすい（仕事に要るものに絞るか、手順はスキル・文書に）` : '');
        count.classList.toggle('ae-count-warn', given.length > TOO_MANY);
      }
      for (const fs of box.querySelectorAll('.ae-group')) {
        const all = fs.querySelectorAll('[data-ae-tool]'), on = fs.querySelectorAll('[data-ae-tool]:checked');
        fs.querySelector('[data-ae-group-count]').textContent = `${on.length} / ${all.length}`;
      }
      const sum = box.querySelector('[data-ae-start-sum]');
      if (sum) {
        const parents = [...box.querySelectorAll('[data-ae-parent]:checked')].map(b => st.list.find(x => x.name === b.dataset.aeParent)?.title || b.dataset.aeParent);
        const who = [v.human_start ? '人（手で）' : '', ...parents].filter(Boolean);
        sum.textContent = who.length ? `起動するのは：${who.join('・')}${parents.length ? '' : '（ほかのエージェントからは起動されません）'}`
          : '起動するのは：だれもいません（人も、どの役も起動できません）';
      }
    }
    const committed = r => r?.committed ? `（コミット ${r.committed.slice(0, 7)}。提出して取り込まれると効きます）` : '';
    // Several changes in one place (asked once). null: cancelled; else whether all were made (it stops at the first failure).
    async function changeAll(what, steps) {
      const dir = await target(what);
      if (dir === undefined) return null;
      let done = true;
      for (const [args, extra] of steps) if (!await ECO.run(dir, args, extra)) { done = false; break; }
      st.dirty = false; await opts.onChanged?.(dir);
      return done;
    }
    // This registration and the roles that start it: taken off them first, added last (so the checks of strength pass)
    async function save() {
      const {args, stdin, parents} = edited();
      if (!args.length && !parents.length) return;
      const name = st.shown.name;
      const parentStep = ([parent, children]) => [['agent', group, 'set', parent, '--children', children.join(',')],
        {success: `「${parent}」の起動してよい子を変えました。`}];
      const steps = [...parents.filter(([, c]) => !c.includes(name)).map(parentStep),
        ...(args.length ? [[['agent', group, 'set', name, ...args], {stdin, success: r => `「${name}」を保存しました${opts.kind === 'module' ? committed(r) : '。'}`}]] : []),
        ...parents.filter(([, c]) => c.includes(name)).map(parentStep)];
      if (await changeAll(`「${st.shown.title}」を保存`, steps) !== null) await load();
    }
    // 追加：新規作成か、プリセット（このPCの手持ちと ECOBuild の見本）から作る
    async function add() {
      const presets = await cli(['agent', 'preset', 'list']);
      if (!presets.ok) return ECO.showError(presets);
      const choices = presets.result;
      const v = await ECO.form({title: opts.kind === 'module' ? 'エージェントを追加' : 'プリセットを足す',
        intro: opts.kind === 'module' ? 'このモジュールのエージェント（役）を足します。保存するとリポジトリにコミットし、提出して取り込まれると起動できます。' : 'このPCのプリセットを足します。モジュールの「エージェント」から写して使えます。',
        fields: [{name: 'how', label: '作り方', type: 'radio', value: choices.length ? 'preset' : 'new', options: [['preset', 'プリセットから作成', 'プリセットを写して、名前を付けて足します'], ['new', '新規作成', '空の役を作ります（文書・ツールは後で）']]},
                 {name: 'from', label: '元にするプリセット', type: 'select', value: choices[0]?.name || '', showIf: x => x.how === 'preset',
                  options: choices.map(p => [p.name, `${p.title}（${p.name}・${SOURCES[p.source] || p.source}）`])},
                 {name: 'name', label: '名前（英小文字・数字・-・_）', placeholder: '例：reviewer', help: 'プリセットから作るときは、空ならプリセットと同じ名前'},
                 {name: 'title', label: '表示名', placeholder: '例：レビュー役', showIf: x => x.how === 'new'},
                 {name: 'who', label: 'だれが起動する', type: 'radio', value: 'human', options: [
                   ['human', '人が手で起動する', '作業空間の「エージェント」の ＋ から。ほかの役の子にはしません（管理役などは起動できない）'],
                   ['parents', 'ほかの役が子として起動する', '選んだ役の「起動してよい子」に入れます']]},
                 {name: 'parents', label: '起動できる役', type: 'checks', showIf: x => x.who === 'parents',
                  options: st.list.map(x => [x.name, `${x.title}（${x.name}）`])},
                 {name: 'no_owner', label: 'コミット・push・提出はさせない（変えたファイルは人が見て、人がコミット・提出する）', type: 'checkbox', value: true}],
        ok: '追加'});
      if (!v) return;
      const name = (v.name || '').trim() || (v.how === 'preset' ? v.from : '');
      if (!name) return ECO.toast('名前を入れてください。', 'bad');
      const from = v.how === 'preset' ? choices.find(p => p.name === v.from) : null;
      const set = [...(v.how === 'new' && (v.title || '').trim() ? ['--title', v.title.trim()] : []),
                   v.who === 'human' ? '--human-start' : '--no-human-start'];
      if (v.no_owner) {   // the tools of the preset (empty for a new one: all), less the ones that change the branch
        const base = from && !from.tools.includes('*') ? st.tools.filter(t => matches(t.name, from.tools)) : st.tools;
        set.push('--tools', base.filter(t => t.mark !== 'owner').map(t => t.name).join(','));
      }
      const parents = v.who === 'parents' ? v.parents || [] : [];
      const steps = [[['agent', group, 'add', name, ...(from ? ['--from-preset', from.name] : [])], {success: r => `「${name}」を追加しました${opts.kind === 'module' ? committed(r) : '。'}`}],
        [['agent', group, 'set', name, ...set], {}],
        ...parents.map(p => [['agent', group, 'set', p, '--children', [...st.list.find(x => x.name === p).children, name].join(',')], {}])];
      if (await changeAll(`「${name}」を追加`, steps) === null) return;
      st.selected = name; await load();
    }
    async function remove() {
      const name = st.shown.name, back = st.samples.has(name);
      const label = back ? (opts.kind === 'module' ? 'プリセットに戻す' : '見本に戻す') : '消す';
      if (!await ECO.confirm({title: label, message: back ? `「${name}」の上書きを消して、${opts.kind === 'module' ? 'プリセット（ECOBuild の見本）' : '見本'}に戻します。` : `「${name}」を文書ごと消します。`, ok: label, danger: true})) return;
      const doc = await change(`「${name}」を${label}`, ['agent', group, 'remove', name, '--yes'], {success: `「${name}」を${back ? '戻しました' : '消しました'}。`});
      if (doc) await load(false);
    }
    async function toPreset() {
      const r = st.shown;
      await ECO.form({title: 'プリセットにする', intro: `「${r.title}」を、このPCのプリセットとして保存します（ハブの設定の「エージェント」に入り、ほかのモジュールに写せます）。保存していない変更は入りません。`,
        fields: [{name: 'name', label: 'プリセットの名前', value: r.name, required: true}], ok: '保存',
        submit: async v => {
          const done = await ECO.run(opts.dir(), ['agent', 'preset', 'add', v.name.trim(), '--from-module', r.name], {success: `プリセット「${v.name.trim()}」にしました。`});
          return done ? '' : '保存できませんでした。';
        }});
    }

    box.addEventListener('click', e => {
      const pick = e.target.closest('[data-ae-select]');
      if (pick) return select(pick.dataset.aeSelect);
      if (e.target.closest('[data-ae-add]')) return add();
      if (e.target.closest('[data-ae-save]')) return save();
      if (e.target.closest('[data-ae-revert]')) { st.dirty = false; return draw(); }
      if (e.target.closest('[data-ae-remove]')) return remove();
      if (e.target.closest('[data-ae-to-preset]')) return toPreset();
      const groupButton = e.target.closest('[data-ae-group]');
      if (groupButton) {
        for (const b of groupButton.closest('.ae-group').querySelectorAll('[data-ae-tool]:not([data-by-pattern])')) b.checked = !!groupButton.dataset.on;
        markDirty();
      }
      const quick = e.target.closest('[data-ae-quick]');
      if (quick) {   // pick by what the tools may do (from すべて too)
        const marks = quick.dataset.aeQuick.split(',');
        box.querySelector('[name=ae-tools-mode][value=pick]').checked = true;
        box.querySelector('.ae-tools').hidden = false;
        for (const b of box.querySelectorAll('[data-ae-tool]:not([data-by-pattern])')) b.checked = marks.includes(b.dataset.mark);
        markDirty();
      }
      opts.top && st.selected === opts.top.key && opts.top.click?.(e);
    });
    box.addEventListener('input', () => { if (st.selected !== opts.top?.key) markDirty(); });
    box.addEventListener('change', e => {
      if (e.target.name === 'ae-tools-mode') box.querySelector('.ae-tools').hidden = e.target.value !== 'pick';
      if (e.target.dataset.aeField === 'model') field('model-other').hidden = e.target.value !== 'other';
      if (st.selected !== opts.top?.key) markDirty();
    });
    return {load, dirty: () => st.dirty || !!opts.top?.dirty?.(), redraw: () => st.list && draw()};
  }
  return {create};
})();
