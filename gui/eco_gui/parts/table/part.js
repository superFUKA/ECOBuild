// 部品「表」。値の言い換え（labels）は見せ方だけ。行のボタンは action を出す。
// 列の key は、行の項目の名前か、入れ子の値への道筋（submission.base）。
// 値の見せ方：ないもの（null）は空、真偽は「はい」「いいえ」、並びは「、」でつなぐ、組は「名前：値」を並べる。
// labels に言い換えがあれば、そちらを使う（真偽は true・false、ないものは空の文字で引く）。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const has = (value, name) => value !== null && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, name);
    const pick = (row, path) => {
      if (has(row, path)) return row[path];  // 名前そのものの項目が先
      let value = row;
      for (const step of String(path).split('.')) {
        if (!has(value, step)) return undefined;
        value = value[step];
      }
      return value;
    };
    const plain = (value) => {
      if (value === null || value === undefined) return '';
      if (value === true) return 'はい';
      if (value === false) return 'いいえ';
      if (Array.isArray(value)) return value.map(plain).filter((text) => text !== '').join('、');
      if (typeof value === 'object') {
        return Object.keys(value).map((name) => [name, plain(value[name])]).filter((pair) => pair[1] !== '')
          .map((pair) => pair[0] + '：' + pair[1]).join('、');
      }
      return String(value);
    };
    const show = (column, value) => {
      const names = props.labels[column.key] || {};
      const named = (item) => {
        const raw = item === null || item === undefined ? '' : typeof item === 'object' ? null : String(item);
        return raw !== null && raw in names ? names[raw] : plain(item);
      };
      if (Array.isArray(value)) {
        const whole = value.join('、');  // 並びをつないだ文字の言い換えが先（今までの書き方）
        return whole in names ? names[whole] : value.map(named).filter((text) => text !== '').join('、');
      }
      return named(value);
    };
    // 色の印（tones）：値そのもの（真偽は true・false、ないものは空の文字）で色を引く。文字は言い換えた後のもの
    const cellOf = (column, value) => {
      const text = show(column, value);
      const tones = props.tones[column.key];
      const raw = value === null || value === undefined ? '' : typeof value === 'object' ? null : String(value);
      const tone = tones && raw !== null && raw in tones ? tones[raw] : '';
      if (!tone || text === '') return h('td', {}, text);
      return h('td', {}, h('span', { class: tone === 'plain' ? 'pill' : 'pill ' + tone }, text));
    };
    const head = h('tr', {}, ...props.columns.map((column) => h('th', {}, column.label)));
    if (props.numbered) head.prepend(h('th', {}, '順'));
    if (props.actions.length) head.append(h('th', {}, ''));
    const body = h('tbody', {});
    props.rows.forEach((row, index) => {
      const line = h('tr', {}, ...props.columns.map((column) => cellOf(column, pick(row, column.key))));
      if (props.numbered) line.prepend(h('td', { class: 'dim' }, String(index + 1)));
      if (props.actions.length) {
        const buttons = props.actions.map((action) => {
          const button = h('button', { type: 'button', class: action.primary ? 'small primary' : action.danger ? 'small danger' : 'small' }, action.label);
          button.addEventListener('click', () => emit('action', { id: String(pick(row, props.key)), action: action.name }));
          return button;
        });
        line.append(h('td', { class: 'actions' }, h('div', { class: 'row' }, ...buttons)));
      }
      body.append(line);
    });
    root.replaceChildren(h('table', {}, h('thead', {}, head), body));
  },
};
