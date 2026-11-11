// 部品「注釈履歴」。今までの GUI は、ecobuild blame の文字をそのまま出力の窓に出していた（static/explorer.js の blame）。
// 同じ文字を、行ごとに「コミット｜行番号｜行」に分けて見せる（見せ方だけ。読むのは画面のつなぎ）。
const LINE = /^(\^?[0-9a-f]{4,40})\s+(?:\S+\s+)?\((.*?)\s+(\d{4}-\d{2}-\d{2})(?:\s+[\d:]+\s+[+-]\d{4})?\s+(\d+)\)(?: (.*))?$/;
const TONES = 6;  // コミットごとの帯の色の数

export default {
  render(root, props, { h, emit, state, redraw }) {
    const box = h('section', { class: 'blame' });
    if (props.error) {
      box.append(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error)));
      root.replaceChildren(box);
      return;
    }
    const raw = String(props.text || '');
    if (!raw.trim()) {
      box.append(props.loading ? h('p', { class: 'empty', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…') : h('p', { class: 'empty' }, props.empty_text));
      root.replaceChildren(box);
      return;
    }
    const rows = raw.replace(/\r\n?/g, '\n').replace(/\n$/, '').split('\n').map((line, i) => {
      const m = LINE.exec(line);
      return m ? { sha: m[1].replace(/^\^/, ''), root: m[1].startsWith('^'), author: m[2].trim(), date: m[3], number: Number(m[4]), code: m[5] || '' }
        : { sha: '', author: '', date: '', number: i + 1, code: line };
    });
    const tones = new Map();
    for (const r of rows) if (r.sha && !tones.has(r.sha)) tones.set(r.sha, tones.size % TONES);
    const people = new Set(rows.map((r) => r.author).filter(Boolean));
    state.query = state.query || '';
    const words = state.query.toLowerCase().split(/\s+/).filter(Boolean);
    const matches = (r) => words.every((w) => (r.sha + ' ' + r.author + ' ' + r.date + ' ' + r.code).toLowerCase().includes(w));
    const shown = words.length ? rows.filter(matches) : rows;

    const search = h('input', { type: 'search', placeholder: '絞り込み（コミット・人・行の文字。空白で区切ると、全部を含む行）', 'aria-label': '注釈履歴を絞り込む', value: state.query });
    search.addEventListener('input', () => { state.query = search.value; state.focus = true; redraw(); });
    const count = h('span', { class: 'count' }, (words.length ? shown.length + ' / ' : '') + rows.length + ' 行・コミット ' + tones.size + '・' + people.size + ' 人');
    const bar = h('div', { class: 'bar' }, search, count);
    const selected = props.selected || '';
    if (selected) {
      const open = h('button', { type: 'button', class: 'small' }, selected + ' の変更を見る');
      open.addEventListener('click', () => emit('opened', { commit: selected }));
      bar.append(open);
    }
    box.append(bar);

    const body = h('tbody', {});
    let before = null;
    for (const r of shown) {
      const first = !before || before.sha !== r.sha || before.number + 1 !== r.number;
      const who = h('td', { class: 'who' });
      if (r.sha && first) {
        const pick = h('button', { type: 'button', class: 'sha', title: r.sha + '（' + r.author + '・' + r.date + '）' + (r.root ? '・最初のコミット' : '') + '\nもう一度押すと、変更を見ます' }, r.sha.slice(0, 8));
        pick.addEventListener('click', () => emit(selected === r.sha ? 'opened' : 'selected', { commit: r.sha }));
        who.append(pick, h('span', { class: 'author' }, r.author), h('span', { class: 'date' }, r.date));
      }
      body.append(h('tr', { class: [r.sha ? 'tone' + tones.get(r.sha) : '', first ? 'first' : '', selected && r.sha === selected ? 'on' : ''].filter(Boolean).join(' ') },
        who, h('td', { class: 'number' }, String(r.number)), h('td', { class: 'code' }, r.code)));
      before = r;
    }
    box.append(shown.length ? h('div', { class: 'lines', tabindex: '0', role: 'region', 'aria-label': '注釈履歴' }, h('table', {}, body))
      : h('p', { class: 'empty' }, '絞り込みに当てはまる行はありません。'));
    root.replaceChildren(box);
    if (state.focus) { state.focus = false; search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
  },
};
