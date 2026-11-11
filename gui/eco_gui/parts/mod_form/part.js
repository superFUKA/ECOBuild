// 部品「入力の窓（フォーム）」。今までの GUI のダイアログ（ECO.form）と同じ見た目・同じ欄の種類。
// 打った値は state に持つ（読み直しで描き直しても消えない）。決めるときに、全部の欄の値をまとめて出す。
export default {
  render(root, props, { h, emit, state, redraw }) {
    state.values = state.values || {};
    const fields = props.fields.filter((f) => f.type !== 'note' && f.name);
    const choices = (f) => {
      if (Array.isArray(f.options)) return f.options.map((o) => ({ value: String(o.value), label: o.label || String(o.value), note: o.note || '' }));
      const source = (f.source === 'more' ? props.more : props.rows) || [];
      const where = f.where || {};
      return source.filter((row) => Object.keys(where).every((key) => (row[key] ?? null) === where[key]))
        .map((row) => ({ value: String(row[f.value_key || 'name']), label: String(row[f.label_key || f.value_key || 'name']),
          note: f.note_key && row[f.note_key] != null ? String(Array.isArray(row[f.note_key]) ? row[f.note_key].join('→') : row[f.note_key]) : '' }));
    };
    const list = (f, value) => Array.isArray(value) ? value.map(String)
      : typeof value === 'string' && value !== '' ? value.split(f.join || ',').map((item) => item.trim()).filter(Boolean) : [];
    // 今の値：打ったもの、なければ初めの値
    const current = (f) => {
      if (f.name in state.values) return state.values[f.name];
      const first = props.initial[f.name];
      if (f.type === 'checks') return list(f, first);
      if (f.type === 'toggle') return first === true || (f.on !== undefined && first === f.on);
      return first === null || first === undefined ? '' : String(first);
    };
    // 出す値：コマンドが受ける形に（つないだ文字・on/off）
    const given = (f) => {
      const value = current(f);
      if (f.type === 'checks') {
        if (f.join === undefined) return value;
        return value.length ? value.join(f.join) : (f.empty || '');
      }
      if (f.type === 'toggle') return f.on !== undefined ? (value ? f.on : f.off) : value;
      if (f.type === 'select') {  // 選べるものにない初めの値は、いちばん上のもの（見えているものを出す）
        const options = choices(f);
        if (f.none_label === undefined && options.length && !options.some((o) => o.value === value)) return options[0].value;
        return value;
      }
      return String(value).trim();
    };

    const form = h('form', { class: 'form' });
    if (props.title) form.append(h('h2', {}, props.title + (props.subject ? '：' + props.subject : '')));
    if (props.intro) form.append(h('p', { class: 'intro' }, props.intro));
    if (props.detail) form.append(h('p', { class: 'intro' }, props.detail));
    if (props.error) form.append(h('p', { role: 'alert' }, props.error));
    for (const f of props.fields) {
      if (f.type === 'note') {
        form.append(h('p', { class: 'intro' }, f.label));
        continue;
      }
      const value = current(f);
      const hint = f.hint ? h('small', { class: 'help' }, f.hint) : '';
      const missing = state.missing === f.name ? h('small', { class: 'error' }, f.type === 'checks' ? '1つ以上選んでください。' : '入れてください。') : '';
      if (f.type === 'toggle') {
        const box = h('input', { type: 'checkbox' });
        box.checked = value === true;
        box.addEventListener('change', () => { state.values[f.name] = box.checked; });
        form.append(h('label', { class: 'check' }, box, h('span', {}, f.label)), hint);
      } else if (f.type === 'checks') {
        const group = h('div', { class: 'field', role: 'group', 'aria-label': f.label }, h('span', {}, f.label));
        const options = choices(f);
        if (options.length === 0) group.append(h('small', { class: 'help' }, props.loading ? '読み込み中…' : f.empty_text || '選べるものがありません。'));
        for (const option of options) {
          const box = h('input', { type: 'checkbox' });
          box.checked = value.includes(option.value);
          box.addEventListener('change', () => {
            const now = current(f).filter((item) => item !== option.value);
            if (box.checked) now.push(option.value);
            // 選べるものの順に並べる（手順の順・一覧の順）
            state.values[f.name] = f.ordered === false ? now : options.map((o) => o.value).filter((item) => now.includes(item));
            if (state.missing === f.name) { state.missing = ''; redraw(); }
          });
          group.append(h('label', { class: 'check' }, box, h('span', {}, option.label, option.note ? h('small', { class: 'help' }, '（' + option.note + '）') : '')));
        }
        group.append(hint, missing);
        form.append(group);
      } else if (f.type === 'select') {
        const select = h('select', {});
        const options = choices(f);
        if (f.none_label !== undefined) select.append(h('option', { value: '' }, f.none_label));
        for (const option of options) {
          const item = h('option', { value: option.value }, option.label + (option.note ? '（' + option.note + '）' : ''));
          if (option.value === value) item.selected = true;
          select.append(item);
        }
        if (options.length === 0 && f.none_label === undefined) select.append(h('option', { value: '' }, props.loading ? '読み込み中…' : f.empty_text || '（選べるものがありません）'));
        select.addEventListener('change', () => { state.values[f.name] = select.value; });
        form.append(h('label', { class: 'field' }, f.label, select, hint, missing));
      } else {
        const input = h('input', { type: 'text', placeholder: f.placeholder || '', spellcheck: 'false', autocomplete: 'off' });
        input.value = value;
        input.addEventListener('input', () => { state.values[f.name] = input.value; });
        form.append(h('label', { class: 'field' }, f.label, input, hint, missing));
      }
    }
    const cancel = h('button', { type: 'button' }, 'やめる');
    cancel.addEventListener('click', () => emit('cancelled', {}));
    const ok = h('button', { type: 'submit', class: props.danger ? 'danger' : 'primary' }, props.ok);
    form.append(h('div', { class: 'actions' }, cancel, ok));
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const values = {};
      for (const f of fields) values[f.name] = given(f);
      const lacking = fields.find((f) => f.required && (values[f.name] === '' || values[f.name] === (f.empty || '') && f.type === 'checks'
        || Array.isArray(values[f.name]) && values[f.name].length === 0));
      if (lacking) {
        state.missing = lacking.name;
        return redraw();
      }
      emit('submitted', { values });
    });
    root.replaceChildren(form);
  },
};
