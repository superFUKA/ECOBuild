// 部品「ブランチ同士の取り込みの事前確認」。今までの GUI（static/branches.js の renderMerge）と同じ並び・同じ文言。
// 受け取った下見の結果を見せるだけ（方式・衝突・取り込める人は ecobuild が答えたもの）。「すべて表示」は、この部品の中だけの状態。
const METHODS = {
  'fast-forward': ['早送り', 'ok', ''],
  merge: ['マージコミット', 'ok', ''],
  conflict: ['衝突する', 'bad', '同じところが両方で変わっているので、このままでは取り込めません。'],
  'up-to-date': ['取り込み済み', '', ''],
};
const FIRST = 8;  // 初めに見せるコミットの数
const two = (n) => String(n).padStart(2, '0');
const localTime = (iso) => {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return String(iso || '').slice(0, 16).replace('T', ' ');
  return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + ' ' + two(d.getHours()) + ':' + two(d.getMinutes());
};

export default {
  render(root, props, { h, state, redraw }) {
    const p = props.plan;
    const box = h('section', { class: 'plan', 'aria-live': 'polite' });
    if (props.error) {
      box.append(h('div', { class: 'banner bad', role: 'alert' }, h('p', {}, props.error)));
    } else if (!p) {
      box.append(props.loading ? h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 何が起きるかを確かめています…')
        : h('p', { class: 'note' }, '取り込み先を選ぶと、取り込む前に、入るコミット・変わるファイル・衝突を確かめます。'));
    } else {
      const key = p.name + '→' + p.into;
      if (state.key !== key) { state.key = key; state.all = false; }  // 別の組み合わせ：一覧は初めの数に戻す
      const [label, tone, why] = METHODS[p.method] || [p.method, '', ''];
      const commits = p.commits || [], files = p.files || [], conflicts = p.conflicts || [], resolved = p.resolved || [];
      const what = h('p', { class: 'what' }, h('span', { class: tone ? 'pill ' + tone : 'pill' }, label), h('span', { class: 'route' }, p.name + ' → ' + p.into));
      if (p.commit_count) what.append(h('span', {}, '入るコミット ', h('b', {}, String(p.commit_count)), ' 件・変わるファイル ', h('b', {}, String(p.file_count || 0)), ' 件'));
      if (why) what.append(h('span', { class: 'dim' }, why));
      if (props.loading) what.append(h('span', { class: 'spinner' }));
      box.append(what);

      if (p.method === 'conflict') {
        box.append(h('div', { class: 'banner bad', role: 'alert' }, h('div', {},
          h('p', {}, '衝突するファイル（' + conflicts.length + '）'),
          h('ul', { class: 'conflicts' }, ...conflicts.map((file) => h('li', {}, file))),
          h('p', {}, '衝突は「衝突を直すタスク」で直します：' + p.into + ' を ' + p.name + ' へ取り込むタスクの作業空間で直して ' + p.name + ' へ入れると、'
            + p.name + ' → ' + p.into + ' が取り込めるようになります。'))));
      }
      if (resolved.length) {
        box.append(h('p', { class: 'note' }, '自動で作るファイル ' + resolved.length + ' 件が衝突しますが、取り込むときに、合わさった設定から作り直します（' + resolved.join('、') + '）。'));
      }
      const shown = state.all ? commits : commits.slice(0, FIRST);
      if (shown.length) {
        box.append(h('ol', { class: 'commits' }, ...shown.map((c) => h('li', {},
          h('code', {}, String(c.sha || '').slice(0, 7)), h('span', { class: 'subject', title: c.subject || '' }, c.subject || ''),
          h('span', { class: 'dim' }, [c.author, localTime(c.date)].filter(Boolean).join('・'))))));
        const more = (p.commit_count || commits.length) - shown.length;
        if (more > 0 && shown.length < commits.length) {
          const all = h('button', { type: 'button', class: 'link' }, 'すべて表示（' + p.commit_count + ' 件）');
          all.addEventListener('click', () => { state.all = true; redraw(); });
          box.append(all);
        } else if (more > 0) {
          box.append(h('p', { class: 'note' }, 'ほか ' + more + ' 件（ログで見られます）'));
        }
      }
      if (p.file_count) {
        const list = h('ul', {}, ...files.map((file) => h('li', {}, file)));
        if (p.file_count > files.length) list.append(h('li', { class: 'dim' }, 'ほか ' + (p.file_count - files.length) + ' 件'));
        const details = h('details', { class: 'files' }, h('summary', {}, '変わるファイル ' + p.file_count + ' 件'), list);
        details.open = state.files === true;
        details.addEventListener('toggle', () => { state.files = details.open; });
        box.append(details);
      }
      if ((p.method === 'fast-forward' || p.method === 'merge') && p.allowed === false) {
        box.append(h('p', { class: 'who' }, '取り込めるのは ' + p.owners + ' です。'));
      }
    }
    root.replaceChildren(box);
  },
};
