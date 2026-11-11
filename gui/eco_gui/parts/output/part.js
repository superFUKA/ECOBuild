// 部品「出力」。今までの GUI（gui/static/outputview.js・build.js の resultLines）と同じ見え方。
// 行の色分け・数え方・要約の作り方は、見せ方だけ（成否は ecobuild の結果のとおり）。履歴は、窓を開いているあいだだけ覚える。
const CTEST = /^\s*\d+% tests passed, (\d+) tests? failed out of \d+/i;
const SUMMARY = /^\s*(Build (FAILED|succeeded)\.?|\d+ (Warning|Error)\(s\)|\d+ 個の(警告|エラー))\s*$|\b0 (errors?|warnings?)\b/i;
const kindOf = (line) => (CTEST.test(line) ? (line.match(CTEST)[1] === '0' ? 'ok' : 'muted')
  : SUMMARY.test(line) ? 'muted'
    : /\b(fatal )?error\b|\bFAILED\b|エラー|^Traceback |^E {3}/i.test(line) ? 'bad' : /\bwarning\b|警告/i.test(line) ? 'warn' : '');
const toolLines = (text) => String(text || '').replace(/\r/g, '').replace(/\n+$/, '').split('\n').map((t) => ({ text: t, kind: kindOf(t) }));
const LABEL = { build: 'ビルド', rebuild: 'リビルド', clean: 'クリーン', test: 'テスト', run: '実行', check: '提出前の確認' };
const CHECK = { generated: '生成ファイルが最新', conflict_markers: '衝突の印がない', build: 'ビルド', test: 'テスト', dependencies: '依存先が記録の版' };
const STATE_TEXT = { ok: '成功', run: '実行中…', bad: '失敗' };

// 終わった実行の結果を、行にする
function resultLines(kind, r) {
  if (!r || typeof r !== 'object') return [];
  const where = [r.project, r.configuration, r.profile].filter(Boolean).join('・');
  if (kind === 'test' && 'passed' in r) {
    const order = { failed: 0, skipped: 1, passed: 2 };
    return [{ text: `${where || 'テスト'}：成功 ${r.passed}・失敗 ${r.failed}・スキップ ${r.skipped}`, kind: r.failed ? 'bad' : 'ok', head: true },
      ...[...(r.cases || [])].sort((a, b) => (order[a.status] ?? 1) - (order[b.status] ?? 1)).map((c) => (c.status === 'failed' ? { text: `✗ ${c.name}`, kind: 'bad' }
        : c.status === 'passed' ? { text: `✓ ${c.name}`, kind: 'ok' } : { text: `- ${c.name}（${c.status}）`, kind: 'muted' }))];
  }
  if (kind === 'run' && 'returncode' in r) {
    return [{ text: `${where} 終了コード ${r.returncode}`.trim(), kind: r.returncode ? 'bad' : 'ok', head: true },
      ...(r.output ? [{ text: '', kind: '' }, ...toolLines(r.output)] : [])];
  }
  if (kind === 'check' && Array.isArray(r.items)) {
    return r.items.flatMap((i) => [{ text: `${i.ok ? '✓' : '✗'} ${CHECK[i.name] || i.name}`, kind: i.ok ? 'ok' : 'bad' },
      ...(i.detail ? toolLines(i.detail).map((l) => ({ ...l, text: '  ' + l.text })) : [])]);
  }
  if (kind in LABEL) {
    return [{ text: `${LABEL[kind]}しました${where ? '：' + where : ''}`, kind: 'ok', head: true },
      ...(r.artifacts && r.artifacts.length ? [{ text: '成果物：', kind: 'muted' }, ...r.artifacts.map((a) => ({ text: '  ' + a, kind: '' }))] : [])];
  }
  return [];
}
// 結果から分かる成否（試験の失敗・0 でない終了コード・通らなかった確認は、コマンドが成功でも「失敗」と出す）
function shownState(state, kind, r) {
  if (state !== 'ok' || !r || typeof r !== 'object') return state;
  if ((kind === 'test' && r.failed) || (kind === 'run' && r.returncode) || (kind === 'check' && (r.items || []).some((i) => !i.ok))) return 'bad';
  return state;
}

