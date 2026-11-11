// 部品「環境チェックの結果」。今までの GUI（static/hub.js の renderDiagnosis）と同じ並び。
// 足りるか・必須かは ecobuild doctor の答え。ここは、3段階の言葉と色で見せるだけ。
export default {
  render(root, props, { h }) {
    if (props.items === null) {
      return root.replaceChildren(h('p', { class: 'summary', role: 'status' }, h('span', { class: 'spinner' }), ' チェックしています…'));
    }
    const missing = props.items.filter((item) => !item.ok && item.required).length;
    const summary = h('p', { class: missing ? 'summary todo' : 'summary', role: 'status' },
      missing ? `対応が必要な項目が ${missing} 件あります。` : '開発に必要な環境が整っています。');
    const list = h('ul', { class: 'diagnostics' });
    for (const item of props.items) {
      const detail = h('small', {}, item.detail || '');
      if (!item.ok && item.hint) detail.append(h('span', { class: 'hint' }, item.hint));
      const state = item.ok ? ['ok', '確認済み'] : item.required ? ['todo', '要対応'] : ['optional', '任意'];
      list.append(h('li', {}, h('div', {}, h('span', { class: 'item-name' }, item.name), detail), h('span', { class: state[0] }, state[1])));
    }
    root.replaceChildren(summary, list);
  },
};
