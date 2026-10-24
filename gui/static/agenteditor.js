'use strict';
// The editor of agent registrations, shared by the module page エージェント (the module's registrations:
// ecobuild agent registry …, committed on a task branch) and the hub's settings (this PC's presets: ecobuild agent preset …).
// Left: the list (the module page puts 全エージェント共通 on top); right: one registration, edited in place in sections
// (基本・文書・最初の発言・渡すツール・起動してよい子) and saved at once. All the data comes from the CLI.
window.AGENT_EDITOR = (() => {
  const {esc} = ECO;
  const SOURCES = {sample: '見本', preset: 'このPCのプリセット', module: 'モジュールの登録'};
  const MARKS = {read: '見る', change: '変える', owner: 'タスクの持ち主だけ（ブランチを変える）', children: '子のエージェント'};
  const MODELS = [['', 'Claude Code の既定'], ['opus', 'Opus'], ['fable', 'Fable'], ['sonnet', 'Sonnet'], ['haiku', 'Haiku']];
  const toolsCache = new Map();   // dir → the tools (they change only with ECOBuild)
  const glob = p => new RegExp('^' + p.replace(/[.+^${}()|\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
  const matches = (name, patterns) => patterns.some(p => glob(p).test(name));

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
    function toolsSection(r, off) {
      const all = r.tools.includes('*');
      const exact = new Set(st.tools.map(t => t.name));
      const others = r.tools.filter(p => p !== '*' && !exact.has(p));
      const groups = Object.keys(MARKS).map(mark => [mark, st.tools.filter(t => t.mark === mark)]).filter(([, l]) => l.length);
      return `<section class="ae-sec"><h4>渡すツール</h4>
        <p class="mi-note">エージェントが ECOBuild でできることは、ここで渡すツールだけです。</p>
        <div class="ae-radio"><label><input type="radio" name="ae-tools-mode" value="all"${all ? ' checked' : ''}${off}> すべて（ECOBuild が増やすツールも）</label>
          <label><input type="radio" name="ae-tools-mode" value="pick"${all ? '' : ' checked'}${off}> 選んだものだけ</label></div>
        <div class="ae-tools"${all ? ' hidden' : ''}>
          ${groups.map(([mark, list]) => `<fieldset class="ae-group"><legend>${esc(MARKS[mark])}<span class="ae-group-actions"><button type="button" class="sm" data-ae-group="${mark}" data-on="1"${off}>すべて</button><button type="button" class="sm" data-ae-group="${mark}" data-on=""${off}>外す</button></span></legend>
            ${list.map(t => { const byPattern = matches(t.name, others);   // given by a pattern below: shown, kept as the pattern
              return `<label class="ae-tool" title="${esc(byPattern ? `「そのほか」のパターンで渡しています\n${t.summary}` : t.summary)}"><input type="checkbox" data-ae-tool="${esc(t.name)}" data-mark="${mark}"${byPattern ? ' data-by-pattern' : ''}${byPattern || r.tools.includes(t.name) ? ' checked' : ''}${byPattern ? ' disabled' : off}><code>${esc(t.name)}</code></label>`; }).join('')}</fieldset>`).join('')}
          <label class="ae-field">そのほか（パターン。カンマ区切り。例：task_*）<input type="text" data-ae-field="patterns" value="${esc(others.join(', '))}"${off}></label>
        </div></section>`;
    }
    function editor() {
      if (st.selected === opts.top?.key) return opts.top.render();
      const r = st.shown;
      if (!r) return `<div class="eco-banner bad">${esc(st.error || '選んでください')}</div>`;
      const off = '';
      const others = st.list.filter(x => x.name !== r.name);
      const model = MODELS.some(([v]) => v === r.model) ? r.model : 'other';
      const sampleNote = r.source === 'sample' ? `<p class="mi-note">${opts.kind === 'module'
        ? 'プリセット（ECOBuild の見本）のままです。直して保存すると、このモジュール用に上書きします（プリセットはそのまま）。'
        : 'ECOBuild の見本です。直して保存すると、このPCのプリセットとして上書きします（見本はそのまま）。'}</p>` : '';
      const removable = r.source === (opts.kind === 'module' ? 'module' : 'preset');
      return `<div class="ae-head"><div><h3>${esc(r.title)} <span class="ae-item-name">${esc(r.name)}</span></h3>
          <div class="ae-item-badges">${badge(opts.kind === 'module' && r.source === 'sample' ? 'プリセットのまま' : SOURCES[r.source] || r.source, 'quiet')}${r.human_start ? badge('人が起動（人と話すトップの役）', 'top') : ''}${r.pending ? badge('まだ効いていない（取り込まれると効く）', 'warn') : ''}</div>${sampleNote}</div>
        <div class="mi-actions"><button type="button" class="primary" data-ae-save disabled>${opts.kind === 'module' ? (r.source === 'sample' ? 'このモジュール用に保存' : '保存してコミット') : '保存'}</button>
          <button type="button" data-ae-revert disabled>元に戻す</button>
          ${opts.kind === 'module' ? '<button type="button" data-ae-to-preset title="この登録を、このPCのプリセットとして保存します（ほかのモジュールでも使えるように）">プリセットにする</button>' : ''}
          ${removable ? `<button type="button" class="danger-text" data-ae-remove>${st.samples.has(r.name) ? (opts.kind === 'module' ? 'プリセットに戻す' : '見本に戻す') : '消す'}</button>` : ''}</div></div>
        <section class="ae-sec"><h4>基本</h4><div class="ae-grid">
          <label class="ae-field">表示名<input type="text" data-ae-field="title" value="${esc(r.title)}"${off}></label>
          <label class="ae-field">モデル<select data-ae-field="model"${off}>${MODELS.map(([v, l]) => `<option value="${v}"${v === model ? ' selected' : ''}>${l}</option>`).join('')}<option value="other"${model === 'other' ? ' selected' : ''}>そのほか…</option></select>
            <input type="text" data-ae-field="model-other" value="${esc(model === 'other' ? r.model : '')}" placeholder="モデルの名前"${model === 'other' ? '' : ' hidden'}${off}></label>
          <label class="ae-check"><input type="checkbox" data-ae-field="human_start"${r.human_start ? ' checked' : ''}${off}> 人が起動できる（作業空間の「エージェント」に出る。人と話すトップの役）</label>
        </div></section>
        <section class="ae-sec"><h4>文書</h4><p class="mi-note">起動のときにエージェントに渡す、この役の文（何者か・何をするか・決まり）。</p>
          <textarea class="ae-doc" data-ae-field="document" rows="${Math.min(28, Math.max(10, r.document.split('\n').length + 2))}"${off}>${esc(r.document)}</textarea></section>
        <section class="ae-sec"><h4>最初の発言</h4><textarea data-ae-field="first_prompt" rows="2"${off}>${esc(r.first_prompt || '')}</textarea></section>
        ${toolsSection(r, off)}
        <section class="ae-sec"><h4>起動してよい子</h4><p class="mi-note">この役が起動できるエージェント。自分より強い（渡すツールが多い）ものは選べません。</p>
          <div class="ae-children">${others.length ? others.map(x => `<label class="ae-check"><input type="checkbox" data-ae-child="${esc(x.name)}"${r.children.includes(x.name) ? ' checked' : ''}${off}> ${esc(x.title)}（${esc(x.name)}）</label>`).join('') : '<span class="mi-note">ほかの役がありません</span>'}</div>
          <label class="ae-field ae-narrow">同時に持てる子の数<input type="number" min="0" data-ae-field="max_children" value="${r.max_children}"${off}></label></section>`;
    }
    function draw() {
      box.innerHTML = `${opts.notice ? opts.notice() : ''}<div class="ae">${side()}<div class="ae-main">${editor()}</div></div>`;
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
      const same = (a, b) => a.length === b.length && a.every(x => b.includes(x));
      const args = [];
      if (v.title !== r.title) args.push('--title', v.title);
      if (v.model !== r.model) args.push('--model', v.model);
      if (v.human_start !== r.human_start) args.push(v.human_start ? '--human-start' : '--no-human-start');
      if (!same(v.tools, r.tools)) args.push('--tools', v.tools.join(','));
      if (!same(v.children, r.children)) args.push('--children', v.children.join(','));
      if (v.max_children !== r.max_children) args.push('--max-children', String(v.max_children));
      if (v.first_prompt !== (r.first_prompt || '').trim()) args.push('--first-prompt', v.first_prompt);
      const document = v.document.trim() !== r.document.trim();
      if (document) args.push('--document', '-');
      return {args, stdin: document ? v.document.trim() + '\n' : undefined};
    }
    function markDirty() {
      if (!st.shown) return;
      const {args} = edited();
      st.dirty = args.length > 0;
      const save = box.querySelector('[data-ae-save]'), revert = box.querySelector('[data-ae-revert]');
      if (save) save.disabled = !st.dirty;
      if (revert) revert.disabled = !st.dirty;
    }
    const committed = r => r?.committed ? `（コミット ${r.committed.slice(0, 7)}。提出して取り込まれると効きます）` : '';
    async function save() {
      const {args, stdin} = edited();
      if (!args.length) return;
      const name = st.shown.name;
      const doc = await change(`「${st.shown.title}」を保存`, ['agent', group, 'set', name, ...args],
        {stdin, success: r => `「${name}」を保存しました${opts.kind === 'module' ? committed(r) : '。'}`});
      if (doc) await load();
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
                 {name: 'title', label: '表示名', placeholder: '例：レビュー役', showIf: x => x.how === 'new'}],
        ok: '次へ'});
      if (!v) return;
      const name = (v.name || '').trim() || (v.how === 'preset' ? v.from : '');
      if (!name) return ECO.toast('名前を入れてください。', 'bad');
      const args = ['agent', group, 'add', name, ...(v.how === 'preset' && v.from ? ['--from-preset', v.from] : [])];
      const doc = await change(`「${name}」を追加`, args, {success: r => `「${name}」を追加しました${opts.kind === 'module' ? committed(r) : '。'}`});
      if (!doc) return;
      if (v.how === 'new' && (v.title || '').trim()) await ECO.run(opts.dir(), ['agent', group, 'set', name, '--title', v.title.trim()], {});
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
        for (const b of box.querySelectorAll(`[data-ae-tool][data-mark="${groupButton.dataset.aeGroup}"]:not([data-by-pattern])`)) b.checked = !!groupButton.dataset.on;
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
