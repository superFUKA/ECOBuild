// 部品「入力の窓（フォーム）」。今までの GUI のダイアログ（ECO.form）と同じ見た目・同じ並び。
// 欄の出し分け（show_if）・初めの値・必須の欄が空なら押せない、は見せ方。値をまとめて出すだけで、何が起きるかは知らない。
const lookup = (data, path) => String(path || '').split('.').filter(Boolean).reduce((at, key) => (at === null || at === undefined ? at : at[key]), data);

export default {
  render(root, props, { h, emit, state }) {
    const fields = props.fields || [];
    const rows = props.rows || [];
    state.touched = state.touched || {};   // 触った欄（読んだ値が後から届いても、打ったものを残す）
    state.values = state.values || {};
    const optionsOf = (f) => {
      if (!f.options_from) return f.options || [];
      const from = f.options_from;
      const key = from.value || 'name';
      return rows.map((row) => {
        const label = String(row[from.label || key] ?? '');
        const noted = from.note ? String(row[from.note] ?? '') : '';
        const notes = [String(row[key] ?? ''), (from.note_labels || {})[noted] || noted].filter((x) => x && x !== label);
        return { value: String(row[key] ?? ''), label: from.note && notes.length ? `${label}（${notes.join('・')}）` : label, help: '' };
      });
    };
    const initial = (f) => {
      const read = props.values ? (f.value_from ? lookup(props.values, f.value_from) : props.values[f.name]) : undefined;
      if (read !== undefined && read !== null) return Array.isArray(read) ? read.join(f.join || ', ') : read;
      if (f.value !== undefined && f.value !== null) return f.value;
      if (f.type === 'checkbox') return false;
      if (f.type === 'select' || f.type === 'radio') { const first = optionsOf(f)[0]; return first ? first.value : ''; }
      return '';
    };
    const valueOf = (f) => (state.touched[f.name] ? state.values[f.name] : initial(f));
    const named = fields.filter((f) => f.name && f.type !== 'section' && f.type !== 'note');
    const byName = Object.fromEntries(named.map((f) => [f.name, f]));
    const visible = (f) => !f.show_if || Object.entries(f.show_if).every(([name, want]) => {
      const other = byName[name];
      const now = other ? valueOf(other) : undefined;
      return Array.isArray(want) ? want.includes(now) : now === want;
    });
    const holders = [];   // {field, box}：出し分けのために覚える
    const error = h('p', { class: 'error', role: 'alert' }, props.error || '');
    const okButton = h('button', { type: 'submit', class: props.danger ? 'danger' : 'primary' }, props.ok || 'OK');

    const refresh = () => {
      for (const { field, box } of holders) box.hidden = !visible(field);
      okButton.disabled = named.some((f) => f.required && visible(f)
        && String(valueOf(f) ?? '').trim() === '' && !(f.empty_uses && byName[f.empty_uses] && visible(byName[f.empty_uses])));
    };
    const set = (f, value) => { state.touched[f.name] = true; state.values[f.name] = value; refresh(); };

    const control = (f) => {
      const now = valueOf(f);
      const help = f.help ? h('span', { class: 'help' }, f.help) : null;
      if (f.type === 'note') return h('p', { class: 'intro' }, f.label || '');
      if (f.type === 'checkbox') {
        const input = h('input', { type: 'checkbox', checked: now === true });
        input.addEventListener('change', () => set(f, input.checked));
        const box = h('label', { class: 'check' }, input, h('span', {}, f.label || ''));
        return help ? h('div', {}, box, help) : box;
      }
      if (f.type === 'radio') {
        const box = h('fieldset', {}, h('legend', {}, f.label || ''));
        for (const option of optionsOf(f)) {
          const input = h('input', { type: 'radio', name: f.name, value: option.value, checked: option.value === now });
          input.addEventListener('change', () => { if (input.checked) set(f, option.value); });
          const text = h('span', {}, option.label);
          if (option.help) text.append(h('small', {}, option.help));
          box.append(h('label', {}, input, text));
        }
        return box;
      }
      let input;
      if (f.type === 'select') {
        input = h('select', {}, ...optionsOf(f).map((option) => h('option', { value: option.value }, option.label)));
        input.value = String(now ?? '');
        input.addEventListener('change', () => set(f, input.value));
      } else if (f.type === 'textarea') {
        input = h('textarea', { rows: f.rows || 4, placeholder: f.placeholder || '', spellcheck: false });
        input.value = String(now ?? '');
        input.addEventListener('input', () => set(f, input.value));
      } else {
        input = h('input', { type: f.type === 'number' ? 'number' : 'text', value: String(now ?? ''), placeholder: f.placeholder || '' });
        if (f.type === 'number') input.min = String(f.min ?? 0);
        input.addEventListener('input', () => set(f, input.value));
      }
      const box = h('label', { class: 'field' }, f.label || '', input);
      if (help) box.append(help);
      return box;
    };

    const form = h('form', { class: 'form' }, h('h2', {}, props.title));
    if (props.intro) form.append(h('p', { class: 'intro' }, props.intro));
    let into = form;
    for (const f of fields) {
      if (f.type === 'section') {
        if (f.collapsed === undefined) {
          into = h('div', { class: 'section' }, h('h3', {}, f.label || ''));
        } else {
          const key = `#${f.label}`;
          const section = h('details', { class: 'section', open: state.touched[key] ? state.values[key] : !f.collapsed }, h('summary', {}, f.label || ''));
          section.addEventListener('toggle', () => { state.touched[key] = true; state.values[key] = section.open; });
          into = section;
        }
        if (f.help) into.append(h('p', { class: 'help' }, f.help));
        form.append(into);
        holders.push({ field: f, box: into });
        continue;
      }
      const box = control(f);
      holders.push({ field: f, box });
      into.append(box);
    }
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => emit('cancelled', {}));
    form.append(error, h('div', { class: 'actions' }, cancel, okButton));
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (okButton.disabled) return;
      const values = {};
      for (const f of named) {
        if (!visible(f)) continue;
        let value = valueOf(f);
        if (typeof value === 'string') value = value.trim();
        if (f.type === 'number' && value !== '') value = Number(value);
        if ((value === '' || value === undefined) && f.empty_uses && byName[f.empty_uses] && visible(byName[f.empty_uses])) value = valueOf(byName[f.empty_uses]);
        values[f.name] = value;
      }
      emit('submitted', { values });
    });
    refresh();
    root.replaceChildren(form);
  },
};
