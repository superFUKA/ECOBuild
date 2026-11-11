// 部品「コンテナの要約」。今までの GUI（modinfo.js の renderContainer）の表と「しくみ」。
// 「古い」「今の作り方」は、届いた状態（outdated・current）をそのまま印にする（この部品では決めない）。
const FILE = '.ecobuild/container/Dockerfile';

export default {
  render(root, props, { h, memory }) {
    if (props.error) return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, `読めませんでした：${props.error}`)));
    const r = props.recipe, st = props.status;
    if (!r) return root.replaceChildren(h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 読み込み中…'));
    const inRepo = !!r.context;
    const tag = (name) => h('span', { class: 'mono', title: name || '' }, name || '');
    const pill = (text, cls) => h('span', { class: cls ? `pill ${cls}` : 'pill' }, text);
    const sub = (text) => h('span', { class: 'sub' }, text);
    const row = (label, value, note) => {
      const cell = h('td', {}, ...[].concat(value));
      if (note) cell.append(h('div', { class: 'sub' }, note));
      return h('tr', {}, h('th', { scope: 'row' }, label), cell);
    };
    const rows = [
      row('環境の作り方', inRepo ? tag(FILE) : sub('型のひな型（まだリポジトリにありません）'),
        inRepo ? '' : '今の仕様に合わせる（ecobuild module upgrade）と、ひな型がリポジトリに置かれ、モジュールに合わせて書き換えられます。'),
      row('環境のイメージ', tag(r.environment)),
      row('コンテナのイメージ', tag(r.image)),
    ];
    if (st) {
      const state = !st.container ? ['この作業空間はコンテナにしていません（このPCで動かします）']
        : st.custom_image ? [`この作業空間だけの設定のイメージ ${st.custom_image} を使います`]
          : st.state === 'none' ? ['コンテナはまだありません（エージェント・ビルド等で使うときに作ります）']
            : st.outdated ? [pill('古い', 'warn'), ` コンテナのイメージ ${st.image || ''} は今の作り方のものではありません。次に動かすときに作り直します。`]
              : [pill('今の作り方', 'ok'), st.image ? ` コンテナは ${st.image} で動いています` : ' コンテナは、今の作り方のイメージで動きます'];
      rows.push(row('この作業空間のコンテナ', state));
    }
    const mine = ((props.images && props.images.images) || []).filter((image) => image.module === r.module);
    const list = mine.map((image) => {
      const line = h('div', { class: 'image' }, tag(image.name), ' ', image.current ? pill('今', 'ok') : pill('古い'));
      if (image.environment) line.append(' ', pill('環境'));
      const used = (image.used_by || []).length;
      line.append(sub(` ${image.size || ''}・${image.created || ''}${used ? `・使用中 ${used}` : ''}`));
      return line;
    });
    rows.push(row('このPCのイメージ', props.images ? (list.length ? list : sub('まだありません')) : sub('読み込み中…'),
      '古いものはハブの設定の「コンテナのイメージ」で片付けられます'));

    const how = h('details', { class: 'recipe', open: memory.get('how', false) === true }, h('summary', {}, 'しくみ'),
      h('p', { class: 'note' }, '環境（ECOBuild のエージェント・ecobuild 等を除いた部分）はリポジトリにコミットするので、ほかのPCでも同じ環境になります。'
        + '解析ツール等は環境に足し、タスクブランチでコミットして PR で反映します。イメージの名前は作り方のハッシュで、環境か ECOBuild が変わると新しく作ります。'
        + '下の「イメージの作り方」で、今の作り方のイメージを作れます。'));
    how.addEventListener('toggle', () => memory.set('how', how.open));
    root.replaceChildren(h('table', { class: 'table' }, h('tbody', {}, ...rows)), how);
  },
};
