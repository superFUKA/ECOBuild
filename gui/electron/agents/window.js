'use strict';
// エージェントの窓の画面：タブ（番号・名前・状態）と、タブごとの端末（xterm.js）。表示するのは選んでいるタブだけ。
// タブのダブルクリックで名前を変え、ドラッグで並べ替え、右クリックで「新しい窓へ」「起動し直す」「続きから起動し直す」「閉じる」。
// 下のバー：状態・モデル・コンテキスト・使用量の制限の残り（5時間・週。20% 以下で黄、5% 以下で赤）・場所。
// ☰：すべてのタブの一覧（状況・最後の出力2行・入力中の文字）。⚙：返答の知らせ方。
// 端末：Ctrl+= / Ctrl+- / Ctrl+0 で文字の大きさ、Ctrl+Shift+C で選んだところをコピー、Ctrl+V で貼り付け。
const $ = id => document.getElementById(id);
const terms = new Map();     // id → {term, fit, el}
let tabs = [], active = null, fontSize = 14;
const STATE_LABELS = {thinking: '考え中', waiting: '裏で実行中', choice: '選択肢', idle: '待機中', starting: '起動中', exited: '終了',
                      listening: '聞き取り中'};
const TOPMOST_LABELS = {always: '常に', auto: '自動', off: 'オフ'};

function makeTerm(info, history) {
  const el = document.createElement('div'); el.className = 'screen'; el.hidden = true; $('screens').append(el);
  const term = new Terminal({fontFamily: 'Cascadia Mono, Consolas, "BIZ UDGothic", monospace', fontSize, cursorBlink: true,
    scrollback: 5000, allowProposedApi: true, theme: {background: '#14181d', foreground: '#edf1f5'}});
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit); term.open(el);
  term.onData(data => agents.input(info.id, data));
  term.attachCustomKeyEventHandler(event => keys(event, term));
  if (history) term.write(history);
  terms.set(info.id, {term, fit, el});
}

function keys(event, term) {
  if (event.type !== 'keydown') return true;
  if (event.ctrlKey && event.shiftKey && event.code === 'KeyC') { navigator.clipboard.writeText(term.getSelection()); return false; }
  if (event.ctrlKey && !event.shiftKey && event.code === 'KeyV') {
    navigator.clipboard.readText().then(text => text && term.paste(text)); return false;
  }
  if (event.ctrlKey && ['Equal', 'Minus', 'Digit0', 'NumpadAdd', 'NumpadSubtract'].includes(event.code)) {
    fontSize = event.code === 'Digit0' ? 14 : Math.max(9, Math.min(28, fontSize + (/Equal|Add/.test(event.code) ? 1 : -1)));
    for (const t of terms.values()) t.term.options.fontSize = fontSize;
    fitActive(); return false;
  }
  return true;
}

function fitActive() {
  const t = terms.get(active); if (!t || t.el.hidden) return;
  try { t.fit.fit(); agents.resize(active, t.term.cols, t.term.rows); } catch (e) { /* not shown yet */ }
}

function show(id) {
  active = id;
  for (const [key, t] of terms) t.el.hidden = key !== id;
  $('empty').hidden = terms.size > 0;
  requestAnimationFrame(() => { fitActive(); terms.get(id)?.term.focus(); });
  renderTabs();
}

function renderTabs() {
  const bar = $('tabs'); bar.replaceChildren();
  for (const info of tabs) {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'tab ' + (info.state || ''); b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', String(info.id === active)); b.draggable = true; b.dataset.id = info.id;
    b.title = `${info.num}  ${info.name}（${STATE_LABELS[info.state] || info.state}）\n${info.dir}`;
    b.innerHTML = `<span class="num"></span><span class="name"></span><span class="x" title="閉じる" aria-label="閉じる">×</span>`;
    b.querySelector('.num').textContent = info.kind === 'operator' ? '◆' : info.num; b.querySelector('.name').textContent = info.name;
    if (info.kind === 'operator') b.querySelector('.x').title = '裏に戻す（オペレーターは止めません）';
    b.addEventListener('click', event => {
      if (event.target.classList.contains('x')) return closeTab(info);
      agents.select(info.id); show(info.id);
    });
    b.addEventListener('dblclick', () => rename(b, info));
    b.addEventListener('contextmenu', event => { event.preventDefault(); tabMenu(info, event.clientX, event.clientY); });
    b.addEventListener('dragstart', event => { b.classList.add('dragging'); event.dataTransfer.setData('text/plain', String(info.id)); });
    b.addEventListener('dragend', () => b.classList.remove('dragging'));
    b.addEventListener('dragover', event => event.preventDefault());
    b.addEventListener('drop', event => {
      event.preventDefault();
      const moved = Number(event.dataTransfer.getData('text/plain')); if (!moved || moved === info.id) return;
      const ids = tabs.map(t => t.id).filter(id => id !== moved);
      ids.splice(ids.indexOf(info.id), 0, moved);
      agents.reorder(ids);
    });
    bar.append(b);
  }
  const current = tabs.find(t => t.id === active);
  document.body.classList.toggle('listening', current?.state === 'listening');
  $('voice').classList.toggle('on', current?.state === 'listening');
  renderStatus(current);
}

