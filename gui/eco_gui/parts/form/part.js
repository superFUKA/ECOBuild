// 部品「入力の窓（フォーム）」。今までの GUI のダイアログ（static/common.js の ECO.form）と同じ見た目・同じ欄の種類。
// ここでするのは見せ方だけ：欄の出し分け・初めの値・必須の確かめ・値の形。値をまとめて出すだけで、何が起きるかは知らない。
// 打った値は state に持つ（読んだ値が後から届いて描き直しても、打ったものは消えない）。
const lookup = (data, path) => String(path || '').split('.').filter(Boolean)
  .reduce((at, key) => (at === null || at === undefined ? undefined : at[key]), data);
const blank = (value) => value === undefined || value === null || value === '';
const same = (a, b) => (a ?? null) === (b ?? null);
const LAYOUT = new Set(['section', 'note']);
const LISTS = (f) => f.type === 'checks' || Boolean(f.multiple);

export default {
  render(root, props, { h, emit, state }) {
    const fields = props.fields || [];
    state.touched = state.touched || {};   // 触った欄（読んだ値が後から届いても、打ったものを残す）
    state.values = state.values || {};
    state.open = state.open || {};         // 畳める節の開閉

    // 読んだ今の値のある場所：at がなければ values そのもの。あれば、その名前をたどった先（なければ、今の値はない）
    const at = props.at === null || props.at === undefined ? [] : [].concat(props.at);
    const base = at.some((key) => key === '') ? undefined
      : at.reduce((data, key) => (data === null || data === undefined ? undefined : data[key]), props.values);
    const known = (path) => { const given = lookup(props.vars || {}, path); return given !== undefined ? given : lookup(base, path); };
    // 文の中の {道筋} を、その値に（空なら、中身のないかっこごと消す）
    const fill = (text) => String(text ?? '').replace(/\{([\w.]+)\}/g, (_, path) => {
      const value = known(path);
      return blank(value) ? '' : Array.isArray(value) ? value.join('、') : String(value);
    }).replace(/（）|\(\)/g, '');

    const optionsOf = (f) => {
      if (!f.options_from) return (f.options || []).map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? o.value ?? ''), help: o.help || '' }));
      const from = f.options_from, key = from.value || 'name', where = from.where || {};
      const source = (from.source === 'more' ? props.more : props.rows) || [];
      return source.filter((row) => Object.keys(where).every((name) => same(row[name], where[name]))).map((row) => {
        const value = String(row[key] ?? ''), label = String(row[from.label || key] ?? '');
        const notes = [].concat(from.note || []).map((name) => {
          const raw = row[name], text = Array.isArray(raw) ? raw.join('→') : String(raw ?? '');
          return (from.note_labels || {})[text] || text;
        }).filter((text) => text && text !== label);
        return { value, label: notes.length ? `${label}（${notes.join('・')}）` : label, help: '' };
      });
    };
    const listOf = (f, raw) => (Array.isArray(raw) ? raw.map(String)
      : typeof raw === 'string' && raw !== '' ? raw.split(f.join || ',').map((item) => item.trim()).filter(Boolean) : []);
    // 初めの値：読んだ今の値 → initial → 欄の value → その種類の既定
    const first = (f) => {
      const read = f.value_from ? known(f.value_from) : base && typeof base === 'object' ? base[f.name] : undefined;
      if (f.type === 'checkbox') {
        if (f.on_value !== undefined) return read === f.on_value;
        if (f.off_value !== undefined) return read !== f.off_value;
      }
      const raw = !blank(read) ? read : !blank((props.initial || {})[f.name]) ? props.initial[f.name] : f.value;
      if (f.type === 'checkbox') return raw === true || (f.on !== undefined && raw === f.on);
      if (LISTS(f)) return listOf(f, raw);
      if (Array.isArray(raw)) return raw.join(f.join || ', ');
      return blank(raw) ? '' : raw;
    };
    const valueOf = (f) => {
      if (state.touched[f.name]) return state.values[f.name];
      const value = first(f);
      if (f.type !== 'select' && f.type !== 'radio') return value;
      const options = optionsOf(f), text = String(value);
      if (options.some((option) => option.value === text)) return text;
      // 選べるものにない値：読んだ一覧から選ぶ欄・空の値は、見えているもの（「選ばない」か先頭）。決まった選択肢の欄は、今の値のまま見せる
      if (f.options_from || text === '') return f.type === 'select' && f.none_label !== undefined ? '' : options.length ? options[0].value : '';
      return text;
    };
    const named = fields.filter((f) => f.name && !LAYOUT.has(f.type));
    const byName = Object.fromEntries(named.map((f) => [f.name, f]));
    const matches = (map) => Object.entries(map).every(([name, want]) => {
      const now = byName[name] ? valueOf(byName[name]) : known(name);
      return Array.isArray(want) ? want.some((one) => same(now, one)) : same(now, want);
    });
    const listed = (f) => (f.list_from ? [].concat(known(f.list_from) || []) : []);
    // 並べるもの（list_from）のある文は、並びが空なら出さない（衝突するファイルがないときの警告など）。
    // empty_text があれば、読み終えてから、代わりにその文を出す
    const visible = (item) => (!item.show_if || matches(item.show_if)) && !(item.hide_if && matches(item.hide_if))
      && !(item.type === 'note' && item.list_from && !listed(item).length && !(item.empty_text && !props.loading && base !== undefined && base !== null));
    const empty = (f) => { const value = valueOf(f); return Array.isArray(value) ? value.every((item) => !String(item).trim()) : String(value ?? '').trim() === ''; };
    const lacking = () => named.find((f) => f.required && visible(f) && empty(f) && !(f.empty_uses && byName[f.empty_uses] && visible(byName[f.empty_uses])));

    const holders = [];   // {item, nodes}：出し分けのために覚える（欄・節・表の行）
    const rows = [];      // 横に並べた行（中の欄が全部隠れたら、行も隠す）
    const error = h('p', { class: 'error', role: 'alert' }, state.error || props.problem || props.error || '');
    const refresh = () => {
      for (const { item, nodes } of holders) for (const node of nodes) node.hidden = !visible(item);
      for (const row of rows) row.hidden = [...row.children].every((child) => child.hidden);
    };
    const set = (f, value) => {
      state.touched[f.name] = true;
      state.values[f.name] = value;
      if (state.error) { state.error = ''; error.textContent = props.problem || props.error || ''; }
      refresh();
    };

    const control = (f) => {
      const now = valueOf(f);
      const help = f.help ? h('small', { class: 'help' }, fill(f.help)) : '';
      const title = f.required ? h('span', {}, fill(f.label), h('span', { class: 'req', 'aria-hidden': 'true' }, '*')) : fill(f.label);
      if (f.type === 'checkbox') {
        const input = h('input', { type: 'checkbox' });
        input.checked = now === true;
        input.addEventListener('change', () => set(f, input.checked));
        return h('div', { class: 'f' }, h('label', { class: f.strong ? 'check strong' : 'check' }, input, h('span', {}, fill(f.label))), help);
      }
      if (f.type === 'radio') {
        const box = h('fieldset', { class: f.inline ? 'f inline' : 'f' }, h('legend', {}, title));
        for (const option of optionsOf(f)) {
          const input = h('input', { type: 'radio', name: f.name, value: option.value });
          input.checked = option.value === now;
          input.addEventListener('change', () => { if (input.checked) set(f, option.value); });
          box.append(h('label', {}, input, h('span', {}, h('strong', {}, option.label), option.help ? h('small', {}, option.help) : '')));
        }
        if (help) box.append(help);
        return box;
      }
      if (f.type === 'checks') {
        const options = optionsOf(f), list = h('div', {});
        for (const option of options) {
          const input = h('input', { type: 'checkbox', value: option.value });
          input.checked = now.includes(option.value);
          input.addEventListener('change', () => {
            const picked = valueOf(f).filter((item) => item !== option.value);
            if (input.checked) picked.push(option.value);
            set(f, options.map((o) => o.value).filter((item) => picked.includes(item)));   // 選べるものの順に（手順の順・一覧の順）
          });
          list.append(h('label', {}, input, h('span', {}, option.label)));
        }
        if (!options.length) list.append(h('small', { class: 'help' }, props.loading ? '読み込み中…' : f.empty_text || '選べるものがありません。'));
        const box = h('fieldset', { class: 'f checks' }, h('legend', {}, title), list);
        if (help) box.append(help);
        return box;
      }
      if (f.multiple) {   // いくつも入れる欄：＋ で足し、× で消す
        const list = h('div', { class: 'multi' });
        const items = now.length ? [...now] : [''];
        const draw = (focus) => {
          list.replaceChildren(...items.map((text, index) => {
            const input = h('input', { type: 'text', placeholder: fill(f.placeholder), autocomplete: 'off', 'aria-label': fill(f.label) });
            input.value = text;
            input.addEventListener('input', () => { items[index] = input.value; set(f, [...items]); });
            const button = index === 0 ? h('button', { type: 'button', title: `${fill(f.label)}の欄を足す`, 'aria-label': `${fill(f.label)}の欄を足す` }, '＋')
              : h('button', { type: 'button', title: 'この欄を消す', 'aria-label': 'この欄を消す' }, '×');
            button.addEventListener('click', () => {
              if (index === 0) items.push(''); else items.splice(index, 1);
              set(f, [...items]);
              draw(index === 0 ? items.length - 1 : Math.min(index, items.length - 1));
            });
            return h('div', { class: 'multi-item' }, input, button);
          }));
          if (focus !== undefined) list.children[focus].querySelector('input').focus();
        };
        draw();
        return h('div', { class: 'f field' }, title, list, help);
      }
      let input;
      if (f.type === 'select') {
        const options = optionsOf(f);
        if (String(now) !== '' && !options.some((option) => option.value === String(now))) options.push({ value: String(now), label: String(now) });
        input = h('select', {});
        if (f.none_label !== undefined) input.append(h('option', { value: '' }, fill(f.none_label)));
        for (const option of options) input.append(h('option', { value: option.value }, option.label));
        if (!options.length && f.none_label === undefined) input.append(h('option', { value: '' }, props.loading ? '読み込み中…' : f.empty_text || '（選べるものがありません）'));
        input.value = String(now);
        input.addEventListener('change', () => set(f, input.value));
      } else if (f.type === 'textarea') {
        input = h('textarea', { rows: String(f.rows || 4), placeholder: fill(f.placeholder), spellcheck: 'false' });
        input.value = String(now);
        input.addEventListener('input', () => set(f, input.value));
      } else {
        input = h('input', { type: f.type === 'number' || f.type === 'date' ? f.type : 'text', placeholder: fill(f.placeholder), autocomplete: 'off', spellcheck: 'false' });
        if (f.type === 'number') { input.min = String(f.min ?? 0); if (f.step !== undefined) input.step = String(f.step); }
        input.value = String(now);
        input.addEventListener('input', () => set(f, input.value));
      }
      return h('label', { class: 'f field' }, title, input, help);
    };
    const note = (f) => {
      const names = listed(f);
      if (f.list_from && !names.length) return h('div', { class: 'f intro' }, fill(f.empty_text));
      const list = names.length ? h('ul', {}, ...names.map((name) => h('li', {}, String(name)))) : '';
      return f.tone ? h('div', { class: `f banner ${f.tone === 'warn' ? '' : f.tone}`.trim(), role: f.tone === 'bad' ? 'alert' : 'note' }, h('div', {}, fill(f.label), list))
        : h('div', { class: 'f intro' }, fill(f.label), list);
    };

    const form = h('form', { class: 'eco-form', novalidate: '' });
    const heading = fill(props.title) + (props.subject ? '：' + props.subject : '');
    if (heading) form.append(h('h2', {}, heading));
    if (props.intro) form.append(h('p', { class: 'intro' }, fill(props.intro)));
    if (props.detail) form.append(h('p', { class: 'intro' }, fill(props.detail)));
    if (props.loading) form.append(h('p', { class: 'intro', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…'));
    if ((props.outcome || []).length) {
      const table = h('dl', { class: 'outcome' });
      for (const row of props.outcome) {
        const nodes = [h('dt', {}, fill(row.label)), h('dd', {}, fill(row.text))];
        table.append(...nodes);
        holders.push({ item: row, nodes });
      }
      form.append(table);
    }
    let into = form, row = null, rowName = '';
    for (const f of fields) {
      if (f.type === 'section') {
        row = null; rowName = '';
        if (f.end) { into = form; continue; }
        const title = [fill(f.label), f.note ? h('small', {}, fill(f.note)) : ''];
        if (f.collapsed === undefined) {
          into = h('div', { class: 'section' }, h('h3', {}, ...title));
        } else {
          const key = String(f.label), section = h('details', { class: 'section' }, h('summary', {}, ...title));
          section.open = key in state.open ? state.open[key] : f.open === true || !f.collapsed;
          section.addEventListener('toggle', () => { state.open[key] = section.open; });
          into = section;
        }
        if (f.help) into.append(h('p', { class: 'help' }, fill(f.help)));
        form.append(into);
        holders.push({ item: f, nodes: [into] });
        continue;
      }
      const node = f.type === 'note' ? note(f) : control(f);
      holders.push({ item: f, nodes: [node] });
      if (f.row) {
        if (f.row !== rowName) { row = h('div', { class: 'row' }); rowName = f.row; rows.push(row); into.append(row); }
        row.append(node);
        row.style.setProperty('--cols', String(row.children.length));
      } else {
        row = null; rowName = '';
        into.append(node);
      }
    }

    const submit = () => {
      const missing = lacking();
      if (missing) {   // 誤りは窓の中に出す（入れた値は残る）
        const label = fill(missing.label).replace(/（[^（）]*）$/, '');
        state.error = missing.type === 'checks' ? `${label}を、1つ以上選んでください。` : `${label}を入力してください。`;
        error.textContent = state.error;
        return;
      }
      const values = {};
      for (const f of named) {
        if (!visible(f)) continue;
        let value = valueOf(f);
        if (f.type === 'checkbox') {
          if (f.inverse) values[f.inverse] = !value;
          if (f.on !== undefined) value = value ? f.on : f.off;
        } else if (LISTS(f)) {
          value = value.map((item) => String(item).trim()).filter(Boolean);
          if (f.join !== undefined) value = value.length ? value.join(f.join) : f.empty || '';
        } else {
          value = String(value ?? '').trim();
          if (value === '' && f.empty_uses && byName[f.empty_uses] && visible(byName[f.empty_uses])) value = String(valueOf(byName[f.empty_uses]) ?? '');
          if (f.type === 'number' && value !== '') value = Number(value);
        }
        values[f.name] = value;
      }
      emit('submitted', { values });
    };
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => emit('cancelled', {}));
    const ok = h('button', { type: 'submit', class: props.danger ? 'danger' : 'primary' }, fill(props.ok) || 'OK');
    form.append(error, h('div', { class: props.sticky ? 'actions sticky' : 'actions' }, cancel, ok));
    form.addEventListener('submit', (event) => { event.preventDefault(); submit(); });
    form.addEventListener('keydown', (event) => {   // Ctrl+Enter：どの欄にいても決める（本文の欄の中でも）
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); submit(); }
    });
    refresh();
    root.replaceChildren(form);
  },
};
