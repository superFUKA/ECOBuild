// 部品「作業のタブ」。今までの GUI（workspace.html の .work-tabs）と同じ：タブに件数の印、←→ で移る、最後のタブを覚える。
const LABELS = { commit: 'コミット', push: 'Push', submit: '提出', log: 'ログ' };

export default {
  render(root, props, { h, emit, state, memory }) {
    const s = props.status || {};
    const loaded = 'branch' in s || 'task' in s;
    const working = Boolean(s.task || s.reviewing);
    const tabs = !loaded ? ['commit', 'push', 'submit', 'log'] : working ? ['commit', ...(s.reviewing ? [] : ['push']), 'submit', 'log'] : [...(s.merging ? ['commit'] : []), 'log'];
    const changes = new Set([...(s.conflicted || []), ...(s.staged || []), ...(s.unstaged || []), ...(s.untracked || [])]).size;
    const counts = { commit: changes, push: s.task && !s.reviewing ? s.ahead || 0 : 0, submit: s.pull_request ? 1 : 0 };
    let current = props.selected || 'commit';
    // 開いたとき・今いる場所にないタブのとき：覚えていたタブ（なければ先頭）を出す
    if (loaded && (!props.selected || !tabs.includes(props.selected))) {
      const kept = memory.get('tab', null);
      current = tabs.includes(kept) ? kept : tabs[0];
      const key = `${props.selected}>${current}`;
      if (state.sent !== key && current !== props.selected) { state.sent = key; emit('selected', { tab: current }); }
    }
    const strip = h('div', { class: 'work-tabs', role: 'tablist', 'aria-label': 'コミット・Push・提出' });
    const pick = (tab) => { memory.set('tab', tab); emit('selected', { tab }); };
    for (const tab of tabs) {
      const on = tab === current;
      const button = h('button', { type: 'button', role: 'tab', 'aria-selected': String(on), tabindex: on ? '0' : '-1' }, LABELS[tab]);
      if (tab in counts && loaded) button.append(h('span', { class: 'tab-count' + (counts[tab] ? '' : ' zero') }, String(counts[tab])));
      button.addEventListener('click', () => pick(tab));
      button.addEventListener('keydown', (event) => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        pick(tabs[(tabs.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]);
      });
      strip.append(button);
    }
    root.replaceChildren(strip);
  },
};
