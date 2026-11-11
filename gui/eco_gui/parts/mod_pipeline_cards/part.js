// 部品「パイプラインのカード」。今までの GUI のパイプライン（.pl-card）と同じに描く。
const STEP_NAMES = { generated: '生成ファイル', conflict_markers: '衝突の印', build: 'ビルド', test: 'テスト' };
const TIMING_NAMES = {
  'before-commit': 'コミットの前', 'after-commit': 'コミットの後', 'before-push': 'Pushの前', 'after-push': 'Pushの後',
  'before-submit': '提出の前', 'after-submit': '提出の後', 'before-finish': '取り込み（完了）の前', 'after-sync': '最新の取り込み（同期）の後',
  'after-start': 'タスクの開始の後',
};

export default {
  render(root, props, { h, emit }) {
    const d = props.data;
    const add = h('button', { type: 'button', class: 'small' }, '＋ パイプライン');
    add.addEventListener('click', () => emit('action', { action: 'add' }));
    const out = [h('div', { class: 'section-row' }, h('h3', {}, 'パイプライン'), h('span', { class: 'end' }, add))];
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      out.push(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
      return root.replaceChildren(...out);
    }
    const pipelines = d.pipelines || [];
    if (!d.pipelines) out.push(h('p', { class: 'note', role: 'status' }, '読み込み中…'));
    else if (pipelines.length === 0) out.push(h('p', { class: 'note' }, 'パイプラインはありません。「＋ パイプライン」で、確かめる手順の並びに名前を付けて作ります。'));
    const triggers = d.triggers || {};
    const local = d.local || {};
    const list = h('div', { class: 'list' });
    for (const p of pipelines) {
      const used = Object.keys(TIMING_NAMES).filter((t) => (triggers[t] || []).includes(p.name) || (local[t] || []).includes(p.name)).map((t) => TIMING_NAMES[t]);
      const now = { name: p.name, steps: (p.steps || []).join(','), tests: (p.tests || []).join(','), used: used.length ? '今、当てているタイミング：' + used.join('、') : '' };
      const button = (action, label, cls) => {
        const item = h('button', { type: 'button', class: cls }, label);
        item.addEventListener('click', () => emit('action', { action, ...now }));
        return item;
      };
      const steps = h('span', { class: 'steps' });
      (p.steps || []).forEach((step, i) => {
        if (i) steps.append(h('span', { class: 'arrow', 'aria-hidden': 'true' }, '→'));
        steps.append(h('span', { class: 'pill' }, STEP_NAMES[step] || step));
      });
      const facts = h('dl', { class: 'settings' });
      if ((p.tests || []).length) facts.append(h('dt', {}, '流す試験'), h('dd', {}, p.tests.join('、')));
      facts.append(h('dt', {}, '当てているタイミング'),
        h('dd', {}, used.length ? used.join('、') : h('span', { class: 'sub' }, 'なし（「▶ 実行」で単体で走らせます）')));
      list.append(h('div', { class: 'ci-card' },
        h('div', { class: 'head' }, h('div', {}, h('strong', {}, p.name), ' ', steps),
          h('div', { class: 'actions' }, button('run', '▶ 実行', 'primary'), button('edit', '編集…', ''), button('remove', '削除…', 'danger-text'))),
        facts));
    }
    if (pipelines.length) out.push(list);
    root.replaceChildren(...out);
  },
};
