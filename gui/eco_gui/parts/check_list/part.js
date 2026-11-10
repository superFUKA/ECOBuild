// 部品「チェックで選ぶ一覧」。今の並び（items）が変わって届いたときだけ、その並びから付け直す
// （読み直しで同じ並びが届いても、付け外しの途中は残す）。パターンに当てはまる名前は、付いたものとして見せる（外せない）。
const matcher = (pattern) => {
  const source = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
  return new RegExp(`^${source}$`);
};
const isPattern = (text) => /[*?]/.test(text);

export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const arrived = JSON.stringify(props.items ?? []);
    if (root.arrived !== arrived) {
      root.arrived = arrived;
      root.chosen = [...(props.items ?? [])];
    }
    const names = props.rows.map((row) => String(row[props.value_key] ?? ''));
    const line = 'display:inline-flex;flex-direction:row;gap:.3rem;align-items:center;margin:0';

    const draw = () => {
      const change = (name, on) => {
        root.chosen = root.chosen.filter((item) => item !== name);
        if (on) root.chosen.push(name);
        emit('changed', { items: [...root.chosen], text: root.chosen.join(',') });
        draw();
      };
      const check = (name, text, hint, covered) => {
        const input = h('input', { type: 'checkbox', checked: covered || root.chosen.includes(name) });
        if (covered) input.disabled = true;
        input.addEventListener('change', () => change(name, input.checked));
        const label = h('label', { style: line }, input, text);
        if (hint) label.title = hint;
        return label;
      };
      const wide = root.chosen.filter(isPattern).map(matcher);
      const top = [];
      if (props.patterns) top.push(check('*', 'すべて（*）', '今あるものも、これから足すものも', false));
      for (const item of root.chosen) {
        if (item === '*' || names.includes(item)) continue;
        top.push(check(item, isPattern(item) ? `${item}（パターン）` : `${item}（一覧にない）`, '', false));
      }
      const list = props.rows.map((row) => {
        const name = String(row[props.value_key] ?? '');
        const text = props.label_key && row[props.label_key] ? `${name}（${row[props.label_key]}）` : name;
        const covered = !root.chosen.includes(name) && wide.some((pattern) => pattern.test(name));
        return check(name, text, props.hint_key ? String(row[props.hint_key] ?? '') : '', covered);
      });
      const box = h('div', { style: 'display:flex;flex-direction:column;gap:.3rem' }, h('span', {}, props.title));
      if (top.length) box.append(h('div', { style: 'display:flex;flex-wrap:wrap;gap:.2rem 1rem' }, ...top));
      if (props.loading && props.rows.length === 0) {
        box.append(h('p', { role: 'status', style: 'margin:0' }, '読み込み中…'));
      } else if (list.length) {
        box.append(h('div', { style: 'display:flex;flex-wrap:wrap;gap:.2rem 1rem;max-height:9rem;overflow:auto;'
          + 'border:1px solid var(--gf-border);padding:.4rem .6rem' }, ...list));
      }
      if (props.patterns) {
        const input = h('input', { type: 'text', placeholder: '例：task_*', 'aria-label': `${props.title}：足すパターン`, style: 'max-width:12rem' });
        const add = h('button', { type: 'button' }, '＋ パターンを足す');
        const push = () => {
          const text = input.value.trim();
          if (text && !text.includes(',')) change(text, true);
        };
        add.addEventListener('click', push);
        input.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' && !event.isComposing) push();
        });
        box.append(h('div', { class: 'row' }, input, add));
      }
      root.replaceChildren(box);
    };
    draw();
  },
};