// 下のバー
function renderStatus(current) {
  const bar = $('status'); bar.replaceChildren();
  document.title = current ? `${current.num} ${current.name} - エージェント` : 'エージェント - ECOBuild';
  if (!current) return;
  const add = (text, cls = '', title = '') => { const s = document.createElement('span'); s.textContent = text; if (cls) s.className = cls; if (title) s.title = title; bar.append(s); return s; };
  const info = current.info || {};
  add(STATE_LABELS[current.state] || '');
  if (info.model) add(info.model + (info.context != null ? ` · ctx ${Math.round(info.context)}%` : ''));
  for (const [label, limit] of [['5時間', info.fiveHour], ['週', info.weekly]]) {
    if (!limit) { add(`${label} —`, '', '使用量の制限は、Claude が最初に返答した後に届きます'); continue; }
    const cls = limit.remaining <= 5 ? 'bad' : limit.remaining <= 20 ? 'warn' : '';
    add(`${label} 残り ${limit.remaining}%`, cls, limit.resetsAt ? `リセット：${resetText(limit.resetsAt)}` : '');
  }
  add('', 'gap');
  if (ringState?.enabled) {
    const ok = ringState.online && ringState.connected;
    add(`リング ${ok ? '●' : '○'}${ringState.battery != null ? ` 🔋${ringState.battery}%` : ''}`, 'ring ' + (ok ? 'ok' : 'off'), ringState.message || '');
    if (ringState.mode === 'operator') add('オペレーターモード', 'mode-op');
    if (ringState.choosing) add('選択モード（上下左右で選んで押し込みで決定）', 'mode-op');
  }
  add(current.dir, 'where', current.dir);
}
let ringState = null;

function resetText(seconds) {
  const at = new Date(seconds * 1000), hours = Math.max(0, (at - Date.now()) / 3600000);
  const day = at.toDateString() === new Date().toDateString() ? '今日' : `${at.getMonth() + 1}/${at.getDate()}`;
  return `${day} ${at.getHours()}:${String(at.getMinutes()).padStart(2, '0')}（あと ${hours < 1 ? Math.round(hours * 60) + ' 分' : Math.round(hours) + ' 時間'}）`;
}

function rename(button, info) {
  const input = document.createElement('input'); input.value = info.name;
  button.querySelector('.name').replaceWith(input); input.focus(); input.select();
  const done = save => { if (save && input.value.trim()) agents.rename(info.id, input.value.trim()); renderTabs(); };
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') done(true); else if (event.key === 'Escape') done(false);
    event.stopPropagation();
  });
  input.addEventListener('blur', () => done(true));
  input.addEventListener('click', event => event.stopPropagation());
}

function closeTab(info) {
  if (info.kind === 'operator') { agents.closeTab(info.id); return; }   // 裏に戻す
  if (!info.exited && !confirm(`${info.num}  ${info.name} のエージェントを終わらせて閉じますか？`)) return;
  agents.closeTab(info.id);
}

