// 部品「完了したタスクブランチを片付ける」。下見の結果を並べるだけ（消す・残すを決めるのは ecobuild）。
export default {
  render(root, props, { h, emit }) {
    const button = (label, cls, output) => {
      const b = h('button', cls ? { type: 'button', class: cls } : { type: 'button' }, label);
      b.addEventListener('click', () => emit(output, {}));
      return b;
    };
    const top = [h('h2', {}, '完了したタスクブランチを片付ける'),
      h('p', { class: 'intro' }, '閉じたタスクのタスクブランチと、その作業空間を消します。取り込んでいないコミットがあるものは残します。')];
    const actions = (...buttons) => h('div', { class: 'actions' }, ...buttons);
    if (props.error) return root.replaceChildren(...top, h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error)), actions(button('閉じる', 'primary', 'cancel')));
    const r = props.preview;
    if (!r) {
      return root.replaceChildren(...top, h('p', { class: 'wait', role: 'status' }, h('span', { class: 'spinner' }), ' 片付けるものを確かめています…'),
        actions(button('キャンセル', '', 'cancel')));
    }
    const removed = r.removed || [], places = r.workspaces_removed || [], skipped = r.skipped || [];
    const list = (title, items) => (items.length ? [h('p', {}, title), h('ul', {}, ...items.map((text) => h('li', {}, text)))] : []);
    root.replaceChildren(...top,
      ...(removed.length ? list('片付けるタスクブランチ：', removed) : [h('p', {}, '片付けるタスクブランチはありません。')]),
      ...list('一緒に消える作業空間：', places.map(String)),
      ...list('残すもの：', skipped.map((s) => s.branch + '：' + s.reason)),
      removed.length ? actions(button('キャンセル', '', 'cancel'), button('片付ける', 'primary', 'clean')) : actions(button('閉じる', 'primary', 'cancel')));
  },
};
