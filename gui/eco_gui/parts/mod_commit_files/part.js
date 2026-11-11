// 部品「コミットの中身」。show の出力を、説明と、ファイルごとの差分に分けて見せる（分けるのは見せ方だけ）。
// ファイルが少なければ初めから開く。開閉は、窓を開いているあいだ覚える（コミットごと）。
const OPEN_UP_TO = 3;

function split(text) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const head = [];
  const files = [];
  let file = null;
  for (const line of lines) {
    const start = line.match(/^diff --git a\/(.*) b\/(.*)$/);
    if (start) {
      file = { path: start[2], lines: [], added: 0, deleted: 0, note: '' };
      files.push(file);
    } else if (!file) head.push(line);
    else {
      if (/^(index |--- |\+\+\+ |similarity index|old mode|new mode)/.test(line)) continue;
      if (/^new file mode/.test(line)) { file.note = '新しいファイル'; continue; }
      if (/^deleted file mode/.test(line)) { file.note = '削除'; continue; }
      if (/^rename from /.test(line)) { file.note = '名前の変更（' + line.slice(12) + ' から）'; continue; }
      if (/^rename to /.test(line)) continue;
      if (/^Binary files /.test(line)) { file.note = file.note || 'バイナリ'; continue; }
      if (line.startsWith('+')) file.added += 1;
      else if (line.startsWith('-')) file.deleted += 1;
      file.lines.push(line);
    }
  }
  while (head.length && !head[head.length - 1].trim()) head.pop();
  return { head, files };
}

export default {
  render(root, props, { h, emit, state }) {
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    if (!props.text) return root.replaceChildren(h('p', { class: 'note', role: 'status' }, props.loading ? '読み込み中…' : props.empty_text));
    const { head, files } = split(props.text);
    const key = head[0] || '';
    if (state.key !== key) { state.key = key; state.open = {}; }
    const out = [h('pre', { class: 'head' }, head.join('\n'))];
    if (files.length) {
      const added = files.reduce((sum, f) => sum + f.added, 0);
      const deleted = files.reduce((sum, f) => sum + f.deleted, 0);
      out.push(h('p', { class: 'sum' }, '変わったファイル ' + files.length + ' 件　', h('span', { class: 'add' }, '+' + added), ' ', h('span', { class: 'del' }, '−' + deleted)));
    }
    for (const f of files) {
      const code = h('pre', { class: 'diff' });
      for (const line of f.lines) {
        const cls = line.startsWith('@@') ? 'hunk' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : '';
        code.append(h('span', { class: cls ? 'line ' + cls : 'line' }, line === '' ? ' ' : line), '\n');
      }
      const summary = h('summary', {}, h('span', { class: 'path' }, f.path), f.note ? h('span', { class: 'pill' }, f.note) : '',
        h('span', { class: 'counts' }, h('span', { class: 'add' }, '+' + f.added), ' ', h('span', { class: 'del' }, '−' + f.deleted)));
      const box = h('details', { class: 'file' }, summary, f.lines.length ? code : h('p', { class: 'note inner' }, '中身の差分はありません。'));
      box.open = f.path in state.open ? state.open[f.path] : files.length <= OPEN_UP_TO;
      box.addEventListener('toggle', () => { state.open[f.path] = box.open; });
      out.push(box);
    }
    root.replaceChildren(...out);
  },
};