function tabMenu(info, x, y) {
  const menu = $('menu'); menu.replaceChildren();
  const items = [['名前を変える', () => rename($('tabs').querySelector(`[data-id="${info.id}"]`), info)],
                 ['新しい窓へ', () => agents.newWindow(info.id)],
                 ['起動し直す（新しい会話）', () => agents.restart(info.id)],
                 ['続きから起動し直す（前の会話の続き）', () => agents.restart(info.id, true)],
                 ['閉じる', () => closeTab(info)]];
  for (const [label, action] of items) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
    b.addEventListener('click', () => { menu.hidden = true; action(); }); menu.append(b);
  }
  menu.hidden = false;
  menu.style.left = Math.min(x, innerWidth - menu.offsetWidth - 8) + 'px'; menu.style.top = Math.min(y, innerHeight - menu.offsetHeight - 8) + 'px';
}
document.addEventListener('click', event => { if (!$('menu').contains(event.target)) $('menu').hidden = true; });

agents.onAdopt((info, history) => { if (!terms.has(info.id)) makeTerm(info, history); });
agents.onRelease(id => { terms.get(id)?.term.dispose(); terms.get(id)?.el.remove(); terms.delete(id); if (active === id) active = null; });
agents.onReset(id => terms.get(id)?.term.reset());
agents.onData((id, data) => terms.get(id)?.term.write(data));
agents.onExit((id, code) => terms.get(id)?.term.write(`\r\n\x1b[90m（エージェントが終わりました：終了コード ${code}。右クリックの「起動し直す」でまた始められます）\x1b[0m\r\n`));
agents.onSelect(id => show(id));
agents.onTabs(({tabs: list, active: selected}) => {
  tabs = list;
  if (selected && selected !== active && terms.has(selected)) show(selected); else renderTabs();
  $('empty').hidden = terms.size > 0;
});
agents.onTopmost(mode => {
  $('topmost-label').textContent = TOPMOST_LABELS[mode] || mode;
  $('topmost').title = `最前面：${TOPMOST_LABELS[mode]}（押すと 常に → 自動 → オフ。自動は返答が届いたときだけ前に出ます）`;
  $('topmost').classList.toggle('on', mode !== 'off');
});
$('topmost').addEventListener('click', () => agents.topmost());
$('minimize').addEventListener('click', () => agents.minimize());
$('close').addEventListener('click', () => agents.closeWindow());
new ResizeObserver(() => fitActive()).observe($('screens'));
agents.ready();

// ---- タブの一覧（☰） ----------------------------------------------------------------------------------
let pickerItems = [], pickerIndex = 0, pickerTimer = null;
async function openPicker() {
  closePanels();
  $('picker-panel').hidden = false;
  await refreshPicker();
  pickerIndex = Math.max(0, pickerItems.findIndex(item => item.id === active));
  renderPicker();
  pickerTimer = setInterval(async () => { await refreshPicker(); renderPicker(); }, 1000);
}
async function refreshPicker() { pickerItems = await agents.picker(); }
function renderPicker() {
  const list = $('picker-list'); list.replaceChildren();
  pickerItems.forEach((item, i) => {
    const li = document.createElement('li'); li.className = (item.state || '') + (i === pickerIndex ? ' current' : '');
    li.innerHTML = '<div class="head"><span class="num"></span><span class="name"></span><span class="state"></span></div><pre></pre>';
    li.querySelector('.num').textContent = item.num; li.querySelector('.name').textContent = item.name + (item.mini ? '（最小化中）' : '');
    li.querySelector('.state').textContent = STATE_LABELS[item.state] || item.state;
    li.querySelector('pre').textContent = [item.lines, item.input && '❯ ' + item.input].filter(Boolean).join('\n');
    li.addEventListener('click', () => pick(i));
    list.append(li);
  });
}
function pick(i) { const item = pickerItems[i]; closePanels(); if (item) agents.focusTab(item.id); }
function closePanels() {
  $('picker-panel').hidden = true; $('settings-panel').hidden = true;
  clearInterval(pickerTimer); pickerTimer = null;
}
document.addEventListener('keydown', event => {
  if (!$('picker-panel').hidden) {
    if (event.key === 'Escape') closePanels();
    else if (event.key === 'ArrowDown') { pickerIndex = Math.min(pickerItems.length - 1, pickerIndex + 1); renderPicker(); }
    else if (event.key === 'ArrowUp') { pickerIndex = Math.max(0, pickerIndex - 1); renderPicker(); }
    else if (event.key === 'Enter') pick(pickerIndex);
    else if (/^[1-9]$/.test(event.key)) pick(pickerItems.findIndex(item => item.num === Number(event.key)));
    else return;
    event.preventDefault(); event.stopPropagation(); return;
  }
  if (!$('settings-panel').hidden && event.key === 'Escape') { closePanels(); event.preventDefault(); return; }
  if (event.ctrlKey && event.shiftKey && event.code === 'KeyA') { event.preventDefault(); openPicker(); }
}, true);
$('picker').addEventListener('click', () => ($('picker-panel').hidden ? openPicker() : closePanels()));

