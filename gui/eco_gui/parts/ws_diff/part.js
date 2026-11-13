// 部品「差分」。今までの GUI（gui/static/common.js の diffHtml・logview.js の右側）と同じ見え方。
// ファイルごとに畳む。小さい差分（12 ファイル・1500 行まで）は初めから開く。開閉は窓の中だけの状態。
export default {
  render(root, props, { h, emit, state, redraw, notice }) {
    const box = h('div', { class: 'log-main' + (props.fill ? ' fill' : '') });
    if (props.error) { box.append(h('p', { role: 'alert' }, props.error)); return root.replaceChildren(box); }
    if (props.loading && !props.text) { box.append(h('p', { class: 'muted' }, '読み込んでいます…')); return root.replaceChildren(box); }
    if (!props.text) { box.append(h('p', { class: 'muted' }, props.empty_text)); return root.replaceChildren(box); }
    if (state.text !== props.text) { state.text = props.text; state.open = new Map(); state.all = null; }

    const parts = String(props.text).split(/^(?=diff --git )/m);
    const head = parts[0].startsWith('diff --git ') ? '' : parts.shift();
    const size = parts.reduce((n, p) => n + p.split('\n').length, 0), openAll = !props.focus && size <= 1500 && parts.length <= 12;
    const copy = (text, what) => { try { navigator.clipboard.writeText(text).then(() => notice('コピーしました。'), () => notice('コピーできませんでした。', 'error')); } catch { /* 写せない環境 */ } emit('copied', { what }); };
    const tool = (label, action) => { const button = h('button', { type: 'button' }, label); button.addEventListener('click', action); return button; };
    const bar = h('div', { class: 'log-commit' }, h('strong', {}, props.title || ''));
    if (props.sha) bar.append(tool('SHAをコピー', () => copy(props.sha, 'sha')));
    if (parts.length) bar.append(tool('すべて開く', () => { state.all = true; state.open = new Map(); redraw(); }), tool('すべて閉じる', () => { state.all = false; state.open = new Map(); redraw(); }));
    bar.append(tool('コピー', () => copy(props.text, 'text')));
    box.append(bar);
    if (head.trim()) box.append(h('pre', { class: 'eco-diff-head' }, head.replace(/\n+$/, '')));
    for (const part of parts) {
      const first = part.indexOf('\n'), match = part.slice(0, first).match(/ b\/(.*)$/), path = match ? match[1] : part.slice(11, first);
      const lines = part.slice(first + 1).replace(/\n$/, '').split('\n');
      const added = lines.filter((l) => l.startsWith('+') && !l.startsWith('+++')).length, removed = lines.filter((l) => l.startsWith('-') && !l.startsWith('---')).length;
      const focused = props.focus ? path === props.focus || path.startsWith(String(props.focus).replace(/\/?$/, '/')) : openAll;
      const file = h('details', { class: 'eco-file' });
      file.open = state.open.has(path) ? state.open.get(path) : state.all === null ? focused : state.all;
      file.addEventListener('toggle', () => { state.open.set(path, file.open); });
      const pre = h('pre', { class: 'eco-diff' });
      for (const line of lines) {
        const cls = line.startsWith('@@') ? 'hunk' : line.startsWith('+') && !line.startsWith('+++') ? 'add' : line.startsWith('-') && !line.startsWith('---') ? 'del'
          : /^(index |\+\+\+|---|new file|deleted file|similarity|rename |old mode|new mode|Binary)/.test(line) ? 'meta' : '';
        pre.append(h('span', { class: cls }, line + '\n'));
      }
      file.append(h('summary', {}, h('span', { class: 'eco-file-path' }, path), h('span', { class: 'add' }, `+${added}`), h('span', { class: 'del' }, `−${removed}`)), pre);
      box.append(file);
    }
    root.replaceChildren(box);
  },
};
