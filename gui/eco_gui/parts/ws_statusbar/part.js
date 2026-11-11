// 部品「ステータスバー」。今までの GUI（workspace.html の #status-bar・workspace.js の renderStatusBar）と同じ並びと文。
// 「HH:MM に確認」は、GitHub の最新を確かめた結果がこの窓に届いた時刻（窓の中だけで覚える）。
const OUTPUT_ICON = '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 14h18"/>';
const FETCH_ICON = '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/>';
const RUN_STATE = { run: ['実行中', '実行中'], ok: ['✓', '成功'], bad: ['✗', '失敗'] };

export default {
  render(root, props, { h, emit, state }) {
    const svg = (inner) => {
      const box = h('span', { class: 'icon', 'aria-hidden': 'true' });
      box.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
      return box;
    };
    const s = props.status || {}, remote = props.remote || {};
    const onTask = Boolean(s.task && !s.reviewing);
    const hidden = Boolean(props.output_hidden);

    const output = h('button', { type: 'button', class: 'status-item', 'aria-pressed': String(!hidden), title: '出力を出す・しまう' }, svg(OUTPUT_ICON), h('span', {}, '出力'));
    // 試験の失敗・0 でない終了コード・通らなかった確認は、コマンドが成功でも「失敗」と出す（出力欄と同じ）
    const r = props.result || {};
    const failed = props.run === 'ok' && ((props.kind === 'test' && r.failed) || (props.kind === 'run' && r.returncode) || (props.kind === 'check' && (r.items || []).some((i) => !i.ok)));
    const ran = failed ? 'bad' : props.run || '';
    const run = RUN_STATE[ran];
    if (run) output.append(h('span', { class: 'status-run ' + ran, title: `最後の実行：${run[1]}` }, run[0]));
    output.addEventListener('click', () => emit('action', { name: hidden ? 'show_output' : 'hide_output' }));

    const right = h('div', { class: 'status-right' });
    if (onTask) {
      right.append(h('span', { class: 'status-item status-text', title: s.ahead ? `Push していないコミットが ${s.ahead} 件あります` : 'コミットはすべて Push してあります' },
        s.ahead ? `↑ 未Push ${s.ahead}` : '↑ Push済み'));
    }
    const behind = remote.base_behind || 0, clashes = (remote.base_conflicts || []).length;
    if (onTask && behind) {
      right.append(h('span', { class: 'status-item status-text' + (clashes ? ' bad' : ''),
        title: `作成元 ${s.base} の新しいコミット ${behind} 件を取り込んでいません` + (clashes ? `（取り込むと衝突するファイル：${remote.base_conflicts.join('、')}）` : '') },
      `↓ ${s.base} より ${behind} 遅れ${clashes ? `・衝突 ${clashes}` : ''}`));
    }
    const key = JSON.stringify(remote);
    if ('branch' in remote && state.key !== key) { state.key = key; state.at = new Date(); }
    const at = state.at;
    const again = h('button', { type: 'button', class: 'status-item', title: 'GitHub の最新を確認します（作成元の遅れ・取り込むと衝突するファイル）' }, svg(FETCH_ICON),
      h('span', {}, at ? `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')} に確認` : '未確認'));
    again.addEventListener('click', () => { state.key = null; emit('action', { name: 'fetch' }); });
    right.append(again);
    root.replaceChildren(h('footer', { class: 'status-bar', 'aria-label': '作業空間の状態' }, h('div', { class: 'status-left' }, output), right));
  },
};
