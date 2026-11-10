// 部品「表」。値の言い換え（labels）は見せ方だけ。行のボタンは action を出す。
// 列の key は、行の項目の名前か、入れ子の値への道筋（submission.base）。
// 値の見せ方：ないもの（null）は空、真偽は「はい」「いいえ」、並びは「、」でつなぐ、組は「名前：値」を並べる。
// labels に言い換えがあれば、そちらを使う（真偽は true・false、ないものは空の文字で引く）。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    if (props.loading && props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, '読み込み中…'));
    if (props.rows.length === 0) return root.replaceChildren(h('p', { role: 'status' }, props.empty_text));
    const cell = 'text-align:left;padding:.35rem .6rem;border-bottom:1px solid var(--gf-border)';
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
    const head = h('tr', {}, ...props.columns.map((column) => h('th', { style: cell }, column.label)));
    if (props.numbered) head.prepend(h('th', { style: cell }, '順'));
    if (props.actions.length) head.append(h('th', { style: cell }, ''));
    const body = h('tbody', {});
    props.rows.forEach((row, index) => {
      const line = h('tr', {}, ...props.columns.map((column) => h('td', { style: cell }, show(column, pick(row, column.key)))));
      if (props.numbered) line.prepend(h('td', { style: cell }, String(index + 1)));
      if (props.actions.length) {
        const buttons = props.actions.map((action) => {
          const button = h('button', { type: 'button' }, action.label);
          button.addEventListener('click', () => emit('action', { id: String(pick(row, props.key)), action: action.name }));
          return button;
        });
        line.append(h('td', { style: cell }, h('div', { class: 'row' }, ...buttons)));
      }
      body.append(line);
    });
    root.replaceChildren(h('table', { style: 'border-collapse:collapse;width:100%' }, h('thead', {}, head), body));
  },
};
