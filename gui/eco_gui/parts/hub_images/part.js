// 部品「コンテナのイメージのまとめ」。今までの GUI（static/hub.js の loadImages）と同じ見せ方。
// まとめるのは見せ方だけ：ecobuild container image list の答えを、モジュールごとの1行にする。
const folder = (path) => String(path).split(/[\\/]/).filter(Boolean).pop() || String(path);
const tag = (name) => String(name).split(':')[1] || '';

export default {
  render(root, props, { h, notice, state }) {
    // 作った・消した結果が届いた：数を知らせる（同じ結果は1回だけ）
    const done = props.done;
    if (done && state.told !== JSON.stringify(done)) {
      state.told = JSON.stringify(done);
      if (Array.isArray(done.built)) notice(done.built.length ? `${done.built.length} 個のイメージを作りました。` : '今の作り方のイメージはすべてあります。');
      else if (Array.isArray(done.removed)) notice(done.removed.length ? `${done.removed.length} 個のイメージを消しました。` : '消す古いイメージはありません。');
    }
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const r = props.data;
    if (!r) return root.replaceChildren(h('p', { class: 'status', role: 'status' }, '読み込んでいます…'));
    if (!r.docker_ready) {
      return root.replaceChildren(h('p', { class: 'status', role: 'status' }, `Docker が使えません（${r.docker_detail || ''}）。環境の準備で導入できます。`));
    }
    const images = r.images || [];
    const missing = r.missing || [];
    const old = images.filter((image) => !image.current && !(image.used_by || []).length).length;
    const status = [
      missing.length ? `まだ作っていない作業空間：${missing.map(folder).join('、')}（作らなくても、コンテナを動かすときに作ります）。` : '',
      old ? `どのコンテナも使っていない古いイメージが ${old} 個あります。` : ''].filter(Boolean).join(' ');
    const list = h('ul', { class: 'image-types' });
    // モジュールごとに1行：今の作り方のイメージ（環境に ECOBuild を重ねたもの）と、残っている古いもの
    for (const module of [...new Set(images.map((image) => image.module))].sort()) {
      const mine = images.filter((image) => image.module === module);
      const now = mine.filter((image) => !image.environment).find((image) => image.current);
      const env = mine.find((image) => image.environment && image.current);
      const older = mine.filter((image) => !image.current);
      const used = mine.flatMap((image) => image.used_by || []);
      const parts = [now ? `${now.size}・${now.created}` : '',
        env ? `環境 ${tag(env.name)}` : '',
        used.length ? '使っている作業空間：' + used.map(folder).join('、') : '',
        older.length ? `古いもの ${older.length} 個（${older.map((image) => image.size).join('・')}${older.some((image) => (image.used_by || []).length)
          ? '。使用中のものは、そのコンテナを次に動かすときに入れ替わります' : ''}）` : ''].filter(Boolean);
      // まだイメージがないのは、ふつうの状態（コンテナを初めて動かすときに作る）：静かに見せる
      const row = h('li', {}, h('span', { class: 'type' }, module), h('span', { class: 'img-tag', title: now ? now.name : '' }, now ? tag(now.name) : ''),
        h('span', { class: now ? 'pill ok' : older.length ? 'pill warn' : 'pill dim' }, now ? '今の作り方' : older.length ? '古いものだけ' : 'まだ作っていません'));
      if (parts.length) row.append(h('small', {}, parts.join('　')));
      list.append(row);
    }
    const nodes = [];
    if (status) nodes.push(h('p', { class: 'status', role: 'status' }, status));
    if (!images.length) nodes.push(h('p', { class: 'status' }, 'イメージはまだありません。'));
    nodes.push(list);
    root.replaceChildren(...nodes);
  },
};
