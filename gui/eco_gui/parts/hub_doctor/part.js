// 部品「環境チェックの結果」。今までの GUI（static/hub.js の renderDiagnosis）と同じ並び。
// 足りるか・必須かは ecobuild doctor の答え。ここは、3段階の言葉と色で見せるだけ。
// 画面から直せるもの（doctor の fix：login・scope）には直すボタン（出力 fix。端末の窓で続ける）。
const FIXES = { login: 'ログイン', scope: '権限を追加' };

export default {
  render(root, props, { h, emit }) {
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
      const mark = h('span', { class: state[0] }, state[1]);
      if (!item.ok && FIXES[item.fix]) {
        const fix = h('button', { type: 'button', class: 'fix' }, FIXES[item.fix]);
        // 権限の項目の id は gh_scope_<権限>（足す権限）
        const scope = item.fix === 'scope' ? String(item.id || '').replace(/^gh_scope_/, '') || 'project' : '';
        fix.addEventListener('click', () => emit('fix', { fix: item.fix, scope }));
        mark.append(fix);
      }
      list.append(h('li', {}, h('div', {}, h('span', { class: 'item-name' }, item.name), detail), mark));
    }
    root.replaceChildren(summary, list);
  },
};
