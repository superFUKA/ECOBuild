// 部品「エージェントの設定」。左に一覧（全エージェント共通 → 役 → スキル）、右に選んだものを、そのままの欄で直す
// （今までの GUI の agenteditor.js・agentrules.js と同じ並び・同じ見た目）。
// この部品がするのは見せ方だけ：選んでいるもの・直している途中の値・変えた項目だけを出すこと。
// 「多すぎる」「この役より強い」は、届いた確かめ（props.fit。ecobuild agent registry fit）のとおりに見せる。
const SOURCES = { sample: '見本', preset: 'このPCのプリセット', module: 'モジュールの登録' };
// ツールができること（CLI が付けた印）：[見せる言葉, 色]
const MARKS = { read: ['見る', ''], change: ['変える', 'warn'], owner: ['ブランチを変える', 'warn'], children: ['子を扱う', 'top'] };
const QUICK = [['read', '見るだけ'], ['read,change', '見る＋作業空間を変える'], ['read,change,children', 'コミット・提出だけさせない'],
  ['read,change,owner', '子を扱う以外すべて']];
const MODELS = [['', 'Claude Code の既定'], ['opus', 'Opus'], ['fable', 'Fable'], ['sonnet', 'Sonnet'], ['haiku', 'Haiku']];
const DOC = 'document';  // 項目の名前（文書・本文）
const glob = (p) => new RegExp('^' + p.replace(/[.+^${}()|\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
const matches = (name, patterns) => patterns.some((p) => glob(p).test(name));
const firstSentence = (text) => { const line = String(text || '').split('\n')[0]; const end = line.indexOf('。'); return end > 0 ? line.slice(0, end + 1) : line; };
const toolsText = (tools) => ((tools || []).includes('*') ? 'ツール：すべて' : `ツール：${(tools || []).length}件の指定`);
const sameSet = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
const listText = (items) => items.join(',') || ',';   // 1つもないときは「,」（空の並び）
const orBlank = (text) => text || ' ';                 // 空にするときは空白1つ（コマンドが前後の空白を取る）
const keyOf = (sel) => `${sel.kind}:${sel.name}`;

export default {
  render(root, props, { h, emit, state, redraw }) {
    if (props.error) return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, `読めませんでした：${props.error}`)));
    const agents = props.agents || [], skills = props.skills || [], tools = props.tools || [];
    if (!state.selected) state.selected = { kind: 'common', name: '' };
    // 外から「これを選ぶ」と届いたら（変わって届いたときだけ）、それを選ぶ
    const asked = JSON.stringify(props.select || null);
    if (state.asked !== asked) {
      state.asked = asked;
      if (props.select && props.select.kind) { state.selected = { kind: props.select.kind, name: props.select.name || '' }; state.dirty = false; state.fit = null;
        const chosen = state.selected;
        Promise.resolve().then(() => emit('selected', chosen));   // 選んだものの中身を読んでもらう
      }
    }
    // 選んでいたものが一覧から消えた（消した・戻した）ら、共通の文へ
    const sel0 = state.selected;
    if ((sel0.kind === 'role' && agents.length && !agents.some((r) => r.name === sel0.name))
      || (sel0.kind === 'skill' && !skills.some((s) => s.name === sel0.name))) {
      state.selected = { kind: 'common', name: '' };
      state.dirty = false;
    }
    const sel = state.selected;
    const shown = sel.kind === 'role' ? props.registration : sel.kind === 'skill' ? props.skill : props.rules;
    const shownKey = JSON.stringify([keyOf(sel), shown]);
    const allKey = JSON.stringify([shownKey, agents, skills, tools, props.presets]);
    // 同じものを描いてあるなら、作り直さない（入力の途中・スクロールを残す）。直している途中は、一覧だけ変わっても作り直さない
    if (state.fit && (state.allKey === allKey || (state.dirty && state.shownKey === shownKey))) return state.fit(props.fit);
    state.allKey = allKey;
    state.shownKey = shownKey;
    state.dirty = false;
    state.fit = () => {};

    const badge = (text, cls) => h('span', { class: cls ? `badge ${cls}` : 'badge' }, text);
    const note = (text) => h('p', { class: 'note' }, text);
    const samples = new Set((props.presets || []).filter((p) => p.source === 'sample').map((p) => p.name));
    const main = h('div', { class: 'main' });
    const guard = h('div', { class: 'banner guard', hidden: true });
    let saveButton = null, revertButton = null;

    // --- 選ぶ（保存していない変更があれば、先に確かめる） ---
    const go = (next) => {
      state.selected = next;
      state.dirty = false;
      state.fit = null;
      emit('selected', next);
      redraw();
    };
    const select = (next) => {
      if (keyOf(next) === keyOf(sel)) return;
      if (!state.dirty) return go(next);
      const leave = h('button', { type: 'button', class: 'danger small' }, '捨てて移る');
      const stay = h('button', { type: 'button', class: 'small' }, '戻る');
      leave.addEventListener('click', () => go(next));
      stay.addEventListener('click', () => { guard.hidden = true; });
      guard.replaceChildren(h('span', {}, '保存していない変更があります。捨てて移りますか？'), leave, stay);
      guard.hidden = false;
      leave.focus();
    };
    const setDirty = (dirty) => {
      state.dirty = dirty;
      if (saveButton) saveButton.disabled = !dirty;
      if (revertButton) revertButton.disabled = !dirty;
      if (!dirty) guard.hidden = true;
    };
    const revert = () => { state.fit = null; state.dirty = false; redraw(); };

    // --- 左：一覧 ---
    const item = (target, title, name, badges, top) => {
      const button = h('button', { type: 'button', class: top ? 'item top' : 'item' },
        h('span', { class: 'item-title' }, title), h('span', { class: 'item-name' }, name));
      if (badges.length) button.append(h('span', { class: 'badges' }, ...badges));
      button.setAttribute('aria-current', String(keyOf(target) === keyOf(sel)));
      button.addEventListener('click', () => select(target));
      return button;
    };
    const side = h('nav', { class: 'side', 'aria-label': 'エージェント' });
    side.append(item({ kind: 'common', name: '' }, '全エージェント共通', 'どのエージェントにも渡す文',
      props.rules && props.rules.pending ? [badge('まだ効いていない', 'warn')] : [], true));
    side.append(h('div', { class: 'side-head' }, '役'));
    for (const r of agents) {
      const badges = [];
      if (r.human_start) badges.push(badge('人が起動', 'top'));
      if (r.source === 'sample') badges.push(badge('プリセットのまま', 'quiet'));
      if (r.pending) badges.push(badge('まだ効いていない', 'warn'));
      side.append(item({ kind: 'role', name: r.name }, r.title, r.name, badges));
    }
    const addRole = h('button', { type: 'button', class: 'add' }, '＋ エージェントを追加');
    addRole.addEventListener('click', () => emit('add', {}));
    side.append(addRole, h('div', { class: 'side-head' }, 'スキル'));
    for (const s of skills) {
      side.append(item({ kind: 'skill', name: s.name }, s.name, firstSentence(s.description), s.pending ? [badge('まだ渡らない', 'warn')] : []));
    }
    const addSkill = h('button', { type: 'button', class: 'add' }, '＋ スキルを追加');
    addSkill.addEventListener('click', () => emit('add_skill', {}));
    side.append(addSkill);

    // --- 右：選んだもの ---
    const section = (title, ...children) => h('section', { class: 'sec' }, h('h4', {}, title), ...children);
    const field = (label, control, cls) => h('label', { class: cls ? `field ${cls}` : 'field' }, label, control);
    const head = (title, name, badges, extra, buttons) => {
      const left = h('div', {}, h('h3', {}, title, ' ', h('span', { class: 'item-name' }, name)), h('div', { class: 'badges' }, ...badges), ...extra);
      return h('div', { class: 'head' }, left, h('div', { class: 'actions' }, ...buttons));
    };
    const textArea = (value, rows, cls) => {
      const area = h('textarea', { rows, spellcheck: false });
      if (cls) area.className = cls;
      area.value = value || '';
      return area;
    };
    const docRows = (text, least) => Math.min(28, Math.max(least, String(text || '').split('\n').length + 2));
    const loading = () => h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 読み込み中…');

    const drawCommon = () => {
      const rules = props.rules;
      if (!rules) return [loading()];
      const area = textArea(rules.common, Math.min(24, Math.max(8, String(rules.common || '').split('\n').length + 2)), 'doc');
      area.placeholder = '例：前後がつながった段階（調べる→設計→実装）は分けずに自分で進める。子に任せるのは、互いに独立した仕事と検証だけ。';
      area.setAttribute('aria-label', '全エージェント共通の文');
      saveButton = h('button', { type: 'button', class: 'primary', disabled: true }, '保存してコミット');
      revertButton = h('button', { type: 'button', disabled: true }, '元に戻す');
      saveButton.addEventListener('click', () => emit('save_rules', { common: area.value }));
      revertButton.addEventListener('click', revert);
      area.addEventListener('input', () => setDirty(area.value.trim() !== String(rules.common || '').trim()));
      return [
        head('全エージェント共通', '', rules.pending ? [badge('まだ効いていない（取り込まれると効く）', 'warn')] : [],
          [note(`このモジュールで起動するどのエージェントにも、役の文書の後に渡します（基準・仕事の分け方の決まり 等）。効く版：${rules.in_force || '—'}`),
            note(`表示している場所：${rules.root || ''}`)],
          [saveButton, revertButton]),
        area,
      ];
    };

    const drawSkill = () => {
      const s = props.skill;
      if (!s || s.name !== sel.name) return [loading()];
      const description = textArea(s.description, 3);
      description.setAttribute('aria-label', '説明');
      const body = textArea(s[DOC], docRows(s[DOC], 10), 'doc');
      body.setAttribute('aria-label', '本文');
      const edited = () => {
        const out = { name: s.name };
        if (description.value.trim() !== String(s.description || '')) out.description = description.value.trim();
        if (body.value.trim() !== String(s[DOC] || '').trim()) out[DOC] = body.value.trim() + '\n';
        return out;
      };
      const mark = () => setDirty(Object.keys(edited()).length > 1);
      description.addEventListener('input', mark);
      body.addEventListener('input', mark);
      saveButton = h('button', { type: 'button', class: 'primary', disabled: true }, '保存してコミット');
      revertButton = h('button', { type: 'button', disabled: true }, '元に戻す');
      const keep = h('button', { type: 'button', title: 'このスキルを、このPCのスキルとして保存します（ほかのモジュールでも使えるように）' }, 'このPCのスキルにする');
      const remove = h('button', { type: 'button', class: 'danger-text' }, '消す');
      saveButton.addEventListener('click', () => emit('save_skill', edited()));
      revertButton.addEventListener('click', revert);
      keep.addEventListener('click', () => emit('skill_to_preset', { name: s.name }));
      remove.addEventListener('click', () => emit('remove_skill', { name: s.name }));
      const out = [
        head(s.name, 'スキル', [badge('モジュールのスキル', 'quiet'), ...(s.pending ? [badge('まだ渡らない（取り込まれると渡る）', 'warn')] : [])], [],
          [saveButton, revertButton, keep, remove]),
        section('説明', note('何をするか・いつ使うか。エージェントはこれを見て、読むかを決めます。'), description),
        section('本文', note('使うときに読む手順・決まり・例（SKILL.md の本文）。'), body),
        section('使える役', note(`${(s.used_by || []).join('・') || 'なし'}（役の「使えるスキル」で変えます）`)),
      ];
      if ((s.files || []).length) {
        const files = h('p', { class: 'note' });
        for (const file of s.files) files.append(h('code', {}, file), ' ');
        files.append(`（${s.folder || ''}）`);
        out.push(section('ほかのファイル', files));
      }
      return out;
    };

    const drawRole = () => {
      const r = props.registration;
      if (!r || r.name !== sel.name) return [loading()];
      const rTools = r.tools || [], rSkills = r.skills || [], rChildren = r.children || [];
      const onChange = [];   // 欄が変わるたびに呼ぶ（保存できるか・数の表示）
      const changed = () => onChange.forEach((fn) => fn());

      // 基本
      const title = h('input', { type: 'text', value: r.title || '' });
      const known = MODELS.some(([v]) => v === (r.model || ''));
      const model = h('select', {}, ...MODELS.map(([v, l]) => h('option', { value: v }, l)), h('option', { value: 'other' }, 'そのほか…'));
      model.value = known ? (r.model || '') : 'other';
      const modelOther = h('input', { type: 'text', value: known ? '' : r.model, placeholder: 'モデルの名前', hidden: known, 'aria-label': 'モデルの名前' });
      model.addEventListener('change', () => { modelOther.hidden = model.value !== 'other'; });
      // 起動
      const humanStart = h('input', { type: 'checkbox', checked: !!r.human_start });
      // 文書・最初の発言
      const body = textArea(r[DOC], docRows(r[DOC], 10), 'doc');
      body.setAttribute('aria-label', '文書');
      const firstPrompt = textArea(r.first_prompt, 2);
      firstPrompt.setAttribute('aria-label', '最初の発言');
      // 改善のループ
      const evaluation = h('input', { type: 'text', value: r.evaluation || '', placeholder: '例：check（only=build,test）。空なら任された仕事に書かれたもの' });
      const lessons = h('input', { type: 'text', value: r.lessons || '', placeholder: '例：.ecobuild/agents/lessons。空なら報告に書くだけ' });
      const number = (key, step, help) => {
        const input = h('input', { type: 'number', min: '0', step: String(step), value: String(r[key] || 0) });
        if (help) input.title = help;
        return input;
      };
      const maxRounds = number('max_rounds', 1, 'それでも届かなければ「質問あり」か「止まっている」で返す');
      const maxTurns = number('max_turns', 1);
      const maxCost = number('max_cost', 0.5);

      // 渡すツール：すべて／選んだものだけ。何についてのツールか（area）ごとの箱
      const allTools = rTools.includes('*');
      const exact = new Set(tools.map((t) => t.name));
      const otherPatterns = rTools.filter((p) => p !== '*' && !exact.has(p));
      const radio = (group, value, checked, text) => {
        const input = h('input', { type: 'radio', name: group, value, checked });
        return [h('label', {}, input, ' ', text), input];
      };
      const [toolsAllLabel, toolsAll] = radio('tools-mode', 'all', allTools, 'すべて（ECOBuild が増やすツールも）');
      const [toolsPickLabel, toolsPick] = radio('tools-mode', 'pick', !allTools, '選んだものだけ');
      const patterns = h('input', { type: 'text', value: otherPatterns.join(', ') });
      const toolBoxes = [];   // {input, tool, byPattern}
      const toolRow = (t) => {
        const byPattern = matches(t.name, otherPatterns);   // 下のパターンで渡している：付いたものとして見せる
        const [kind, cls] = MARKS[t.mark] || [t.mark, ''];
        const input = h('input', { type: 'checkbox', checked: byPattern || allTools || rTools.includes(t.name), disabled: byPattern });
        toolBoxes.push({ input, tool: t, byPattern });
        const row = h('label', { class: 'tool', title: (byPattern ? '下のパターンで渡しています\n' : '') + (t.summary || '') },
          input, h('span', { class: 'tool-text' }, firstSentence(t.summary) || t.name), h('code', {}, t.name));
        if (kind && cls) row.append(badge(kind, cls));
        return row;
      };
      const areas = [];
      for (const t of tools) {
        const label = t.area || 'そのほか';
        let area = areas.find((a) => a.label === label);
        if (!area) { area = { label, tools: [] }; areas.push(area); }
        area.tools.push(t);
      }
      const groupCounts = [];
      const groups = areas.map((area) => {
        const from = toolBoxes.length;
        const rows = area.tools.map(toolRow);
        const mine = toolBoxes.slice(from);
        const count = h('span', { class: 'group-count' });
        groupCounts.push(() => { count.textContent = `${mine.filter((b) => b.input.checked).length} / ${mine.length}`; });
        const on = h('button', { type: 'button', class: 'small' }, 'すべて');
        const off = h('button', { type: 'button', class: 'small' }, '外す');
        const set = (value) => { for (const b of mine) if (!b.byPattern) b.input.checked = value; toolsChanged(); };
        on.addEventListener('click', () => set(true));
        off.addEventListener('click', () => set(false));
        on.setAttribute('aria-label', `${area.label}：すべて`);
        off.setAttribute('aria-label', `${area.label}：外す`);
        return h('fieldset', { class: 'group' }, h('legend', {}, area.label, count, h('span', { class: 'group-actions' }, on, off)), ...rows);
      });
      const toolsMore = h('details', { class: 'more', open: otherPatterns.length > 0 }, h('summary', {}, '名前のパターンで渡す（上級）'),
        field('パターン（カンマ区切り。例：task_*。後で増えるツールも合えば渡します）', patterns));
      const toolsBox = h('div', { class: 'tools', hidden: allTools }, ...groups, toolsMore);
      const count = h('span', { class: 'count' });
      const quick = h('div', { class: 'quick' }, h('span', {}, 'まとめて選ぶ：'));
      for (const [marks, label] of QUICK) {
        const button = h('button', { type: 'button', class: 'small' }, label);
        button.addEventListener('click', () => {   // できることの印で選ぶ（「すべて」からでも）
          const wanted = marks.split(',');
          toolsPick.checked = true;
          toolsBox.hidden = false;
          for (const b of toolBoxes) if (!b.byPattern) b.input.checked = wanted.includes(b.tool.mark);
          toolsChanged();
        });
        quick.append(button);
      }
      quick.append(count);
      const splitList = (text) => text.split(',').map((s) => s.trim()).filter(Boolean);
      const draftTools = () => (toolsPick.checked
        ? [...new Set(toolBoxes.filter((b) => b.input.checked && !b.byPattern).map((b) => b.tool.name).concat(splitList(patterns.value)))]
        : ['*']);
      let timer = null;
      function toolsChanged() {
        changed();
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => emit('tools_changed', { name: r.name, text: listText(draftTools()) }), 350);   // 続けて選ぶあいだは、最後だけ確かめる
      }
      for (const input of [toolsAll, toolsPick]) input.addEventListener('change', () => { toolsBox.hidden = !toolsPick.checked; toolsChanged(); });
      for (const b of toolBoxes) b.input.addEventListener('change', toolsChanged);
      patterns.addEventListener('change', toolsChanged);

      // 使えるスキル
      const allSkills = rSkills.includes('*');
      const skillNames = new Set(skills.map((s) => s.name));
      const otherSkills = rSkills.filter((p) => p !== '*' && !skillNames.has(p));
      const [skillsAllLabel, skillsAll] = radio('skills-mode', 'all', allSkills, 'すべて（後で足すスキルも）');
      const [skillsPickLabel, skillsPick] = radio('skills-mode', 'pick', !allSkills, '選んだものだけ');
      const skillPatterns = h('input', { type: 'text', value: otherSkills.join(', ') });
      const skillBoxes = skills.map((s) => {
        const byPattern = matches(s.name, otherSkills);
        const input = h('input', { type: 'checkbox', checked: allSkills || byPattern || rSkills.includes(s.name), disabled: byPattern });
        return { input, name: s.name, byPattern, row: h('label', { class: 'tool', title: s.description || '' }, input,
          h('span', { class: 'tool-text' }, firstSentence(s.description)), h('code', {}, s.name)) };
      });
      const skillsBox = h('div', { class: 'skills', hidden: allSkills });
      if (skillBoxes.length) skillsBox.append(...skillBoxes.map((b) => b.row));
      else skillsBox.append(h('span', { class: 'note' }, 'このモジュールにスキルがありません'));
      skillsBox.append(h('details', { class: 'more', open: otherSkills.length > 0 }, h('summary', {}, '名前のパターンで選ぶ（上級）'),
        field('パターン（カンマ区切り。例：build-*）', skillPatterns)));
      for (const input of [skillsAll, skillsPick]) input.addEventListener('change', () => { skillsBox.hidden = !skillsPick.checked; });
      const draftSkills = () => (skillsPick.checked
        ? [...new Set(skillBoxes.filter((b) => b.input.checked && !b.byPattern).map((b) => b.name).concat(splitList(skillPatterns.value)))]
        : ['*']);

      // 起動してよい子
      const names = new Set(agents.map((x) => x.name));
      const childBoxes = [];   // {input, name, row, warn}
      const childRows = agents.map((x) => {
        const input = h('input', { type: 'checkbox', checked: rChildren.includes(x.name) });
        const mainBox = h('span', { class: 'child-main' }, h('span', { class: 'item-title' }, x.title), ' ', h('span', { class: 'item-name' }, x.name));
        if (x.name === r.name) mainBox.append(badge('この役自身', 'quiet'));
        const modelName = (MODELS.find(([v]) => v === (x.model || '')) || [0, x.model])[1];
        mainBox.append(h('span', { class: 'child-info' }, `${modelName}・${toolsText(x.tools)}`));
        const warn = h('span', { class: 'child-warn', hidden: true }, badge('この役より強い（渡すツールが多い）', 'warn'));
        const row = h('label', { class: 'child' }, input, mainBox, warn);
        childBoxes.push({ input, name: x.name, row, warn });
        return row;
      });
      for (const n of rChildren.filter((c) => !names.has(c))) {
        const input = h('input', { type: 'checkbox', checked: true });
        const row = h('label', { class: 'child' }, input, h('span', { class: 'child-main' }, h('span', { class: 'item-name' }, n), badge('このモジュールにない', 'warn'),
          h('span', { class: 'child-info' }, '外すか、左の「＋ エージェントを追加」で同じ名前を足してください')));
        childBoxes.push({ input, name: n, row, warn: null });
        childRows.push(row);
      }
      const maxChildren = h('input', { type: 'number', min: '0', value: String(r.max_children || 0) });

      // 変えた項目だけ
      const numberOf = (input) => Math.max(0, Number(input.value) || 0);
      const edited = () => {
        const out = { name: r.name };
        const v = {
          title: title.value.trim(), model: model.value === 'other' ? modelOther.value.trim() : model.value,
          tools: draftTools(), skills: draftSkills(), children: childBoxes.filter((b) => b.input.checked).map((b) => b.name),
        };
        if (v.title !== (r.title || '')) out.title = v.title;
        if (v.model !== (r.model || '')) out.model = orBlank(v.model);
        if (humanStart.checked !== !!r.human_start) out.human_start = humanStart.checked;
        if (!sameSet(v.tools, rTools)) out.tools = listText(v.tools);
        if (!sameSet(v.skills, rSkills)) out.skills = listText(v.skills);
        if (!sameSet(v.children, rChildren)) out.children = listText(v.children);
        if (numberOf(maxChildren) !== (r.max_children || 0)) out.max_children = numberOf(maxChildren);
        if (firstPrompt.value.trim() !== String(r.first_prompt || '').trim()) out.first_prompt = orBlank(firstPrompt.value.trim());
        if (evaluation.value.trim() !== (r.evaluation || '')) out.evaluation = orBlank(evaluation.value.trim());
        if (lessons.value.trim() !== (r.lessons || '')) out.lessons = orBlank(lessons.value.trim());
        if (numberOf(maxRounds) !== (r.max_rounds || 0)) out.max_rounds = numberOf(maxRounds);
        if (numberOf(maxTurns) !== (r.max_turns || 0)) out.max_turns = numberOf(maxTurns);
        if (numberOf(maxCost) !== (r.max_cost || 0)) out.max_cost = numberOf(maxCost);
        if (body.value.trim() !== String(r[DOC] || '').trim()) out[DOC] = body.value.trim() + '\n';
        return out;
      };

      // 選んだ結果：渡す数（数えるだけ）と、届いた確かめ（多すぎる・この役より強い）
      let fit = null;
      const showFit = () => {
        const given = toolsPick.checked ? toolBoxes.filter((b) => b.input.checked) : toolBoxes;
        const owner = given.filter((b) => b.tool.mark === 'owner').length;
        const fresh = fit && fit.name === r.name;
        const tooMany = fresh && fit.too_many && given.length > fit.limit;
        count.textContent = `${given.length} / ${toolBoxes.length} 個を渡す${owner ? `（コミット・提出のツール ${owner} 個を含む）` : '（コミット・提出はさせない）'}`
          + (tooMany ? `。多めです：ツールが ${fit.limit} を超えると選び方が落ちやすい（仕事に要るものに絞るか、手順はスキル・文書に）` : '');
        count.className = tooMany ? 'count count-warn' : 'count';
        groupCounts.forEach((fn) => fn());
        const strong = new Set(fresh ? fit.stronger || [] : []);
        for (const b of childBoxes) {
          if (!b.warn) continue;
          const isStrong = strong.has(b.name) && b.name !== r.name;
          b.warn.hidden = !isStrong;
          b.input.disabled = isStrong && !b.input.checked;
          b.row.className = isStrong ? 'child off' : 'child';
        }
      };
      onChange.push(() => setDirty(Object.keys(edited()).length > 1), showFit);
      state.fit = (next) => { fit = next || null; showFit(); };
      state.fit(props.fit);

      const inputs = [title, model, modelOther, humanStart, body, firstPrompt, evaluation, lessons, maxRounds, maxTurns, maxCost, skillsAll, skillsPick,
        skillPatterns, maxChildren, ...skillBoxes.map((b) => b.input), ...childBoxes.map((b) => b.input)];
      for (const input of inputs) { input.addEventListener('input', changed); input.addEventListener('change', changed); }

      // 見出し
      const removable = r.source === 'module';
      saveButton = h('button', { type: 'button', class: 'primary', disabled: true }, r.source === 'sample' ? 'このモジュール用に保存' : '保存してコミット');
      revertButton = h('button', { type: 'button', disabled: true }, '元に戻す');
      const keep = h('button', { type: 'button', title: 'この登録を、このPCのプリセットとして保存します（ほかのモジュールでも使えるように）' }, 'プリセットにする');
      saveButton.addEventListener('click', () => emit('save', edited()));
      revertButton.addEventListener('click', revert);
      keep.addEventListener('click', () => emit('to_preset', { name: r.name }));
      const buttons = [saveButton, revertButton, keep];
      if (removable) {
        const remove = h('button', { type: 'button', class: 'danger-text' }, samples.has(r.name) ? 'プリセットに戻す' : '消す');
        remove.addEventListener('click', () => emit('remove', { name: r.name }));
        buttons.push(remove);
      }
      const badges = [badge(r.source === 'sample' ? 'プリセットのまま' : SOURCES[r.source] || r.source, 'quiet')];
      if (r.human_start) badges.push(badge('人が起動', 'top'));
      if (r.pending) badges.push(badge('まだ効いていない（取り込まれると効く）', 'warn'));
      const extra = r.source === 'sample'
        ? [note('プリセット（ECOBuild の見本）のままです。直して保存すると、このモジュール用に上書きします（プリセットはそのまま）。')] : [];
      const marksNote = h('p', { class: 'note' }, 'エージェントが ECOBuild でできることは、ここで渡すツールだけです。印：', badge('変える', 'warn'), ' 作業空間のファイルを変える　',
        badge('ブランチを変える', 'warn'), ' コミット・push・提出（タスクの持ち主だけ）　', badge('子を扱う', 'top'), ' 子のエージェント');
      return [
        head(r.title, r.name, badges, extra, buttons),
        section('基本', h('div', { class: 'grid' }, field('表示名', title), h('label', { class: 'field' }, 'モデル', model, modelOther))),
        section('起動', h('label', { class: 'check' }, humanStart, ' 人が手で起動できる（作業空間の「エージェント」の ＋ に出る）')),
        section('文書', note('起動のときにエージェントに渡す、この役の文（何者か・何をするか・決まり）。'), body),
        section('最初の発言', firstPrompt),
        section('改善のループと止める条件',
          note('評価 → 直す → 評価し直す を回し、良くなった変更だけを残す。決めたものは起動のときの文に入ります。0 は「決めない／上限なし」。ターン数・費用の上限は、ほかのエージェントが起動したとき（画面なし）に ECOBuild が止めます。'),
          h('div', { class: 'grid' }, field('評価のしかた', evaluation), field('教訓の記録先（モジュールの中のフォルダー）', lessons)),
          h('div', { class: 'grid' }, field('評価し直す回数の上限', maxRounds, 'narrow'), field('ターン数の上限', maxTurns, 'narrow'), field('費用の上限（ドル）', maxCost, 'narrow'))),
        section('渡すツール', marksNote, h('div', { class: 'radio' }, toolsAllLabel, toolsPickLabel), quick, toolsBox),
        section('使えるスキル',
          note('スキルは、必要なときにエージェントが読む手順・知識です（ツールは増えません）。左の「スキル」で足し・直します。エージェントに渡るのは、取り込まれたスキルのうちここで選んだものです。'),
          h('div', { class: 'radio' }, skillsAllLabel, skillsPickLabel), skillsBox),
        section('起動してよい子',
          note('この役が子として起動できるエージェントを、このモジュールのエージェントから選びます（左の一覧と同じ。足すと、ここにも出ます）。この役より強い（渡すツールが多い）ものは選べません。'),
          h('div', { class: 'children' }, ...childRows), field('同時に持てる子の数', maxChildren, 'narrow')),
      ];
    };

    const drawn = sel.kind === 'role' ? drawRole() : sel.kind === 'skill' ? drawSkill() : drawCommon();
    main.append(guard, ...drawn);
    // 同じものを描き直すとき（保存の後など）は、スクロールの位置を残す
    const top = state.mainOf === keyOf(sel) && state.main ? state.main.scrollTop : 0;
    const sideTop = state.side ? state.side.scrollTop : 0;
    root.replaceChildren(h('div', { class: 'ae' }, side, main));
    main.scrollTop = top;
    side.scrollTop = sideTop;
    state.main = main;
    state.side = side;
    state.mainOf = keyOf(sel);
  },
};
