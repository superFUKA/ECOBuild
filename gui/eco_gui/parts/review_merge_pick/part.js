// 部品「ブランチ同士の取り込み：向きと相手を選ぶ」。今までの GUI（static/branches.js の renderMerge の上の行と、カードの見出し）と同じ並び・同じ文言。
// 選んだ組（取り込むブランチ・取り込み先）と開閉を出すだけ。下見・取り込みは、画面のつなぎが ecobuild に頼む。
const METHODS = { 'fast-forward': ['早送り', 'ok'], merge: ['マージコミット', 'ok'], conflict: ['衝突する', 'bad'], 'up-to-date': ['取り込み済み', ''] };

export default {
  render(root, props, { h, emit, state }) {
    const shared = (props.branches || []).filter((b) => !b.is_task_branch);
    const fixed = props.name || props.default_base || '';
    const chosen = shared.find((b) => b.name === fixed);
    const source = props.source || '', into = props.into || '';
    const paired = Boolean(fixed && source && into && source !== into && (source === fixed || into === fixed));
    const later = (run) => Promise.resolve().then(run);
    // 初めの相手：このブランチから作ったもの、なければ作成元、なければほか（取り込むブランチの側に置くときは、作成元が先）。ブランチごとに1回
    if (fixed && shared.length && !paired && state.askedFor !== fixed) {
      state.askedFor = fixed;
      const others = shared.filter((b) => b.remote && b.name !== fixed), base = chosen && chosen.base;
      const made = others.find((b) => b.base === fixed), from = others.find((b) => b.name === base);
      const other = ((props.side === 'from' ? from || made : made || from) || others[0] || {}).name || '';
      if (other && (!chosen || chosen.remote)) later(() => emit('changed', props.side === 'from' ? { source: fixed, into: other } : { source: other, into: fixed }));
    }
    const fixedSide = paired ? (into === fixed ? 'into' : 'from') : props.side === 'from' ? 'from' : 'into';
    const p = props.plan && props.plan.name === source && props.plan.into === into ? props.plan : null;
    const foldable = props.foldable !== false;
    const open = foldable ? props.open === true : true;
    // することがある（取り込める・衝突する）ときは、カードを開ける（ブランチごとに1回。手で畳んだら、そのまま）
    if (foldable && p && p.method !== 'up-to-date' && props.open !== true && state.openedFor !== fixed) {
      state.openedFor = fixed;
      later(() => emit('toggled', { open: true }));
    }
    if (!foldable && props.open !== true && !state.forced) { state.forced = true; later(() => emit('toggled', { open: true })); }

    const sum = h('span', { class: 'sum' });
    if (props.loading) sum.append(h('span', { class: 'spinner' }));
    else if (p) {
      const [label, tone] = METHODS[p.method] || [p.method, ''];
      sum.append(h('span', { class: tone ? 'pill ' + tone : 'pill' }, label));
      if (p.commit_count) sum.append(h('span', { class: 'dim' }, p.name + ' → ' + p.into + '・' + p.commit_count + ' 件'));
    }
    const title = [h('h4', {}, 'ブランチ同士の取り込み ', h('span', { class: 'dim' }, '提出（PR）なしで直接'))];
    let head;
    if (foldable) {
      const fold = h('button', { type: 'button', class: 'fold', 'aria-expanded': String(open) }, h('span', { class: 'caret', 'aria-hidden': 'true' }, open ? '▾' : '▸'), ...title);
      fold.addEventListener('click', () => emit('toggled', { open: !open }));
      head = h('header', {}, fold, sum);
    } else head = h('header', {}, h('div', { class: 'fold' }, ...title), sum);
    const box = h('section', { class: 'merge' }, head);

    if (open) {
      const side = (key, label) => {
        if (key === fixedSide) return h('div', { class: 'pick' }, h('span', {}, label), h('span', { class: 'fixed', title: fixed }, fixed || '—'));
        const value = paired ? (key === 'into' ? into : source) : '';
        const select = h('select', { 'aria-label': label });
        if (!value) select.append(h('option', { value: '' }, '（選んでください）'));
        for (const b of shared.filter((x) => x.name !== fixed)) {
          const option = h('option', { value: b.name }, b.name + (b.remote ? '' : '（GitHub にない）'));
          if (!b.remote) option.disabled = true;
          if (b.name === value) option.selected = true;
          select.append(option);
        }
        select.addEventListener('change', () => {
          if (select.value) emit('changed', key === 'into' ? { source: fixed, into: select.value } : { source: select.value, into: fixed });
        });
        return h('label', { class: 'pick' }, h('span', {}, label), select);
      };
      const swap = h('button', { type: 'button', class: 'arrow', title: '取り込む向きを入れ替える', 'aria-label': '取り込む向きを入れ替える' }, '→');
      swap.addEventListener('click', () => { if (paired) emit('changed', { source: into, into: source }); });
      const again = h('button', { type: 'button', class: 'link' }, '確かめ直す');
      again.addEventListener('click', () => emit('reload', {}));
      box.append(h('div', { class: 'row' }, side('from', '取り込むブランチ'), swap, side('into', '取り込み先'), again));
      if (props.error) box.append(h('div', { class: 'banner bad', role: 'alert' }, h('p', {}, props.error)));
      else if (chosen && !chosen.remote) box.append(h('p', { class: 'note' }, fixed + ' は GitHub にないので、取り込みには使えません。'));
      else if (shared.length && !shared.some((b) => b.remote && b.name !== fixed)) box.append(h('p', { class: 'note' }, '取り込む相手にできる、ほかの共有ブランチ（GitHub にあるもの）がありません。'));
    }
    root.replaceChildren(box);
  },
};
