'use strict';
// Shared by every page: talking to the local server, running ecobuild commands, dialogs and notifications.
const ECO = (() => {
  const params = new URLSearchParams(location.search);
  // The server makes a new token every start. It arrives on the first URL and is kept for the other windows.
  if (params.get('t')) {
    try { localStorage.setItem('ecobuild-gui-token', params.get('t')); } catch (e) { /* storage blocked */ }
  }
  let token = params.get('t') || '';
  try { token = token || localStorage.getItem('ecobuild-gui-token') || ''; } catch (e) { /* storage blocked */ }

  // A time from GitHub / git (ISO 8601, in UTC or the writer's offset) as this PC's local time, as ecobuild shows it:
  // 'YYYY-MM-DD' (withTime: 'YYYY-MM-DD HH:MM'). Cutting the text instead would show the day before for the early hours.
  const localTime = (iso, withTime = false) => {
    const d = new Date(iso);
    if (!iso || isNaN(d)) return String(iso ?? '').slice(0, withTime ? 16 : 10).replace('T', ' ');
    const two = n => String(n).padStart(2, '0'), day = `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`;
    return withTime ? `${day} ${two(d.getHours())}:${two(d.getMinutes())}` : day;
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  async function call(api, body = {}) {
    // In the Electron window the folder picker comes from the window itself (one the server opens hides behind it).
    const shell = window.ecobuildShell || (() => { try { return window.top.ecobuildShell; } catch (e) { return null; } })();
    if (api === 'pick-folder' && shell?.pickFolder) return shell.pickFolder(body);
    if (api === 'open' && shell?.openPath) {
      const opened = await shell.openPath(body);
      if (opened?.error) throw new Error(opened.error);
      return {};
    }
    let response;
    try {
      response = await fetch('/api/' + api, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-ECOBuild-Token': token}, body: JSON.stringify(body)});
    } catch (e) {
      throw new Error('GUIのサーバーに接続できません。ECOBuild GUI を起動し直してください。');
    }
    const data = await response.json().catch(() => ({error: 'サーバーの応答を読み取れませんでした。'}));
    if (data.error) throw new Error(data.error);
    return data.value;
  }

  // Running commands, shown at the bottom left so long operations (build, clone) are visible.
  const running = document.createElement('div'); running.className = 'eco-running'; running.setAttribute('aria-live', 'polite');
  const toasts = document.createElement('div'); toasts.className = 'eco-toasts'; toasts.setAttribute('role', 'status');
  document.addEventListener('DOMContentLoaded', () => document.body.append(running, toasts, refreshing));
  // Electron (Windows・Linux): the window has no system title bar; the page's top is the bar (see the CSS).
  if (window.ecobuildShell?.frameless && window.top === window) document.documentElement.classList.add('frameless');

  // Cached reads: stale-while-revalidate (as HTTP caches and React Query・SWR do). query() answers at once with what was
  // read before (kept by the GUI server, across windows and restarts) and reads again behind it; when the new answer
  // differs, onFresh(doc) gets it (the page shows it). Nothing kept: it waits for the command, as cli() does.
  // - read again when older than STALE_MS, or after a command that changes something (the server marks all as stale)
  // - the same read at the same time runs once (here and in the server)
  // - when the window comes back (focus), the reads shown in the last minutes are read again if stale
  // - the reads behind show as one small mark in the corner (更新中), not as loading screens
  const STALE_MS = 15000, RECENT_MS = 10 * 60000, queries = new Map(), inflight = new Map();
  const refreshing = document.createElement('div'); refreshing.className = 'eco-refreshing'; refreshing.hidden = true;
  refreshing.setAttribute('role', 'status'); refreshing.innerHTML = '<span class="eco-spinner"></span><span>更新中</span>';
  const behind = new Set();
  function showRefreshing() {
    refreshing.hidden = !behind.size;
    refreshing.title = [...behind].map(k => 'ecobuild ' + queries.get(k)?.args.join(' ')).join('\n');
  }
  const queryKey = (dir, args) => (dir || '').replaceAll('\\', '/').toLowerCase() + '\n' + args.join('\0');
  function fetchQuery(key) {
    if (inflight.has(key)) return inflight.get(key);
    const {dir, args} = queries.get(key);
    const job = call('query', {dir, args, mode: 'fresh'})
      .catch(e => ({doc: {ok: false, result: null, notices: [], error: {code: 'gui', message: e.message}, argv: ['ecobuild', ...args]}, time: Date.now() / 1000}))
      .finally(() => inflight.delete(key));
    inflight.set(key, job);
    return job;
  }
  async function revalidate(key, shown) {
    if (inflight.has(key) && behind.has(key)) return;
    behind.add(key); showRefreshing();
    try {
      const {doc, time} = await fetchQuery(key), entry = queries.get(key);
      entry.fetched = time * 1000;
      if (doc.ok && JSON.stringify(doc.result) !== shown) { entry.shown = JSON.stringify(doc.result); entry.onFresh?.(doc); }
    } finally { behind.delete(key); showRefreshing(); }
  }
  async function query(dir, args, onFresh) {
    const key = queryKey(dir, args), entry = queries.get(key) || {};
    Object.assign(entry, {dir, args, onFresh, used: Date.now()}); queries.set(key, entry);
    const kept = await call('query', {dir, args, mode: 'cache'}).catch(() => null);
    if (!kept) {
      const {doc, time} = await fetchQuery(key);
      entry.fetched = time * 1000; entry.shown = JSON.stringify(doc.result);
      return doc;
    }
    entry.fetched = kept.time * 1000; entry.shown = JSON.stringify(kept.doc.result);
    if (kept.stale || Date.now() - entry.fetched > STALE_MS) revalidate(key, entry.shown);
    return kept.doc;
  }
  let hiddenSince = 0;
  window.addEventListener('blur', () => { hiddenSince = Date.now(); });
  window.addEventListener('focus', () => {
    if (!hiddenSince || Date.now() - hiddenSince < 1000) return;
    hiddenSince = 0;
    for (const [key, entry] of queries) {
      if (Date.now() - entry.used < RECENT_MS && Date.now() - (entry.fetched || 0) > STALE_MS) revalidate(key, entry.shown);
    }
  });
  // What a module's screens read first (prefetch: kept when the module is made or taken, so it opens at once).
  const FIRST_READS = [['module', 'show'], ['task', 'list'], ['milestone', 'list'], ['sprint', 'list'], ['branch', 'list'],
    ['profile', 'list'], ['project', 'list'], ['module', 'settings'], ['deps', 'list'], ['task', 'list', '--to-review'], ['task', 'list', '--submitted'],
    ['task', 'list', '--all'], ['task', 'next', '--count', '10'], ['task', 'overdue', '--days', '7'], ['task', 'workload'], ['milestone', 'status']];
  const prefetch = (dir, extra = []) => call('prefetch', {dir, queries: [...FIRST_READS, ...extra]});

  function toast(message, kind = 'ok', ms = 4500) {
    const item = document.createElement('div'); item.className = 'eco-toast ' + kind; item.textContent = message;
    toasts.append(item); setTimeout(() => item.remove(), ms);
  }

  const label = args => args.filter(a => a !== '--yes').slice(0, 4).join(' ');
  // onProgress(lines): while it runs, the lines ecobuild reports (what it is doing now), read every moment.
  async function cli(dir, args, {stdin, quiet = false, onProgress} = {}) {
    let row, poll;
    if (!quiet) { row = document.createElement('div'); row.innerHTML = `<span class="eco-spinner"></span><span>実行中</span><code>ecobuild ${esc(label(args))}</code>`; running.append(row); }
    const progress = onProgress ? Math.random().toString(36).slice(2) : undefined;
    if (progress) {
      let seen = 0;
      poll = setInterval(async () => {
        try {
          const {lines} = await call('progress', {id: progress});
          if (lines.length > seen) { seen = lines.length; onProgress(lines); }
        } catch (e) { /* the next time */ }
      }, 400);
    }
    try {
      return await call('action', {name: 'run', params: {dir: dir || undefined, args: args.map(String), stdin}, origin: windowId, window: topState(), progress});
    } catch (e) {
      return {ok: false, result: null, notices: [], error: {code: 'gui', message: e.message}, argv: ['ecobuild', ...args]};
    } finally { row?.remove(); clearInterval(poll); }
  }

  function detailText(details) {
    if (details == null || details === '') return '';
    if (typeof details === 'string') return details;
    if (Array.isArray(details)) return details.map(d => typeof d === 'string' ? d : JSON.stringify(d)).join('\n');
    if (details.output) return details.output;
    return JSON.stringify(details, null, 2);
  }

  // The details are the tools' own output (git・gh・CMake, often in English): folded under the message and the hint,
  // except for a build, test or run, whose output is what tells the cause.
  const OUTPUT_FIRST = new Set(['build_failed', 'test_failed', 'run_failed', 'cppbuild_error', 'check_failed', 'gui_no_output']);
  const detailHtml = (e, detail) => detail ? `<details class="eco-detail"${OUTPUT_FIRST.has(e.code) ? ' open' : ''}><summary>詳細（ツールの出力）</summary><pre>${esc(detail)}</pre></details>` : '';
  function showError(doc, title = '失敗しました') {
    const e = doc.error || {message: '不明なエラーです。'};
    const detail = detailText(e.details) || (doc.ok === false && !e.details && doc.stderr && e.code === 'gui_no_output' ? doc.stderr : '');
    return dialog({title, wide: !!detail && OUTPUT_FIRST.has(e.code), body: `<p>${esc(e.message)}</p>${e.hint ? `<p class="eco-hint">${esc(e.hint)}</p>` : ''}${detailHtml(e, detail)}${doc.argv ? `<p class="eco-cmd">${esc(doc.argv.join(' '))}</p>` : ''}`, buttons: [['閉じる', 'primary', true]]});
  }

  // Runs a command; on "confirmation_required" asks with the CLI's own message and runs again with --yes.
  // Shows errors in a dialog and notices as notifications. Returns the document when it succeeded, otherwise null.
  // In a form (see form()), a failure is not shown here: the form opens again with the error.
  // Elsewhere the "busy" overlay shows while the command runs (after a moment, so quick commands do not flicker).
  let formDepth = 0, lastError = null;
  async function run(dir, args, {success, stdin, confirm: confirmText, title, busy: busyText} = {}) {
    if (confirmText && !await confirm({title: title || '確認', message: confirmText, ok: '実行する'})) return null;
    const inForm = formDepth > 0;
    let overlay = inForm ? null : busy({title: busyText || '実行しています…', sub: 'ecobuild ' + label(args), delay: 300});
    let doc = await cli(dir, args, {stdin});
    if (!doc.ok && doc.error?.code === 'confirmation_required') {
      overlay?.end();
      const ok = await confirm({title: title || '確認', message: doc.error.message.replace(/^確認が必要です：/, ''), detail: detailText(doc.error.details), ok: '実行する', danger: true});
      if (!ok) return null;
      overlay = inForm ? null : busy({title: busyText || '実行しています…', sub: 'ecobuild ' + label(args), delay: 300});
      doc = await cli(dir, [...args, '--yes'], {stdin});
    }
    // The module's configuration was brought up to date (e.g. a newer ECOBuild/CppBuild added solution folders), so
    // generated/managed files changed and the command (task submit) wants them committed: offer to commit just those.
    const outdated = !doc.ok && doc.error?.code === 'generated_files_outdated' && Array.isArray(doc.error.details) ? doc.error.details : [];
    if (outdated.length) {
      overlay?.end();
      const ok = await confirm({title: '生成ファイルのコミット', message: 'ECOBuild の更新などで、自動で作られるファイルが変わりました。先にこれらだけをコミットしてから続けますか？', detail: outdated.join('\n'), ok: 'コミットして続ける'});
      if (!ok) return null;
      overlay = inForm ? null : busy({title: busyText || '実行しています…', sub: 'ecobuild ' + label(args), delay: 300});
      const step = await cli(dir, ['task', 'commit', ...outdated, '--message', '生成ファイルを構成の更新に合わせる']);
      doc = step.ok ? await cli(dir, args, {stdin}) : step;
    }
    overlay?.end();
    if (!doc.ok && !inForm && doc.error?.code === 'repository_archived') { await offerUnarchive(dir, doc); return null; }
    if (!doc.ok) { if (inForm) lastError = doc; else await showError(doc); return null; }
    if (success) toast(typeof success === 'function' ? success(doc.result) : success);
    for (const notice of doc.notices || []) toast('お知らせ：' + notice, 'info', 9000);
    return doc;
  }

  // The module's GitHub repository was archived (on the GitHub site, another PC or the hub): changes cannot be pushed.
  // Offer to undo the archive (ecobuild module unarchive, with the name from ecobuild module show).
  async function offerUnarchive(dir, doc) {
    const e = doc.error;
    const undo = await dialog({title: 'GitHubのリポジトリがアーカイブされています', body: `<p>${esc(e.message)}</p><p class="eco-hint">アーカイブを解除すると、再び Push や PR・タスクの変更ができるようになります。使わないモジュールであれば、解除せずにハブの「アーカイブ済み」から削除できます。</p>${doc.argv ? `<p class="eco-cmd">${esc(doc.argv.join(' '))}</p>` : ''}`,
      buttons: [['閉じる', '', false], ['アーカイブを解除', 'primary', true]]});
    if (!undo || !dir) return;
    const show = await cli(dir, ['module', 'show'], {quiet: true});
    if (!show.ok || !show.result.repository) return showError(show.ok ? {error: {message: 'GitHubのリポジトリの名前が分かりませんでした。', hint: 'ハブの「アーカイブ済み」から解除してください。'}} : show);
    const r = await run(dir, ['module', 'unarchive', show.result.repository], {success: x => `${x.repository} のアーカイブを解除しました。もう一度実行してください。`, busy: 'アーカイブを解除しています…'});
    if (r) window.dispatchEvent(new CustomEvent('eco-unarchived', {detail: r.result}));
  }

  // Generic modal. buttons: [label, class, value]. Resolves with the value of the pressed button (or null).
  function dialog({title, body = '', buttons = [['閉じる', 'primary', true]], wide = false, onOpen}) {
    return new Promise(resolve => {
      const d = document.createElement('dialog'); d.className = 'eco-dialog' + (wide ? ' wide' : '');
      d.innerHTML = `<h2>${esc(title)}</h2><div class="eco-body">${body}</div><div class="eco-actions"></div>`;
      const actions = d.querySelector('.eco-actions');
      let result = null;
      for (const [text, cls, value] of buttons) {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = text; if (cls) b.className = cls;
        b.addEventListener('click', () => { result = value; d.close(); }); actions.append(b);
      }
      d.addEventListener('close', () => { d.remove(); resolve(result); });
      document.body.append(d); d.showModal(); onOpen?.(d);
      actions.querySelector('.primary, .danger')?.focus();
    });
  }

  const confirm = ({title, message, detail, ok = 'OK', danger = false}) => dialog({title, body: `<p class="eco-message">${esc(message)}</p>${detail ? `<pre>${esc(detail)}</pre>` : ''}`, wide: !!detail, buttons: [['キャンセル', '', false], [ok, danger ? 'danger' : 'primary', true]]}).then(Boolean);

  function colorDiff(text) {
    return String(text).split('\n').map(line => {
      const cls = /^(\+\+\+|---|diff |index |new file|deleted file|similarity|rename )/.test(line) ? 'meta' : line.startsWith('@@') ? 'hunk' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : '';
      return cls ? `<span class="${cls}">${esc(line)}</span>` : esc(line);
    }).join('\n');
  }
  // A diff in one section per file (folded when there is much: open the files to read), after what comes before the
  // first file (git show: the commit and its --stat). focus: the files under this path open, the others are folded.
  // query: only the files whose path or lines have it.
  function diffHtml(text, {focus = '', query = ''} = {}) {
    const parts = String(text || '').split(/^(?=diff --git )/m);
    const head = parts[0].startsWith('diff --git ') ? '' : parts.shift();
    const q = query.toLowerCase(), files = parts.filter(p => !q || p.toLowerCase().includes(q));
    const size = files.reduce((n, p) => n + p.split('\n').length, 0), openAll = !focus && size <= 1500 && files.length <= 12;
    const sections = files.map(part => {
      const first = part.indexOf('\n'), path = (part.slice(0, first).match(/ b\/(.*)$/) || [, part.slice(11, first)])[1];
      const lines = part.slice(first + 1).replace(/\n$/, '').split('\n');
      const added = lines.filter(l => l.startsWith('+') && !l.startsWith('+++')).length, removed = lines.filter(l => l.startsWith('-') && !l.startsWith('---')).length;
      const open = focus ? path === focus || path.startsWith(focus.replace(/\/?$/, '/')) : openAll;
      return `<details class="eco-file"${open ? ' open' : ''}><summary><span class="eco-file-path">${esc(path)}</span><span class="add">+${added}</span><span class="del">−${removed}</span></summary><pre class="eco-diff">${colorDiff(lines.join('\n'))}</pre></details>`;
    });
    return (head.trim() && !q ? `<pre class="eco-diff-head">${esc(head.replace(/\n+$/, ''))}</pre>` : '') + (sections.join('') || (q ? '<p class="eco-intro">一致するファイルはありません。</p>' : ''));
  }
  // Lines that have the query, with it marked (the whole text when there is none).
  function filterLines(text, query) {
    if (!query) return {html: esc(text), shown: null};
    const q = query.toLowerCase(), hits = String(text).split('\n').filter(l => l.toLowerCase().includes(q));
    const mark = line => { let out = '', at = 0, i; const low = line.toLowerCase(); while ((i = low.indexOf(q, at)) >= 0) { out += esc(line.slice(at, i)) + `<mark>${esc(line.slice(i, i + q.length))}</mark>`; at = i + q.length; } return out + esc(line.slice(at)); };
    return {html: hits.map(mark).join('\n'), shown: hits.length};
  }
  const copyText = text => navigator.clipboard.writeText(text).then(() => toast('コピーしました。'), () => toast('コピーできませんでした。', 'bad'));
  // Text (a log, blame, a guide) or a diff to read: a search box (text: only the lines that have it; diff: only the files
  // that have it), copy, and for a diff the files folded and opened together.
  // Looking at changes (a diff, a commit, a task's changes) is TortoiseGit's job: ecobuild … --gui opens it there,
  // which shows it better than text here. Without TortoiseGit, or when it cannot show it (the first commit has nothing
  // to compare with), it is shown here as text (asText).
  let noTortoiseGit = false;
  async function inTortoiseGit(dir, args, asText) {
    if (!noTortoiseGit) {
      const doc = await cli(dir, [...args, '--gui']);
      if (doc.ok) { if (doc.result?.opened === null) toast('差分はありません。', 'info'); return; }
      if (doc.error?.code === 'tool_missing') {
        noTortoiseGit = true;
        toast('TortoiseGit が見つからないため、この画面に文字で表示します（TortoiseGit を入れると、そちらで開きます）。', 'info');
      } else if (doc.error?.code !== 'revision_not_found') return showError(doc);
    }
    return asText();
  }
  const output = (title, text, {diff = false, sub = '', focus = ''} = {}) => dialog({title, wide: true,
    body: `${sub ? `<p class="eco-intro">${esc(sub)}</p>` : ''}<div class="eco-out-tools"><input type="search" class="eco-out-search" placeholder="${diff ? 'ファイル・内容で絞り込み' : '絞り込み（この文字を含む行だけ）'}" aria-label="絞り込み"><span class="eco-out-count"></span>
      ${diff ? '<button type="button" data-out="open">すべて開く</button><button type="button" data-out="fold">すべて閉じる</button>' : ''}<button type="button" data-out="copy">コピー</button></div><div class="eco-out-body"></div>`,
    onOpen: d => {
      d.classList.add('eco-output');
      const box = d.querySelector('.eco-out-body'), search = d.querySelector('.eco-out-search'), count = d.querySelector('.eco-out-count');
      const render = () => {
        if (diff) { box.innerHTML = diffHtml(text, {focus, query: search.value.trim()}); return; }
        const {html, shown} = filterLines(text || '', search.value.trim());
        box.innerHTML = `<pre>${html}</pre>`; count.textContent = shown == null ? '' : `${shown} 行`;
      };
      render();
      search.addEventListener('input', render);
      d.querySelector('.eco-out-tools').addEventListener('click', e => {
        const what = e.target.closest('[data-out]')?.dataset.out;
        if (what === 'copy') copyText(text || '');
        if (what === 'open' || what === 'fold') box.querySelectorAll('details.eco-file').forEach(f => { f.open = what === 'open'; });
      });
    }});

  // Form dialog. fields: {name, label, type, value, options: [[value, label, note]], placeholder, required, help, min}.
  // submit(values) may return an error string to keep the dialog open. Resolves with the values (or null when cancelled).
  // With submit: pressing the button closes the form and shows the busy overlay; when submit fails, the form opens again
  // with the error (the values entered stay).
  // Layout of the fields: the ones with the same `row` sit side by side; {type: 'section', label} starts a group under a
  // heading ({collapsed: true}: folded until opened, for what is seldom set; {end: true} ends it); `showIf: values => bool` shows a field only
  // when it applies; a radio with `inline` lays its choices side by side.
  // Choices that take time to read (GitHub) do not hold the dialog back: `more: Promise<[[value, label]]>` on a select,
  // checks or text field (its suggestions) adds them to the open dialog when they arrive.
  const LAYOUT = new Set(['html', 'section']);
  function form({title, intro = '', fields = [], ok = 'OK', danger = false, wide = false, submit, extra = '', busy: busyText, onChange}) {
    return new Promise(resolve => {
      const d = document.createElement('dialog');
      d.className = 'eco-dialog' + (wide ? ' wide' : fields.some(f => f.row) ? ' roomy' : '');
      const fieldHtml = f => {
        const id = 'f-' + f.name, attrs = `name="${esc(f.name)}" ${f.required ? 'required' : ''} ${f.placeholder ? `placeholder="${esc(f.placeholder)}"` : ''} ${f.min != null ? `min="${f.min}"` : ''}`;
        const help = f.help ? `<span class="eco-help">${esc(f.help)}</span>` : '';
        if (f.type === 'html') return f.html;
        if (f.type === 'checkbox') return `<label class="eco-check"><input type="checkbox" ${attrs} ${f.value ? 'checked' : ''}> ${esc(f.label)}</label>${help}`;
        if (f.type === 'checks') return `<fieldset class="eco-checks" data-field="${esc(f.name)}"><legend>${esc(f.label)}</legend><div>${f.options.length ? f.options.map(([v, l]) => `<label><input type="checkbox" name="${esc(f.name)}" value="${esc(v)}" ${(f.value || []).includes(v) ? 'checked' : ''}><span>${esc(l ?? v)}</span></label>`).join('') : `<span class="eco-help">${esc(f.empty || '選べるものがありません')}</span>`}</div></fieldset>${help}`;
        if (f.type === 'radio') return `<fieldset${f.inline ? ' class="eco-inline"' : ''}><legend>${esc(f.label)}</legend>${f.options.map(([v, l, note]) => `<label><input type="radio" name="${esc(f.name)}" value="${esc(v)}" ${String(v) === String(f.value) ? 'checked' : ''}><span><strong>${esc(l)}</strong>${note ? `<small>${esc(note)}</small>` : ''}</span></label>`).join('')}</fieldset>${help}`;
        if (f.type === 'select') return `<label class="eco-field">${esc(f.label)}<select ${attrs}>${f.options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(f.value ?? '') ? 'selected' : ''}>${esc(l ?? v)}</option>`).join('')}</select>${help}</label>`;
        if (f.type === 'textarea') return `<label class="eco-field">${esc(f.label)}<textarea ${attrs} rows="${f.rows || 4}">${esc(f.value ?? '')}</textarea>${help}</label>`;
        const list = f.suggestions?.length ? `<datalist id="${id}-list">${f.suggestions.map(([v, l]) => `<option value="${esc(v)}"${l ? ` label="${esc(l)}"` : ''}></option>`).join('')}</datalist>` : '';
        return `<label class="eco-field">${esc(f.label)}<input id="${id}" type="${f.type || 'text'}" ${attrs} ${list ? `list="${id}-list"` : ''} value="${esc(f.value ?? '')}" autocomplete="off">${list}${help}</label>`;
      };
      const wrap = f => f.type === 'html' ? f.html : `<div class="eco-f" data-field="${esc(f.name)}">${fieldHtml(f)}</div>`;
      let html = '', closing = '';
      for (let i = 0; i < fields.length;) {
        const f = fields[i];
        if (f.type === 'section') {
          html += closing;
          if (f.end) { closing = ''; i++; continue; }   // {type: 'section', end: true}: the fields after it are outside
          const note = f.note ? `<small>${esc(f.note)}</small>` : '';
          html += f.collapsed ? `<details class="eco-section"${f.open ? ' open' : ''}><summary>${esc(f.label)}${note}</summary>` : `<div class="eco-section"><h3>${esc(f.label)}${note}</h3>`;
          closing = f.collapsed ? '</details>' : '</div>'; i++; continue;
        }
        if (f.row) {
          const group = [];
          while (i < fields.length && fields[i].row === f.row) group.push(fields[i++]);
          html += `<div class="eco-row" style="--cols:${group.length}">${group.map(wrap).join('')}</div>`; continue;
        }
        html += wrap(f); i++;
      }
      html += closing;
      d.innerHTML = `<form><h2>${esc(title)}</h2>${intro ? `<div class="eco-intro">${intro}</div>` : ''}${html}${extra}<p class="eco-error" role="alert"></p><div class="eco-actions"><button type="button" data-cancel>キャンセル</button><button type="submit" class="${danger ? 'danger' : 'primary'}">${esc(ok)}</button></div></form>`;
      const formEl = d.querySelector('form'), error = d.querySelector('.eco-error'), okButton = d.querySelector('[type=submit]');
      let result = null, working = false;
      d.querySelector('[data-cancel]').addEventListener('click', () => d.close());
      const readValues = () => {
        const values = {};
        for (const f of fields) {
          if (LAYOUT.has(f.type)) continue;
          if (f.type === 'checkbox') values[f.name] = formEl.elements[f.name].checked;
          else if (f.type === 'checks') values[f.name] = [...formEl.querySelectorAll(`[name="${f.name}"]:checked`)].map(x => x.value);
          else if (f.type === 'radio') values[f.name] = formEl.querySelector(`[name="${f.name}"]:checked`)?.value ?? '';
          else values[f.name] = formEl.elements[f.name].value.trim();
        }
        return values;
      };
      // Fields that do not apply are hidden (and disabled, so a required one does not block sending).
      const conditional = fields.filter(f => f.showIf);
      const applyConditions = () => {
        const values = readValues();
        for (const f of conditional) {
          const box = formEl.querySelector(`.eco-f[data-field="${CSS.escape(f.name)}"]`), on = !!f.showIf(values);
          box.hidden = !on;
          for (const input of box.querySelectorAll('input, select, textarea')) input.disabled = !on;
          const row = box.closest('.eco-row');
          if (row) row.hidden = ![...row.children].some(c => !c.hidden);
        }
      };
      for (const f of fields.filter(f => f.more)) {
        const box = formEl.querySelector(`.eco-f[data-field="${CSS.escape(f.name)}"]`);
        box?.classList.add('eco-more');
        Promise.resolve(f.more).then(options => {
          box?.classList.remove('eco-more');
          if (!box || !options?.length) return;
          if (f.type === 'select') {
            const select = box.querySelector('select'), present = new Set([...select.options].map(o => o.value));
            for (const [v, l] of options) if (!present.has(String(v))) select.add(new Option(l ?? v, v));
          } else if (f.type === 'checks') {
            const list = box.querySelector('.eco-checks > div'), present = new Set([...list.querySelectorAll('input')].map(i => i.value));
            const added = options.filter(([v]) => !present.has(String(v)));
            if (added.length) list.querySelector('.eco-help')?.remove();
            for (const [v, l] of added) list.insertAdjacentHTML('beforeend', `<label><input type="checkbox" name="${esc(f.name)}" value="${esc(v)}"><span>${esc(l ?? v)}</span></label>`);
          } else {
            const input = box.querySelector('input'), id = `f-${f.name}-more`;
            let list = box.querySelector('datalist');
            if (!list) { list = document.createElement('datalist'); list.id = id; box.querySelector('label').append(list); input.setAttribute('list', id); }
            const present = new Set([...list.options].map(o => o.value));
            for (const [v, l] of options) if (!present.has(String(v))) { const o = document.createElement('option'); o.value = v; if (l) o.label = l; list.append(o); }
          }
        }, () => box?.classList.remove('eco-more'));
      }
      if (conditional.length) { formEl.addEventListener('input', applyConditions); formEl.addEventListener('change', applyConditions); applyConditions(); }
      if (onChange) { const changed = () => onChange(readValues(), formEl); formEl.addEventListener('input', changed); formEl.addEventListener('change', changed); changed(); }
      formEl.addEventListener('keydown', event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); formEl.requestSubmit(); } });
      formEl.addEventListener('submit', async event => {
        event.preventDefault();
        const values = readValues();
        error.textContent = '';
        if (submit) {
          working = true; d.close();
          const overlay = busy({title: busyText || title + '…'});
          formDepth++; lastError = null;
          let message;
          try { message = await submit(values, d); } catch (e) { message = e.message; } finally { formDepth--; overlay.end(); working = false; }
          if (message) {
            const e = lastError?.error;
            if (e) error.innerHTML = esc([e.message, e.hint].filter(Boolean).join('\n')) + detailHtml(e, detailText(e.details)); else error.textContent = message;
            lastError = null; d.showModal(); return;
          }
        }
        result = values; d.close();
      });
      // The close event comes later than close(): when submit failed at once, the form is open again by then.
      d.addEventListener('close', () => { if (working || d.open) return; d.remove(); resolve(result); });
      document.body.append(d); d.showModal();
      const first = fields.find(f => f.focus);   // {focus: true}: the field to type in first (otherwise the first one)
      (first ? formEl.elements[first.name] : formEl.querySelector('input:not([type=checkbox]):not([type=radio]), textarea, select'))?.focus();
      d.formEl = formEl;
    });
  }

  // Busy overlay ("ぐるぐる"): a spinning ring, what is being done, and the elapsed seconds.
  // Returns {end(), done(text), progress(lines)}; done() shows a check mark and the time it took before closing.
  // progress(lines) shows what the command reports as it goes: the last line is the work now, the ones before are done.
  function busy({title = '実行しています…', sub = '', steps = [], delay = 0} = {}) {
    const el = document.createElement('div'); el.className = 'eco-busy'; el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite');
    el.innerHTML = `<div class="eco-busy-card"><div class="eco-ring" aria-hidden="true"><span class="ring"></span><span class="ring-check">✓</span></div>
      <h2>${esc(title)}</h2>${sub ? `<p class="eco-busy-sub">${esc(sub)}</p>` : ''}${steps.length ? `<ol class="eco-busy-steps">${steps.map(x => `<li>${esc(x)}</li>`).join('')}</ol>` : ''}<ol class="eco-busy-live"></ol>
      <p class="eco-busy-time"><span>0</span> 秒経過</p></div>`;
    const started = Date.now(), seconds = () => Math.floor((Date.now() - started) / 1000);
    const timer = setInterval(() => { el.querySelector('.eco-busy-time span').textContent = seconds(); }, 1000);
    const show = setTimeout(() => document.body.append(el), delay);
    const end = () => { clearTimeout(show); clearInterval(timer); el.remove(); };
    const done = text => new Promise(resolve => {
      clearInterval(timer); clearTimeout(show); document.body.append(el); el.classList.add('done');
      el.querySelector('h2').textContent = text; el.querySelector('.eco-busy-time').textContent = `${seconds()} 秒かかりました`;
      setTimeout(() => { el.remove(); resolve(); }, 1100);
    });
    const progress = lines => {
      el.querySelector('.eco-busy-live').innerHTML = lines.map((line, index) =>
        `<li class="${index === lines.length - 1 ? 'now' : 'past'}">${esc(line)}</li>`).join('');
    };
    return {end, done, progress};
  }

  // The account at the bottom of the left menu (the hub and the module screen): the GitHub login, as in Teams.
  // Clicking it opens the account settings (accountSettings).
  function showAccount(me) {
    const box = document.getElementById('nav-account'); if (!box) return;
    box.querySelector('.nav-avatar').textContent = (me[0] || '?').toUpperCase();
    box.querySelector('.nav-account-name').textContent = me || '（取得できませんでした）';
    box.title = (me ? `ログイン中のGitHubアカウント：${me}` : 'GitHubのアカウントを取得できませんでした（gh auth login）') + '（クリックでアカウントの設定）';
  }
  document.addEventListener('DOMContentLoaded', () => {
    const box = document.getElementById('nav-account'); if (!box) return;
    box.setAttribute('role', 'button'); box.tabIndex = 0;
    box.addEventListener('click', () => accountSettings());
    box.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); accountSettings(); } });
    info().then(i => showAccount(i.me || ''));
  });

  // Account settings: the GitHub login (gh: log in with another account, switch, the permissions it has), the author of
  // commits (git: ecobuild setup --name/--email) and the default owner of new modules (ecobuild config owner).
  // The login and the permissions come from GitHub (account: ecobuild has no command for them); the rest from ecobuild.
  const SCOPES = [['repo', 'リポジトリの読み書き', ''], ['project', 'タスク管理（GitHub Projects）', 'project'],
    ['workflow', 'CI のワークフローの変更', 'workflow'], ['delete_repo', 'リポジトリの削除', 'delete_repo']];
  async function accountSettings() {
    let d = null;
    const body = () => d?.querySelector('.eco-body');
    const render = async () => {
      if (!body()) return;
      body().innerHTML = loading('アカウントの情報を読み込んでいます…');
      const [account, doctor, config] = await Promise.all([call('account').catch(() => ({login: ''})),
        cli(null, ['doctor'], {quiet: true}), cli(null, ['config', 'list'], {quiet: true})]);
      if (!body()) return;
      showAccount(account.login || '');
      const item = name => (doctor.ok ? doctor.result.items : []).find(i => i.name === name);
      const author = item('git の名前・メール'), [, name = '', email = ''] = (author?.ok && /^(.*?)\s*<(.*)>$/.exec(author.detail)) || [];
      const owner = config.ok ? config.result.owner || '' : '';
      const scopes = new Set(account.scopes || []);
      const me = account.login;
      body().innerHTML = `<div class="eco-account-head"><span class="eco-account-avatar" aria-hidden="true">${esc((me[0] || '?').toUpperCase())}</span>
          <div><div class="eco-account-name">${esc(me || 'ログインしていません')}</div><div class="eco-help">${me ? esc(account.name ? account.name + '・GitHub アカウント' : 'GitHub アカウント') : 'GitHub CLI（gh）にログインしてください'}</div></div>
          ${account.url ? `<button type="button" data-account="profile">GitHub で開く</button>` : ''}</div>
        <section class="eco-account-part"><h3>GitHub のログイン</h3>
          <p class="eco-help">ECOBuild は GitHub CLI（gh）のログインを使います。ターミナルが開き、ブラウザで承認します。</p>
          <div class="eco-account-buttons"><button type="button" data-account="login">${me ? '別のアカウントでログイン' : 'ログイン'}</button>${me ? '<button type="button" data-account="switch">ログイン済みのアカウントに切り替える</button>' : ''}</div></section>
        ${me ? `<section class="eco-account-part"><h3>権限</h3><ul class="eco-account-list eco-account-scopes">${SCOPES.map(([scope, text, add]) => `<li><span>${esc(text)}<small>${esc(scope)}</small></span>
          ${scopes.has(scope) ? '<span class="eco-account-ok">あります</span>' : add ? `<button type="button" data-scope="${esc(add)}">権限を追加</button>` : '<span class="eco-account-no">ありません</span>'}</li>`).join('')}</ul></section>` : ''}
        <section class="eco-account-part"><h3>コミットの作成者</h3><ul class="eco-account-list"><li><span>${author?.ok ? `${esc(name)}<small>${esc(email)}</small>` : `未設定<small>${esc(author?.hint || '')}</small>`}</span>
          <button type="button" data-account="author">変更</button></li></ul></section>
        <section class="eco-account-part"><h3>新しいモジュールの所有者</h3><ul class="eco-account-list"><li><span>${owner ? esc(owner) : `ログイン中のユーザー${me ? `（${esc(me)}）` : ''}`}<small>モジュールの作成・取得で所有者（ユーザー・組織）を指定しなかったとき</small></span>
          <button type="button" data-account="owner">変更</button></li></ul></section>`;
      d.author = {name, email}; d.owner = owner; d.profile = account.url;
    };
    const afterTerminal = text => toast(text + '終わったら「読み直す」を押してください。', 'ok', 8000);
    const onClick = async e => {
      const scope = e.target.closest('[data-scope]')?.dataset.scope, what = e.target.closest('[data-account]')?.dataset.account;
      if (scope) { await call('gh-scope', {scope}).then(() => afterTerminal('ターミナルで権限の追加を承認してください。'), err => toast(err.message, 'bad')); return; }
      if (what === 'profile') window.open(d.profile, '_blank', 'noopener');
      if (what === 'login' || what === 'switch') await call('gh-login', {switch: what === 'switch'}).then(() => afterTerminal('ターミナルで続けてください。'), err => toast(err.message, 'bad'));
      if (what === 'author') {
        const done = await form({title: 'コミットの作成者', intro: 'コミットに記録する名前とメールアドレスです（git のこのPCの設定。すべてのモジュールに共通）。', fields: [
          {name: 'name', label: '名前', value: d.author.name, required: true, focus: true}, {name: 'email', label: 'メールアドレス', type: 'email', value: d.author.email, required: true}], ok: '保存',
          submit: async v => { if (!await run(null, ['setup', '--name', v.name.trim(), '--email', v.email.trim()], {success: 'コミットの作成者を保存しました。'})) return '保存できませんでした。'; }});
        if (done) await render();
      }
      if (what === 'owner') {
        const done = await form({title: '新しいモジュールの所有者', intro: 'モジュールの作成・取得で所有者を指定しなかったときに使う、GitHub のユーザーまたは組織です。空にするとログイン中のユーザーを使います。', fields: [
          {name: 'owner', label: 'GitHub のユーザー名・組織名', value: d.owner, placeholder: '未設定ならログイン中のユーザー', focus: true}], ok: '保存',
          submit: async v => { const owner = v.owner.trim(); if (!await run(null, owner ? ['config', 'set', 'owner', owner] : ['config', 'unset', 'owner'], {success: owner ? `既定の所有者を ${owner} にしました。` : 'ログイン中のユーザーを使います。'})) return '保存できませんでした。'; }});
        if (done) await render();
      }
    };
    const closed = dialog({title: 'アカウント', body: '', buttons: [['読み直す', '', 'reload'], ['閉じる', 'primary', null]], onOpen: el => {
      d = el; d.classList.add('eco-account');
      d.querySelector('.eco-body').addEventListener('click', onClick);
      // 「読み直す」: ログインし直した・権限を足した後に。押しても閉じない。
      const reload = [...d.querySelectorAll('.eco-actions button')].find(b => b.textContent === '読み直す');
      reload.addEventListener('click', e => { e.stopImmediatePropagation(); render(); }, {capture: true});
      render();
    }});
    await closed;
  }
  // Submissions (PRs): how one reads, what each action on it does (shown on the pointer), and its details — the same in
  // the workspace's 提出 and the module's ブランチ.
  const submissionText = s => !s ? '未提出' : s.state === 'merged' ? (s.partial ? '中間提出は取り込み済み' : '取り込み済み')
    : s.state === 'closed' ? '取り下げ済み' : `${s.draft ? '下書きの' : ''}${s.partial ? '中間提出' : '提出'}中`;
  const SUBMISSION_HELP = {
    refresh: 'GitHubから、この提出の最新の状態（レビュー・コメント・CI）を読み直します。',
    diff: 'このタスクブランチと作成元との差分（取り込むと入る変更）を見ます。',
    comment: '提出にコメントを書きます。',
    task: 'タスク管理で、このタスクを開きます。',
    submit: '提出：PR を出して、見てもらえるようにします。確認（ビルド・テスト）をしてから Push します。「取り込まれたらタスクを完了する」なら取り込まれたときにタスクを閉じ、外すと閉じずに続けます（中間提出）。提出済みなら、コミットを送り直し、完了するかを変えられます。',
    ready: '下書きの提出を、見てもらえる状態にします。',
    finish: '取り込む：CIの結果を待って、提出（PR）を作成元へ取り込みます。タスクは提出のとおり、閉じるか続けます。',
    withdraw: '取り下げ：提出をやめて作業中に戻します（タスクブランチはそのまま。もう一度提出できます）。',
    'local-review': '手元で確認：提出された変更を手元に取り出し、ビルド・テスト・実行で確かめます（確かめたら承認か差し戻し）。',
    'review-done': '手元での確認をやめて、確認の前の場所へ戻ります（承認も差し戻しもしません）。',
    approve: '承認して取り込む：提出を承認し、そのまま作成元へ取り込みます。タスクは提出のとおり、閉じるか続けます。',
    reject: '差し戻し：直してほしいことを書いて、担当者へ戻します（タスクは作業中に戻ります）。',
    merge: '取り込む：ブランチ同士の提出を、マージコミットで取り込み先へ取り込みます。',
  };
  // What submitting and taking in do, side by side in their dialogs. Whether the task is closed is chosen when submitting
  // (「取り込まれたらタスクを完了する」); the row with a key is rewritten while the dialog is open.
  const outcome = rows => `<dl class="eco-outcome">${rows.map(([k, v, key]) => `<dt>${k}</dt><dd${key ? ` data-outcome="${key}"` : ''}>${v}</dd>`).join('')}</dl>`;
  const into = base => '作成元' + (base ? `（${esc(base)}）` : '');
  const CLOSE_TEXT = '閉じて、タスクブランチを片付けます', KEEP_TEXT = '閉じずに続けます（タスクブランチを作成元の最新から作り直します）';
  const taskOutcome = complete => complete ? CLOSE_TEXT : KEEP_TEXT;
  const setTaskOutcome = (formEl, complete) => { const row = formEl.closest('dialog')?.querySelector('[data-outcome="task"]'); if (row) row.textContent = taskOutcome(complete); };
  const submitOutcome = (base, {submitted = false, complete = true} = {}) => outcome([['PR', submitted ? '出している提出に、Push したコミットが加わります' : `${into(base)}へ出します（Push してから）`],
    ['取り込み', '見る人の承認で取り込まれます（自分で取り込むなら、モジュールの「提出」かタスク管理の「取り込む」。取り込めるのは取り込み先のブランチを作った人と管理者）'], ['取り込まれたら', taskOutcome(complete), 'task']]);
  // The take-in dialog (task finish on an open submission), the same wherever it is: resolves to the CLI's arguments
  // after the number, or null. partial: the submission's (the default of 閉じずに続ける).
  async function finishForm({number, base, partial = false}) {
    const v = await form({title: `取り込む：#${number}`,
      intro: outcome([['取り込み', `CI を待って、提出を${into(base)}へ取り込みます`], ['タスク', taskOutcome(!partial), 'task']]),
      fields: [{name: 'subject', label: '取り込むコミットの件名（空ならタスクの題名）'}, {name: 'ignore', label: 'CIが失敗していても取り込む', type: 'checkbox'},
        {name: 'complete', label: 'タスクを完了する（外すと、取り込んだ後も閉じずに続ける）', type: 'checkbox', value: !partial}], ok: '取り込む',
      onChange: (values, formEl) => setTaskOutcome(formEl, values.complete)});
    return v ? [...(v.subject ? ['--subject', v.subject] : []), ...(v.ignore ? ['--ignore-checks'] : []), v.complete ? '--complete' : '--partial'] : null;
  }
  // Completing a task (task finish --complete), from 完了にする in task management: what is not taken in yet (an open
  // submission, commits not submitted) is taken in first. Resolves to the CLI's arguments after the number, or null.
  async function completeForm({number, submitted, base}) {
    const v = await form({title: `完了にする：#${number}`,
      intro: outcome([['取り込み', submitted ? `出している提出を、CI を待って${into(base)}へ取り込みます` : `まだ取り込んでいない変更があれば、提出して${into(base)}へ取り込みます（なければ取り込みません）`],
        ['タスク', CLOSE_TEXT]]),
      fields: [{name: 'ignore', label: 'CIが失敗していても完了する', type: 'checkbox'}], ok: '完了にする'});
    return v ? ['--complete', ...(v.ignore ? ['--ignore-checks'] : [])] : null;
  }
  // The account's role in a module (account show: GitHub's permission): 管理 is for admins; a submission is handled
  // (approved, sent back, taken in) by whoever made the branch it goes into, and admins (the default branch: admins).
  // Not known (an older ecobuild, offline): nothing is greyed — the CLI checks anyway.
  const access = dir => query(dir, ['account', 'show']).then(d => d.ok ? d.result : null, () => null);
  const isAdmin = a => !a || !!a.admin;
  const creatorOf = (a, base) => base && base !== a?.default_base ? a?.creators?.[base] || '' : '';
  const canTakeIn = (a, base) => !a || a.admin || (!!creatorOf(a, base) && creatorOf(a, base).toLowerCase() === a.login.toLowerCase());
  const takeInNote = (a, base) => `${base} への提出を処理できるのは、${creatorOf(a, base) ? `${base} を作った ${creatorOf(a, base)} と` : ''}管理者だけです`;
  const ADMIN_NOTE = '管理者だけが行えます';
  const ROLE_NAMES = {read: '読む', triage: 'タスクの整理', write: '書き込み', maintain: '管理の一部', admin: '管理者'};
  // A button for an action on a submission (data-pr-action): its help as the title, a note after it (why it is off etc.).
  function submissionButton(action, label, {enabled = true, kind = '', note = ''} = {}) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label; b.disabled = !enabled; b.dataset.prAction = action === 'review-done' ? 'local-review' : action;
    b.title = (SUBMISSION_HELP[action] || '') + (note ? `\n（${note}）` : '');
    if (kind) b.className = kind;
    return b;
  }
  const checkMark = c => c.status !== 'completed' ? '<span class="check-wait">実行中</span>' : ['success', 'skipped', 'neutral'].includes(c.conclusion) ? '<span class="check-ok">成功</span>' : `<span class="check-bad">${esc(c.conclusion || '失敗')}</span>`;
  // The commits a submission takes in (task status: on the task branch, not on its base; newest first, "sha subject").
  // An older ecobuild does not say: nothing is shown then.
  function submissionCommits(commits) {
    if (!Array.isArray(commits)) return '';
    if (!commits.length) return '<p class="sub-commits-none">提出に入るコミットはありません（作成元と同じです）。</p>';
    return `<div class="sub-commits"><div class="sub-commits-head">提出に入るコミット（${commits.length}件、新しい順）</div><ul>${commits.map(c => {
      const [sha, ...subject] = c.split(' ');
      return `<li><code>${esc(sha)}</code> ${esc(subject.join(' '))}</li>`;
    }).join('')}</ul></div>`;
  }
  // The details of a task's submission (task status): state, branch, assignees, CI, reviews and comments.
  // note: added after the state (HTML).
  function submissionDetail(t, {own = false, note = ''} = {}) {
    const sub = t.pull_request, open = sub?.state === 'open';
    const a = t.activity || {reviews: [], comments: [], checks: [], mergeable: ''};
    const mergeable = {MERGEABLE: '取り込めます', CONFLICTING: '衝突があります（タスクブランチで最新を取り込んで解決してください）', UNKNOWN: '確認中'}[a.mergeable] || a.mergeable;
    return `<dl>
      <dt>タスク</dt><dd><strong>#${t.number} ${esc(t.title)}</strong></dd>
      <dt>提出</dt><dd>${esc(submissionText(sub))}${open ? ' · ' + esc(mergeable) : ''}${note}</dd>
      <dt>タスクブランチ</dt><dd>${esc(t.branch || `task/${t.number}`)}${t.base ?` → ${esc(t.base)}` : ''}</dd>
      <dt>担当者</dt><dd>${esc(t.assignees.join(', ') || 'なし')}${own ? '（自分）' : ''}</dd>
      <dt>CI</dt><dd>${a.checks.length ? a.checks.map(c => `${esc(c.name)}：${checkMark(c)}`).join('<br>') : 'なし'}</dd>
      ${sub ? `<dt>URL</dt><dd>${esc(sub.url)}</dd>` : ''}</dl>
    ${submissionCommits(t.commits)}
    ${a.reviews.map(r => `<div class="entry"><b>${esc(r.author)}</b> · ${esc({APPROVED: '承認', CHANGES_REQUESTED: '差し戻し', COMMENTED: 'コメント'}[r.state] || r.state)}${r.body ? '\n' + esc(r.body) : ''}</div>`).join('')}
    ${a.comments.map(c => `<div class="entry"><b>${esc(c.author)}</b>\n${esc(c.body)}</div>`).join('')}
    ${(t.comments || []).map(c => `<div class="entry"><b>${esc(c.author)}</b>（タスク）\n${esc(c.body)}</div>`).join('')}`;
  }

  // GUI actions (gui/actions.py) ------------------------------------------------------------------------------------
  // The buttons and the outside (ecobuild gui・MCP, e.g. an AI agent) call the same actions. This window tells the
  // server what it shows (window state: for ecobuild gui windows) and waits for what happens elsewhere (events): a
  // command run by an agent or another window shows here, and an agent can move this window or open things from it.
  const windowId = (() => { try { if (window.top !== window && window.top.ECO?.windowId) return window.top.ECO.windowId; } catch (e) { /* other origin */ }
    return Math.random().toString(36).slice(2, 10); })();
  const top = window.top === window;
  // kind: the hub, a module's window, or a tool window (log.html・panel.html: never the place to open the hub or a module).
  const windowState = {id: windowId, kind: /module\.html$/.test(location.pathname) ? 'module' : /log\.html$/.test(location.pathname) || /panel\.html$/.test(location.pathname) ? 'tool' : 'hub', module: params.get('path') || params.get('module') || undefined, title: document.title,
                       focused_at: top && document.hasFocus() ? Date.now() / 1000 : undefined};
  let stateTimer = null;
  const topState = () => { try { if (!top) return window.top.ECO?.windowState; } catch (e) { /* other origin */ } return windowState; };
  function setState(partial) {
    if (!top) { try { window.top.ECO?.setState(partial); } catch (e) { /* other origin */ } return; }
    Object.assign(windowState, partial);
    clearTimeout(stateTimer);
    stateTimer = setTimeout(() => call('window-state', {window: windowState}).catch(() => {}), 150);
  }
  // When the window came to the front (a frame inside it too): the one the person looks at is the latest (ecobuild gui windows)
  window.addEventListener('focus', () => setState({focused_at: Date.now() / 1000}));
  const changeHandlers = [], navigateHandlers = [];
  const onChange = fn => changeHandlers.push(fn);       // fn(event): something ran elsewhere (refresh what is shown)
  const onNavigate = fn => navigateHandlers.push(fn);   // fn({page, tab, task, command}): go there in this window
  // Opens a GUI page (module.html?path=…#…, log.html?…) as its own app window: Electron opens window.open as a window
  // (also from a page inside the window, as the workspace's frame), otherwise the server starts it (Edge).
  // features: where and how large (left=…,top=…,width=…,height=…: a panel dragged out opens where it was dropped).
  function openPage(page, features = '') {
    const electron = window.ecobuildShell || (() => { try { return window.top.ecobuildShell; } catch (e) { return null; } })();
    if (electron) return Promise.resolve(window.open(page, '_blank', features));
    return call('open-window', {page}).catch(() => window.open(page, '_blank'));
  }
  async function apply(effect) {
    if (effect.navigate) for (const fn of navigateHandlers) fn(effect.navigate);
    if (effect['open-window']) await openPage(effect['open-window']);
    if (effect.open) await call('open', effect.open);
  }
  // An action by name (actions.py). What happens in this window (open, move) is done here.
  async function action(name, actionParams = {}) {
    const result = await call('action', {name, params: actionParams, origin: windowId, window: topState()});
    if (result?.apply) await apply(result.apply);
    return result;
  }
  const byWhom = e => e.by === 'agent' ? 'エージェント' : '別の画面';
  async function handle(e) {
    const mine = e.target ? e.target === windowId : true;
    if (e.type === 'ran' && e.origin !== windowId) {
      toast(`${byWhom(e)}が実行しました：ecobuild ${e.args.join(' ')}${e.ok ? '' : `（失敗：${e.message || ''}）`}`, e.ok ? 'info' : 'bad', 7000);
      for (const fn of changeHandlers) { try { fn(e); } catch (error) { console.error(error); } }
    } else if (e.type === 'notify') {
      toast(`${e.by === 'agent' ? 'エージェントから' : '知らせ'}：${e.message}`, e.kind || 'info', 12000);
    } else if (mine && e.type === 'navigate') {
      for (const fn of navigateHandlers) fn(e);
      // Electron: the app brings the window up (restored when minimized, in front); window.focus() alone does not.
      if (window.ecobuildShell?.focusWindow) window.ecobuildShell.focusWindow(); else window.focus();
    } else if (mine && e.type === 'open-window') {
      await openPage(e.page);
    } else if (mine && e.type === 'open-path') {
      await call('open', {dir: e.dir, path: e.path, reveal: e.reveal}).catch(error => toast(error.message, 'bad'));
    }
  }
  async function listen() {
    let since = null;
    for (;;) {
      try {
        const answer = await call('events', {since, window: windowState, wait: 20});
        if (since !== null) for (const e of answer.events) await handle(e);
        since = answer.seq;
      } catch (e) { await new Promise(r => setTimeout(r, 3000)); }
    }
  }
  if (top) document.addEventListener('DOMContentLoaded', () => { listen(); });
  // A closed window is forgotten at once (else, for a while, opening its module would move to a window that is gone).
  // keepalive: the request is sent although the page is going away.
  if (top) window.addEventListener('pagehide', () => {
    try {
      fetch('/api/window-closed', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json', 'X-ECOBuild-Token': token},
        body: JSON.stringify({id: windowId})}).catch(() => {});
    } catch (e) { /* the page is gone */ }
  });

  // The left menu's fold button (the hub and the module screen): folded or not is kept on this PC, the same for both.
  const NAV_COLLAPSED_KEY = 'ecobuild-gui-nav-collapsed';
  function navToggle(toggle, target) {
    const set = collapsed => {
      target.classList.toggle('nav-collapsed', collapsed);
      toggle.setAttribute('aria-expanded', String(!collapsed)); toggle.title = collapsed ? 'メニューを展開' : 'メニューを折りたたむ';
    };
    try { set(localStorage.getItem(NAV_COLLAPSED_KEY) === '1'); } catch (e) { /* storage blocked */ }
    toggle.addEventListener('click', () => {
      const collapsed = !target.classList.contains('nav-collapsed'); set(collapsed);
      try { localStorage.setItem(NAV_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (e) { /* storage blocked */ }
    });
  }

  // Context menu: items are [label, action, enabled = true] or '-' for a separator.
  // menuOpener: the button that opened the menu. Pressing it again only closes the menu (the press closes it; the click
  // that follows is swallowed, or it would open it again).
  let openMenu = null, menuOpener = null, lastPressed = null, swallowClick = null;
  function menu(items, x, y) {
    openMenu?.remove();
    const el = document.createElement('div'); el.className = 'eco-menu'; el.setAttribute('role', 'menu');
    for (const item of items) {
      if (item === '-') { el.append(document.createElement('hr')); continue; }
      const [text, action, enabled = true, tip = ''] = item;   // tip: shown when the pointer is on the item
      if (action === null) { const head = document.createElement('div'); head.className = 'eco-menu-head'; head.textContent = text; el.append(head); continue; }   // a heading of the items below
      const b = document.createElement('button'); b.type = 'button'; b.setAttribute('role', 'menuitem'); b.textContent = text; b.disabled = !enabled; if (tip) b.title = tip;
      b.addEventListener('click', () => { el.remove(); openMenu = null; action(); });
      el.append(b);
    }
    document.body.append(el); openMenu = el; menuOpener = lastPressed?.closest?.('button, summary') || null;
    el.style.left = Math.max(8, Math.min(x, innerWidth - el.offsetWidth - 8)) + 'px';
    el.style.top = Math.max(8, Math.min(y, innerHeight - el.offsetHeight - 8)) + 'px';
    el.querySelector('button:not(:disabled)')?.focus();
  }
  document.addEventListener('pointerdown', e => {
    if (openMenu && !openMenu.contains(e.target)) {
      if (menuOpener?.contains(e.target)) swallowClick = menuOpener;
      openMenu.remove(); openMenu = null;
    }
    lastPressed = e.target;
  }, true);
  document.addEventListener('keydown', () => { lastPressed = null; }, true);   // opened with the keyboard: no opener to watch
  document.addEventListener('click', e => {
    if (swallowClick?.contains(e.target)) { e.stopImmediatePropagation(); e.preventDefault(); }
    swallowClick = null;
  }, true);
  document.addEventListener('keydown', e => {
    if (!openMenu) return;
    if (e.key === 'Escape') { openMenu.remove(); openMenu = null; return; }
    if (['ArrowDown', 'ArrowUp'].includes(e.key)) {
      e.preventDefault(); const items = [...openMenu.querySelectorAll('button:not(:disabled)')], i = items.indexOf(document.activeElement);
      items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
    }
  });
  window.addEventListener('blur', () => { openMenu?.remove(); openMenu = null; });

  // The ⋯ menus made of <details> (a card's or a panel's) close like the menus above: a click outside, Escape, choosing
  // one of their items, another one opening, or the window losing the focus (a click in another frame).
  const POPUPS = 'details.share-more, details.tk-menu, details[data-popup]';
  const closePopups = (except = null) => document.querySelectorAll(POPUPS).forEach(d => { if (d !== except && d.open) d.open = false; });
  document.addEventListener('pointerdown', e => closePopups(e.target.closest?.(POPUPS)));
  document.addEventListener('click', e => {
    const popup = e.target.closest?.(POPUPS);
    if (popup && e.target.closest('button') && !e.target.closest('summary')) setTimeout(() => { popup.open = false; });
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const open = [...document.querySelectorAll(POPUPS)].find(d => d.open);
    if (open) { open.open = false; open.querySelector('summary')?.focus(); }
  });
  document.addEventListener('toggle', e => { if (e.target.matches?.(POPUPS) && e.target.open) closePopups(e.target); }, true);
  window.addEventListener('blur', () => closePopups());

  // Which Visual Studio opens the solution: chosen next to the button, kept per PC; 2026 by default.
  const VS_KEY = 'ecobuild-gui-vs';
  function vsVersion() { try { return localStorage.getItem(VS_KEY) || '2026'; } catch (e) { return '2026'; } }
  function setVsVersion(version) { try { localStorage.setItem(VS_KEY, version); } catch (e) { /* storage blocked */ } }
  // Open the place's solution in Visual Studio (the GUI does this; ecobuild has no such command).
  // The solution is made by a build (cpp), so when there is none yet, offer to build first.
  async function openInVisualStudio(dir, {build, version = vsVersion()} = {}) {
    let opened;
    try { opened = await action('vs', {dir, version}); } catch (e) { toast(e.message, 'bad', 9000); return false; }
    if (!opened.solution) {
      if (!await confirm({title: `Visual Studio ${version} で開く`, message: 'ソリューション（.sln／.slnx）がまだありません（ビルドすると作成されます）。ビルドしてから開きますか？', ok: 'ビルドして開く'})) return false;
      const doc = build ? await build() : await run(dir, ['build'], {busy: 'ビルドしています…'});
      if (!doc) return false;
      try { opened = await action('vs', {dir, version}); } catch (e) { toast(e.message, 'bad', 9000); return false; }
      if (!opened.solution) { toast('ビルドしましたが、ソリューションが見つかりませんでした（このモジュールの型ではソリューションが作成されない可能性があります）。', 'bad', 8000); return false; }
    }
    toast(`Visual Studio ${version} で開きます：` + opened.solution.split('/').pop());
    return true;
  }

  // The module's type (module-defaults: read from .ecobuild/ecobuild.toml, without waiting for GitHub) and what the screens
  // offer for it: the commands differ by type (ecobuild --help in the module). A type the GUI does not know gets the
  // commands every type has (build・test・run・clean with a configuration, profile add with a configuration).
  const TYPES = {
    cpp: {configurations: ['Debug', 'Release', 'RelWithDebInfo', 'MinSizeRel'], projects: true, solution: true, templates: true,
      configurationHelp: {Debug: '開発用（最適化なし・デバッグ情報あり）', Release: '配布用（速さ優先で最適化）',
        RelWithDebInfo: 'Release＋デバッグ情報', MinSizeRel: '小ささ優先で最適化'}},
    python: {configurations: ['Debug', 'Release'], parallel: true, fileTests: true,
      configurationHelp: {Debug: '開発用（.venv に編集可能で入れる）', Release: '配布用（wheel・sdist も作る）'}},
    generic: {configurations: ['Debug', 'Release'],
      configurationHelp: {Debug: '開発用', Release: '配布用'}},
  };
  const types = new Map();
  function moduleType(dir) {
    if (!types.has(dir)) types.set(dir, call('module-defaults', {dir}).then(d => d.type || '').catch(() => ''));
    return types.get(dir);
  }
  const typeFeatures = type => TYPES[type] || {configurations: ['Debug', 'Release']};

  // Splits text into command arguments for comma lists.
  const commaList = text => String(text || '').split(',').map(s => s.trim()).filter(Boolean);

  // The name of a task branch (task/<n>-<name>), as ecowork's branch_label: Japanese stays as it is; what git or
  // Windows cannot take becomes "-". branchNameError: why a name typed cannot be used ('' if it can).
  const branchLabel = title => {
    let label = String(title || '').replace(/[\s~^:?*[\]\\/"<>|\x00-\x1f\x7f]+|\.{2,}|@\{/g, '-').replace(/-{2,}/g, '-').replace(/^[-.]+|[-.]+$/g, '');
    while (label.endsWith('.lock')) label = label.slice(0, -5).replace(/[-.]+$/, '');
    return label;
  };
  const branchNameError = name => !name.trim() ? 'タスクブランチの名前を入力してください。'
    : branchLabel(name.trim()) !== name.trim() ? 'タスクブランチの名前に使えない文字があります（空白と ~ ^ : ? * [ ] \\ / " < > | と「..」）。' : '';
  // The task number of a task branch (task/<n> or task/<n>-<name>), or null.
  const taskOfBranch = name => { const m = /^task\/(\d+)(?:-.+)?$/.exec(name || ''); return m ? Number(m[1]) : null; };

  let infoPromise;
  const info = () => (infoPromise ||= call('info').catch(() => ({me: ''})));
  // The server runs in the background and ends when no window has contacted it for a while: tell it this window is open.
  // (In Electron the server ends with the app instead.)
  if (window.parent === window && !window.ecobuildShell) setInterval(() => call('ping').catch(() => {}), 20000);
  // The server keeps the code it started with; after the GUI is updated it must be restarted.
  document.addEventListener('DOMContentLoaded', () => info().then(i => {
    if (!i.stale || window.parent !== window) return;
    const bar = document.createElement('div'); bar.className = 'eco-stale'; bar.setAttribute('role', 'alert'); bar.textContent = i.stale;
    document.body.prepend(bar);
  }));

  const loading = text => `<div class="eco-loading"><span class="eco-spinner"></span>${esc(text || '読み込んでいます…')}</div>`;

  return {call, cli, run, showError, offerUnarchive, dialog, confirm, form, output, inTortoiseGit, toast, esc, localTime, commaList, branchLabel, branchNameError, taskOfBranch, info, loading, detailText, colorDiff, diffHtml, copyText, params, busy, menu, openInVisualStudio, vsVersion, setVsVersion, moduleType, typeFeatures, navToggle, query, prefetch, action, setState, onChange, onNavigate, openPage, windowId, windowState,
    access, isAdmin, canTakeIn, takeInNote, adminNote: ADMIN_NOTE, roleNames: ROLE_NAMES,
    submissionText, checkMark, submissionHelp: SUBMISSION_HELP, submitOutcome, setTaskOutcome, finishForm, completeForm, submissionButton, submissionDetail, submissionCommits};
})();
// The pages inside a window (the workspace's frame) use the window's ECO: the same window id for the actions.
window.ECO = ECO;
