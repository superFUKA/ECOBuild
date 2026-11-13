// 部品「提出の見出し」。今までの GUI（workspace.css の .pr-head・.pr-state・.pr-meta）と同じ見え方。
const STATES = { open: '提出中', merged: '取り込み済み', closed: '閉じた' };

export default {
  render(root, props, { h, emit, notice }) {
    const s = props.status || {}, pr = s.pull_request;
    const box = h('div', { class: 'pr' });
    if (!('branch' in s) && !('task' in s)) { box.append(h('p', { class: 'muted' }, '読み込んでいます…')); return root.replaceChildren(box); }
    if (!pr) {
      box.append(h('div', { class: 'pr-head' }, h('div', { class: 'pr-title' }, h('strong', {}, s.task ? `タスク #${s.task}` : '提出'), h('span', { class: 'pr-state' }, 'まだ提出していません'))));
      if (s.task && s.ahead) box.append(h('p', { class: 'pr-note' }, `まだ Push していないコミットが ${s.ahead} 件あります。提出すると、一緒に Push します。`));
      return root.replaceChildren(box);
    }
    const state = String(pr.state || '').toLowerCase(), kind = pr.draft && state === 'open' ? 'draft' : state;
    box.append(h('div', { class: 'pr-head' }, h('div', { class: 'pr-title' }, h('strong', {}, `PR #${pr.number}`),
      h('span', { class: 'pr-state ' + kind }, kind === 'draft' ? '下書き' : STATES[state] || pr.state || ''))));
    const meta = h('div', { class: 'pr-meta' }, `取り込み先：${pr.base || ''}`, h('span', { class: 'sep' }, '·'), pr.partial ? '取り込んだら、タスクを続ける（中間提出）' : '取り込んだら、タスクを完了する');
    const row = h('div', { class: 'pr-meta-row' }, meta);
    if (pr.url) {
      const copy = h('button', { type: 'button', class: 'link-button', title: 'URL をコピー' }, pr.url);
      copy.addEventListener('click', () => { try { navigator.clipboard.writeText(pr.url).then(() => notice('コピーしました。'), () => notice('コピーできませんでした。', 'error')); } catch { /* 写せない環境 */ } emit('copied', { url: pr.url }); });
      row.append(copy);
    }
    box.append(row);
    if (state === 'open' && s.ahead) box.append(h('p', { class: 'pr-note' }, `まだ Push していないコミットが ${s.ahead} 件あります（「Push」で提出に入ります）。`));
    root.replaceChildren(box);
  },
};
