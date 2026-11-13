// 部品「README」。今までの GUI のホームの README と同じに描く（GitHub のページのように）。
// Markdown は要素として組み立てる（文字はそのまま文字として入れる。リンクは http(s) だけ）。
function inline(h, text) {
  const out = [];
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)/g;
  let at = 0;
  for (let found = pattern.exec(text); found; found = pattern.exec(text)) {
    if (found.index > at) out.push(text.slice(at, found.index));
    if (found[1] !== undefined) out.push(h('code', {}, found[1]));
    else if (found[2] !== undefined) out.push(h('strong', {}, found[2]));
    else if (/^https?:/.test(found[4])) out.push(h('a', { href: found[4], target: '_blank', rel: 'noopener' }, found[3]));
    else out.push(h('span', { class: 'inner-link', title: found[4] }, ...inline(h, found[3])));  // モジュールの中のファイルへのリンク：名前だけ見せる
    at = found.index + found[0].length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

function markdown(h, source) {
  const out = [];
  const lines = source.replace(/\r\n?/g, '\n').split('\n');
  let paragraph = [];
  let list = null;
  const flush = () => {
    if (paragraph.length) { out.push(h('p', {}, ...inline(h, paragraph.join(' ')))); paragraph = []; }
    if (list) { out.push(h(list.tag, {}, ...list.items.map((item) => h('li', {}, ...inline(h, item))))); list = null; }
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(/^\s*(```|~~~)/);
    if (fence) {
      flush();
      const code = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith(fence[1]); i++) code.push(lines[i]);
      out.push(h('pre', {}, h('code', {}, code.join('\n'))));
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) { flush(); out.push(h('h' + Math.min(6, heading[1].length + 1), {}, ...inline(h, heading[2]))); continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); out.push(h('hr', {})); continue; }
    const item = line.match(/^\s*([-*+]|\d+\.)\s+(.*)$/);
    if (item) {
      const tag = /\d/.test(item[1]) ? 'ol' : 'ul';
      if (paragraph.length || (list && list.tag !== tag)) flush();
      if (!list) list = { tag, items: [] };
      list.items.push(item[2]);
      continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) { flush(); out.push(h('blockquote', {}, ...inline(h, quote[1]))); continue; }
    if (!line.trim()) { flush(); continue; }
    if (list) list.items[list.items.length - 1] += ' ' + line.trim(); else paragraph.push(line.trim());
  }
  flush();
  return out;
}

export default {
  render(root, props, { h, emit }) {
    const readme = props.readme;
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      return root.replaceChildren(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    if (!readme) {
      return root.replaceChildren(h('p', { class: 'note', role: 'status' }, props.loading ? '読み込み中…'
        : 'README はありません。モジュールのいちばん上のフォルダーに README.md を置くと、ここに出ます。'));
    }
    const body = h('div', { class: 'readme' });
    if (/\.(md|markdown)$/i.test(readme.path || '')) body.append(...markdown(h, readme.text || ''));
    else body.append(h('pre', {}, readme.text || ''));
    if (readme.truncated) body.append(h('p', {}, '…'));
    const edit = h('button', { type: 'button', class: 'small', title: '既定のアプリで開きます（変えたらタスクブランチでコミット）' }, '✎ 編集');
    edit.addEventListener('click', () => emit('edit', { path: readme.path || 'README.md' }));
    root.replaceChildren(h('div', { class: 'head' }, h('h3', { class: 'title' }, readme.path || 'README'), edit), body);
  },
};
