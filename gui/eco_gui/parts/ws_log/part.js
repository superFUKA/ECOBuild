// 部品「ログ」。今までの GUI（gui/static/logview.js）の左の一覧と同じ見え方。
// 選んだコミットの変更は、別の部品（ws-diff）が出す。絞り込みの文字は、窓の中だけの状態。
const two = (n) => String(n).padStart(2, '0');
function localTime(iso) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return String(iso || '').slice(0, 16).replace('T', ' ');
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
}

export default {
  render(root, props, { h, emit, state, redraw, menu }) {
    if (state.query === undefined) state.query = '';
    const box = h('div', { class: 'log-side' + (props.short ? ' log-short' : '') });
    const search = h('input', { type: 'search', class: 'log-search', placeholder: '件名・作成者・SHA・#タスクで絞り込み', 'aria-label': 'ログを絞り込む', value: state.query });
    search.addEventListener('input', () => { state.query = search.value; state.typing = true; redraw(); });
    // どのブランチのログを見るか（取り出さずに読む。今のブランチが既定）
    if (props.branches && props.branches.length) {
      const pick = h('select', { class: 'log-branch', 'aria-label': 'ログを見るブランチ', title: 'ログを見るブランチ（取り出さずに読みます）' },
        h('option', { value: '' }, '今のブランチ'));
      for (const b of props.branches) pick.append(h('option', { value: b.name }, b.name));
      pick.value = props.branch || '';
      pick.addEventListener('change', () => emit('branch', { name: pick.value }));
      box.append(pick);
    }
    if (props.search) box.append(search);
    const list = h('ul', { class: 'log-entries', role: 'listbox', tabindex: '0', 'aria-label': 'コミット' });
    box.append(list);
    const finish = () => {
      root.replaceChildren(box);
      if (state.typing) { state.typing = false; search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
    };
    if (props.error) { list.append(h('li', { class: 'muted' }, `読み込めませんでした：${props.error}`)); return finish(); }
    if (props.loading && props.commits.length === 0) { list.append(h('li', { class: 'muted' }, '読み込んでいます…')); return finish(); }

    const q = state.query.trim().toLowerCase();
    const visible = props.commits.filter((c) => !q || [c.sha, c.subject, c.author, c.issue ? '#' + c.issue : ''].some((v) => String(v || '').toLowerCase().includes(q)));
    const copy = (text) => { try { navigator.clipboard.writeText(text); } catch { /* 写せない環境 */ } };
    const openMenu = async (c, event) => {
      const index = props.commits.findIndex((e) => e.sha === c.sha), before = c.sha + '~1';
      const later = index === 0 ? 'このコミット' : `このコミットから後（${index + 1}件）`;
      const items = [{ id: 'show', label: '変更を見る' }, { id: 'copy', label: 'SHAをコピー' }];
      if (props.mode === 'log') items.push({ separator: true }, { id: 'restore', label: 'この版の状態に戻す…' }, { id: 'reset', label: 'ここまで戻す…', danger: true });
      if (props.mode === 'push') items.push({ separator: true }, { id: 'undo', label: `${later}を取り消す（変更は残す）` }, { id: 'drop', label: `${later}を捨てる…`, danger: true });
      const id = await menu(event, items);
      if (id === 'copy') return copy(c.sha);
      if (id) emit('action', { name: id, sha: c.sha, before });
    };
    const tip = 'ダブルクリックで変更を見る' + (props.mode === 'plain' ? '' : '・右クリックで操作');
    for (const c of visible) {
      const meta = h('small', {});
      if (c.pull_request) meta.append(h('span', { class: 'log-merge', title: `PR #${c.pull_request} を取り込んだコミット（スカッシュ）` }, `取り込み PR #${c.pull_request}${c.issue ? `・タスク #${c.issue}` : ''}`), ' ');
      else if (c.issue) meta.append(h('span', { class: 'log-merge', title: `タスク #${c.issue} を提出せずに反映したコミット（スカッシュ）` }, `反映 タスク #${c.issue}`), ' ');
      meta.append(`${c.author || ''}・${localTime(c.date)}`);
      const row = h('li', { role: 'option', 'aria-selected': String(c.sha === props.selected), title: tip },
        h('code', {}, String(c.sha).slice(0, 8)), h('span', { class: 'log-subject' }, c.subject || ''), meta);
      row.addEventListener('click', () => { if (c.sha !== props.selected) emit('selected', { sha: c.sha }); });
      row.addEventListener('dblclick', () => emit('action', { name: 'show', sha: c.sha, before: c.sha + '~1' }));
      row.addEventListener('contextmenu', (event) => { event.preventDefault(); if (c.sha !== props.selected) emit('selected', { sha: c.sha }); openMenu(c, event); });
      list.append(row);
    }
    if (!visible.length) list.append(h('li', { class: 'muted' }, props.commits.length ? '一致するコミットはありません。' : props.empty_text));
    list.addEventListener('keydown', (event) => {
      const at = visible.findIndex((c) => c.sha === props.selected);
      if (event.key === 'Enter' && at >= 0) { event.preventDefault(); emit('action', { name: 'show', sha: visible[at].sha, before: visible[at].sha + '~1' }); }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      const next = visible[Math.max(0, Math.min(visible.length - 1, at + (event.key === 'ArrowDown' ? 1 : -1)))];
      if (next && next.sha !== props.selected) emit('selected', { sha: next.sha });
    });
    const limit = props.count || 30;
    if (props.commits.length >= limit) {
      const more = h('button', { type: 'button', class: 'log-more' }, 'さらに読み込む');
      more.addEventListener('click', () => emit('more', { count: limit + 30 }));
      box.append(more);
    }
    const scroll = state.scroll || 0;
    list.addEventListener('scroll', () => { state.scroll = list.scrollTop; });
    finish();
    list.scrollTop = scroll;
    const on = list.querySelector('[aria-selected=true]');
    if (on && state.seen !== props.selected) { state.seen = props.selected; on.scrollIntoView({ block: 'nearest' }); }
  },
};