export default {
  render(root, props, { h, emit, state, redraw, menu }) {
    // 実行の移り変わりを覚える（秒数・履歴）。窓を開き直すと空に戻る
    if (!state.runs) { state.runs = []; state.wrap = true; state.query = ''; }
    const now = Date.now();
    const running = props.state === 'run';
    let current = state.runs[0];
    if (running && (!current || current.ended)) {  // 新しい実行が始まった
      current = { id: now, started: now, ended: 0 };
      state.runs.unshift(current);
      state.runs.length = Math.min(state.runs.length, 10);
      state.shown = null; state.problems = false;
    }
    if (!current && (props.lines.length || props.state)) { current = { id: now, started: 0, ended: now }; state.runs.unshift(current); }
    if (current && !(current.ended && current.started && running)) {
      if (!running && current.started && !current.ended) current.ended = now;
      const lines = [...props.lines.map((text) => ({ text, kind: kindOf(text) })), ...(running ? [] : resultLines(props.kind || '', props.result))];
      Object.assign(current, { title: props.title || '', state: shownState(props.state || '', props.kind || '', props.result), lines });
    }
    const run = state.runs.find((r) => r.id === state.shown) || current;
    clearInterval(state.tick);

    const box = h('div', { class: 'output-view' + (props.fill ? ' fill' : '') });
    if (!run) {
      box.append(h('pre', { class: 'out-text', tabindex: '0', role: 'log' }, h('span', { class: 'line muted' }, props.empty_text)));
      return root.replaceChildren(box);
    }
    const seconds = () => (run.started ? (((run.ended || Date.now()) - run.started) / 1000).toFixed(run.ended ? 1 : 0) + ' 秒' : '');
    const time = h('span', { class: 'out-time' }, seconds());
    if (run === current && running) state.tick = setInterval(() => { time.textContent = seconds(); }, 1000);

    const errors = run.lines.filter((l) => l.kind === 'bad' && !l.head).length, warnings = run.lines.filter((l) => l.kind === 'warn' && !l.head).length;
    const q = state.query.trim().toLowerCase();
    const visible = run.lines.filter((l) => (!state.problems || l.kind === 'bad' || l.kind === 'warn') && (!q || l.text.toLowerCase().includes(q)));
    const text = h('pre', { class: 'out-text' + (state.wrap ? '' : ' nowrap'), tabindex: '0', role: 'log' });
    const mark = (line) => {
      if (!q) return [line || ' '];
      const out = [], low = line.toLowerCase();
      let at = 0, i;
      while ((i = low.indexOf(q, at)) >= 0) { out.push(line.slice(at, i), h('mark', {}, line.slice(i, i + q.length))); at = i + q.length; }
      out.push(line.slice(at));
      return out;
    };
    for (const l of visible) text.append(h('span', { class: `line ${l.kind || ''}${l.head ? ' head' : ''}` }, ...mark(l.text)));
    if (!visible.length) {
      text.append(h('span', { class: 'line muted' }, state.problems ? 'エラー・警告はありません。' : q ? '一致する行はありません。' : run.state === 'run' ? '実行しています…' : props.empty_text));
    }

    const head = h('div', { class: 'out-head' });
    if (run.title) head.append(h('strong', { class: 'out-title' }, run.title));
    if (run.state) head.append(h('span', { class: 'build-state out-state ' + run.state }, STATE_TEXT[run.state]));
    head.append(time);
    const toggleProblems = () => { state.problems = !state.problems; redraw(); };
    if (errors || warnings) {
      const counts = h('button', { type: 'button', class: 'out-counts', title: 'エラー・警告の行だけ表示／すべて表示' });
      if (errors) counts.append(h('span', { class: 'bad' }, `エラー ${errors}`));
      if (warnings) counts.append(h('span', { class: 'warn' }, `警告 ${warnings}`));
      counts.addEventListener('click', toggleProblems);
      head.append(counts);
    }
    const search = h('input', { type: 'search', class: 'out-search', placeholder: '絞り込み', 'aria-label': '出力を絞り込む', value: state.query });
    search.addEventListener('input', () => { state.query = search.value; state.typing = true; redraw(); });
    const tool = (label, pressed, title, action) => {
      const button = h('button', { type: 'button', title: title || '' }, label);
      if (pressed !== null) button.setAttribute('aria-pressed', String(pressed));
      button.addEventListener('click', action);
      return button;
    };
    const history = tool('履歴', null, '前の出力（最近の10回）', async () => {
      const r = history.getBoundingClientRect();
      const id = await menu({ clientX: r.right - 260, clientY: r.bottom + 4 }, state.runs.map((x) => ({
        id: String(x.id), label: `${x.id === run.id ? '✓ ' : '　'}${x.title || '出力'}・${(STATE_TEXT[x.state] || '').replace('…', '')}`,
        hint: x.started ? new Date(x.started).toLocaleTimeString() : '' })));
      if (id) { state.shown = Number(id); redraw(); }
    });
    history.setAttribute('aria-haspopup', 'menu');
    head.append(h('span', { class: 'out-tools' },
      h('span', { class: 'out-shown' }, visible.length < run.lines.length ? `${visible.length} / ${run.lines.length} 行` : ''), search,
      tool('エラー・警告だけ', Boolean(state.problems), '', toggleProblems),
      tool('折り返し', state.wrap, '', () => { state.wrap = !state.wrap; redraw(); }),
      history,
      tool('コピー', null, '出力をコピー', () => {
        try { navigator.clipboard.writeText(run.lines.map((l) => l.text).join('\n')); } catch { /* 写せない環境 */ }
        emit('copied', { count: run.lines.length });
      })));
    box.append(head, text);
    root.replaceChildren(box);
    if (state.typing) { state.typing = false; search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
    // 実行中は下を追う。失敗したら最初のエラーへ。ほかは、見ていた位置のまま
    const key = `${run.id}/${run.state}`;
    const first = run.state === 'bad' && state.placed !== key ? text.querySelector('.line.bad:not(.head)') : null;
    if (run.state === 'run') text.scrollTop = text.scrollHeight;
    else if (first) first.scrollIntoView({ block: 'center' });
    else if (state.placed === key) text.scrollTop = state.scroll || 0;
    state.placed = key;
    text.addEventListener('scroll', () => { state.scroll = text.scrollTop; });
  },
};
