// 部品「タイミングの表」。今までの GUI のパイプラインのタイミング（.pl-timings）と同じに描く。
const TIMINGS = [
  ['コミット', [['before-commit', '前'], ['after-commit', '後']]],
  ['Push', [['before-push', '前'], ['after-push', '後']]],
  ['提出', [['before-submit', '前'], ['after-submit', '後']]],
  ['取り込み（完了）', [['before-finish', '前']]],
  ['最新の取り込み（同期）', [['after-sync', '後']]],
  ['タスクの開始', [['after-start', '後']]],
];

export default {
  render(root, props, { h, emit }) {
    const d = props.data;
    const out = [h('div', { class: 'section-row' }, h('h3', {}, 'タイミング'))];
    if (props.error || !d.pipelines) {  // 誤りは、上のカードの部品が出す
      if (!props.error) out.push(h('p', { class: 'note', role: 'status' }, '読み込み中…'));
      return root.replaceChildren(...(props.error ? [] : out));
    }
    const triggers = d.triggers || {};
    const local = d.local || {};
    const none = d.pipelines.length === 0;
    const body = h('tbody', {});
    for (const [operation, timings] of TIMINGS) {
      timings.forEach(([timing, when], i) => {
        const shared = triggers[timing] || [];
        const mine = (local[timing] || []).filter((name) => !shared.includes(name));
        const chips = h('td', {});
        for (const name of shared) chips.append(h('span', { class: 'pill ok' }, name), ' ');
        for (const name of mine) chips.append(h('span', { class: 'pill' }, name + '（このPCだけ）'), ' ');
        if (!shared.length && !mine.length) chips.append(h('span', { class: 'sub' }, 'なし'));
        const button = (label, isLocal) => {
          const item = h('button', { type: 'button', class: 'small' }, label);
          if (none) { item.setAttribute('aria-disabled', 'true'); item.title = '先にパイプラインを作ってください'; }
          item.addEventListener('click', () => {
            if (!none) emit('changed', { timing, local: isLocal, names: (isLocal ? local[timing] || [] : shared).join(','), label: operation + 'の' + when });
          });
          return item;
        };
        const row = h('tr', {});
        if (i === 0) row.append(h('td', { rowspan: String(timings.length) }, operation));
        row.append(h('td', {}, when, h('small', { class: 'sub' }, when === '前' ? '（失敗したら止める）' : '（知らせるだけ）')), chips,
          h('td', { class: 'row-actions' }, button('変える…', false), button('このPCで足す…', true)));
        body.append(row);
      });
    }
    out.push(h('table', { class: 'timings' }, h('thead', {}, h('tr', {}, h('th', {}, '操作'), h('th', {}, 'いつ'), h('th', {}, '走らせるパイプライン'),
      h('th', {}, h('span', { class: 'sr-only' }, '操作')))), body));
    root.replaceChildren(...out);
  },
};