// ---- 知らせ方（⚙） ---------------------------------------------------------------------------------------
const HOLD_LABEL = ms => ms === -1 ? '消さない' : ms < 60000 ? `${ms / 1000} 秒` : `${ms / 60000} 分`;
for (const s of ECOSounds.list) { const o = document.createElement('option'); o.value = s.id; o.textContent = s.label; $('notify-sound').append(o); }
agents.onNotify((notify, holds) => {
  for (const r of document.querySelectorAll('#notify-style input')) r.checked = r.value === notify.style;
  $('notify-sound').value = notify.sound; $('notify-volume').value = notify.volume;
  const hold = $('notify-hold'); hold.replaceChildren();
  for (const ms of holds) { const o = document.createElement('option'); o.value = ms; o.textContent = HOLD_LABEL(ms); hold.append(o); }
  hold.value = notify.hold;
});
$('notify-style').addEventListener('change', event => agents.setNotify({style: event.target.value}));
$('notify-sound').addEventListener('change', () => { agents.setNotify({sound: $('notify-sound').value}); agents.testSound(); });
$('notify-volume').addEventListener('change', () => { agents.setNotify({volume: Number($('notify-volume').value)}); agents.testSound(); });
$('notify-hold').addEventListener('change', () => agents.setNotify({hold: Number($('notify-hold').value)}));
$('notify-test').addEventListener('click', () => agents.testSound());
$('settings').addEventListener('click', () => { const open = $('settings-panel').hidden; closePanels(); $('settings-panel').hidden = !open; });
$('settings-close').addEventListener('click', closePanels);

// ---- 音声入力（🎤：録音の開始・停止。Ctrl+Alt+V でも。Ctrl+Alt+↓ で送信、Ctrl+Alt+↑ で消す） ---------------------
$('voice').addEventListener('click', () => { if (active) agents.voice(active); });

// ---- リング（⚙ の中） --------------------------------------------------------------------------------------
agents.onRing(state => {
  ringState = state;
  $('ring-resident').checked = !!state.resident; $('ring-resident').disabled = !state.match;
  $('ring-enabled').checked = !!state.enabled; $('ring-guard').checked = state.guard !== false; $('ring-keepalive').checked = state.keepalive !== false;
  if (document.activeElement !== $('ring-match')) $('ring-match').value = state.match || '';
  $('ring-status').textContent = !state.enabled ? '使っていません' : `${state.message || ''}${state.calibrated === false && state.connected ? '（操作がまだ登録されていません）' : ''}`;
  renderStatus(tabs.find(t => t.id === active));
});
$('ring-enabled').addEventListener('change', () => agents.ringConfig({enabled: $('ring-enabled').checked, match: $('ring-match').value.trim()}));
$('ring-resident').addEventListener('change', () => agents.ringConfig({resident: $('ring-resident').checked}));
$('ring-guard').addEventListener('change', () => agents.ringConfig({guard: $('ring-guard').checked}));
$('ring-keepalive').addEventListener('change', () => agents.ringConfig({keepalive: $('ring-keepalive').checked}));
$('ring-match').addEventListener('change', () => agents.ringConfig({match: $('ring-match').value.trim()}));
$('ring-find').addEventListener('click', async () => {
  $('ring-status').textContent = '探しています…';
  const found = await agents.ringFind();
  if (!found.length) { $('ring-status').textContent = 'Ring II が見つかりませんでした（ペアリング・接続を確かめ、リングを操作して起こしてください）'; return; }
  $('ring-match').value = found[0].match; agents.ringConfig({match: found[0].match});
  $('ring-status').textContent = `見つかりました：${found[0].match}`;
});
$('ring-calibrate').addEventListener('click', () => agents.ringCalibrate(''));
$('ring-calibrate-operator').addEventListener('click', () => agents.ringCalibrate('operator'));
agents.onScroll((id, lines) => terms.get(id)?.term.scrollLines(lines));
agents.onPicker(() => ($('picker-panel').hidden ? openPicker() : closePanels()));
