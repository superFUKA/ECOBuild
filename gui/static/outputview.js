'use strict';
// The output of a build・test・run・check (OUTPUT.view), as an IDE's output pane: line by line, errors and warnings
// colored and counted (the counts show only them), a file(line) in a line opens in Visual Studio, a search box narrows
// the lines, 「履歴」 shows an earlier run. The runs are made by the workspace (build.js); the same view draws them in the
// workspace's footer and in a window of its own (panels.js).
// A run: {id, title, command, state: run・ok・bad, started, ended, lines, progress}. A line: {text, kind, head} — kind
// ok・bad・warn・muted・err (a program's stderr) (toolLines reads it from a tool's text); head: ecobuild's own message
// (colored, not counted).
const OUTPUT = (() => {
  const {esc} = ECO;
  // A tool's summary (Build FAILED. / 2 Error(s) / 0 個の警告) is not counted: the lines it counts are. CTest's
  // (100% tests passed, 0 tests failed out of 1) is ok when nothing failed (its "failed" is not an error).
  const ctestSummary = /^\s*\d+% tests passed, (\d+) tests? failed out of \d+/i;
  const kindOf = line => ctestSummary.test(line) ? (line.match(ctestSummary)[1] === '0' ? 'ok' : 'muted')
    : /^\s*(Build (FAILED|succeeded)\.?|\d+ (Warning|Error)\(s\)|\d+ 個の(警告|エラー))\s*$|\b0 (errors?|warnings?)\b/i.test(line) ? 'muted'
    : /\b(fatal )?error\b|\bFAILED\b|エラー|^Traceback |^E {3}/i.test(line) ? 'bad' : /\bwarning\b|警告/i.test(line) ? 'warn' : '';
  const toolLines = (output, kind = null) => String(output || '').replace(/\r/g, '').replace(/\n+$/, '').split('\n').map(t => ({text: t, kind: kind ?? kindOf(t)}));
  // The events ecobuild reports on its stderr while it runs (ecobuild --help --json の events: {kind, text, stream,
  // source}): its progress (muted), notices, warnings and errors (colored, not counted), and the output of the tools and
  // programs it runs (colored as a tool's line; what the program wrote to its stderr stands apart). An output event is
  // what the tool wrote (a line with its \n, or the start of one): the pieces of a stream are joined into lines.
  // output: false leaves the output out (the result has it).
  const OWN = {progress: 'muted', notice: '', warning: 'warn', error: 'bad'};
  function eventLines(events, {output = true} = {}) {
    const lines = [], open = {};
    const outputLine = (text, stream) => ({text, kind: kindOf(text) || (stream === 'stderr' ? 'err' : '')});
    for (const e of events || []) {
      if (e.kind !== 'output') {
        if (e.kind in OWN) lines.push({text: e.kind === 'notice' ? `お知らせ：${e.text}` : e.text, kind: OWN[e.kind], head: e.kind !== 'progress'});
        continue;
      }
      if (!output) continue;
      const stream = e.stream === 'stderr' ? 'stderr' : 'stdout', parts = (open[stream]?.text || '') + String(e.text).replace(/\r/g, '');
      if (open[stream]) lines.splice(lines.indexOf(open[stream]), 1);
      const pieces = parts.split('\n'), rest = pieces.pop();
      lines.push(...pieces.map(t => outputLine(t, stream)));
      open[stream] = rest ? outputLine(rest, stream) : null;
      if (rest) lines.push(open[stream]);
    }
    return lines;
  }
  // A file and line in a compiler's or Python's message: C:\…\a.cpp(12,5)・src/a.cpp:12:5・File "…\a.py", line 12.
  const SOURCE = 'c|cc|cpp|cxx|c\\+\\+|h|hh|hpp|hxx|inl|ixx|ipp|py|pyi|cmake|txt|toml|json|cs|rs|js|ts';
  const FILE_AT = new RegExp(`File "([^"]+)", line (\\d+)|((?:[A-Za-z]:)?[\\w.\\-\\\\/]*\\.(?:${SOURCE}))(?:\\((\\d+)(?:,\\d+)?\\)|:(\\d+)(?::\\d+)?)`, 'gi');
  const inside = (dir, path) => {
    const p = path.replaceAll('\\', '/'), root = dir.replaceAll('\\', '/').replace(/\/+$/, '') + '/';
    if (p.toLowerCase().startsWith(root.toLowerCase())) return p.slice(root.length);
    return /^([A-Za-z]:|\/)/.test(p) ? '' : p.replace(/^\.\//, '');
  };
  const mark = (s, q) => {
    if (!q) return esc(s);
    let out = '', at = 0, i; const low = s.toLowerCase();
    while ((i = low.indexOf(q, at)) >= 0) { out += esc(s.slice(at, i)) + `<mark>${esc(s.slice(i, i + q.length))}</mark>`; at = i + q.length; }
    return out + esc(s.slice(at));
  };
  const lineHtml = (dir, s, q) => {
    let out = '', at = 0;
    for (const m of s.matchAll(FILE_AT)) {
      const relative = inside(dir, m[1] || m[3]), line = m[2] || m[4] || m[5];
      if (!relative) continue;
      out += mark(s.slice(at, m.index), q) + `<a href="#" data-open="${esc(relative)}" title="${esc(relative)} を開く（${line} 行目）">${mark(m[0], q)}</a>`;
      at = m.index + m[0].length;
    }
    return out + mark(s.slice(at), q);
  };
  const seconds = run => (((run.ended || Date.now()) - run.started) / 1000).toFixed(run.ended ? 1 : 0) + ' 秒';
  const stateText = state => state === 'ok' ? '成功' : state === 'run' ? '実行中…' : '失敗';
  // Opening a file: in the workspace its own way (Visual Studio, else the default app); in a window, the same actions.
  const openFile = (dir, path) => {
    if (window.WS?.openInEditor && WS.dir === dir) return WS.openInEditor(path);
    return ECO.action('vs', {dir, path, version: ECO.vsVersion()})
      .catch(() => ECO.action('folder', {dir, path}).catch(e => ECO.toast(e.message, 'bad')));
  };

  function view(box, {dir}) {
    box.classList.add('output-view');
    box.innerHTML = `<div class="out-head"><strong class="out-title" hidden></strong><span class="build-state out-state" hidden></span><span class="out-time"></span>
      <button type="button" class="out-counts" title="エラー・警告の行だけ表示／すべて表示" hidden></button>
      <span class="out-tools"><span class="out-shown"></span><input type="search" class="out-search" placeholder="絞り込み" aria-label="出力を絞り込む">
        <button type="button" data-out="problems" aria-pressed="false">エラー・警告だけ</button><button type="button" data-out="wrap" aria-pressed="true">折り返し</button><button type="button" data-out="history" aria-haspopup="menu" title="前の出力（最近の10回）">履歴</button><button type="button" data-out="copy" title="出力をコピー">コピー</button></span></div>
      <pre class="out-text"></pre>`;
    const $ = s => box.querySelector(s), text = $('.out-text'), search = $('.out-search');
    let runs = [], shownId = null, newestId = null, shownState = '', onlyProblems = false;
    const shown = () => runs.find(r => r.id === shownId);
    function render({follow = false} = {}) {
      const run = shown(); if (!run) return;
      $('.out-title').textContent = run.title; $('.out-title').hidden = false;   // the tab says 出力: here the run's name only
      $('.out-state').hidden = false; $('.out-state').textContent = stateText(run.state);
      $('.out-state').className = 'build-state out-state ' + run.state;
      $('.out-time').textContent = seconds(run);
      const lines = [{text: run.command, kind: 'muted'}, ...(run.state === 'run' ? eventLines(run.progress) : run.lines)];
      const errors = lines.filter(l => l.kind === 'bad' && !l.head).length, warnings = lines.filter(l => l.kind === 'warn' && !l.head).length;
      $('.out-counts').innerHTML = (errors ? `<span class="bad">エラー ${errors}</span>` : '') + (warnings ? `<span class="warn">警告 ${warnings}</span>` : '');
      $('.out-counts').hidden = !errors && !warnings;
      const q = search.value.trim().toLowerCase();
      const visible = lines.filter(l => (!onlyProblems || l.kind === 'bad' || l.kind === 'warn') && (!q || l.text.toLowerCase().includes(q)));
      text.innerHTML = visible.map(l => `<span class="line ${l.kind || ''}${l.head ? ' head' : ''}">${lineHtml(dir, l.text, q) || ' '}</span>`).join('')
        || `<span class="line muted">${onlyProblems ? 'エラー・警告はありません。' : '一致する行はありません。'}</span>`;
      $('.out-shown').textContent = visible.length < lines.length ? `${visible.length} / ${lines.length} 行` : '';
      if (follow) text.scrollTop = text.scrollHeight;
    }
    // A run shown from its start; one that failed, at its first error.
    function show(id) {
      shownId = id; shownState = shown()?.state || ''; render();
      const first = shownState === 'bad' && text.querySelector('.line.bad:not(.head)');
      if (first) first.scrollIntoView({block: 'center'}); else text.scrollTop = shownState === 'run' ? text.scrollHeight : 0;
    }
    setInterval(() => { const run = shown(); if (run?.state === 'run') $('.out-time').textContent = seconds(run); }, 1000);
    const toggleProblems = () => { onlyProblems = !onlyProblems; $('[data-out=problems]').setAttribute('aria-pressed', String(onlyProblems)); render(); };
    $('.out-counts').addEventListener('click', toggleProblems);
    search.addEventListener('input', () => render());
    text.addEventListener('click', e => { const a = e.target.closest('[data-open]'); if (a) { e.preventDefault(); openFile(dir, a.dataset.open); } });
    $('.out-tools').addEventListener('click', e => {
      const button = e.target.closest('[data-out]'), what = button?.dataset.out, run = shown(); if (!what || !run) return;
      if (what === 'problems') toggleProblems();
      if (what === 'wrap') button.setAttribute('aria-pressed', String(!text.classList.toggle('nowrap')));
      if (what === 'copy') ECO.copyText([run.command, ...run.lines.map(l => l.text)].join('\n'));
      if (what === 'history') {
        const r = button.getBoundingClientRect();
        ECO.menu(runs.map(x => [`${x.id === shownId ? '✓ ' : '　'}${x.title}・${stateText(x.state).replace('…', '')}・${new Date(x.started).toLocaleTimeString()}`,
          () => show(x.id)]), r.right - 260, r.bottom + 4);
      }
    });
    return {
      // The runs, newest first: a new run is shown at once (and followed while it runs); the one shown is drawn again.
      update(next) {
        runs = next || [];
        const newest = runs[0];
        if (newest && newest.id !== newestId) { newestId = newest.id; show(newest.id); return; }
        const run = shown();
        if (!run) { if (newest) show(newest.id); return; }
        if (run.state !== shownState) show(run.id); else render({follow: run.state === 'run'});
      },
    };
  }
  return {view, toolLines, eventLines};
})();
