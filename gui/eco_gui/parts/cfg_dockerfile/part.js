// 部品「Dockerfile のエディター」。今までの GUI（static/imageeditor.js）と同じ並び・同じ文言。
// 書けるか・試せるかは、届いた答え（editable・reason・docker_ready）のとおり。保存・試す・閉じるは出力で出す（実行は画面のつなぎ）。
const FILE = '.ecobuild/container/Dockerfile';
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// 分かっていること：[文, 種類（'' / 'ok' / 'warn'）]
function notes(r) {
  if (!r) return [];
  return [
    [r.exists ? `リポジトリの ${FILE}（材料のハッシュ ${r.hash}）` : `まだ ${FILE} はありません（型のひな型を表示しています。保存するとリポジトリに置きます）`, ''],
    [`イメージ：${r.image}（${r.image_ready ? 'このPCにあります' : 'まだ作っていません'}）`, r.image_ready ? 'ok' : ''],
    ...(r.outdated ? [[`この作業空間のコンテナは古いイメージ（${r.container_image}）です。次に動かすときに作り直します`, 'warn']] : []),
  ];
}

export default {
  render(root, props, { h, emit, keys, state, redraw }) {
    if (props.error) return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, `読めませんでした：${props.error}`)));
    // 今の中身：保存したら、その答え。読み直した答えは、書きかけでなければ取り込む
    if (props.saved && !same(props.saved, state.saved)) {
      state.saved = props.saved;
      state.base = props.saved;
      state.text = props.saved.text;
    }
    if (props.data && !same(props.data, state.data)) {
      state.data = props.data;
      const dirty = state.base && state.text !== state.base.text;
      if (!dirty) { state.base = props.data; state.text = props.data.text; }
      else state.base = { ...props.data, text: state.base.text };
    }
    const r = state.base || null;
    const dirty = () => !!r && state.text !== r.text;

    const text = h('textarea', { spellcheck: 'false', rows: 16, 'aria-label': FILE });
    text.value = r ? state.text : '読み込んでいます…';
    text.readOnly = !r || !r.editable;
    const reason = h('p', { class: 'reason' });
    const close = h('button', { type: 'button' }, '閉じる');
    const build = h('button', { type: 'button' }, '試しに作る');
    const save = h('button', { type: 'button', class: 'primary' }, '保存');
    // ボタンの今：できないものは灰色と理由（ファイル（タスクブランチ）が先、次に Docker（試す））
    const update = () => {
      const saveReason = !r ? '読み込んでいます' : !r.editable ? (r.reason || 'タスクブランチでだけ書き換えられます') : !dirty() ? '変更はありません' : '';
      const buildReason = !r ? '読み込んでいます'
        : !r.docker_ready ? `Docker が使えません（${r.docker_detail || '状態が分かりません'}）。ecobuild setup --docker で導入できます`
          : dirty() && !r.editable ? '保存できないので、書きかけのまま試せません' : '';
      save.disabled = !!saveReason;
      save.title = saveReason || `${FILE} に書きます（ecobuild container dockerfile --write）`;
      build.disabled = !!buildReason;
      build.title = buildReason || (dirty() ? '保存してから、この Dockerfile でイメージを作ります（container image build）'
        : 'この Dockerfile でイメージを作ります（container image build。数分かかります）');
      reason.textContent = r && !r.editable ? `保存できません：${saveReason}` : r && r.editable && !r.docker_ready ? `試しに作れません：${buildReason}` : '';
    };
    const doSave = () => { if (!save.disabled) emit('save', { text: state.text }); };
    const doClose = () => {
      if (dirty()) { state.asking = true; redraw(); return; }
      emit('close', {});
    };
    text.addEventListener('input', () => { state.text = text.value; if (state.asking) { state.asking = false; redraw(); return; } update(); });
    text.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab' || text.readOnly || event.ctrlKey || event.altKey) return;
      event.preventDefault();  // Tab：空白4つ（フォーカスを移さない）
      text.setRangeText('    ', text.selectionStart, text.selectionEnd, 'end');
      state.text = text.value;
      update();
    });
    close.addEventListener('click', doClose);
    build.addEventListener('click', () => { if (!build.disabled) emit('build', { text: state.text, dirty: dirty() }); });
    save.addEventListener('click', doSave);
    keys('Ctrl+S', doSave);
    keys('Escape', doClose);  // Esc も「閉じる」と同じ（保存していない変更があれば確かめる）
    update();

    const out = [
      h('p', { class: 'intro' }, '保存してもコミットはしません（コミットは作業空間の「コミット」で）。'),
      h('ul', { class: 'notes' }, ...notes(r).map(([line, kind]) => h('li', { class: kind }, line))),
      text, reason,
    ];
    if (state.asking) {
      const discard = h('button', { type: 'button', class: 'danger' }, '保存せずに閉じる');
      discard.addEventListener('click', () => emit('close', {}));
      const back = h('button', { type: 'button' }, '戻る');
      back.addEventListener('click', () => { state.asking = false; redraw(); });
      out.push(h('div', { class: 'banner ask', role: 'alert' }, h('span', {}, 'Dockerfile の変更を保存していません。保存せずに閉じますか。'), back, discard));
    } else {
      out.push(h('div', { class: 'actions' }, close, build, save));
    }
    out.push(h('details', {}, h('summary', {}, '読むだけ：ECOBuild が重ねる層（ECOBuild の版で変わるので、リポジトリには書きません）'),
      h('pre', {}, props.layer || '読み込んでいます…')));
    root.replaceChildren(...out);
  },
};
