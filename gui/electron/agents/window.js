'use strict';
// エージェントの窓の画面：タブ（番号・名前・状態）と、タブごとの端末（xterm.js）。表示するのは選んでいるタブだけ。
// タブのダブルクリックで名前を変え、ドラッグで並べ替え、右クリックで「新しい窓へ」「起動し直す」「続きから起動し直す」「閉じる」。
// ヘッダー：タブ（種類の色の番号＋名前。状態は下端の線）・＋（作業空間のエージェントを開く）・☰・🎙・📌・⚙・–・×。
// 進行役の窓には、進行役のタブの隣に「チーム」（AI が起動した作業役を見る。teamui.js）。
// フッター：オペレーターモードの札・状態・モデル・場所・（右寄せで）使用量の制限の残り（5時間・週。20% 以下で黄、5% 以下で赤）・
// リングの丸（緑：つながっている・黄：登録なし・赤：受信係が止まっている）。窓の枠：選んでいる窓は青、オペレーターモードは紫、聞き取り中は赤。
// ☰：すべてのタブの一覧（状況・最後の出力2行・入力中の文字）。⚙：返答の知らせ方とリング。
// 端末：Ctrl+= / Ctrl+- / Ctrl+0 で文字の大きさ、Ctrl+V で貼り付け。コピー：Claude Code の中でドラッグして選ぶ（Claude Code が
// 端末へ OSC 52 でクリップボードに入れるよう頼む）か、Shift を押しながらドラッグして Ctrl+C・Ctrl+Shift+C。右クリックで
// コピー・貼り付け・最後の返答をコピー（返答の全文）。クリップボードは main で扱う。
const $ = id => document.getElementById(id);
const terms = new Map();     // id → {term, fit, el}
let tabs = [], active = null, fontSize = 14;
const STATE_LABELS = {thinking: '考え中', waiting: '裏で実行中', choice: '選択肢', idle: '待機中', starting: '起動中', exited: '終了',
                      listening: '聞き取り中'};
const TOPMOST_LABELS = {always: '常に', auto: '自動', off: 'オフ'};

function makeTerm(info, history) {
  const el = document.createElement('div'); el.className = 'screen'; el.hidden = true; $('screens').append(el);
  const term = new Terminal({fontFamily: 'Cascadia Mono, Consolas, "BIZ UDGothic", monospace', fontSize, cursorBlink: true,
    scrollback: 5000, allowProposedApi: true, theme: {background: '#15171c', foreground: '#d7dae0'}});
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit); term.open(el);
  term.onData(data => agents.input(info.id, data));
  term.attachCustomKeyEventHandler(event => keys(event, term));
  // OSC 52：アプリ（Claude Code）が選んだ文字をクリップボードに入れるよう頼んでくる（"c;<base64>"。"?" は読み出しの頼みで、答えない）
  term.parser.registerOscHandler(52, data => {
    const encoded = data.slice(data.indexOf(';') + 1);
    if (!encoded || encoded === '?') return true;
    try { agents.copy(new TextDecoder().decode(Uint8Array.from(atob(encoded), c => c.charCodeAt(0)))); } catch (e) { /* 壊れた頼み */ }
    return true;
  });
  el.addEventListener('contextmenu', event => { event.preventDefault(); termMenu(info, term, event.clientX, event.clientY); });
  if (history) term.write(history);
  terms.set(info.id, {term, fit, el});
}

function keys(event, term) {
  if (event.type !== 'keydown') return true;
  // Ctrl+Shift+C、選んでいるときの Ctrl+C はコピー（選んでいなければ Ctrl+C はそのまま Claude へ）
  if (event.ctrlKey && event.code === 'KeyC' && (event.shiftKey || term.hasSelection())) {
    if (term.hasSelection()) { agents.copy(term.getSelection()); term.clearSelection(); }
    return false;
  }
  if (event.ctrlKey && !event.shiftKey && event.code === 'KeyV') {
    agents.paste().then(text => text && term.paste(text)); return false;
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
  if (typeof teamClosePane === 'function') teamClosePane();   // 端末のタブを選んだ：チームの表示を閉じる（teamui.js）
  active = id;
  for (const [key, t] of terms) t.el.hidden = key !== id;
  $('empty').hidden = terms.size > 0;
  requestAnimationFrame(() => { fitActive(); terms.get(id)?.term.focus(); });
  renderTabs();
}

function renderTabs() {
  const bar = $('tabs'); bar.replaceChildren();
  for (const info of tabs) {
    const b = document.createElement('button'); b.type = 'button';
    b.className = 'tab' + (info.id === active ? ' active' : '') + (info.exited ? ' exited' : '') + (info.unread && info.id !== active ? ' unread' : '')
      + (info.pinned ? ' pinned' : '');
    b.dataset.state = info.state || '';
    b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(info.id === active)); b.draggable = !info.pinned; b.dataset.id = info.id;
    const role = info.role === 'lead' ? '進行役' : info.role === 'manager' ? '管理役' : info.role === 'worker' ? '作業役' : '';
    b.title = `${info.num}  ${info.name}（${role ? role + '・' : ''}${STATE_LABELS[info.state] || info.state}）\n${info.dir}`
      + (info.pinned ? '\nこの窓の進行役（左端に固定）' : '');
    b.innerHTML = `<b></b><span class="name"></span><span class="x" title="閉じる" aria-label="閉じる">×</span>`;
    b.querySelector('b').textContent = info.kind === 'operator' ? '◆' : info.role === 'lead' ? '進' : info.role === 'manager' ? '管' : info.num;
    b.querySelector('b').dataset.kind = info.role === 'lead' || info.role === 'manager' ? info.role : info.kind;
    const icon = prefs?.icons?.[info.kind === 'operator' ? 'operator' : 'agent'];
    if (icon) { const img = document.createElement('img'); img.className = 'avatar'; img.src = icon; img.alt = ''; b.prepend(img); }
    b.querySelector('.name').textContent = info.name;
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
  if (typeof teamTab === 'function') teamTab(bar);   // 進行役の窓：進行役のタブの隣に「チーム」（teamui.js）
  const current = tabs.find(t => t.id === active);
  document.body.classList.toggle('listening', current?.state === 'listening');
  $('voice').classList.toggle('on', current?.state === 'listening');
  renderStatus(current);
}

// フッター
function renderStatus(current) {
  const bar = $('status'); bar.replaceChildren();
  document.title = current ? `${current.num} ${current.name} - エージェント` : 'エージェント - ECOBuild';
  document.body.classList.toggle('operator', ringState?.enabled && ringState.mode === 'operator');
  renderRingDot();
  if (!current) return;
  const add = (text, cls = '', title = '') => { const s = document.createElement('span'); s.textContent = text; if (cls) s.className = cls; if (title) s.title = title; bar.append(s); return s; };
  const info = current.info || {};
  if (ringState?.choosing) add('選択モード', 'choosing', '上下左右で選んで、押し込みで決定');
  add(STATE_LABELS[current.state] || '', current.state === 'listening' ? 'listening' : '');
  if (info.model) {
    const m = add(info.model + (info.context != null ? ` · ctx ${Math.round(info.context)}%` : ''), 'model', 'クリックでモデルを切り替える');
    m.addEventListener('click', event => { event.stopPropagation(); modelMenu(current, event.clientX, event.clientY); });
  }
  add(current.kind === 'operator' ? 'オペレーター' : shortDir(current.dir), 'where', current.dir);
  let first = true;
  for (const [label, limit] of [['5h', info.fiveHour], ['週', info.weekly]]) {
    const s = !limit ? add(`${label} —`, 'limit', '使用量の制限は、Claude が最初に返答した後に届きます')
      : add(`${label} ${limit.remaining}%`, 'limit' + (limit.remaining <= 5 ? ' bad' : limit.remaining <= 20 ? ' low' : ''),
            `残り ${limit.remaining}%` + (limit.resetsAt ? `。リセット：${resetText(limit.resetsAt)}` : ''));
    if (first) { s.classList.add('right'); first = false; }
  }
  if (ringState?.enabled && ringState.battery != null) add(`🔋${ringState.battery}%`, 'limit' + (ringState.battery <= 10 ? ' bad' : ringState.battery <= 25 ? ' low' : ''), 'リングの電池');
}
let ringState = null;
const shortDir = dir => String(dir || '').replaceAll('\\', '/').split('/').filter(Boolean).slice(-2).join('/');

// リングの丸：緑＝つながっていて登録あり、黄＝つながっているが登録なし・見つからない、赤＝受信係が止まっている
function renderRingDot() {
  const dot = $('ring-dot'), r = ringState;
  dot.hidden = !r?.enabled;
  if (!r?.enabled) return;
  dot.className = 'dot ' + (!r.online ? 'off' : r.connected && r.calibrated ? 'ok' : 'warn');
  dot.title = `リング：${r.message || ''}${r.calibrated === false && r.connected ? '（操作が登録されていません）' : ''}`;
}

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

// 端末の右クリック：コピー（選んでいるとき）・貼り付け・最後の返答をコピー
function termMenu(info, term, x, y) {
  const menu = $('menu'); menu.replaceChildren();
  const items = [];
  if (term.hasSelection()) items.push(['コピー', () => { agents.copy(term.getSelection()); term.clearSelection(); }]);
  items.push(['貼り付け', () => agents.paste().then(text => text && term.paste(text))]);
  items.push(['最後の返答をコピー', async () => { const text = await agents.lastReply(info.id); if (text) agents.copy(text); }]);
  const hint = document.createElement('div'); hint.className = 'head'; hint.textContent = '文字は Claude の中でドラッグして選ぶとコピーされます（Shift を押しながらドラッグでも選べます）';
  for (const [label, action] of items) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
    b.addEventListener('click', () => { menu.hidden = true; action(); }); menu.append(b);
  }
  menu.append(hint);
  menu.hidden = false;
  menu.style.left = Math.min(x, innerWidth - menu.offsetWidth - 8) + 'px'; menu.style.top = Math.min(y, innerHeight - menu.offsetHeight - 8) + 'px';
}

function closeTab(info) {
  if (info.kind === 'operator') { agents.closeTab(info.id); return; }   // 裏に戻す
  if (!info.exited && !confirm(`${info.num}  ${info.name} のエージェントを終わらせて閉じますか？`)) return;
  agents.closeTab(info.id);
}

function tabMenu(info, x, y) {
  const menu = $('menu'); menu.replaceChildren();
  const items = [['名前を変える', () => rename($('tabs').querySelector(`[data-id="${info.id}"]`), info)],
                 ...(info.pinned ? [] : [['新しい窓へ', () => agents.newWindow(info.id)]]),
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
  // 出していたタブが閉じた：チームを出しているなら、チームを出したまま（引き取ったタブを「返す」で閉じたとき等）
  if (selected && selected !== active && terms.has(selected)) {
    if (active === null && typeof teamOpen !== 'undefined' && teamOpen) { active = selected; renderTabs(); } else show(selected);
  } else renderTabs();
  $('empty').hidden = terms.size > 0;
});
agents.onTopmost(mode => {
  $('topmost').textContent = `📌 ${TOPMOST_LABELS[mode] || mode}`; $('topmost').dataset.mode = mode;
  $('topmost').title = `最前面：${TOPMOST_LABELS[mode]}（押すと 常に → 自動 → オフ。自動は返答が届いたときだけ前に出ます）`;
});
// 選んでいる窓（フォーカスがある）は枠を青く
addEventListener('focus', () => document.body.classList.add('selected'));
addEventListener('blur', () => document.body.classList.remove('selected'));
document.body.classList.toggle('selected', document.hasFocus());
$('topmost').addEventListener('click', () => agents.topmost());
$('minimize').addEventListener('click', () => agents.minimize());
$('close').addEventListener('click', () => agents.closeWindow());
new ResizeObserver(() => fitActive()).observe($('screens'));
agents.ready();

// ---- タブの一覧（☰） ----------------------------------------------------------------------------------
let pickerItems = [], pickerIndex = 0, pickerTimer = null;
async function openPicker() {
  closePanels();
  $('picker-panel').hidden = false; agents.pickerOpen(true);
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
    li.innerHTML = '<div class="line"><span class="num"></span><span class="name"></span><span class="state"></span></div><pre></pre>';
    li.querySelector('.num').textContent = item.num; li.querySelector('.name').textContent = item.name + (item.mini ? '（最小化中）' : '');
    li.querySelector('.state').textContent = STATE_LABELS[item.state] || item.state;
    li.querySelector('pre').textContent = [item.lines, item.input && '❯ ' + item.input].filter(Boolean).join('\n');
    li.addEventListener('click', () => pick(i));
    list.append(li);
  });
}
function pick(i) { const item = pickerItems[i]; closePanels(); if (item) agents.focusTab(item.id); }
function closePanels() {
  if (!$('picker-panel').hidden) agents.pickerOpen(false);
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

// ---- 音声入力（🎙：録音の開始・停止。Ctrl+Alt+V でも。Ctrl+Alt+↓ で送信、Ctrl+Alt+↑ で消す） ---------------------
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
// スクロール：全画面の表示（Claude Code）は端末に履歴がないので、マウスホイールの合図を送る。そうでなければ端末の履歴を
agents.onScroll((id, lines) => {
  const t = terms.get(id); if (!t) return;
  if (t.term.buffer.active.type === 'alternate') {
    const wheel = `\x1b[<${lines < 0 ? 64 : 65};${Math.floor(t.term.cols / 2)};${Math.floor(t.term.rows / 2)}M`;
    agents.input(id, wheel.repeat(Math.abs(lines)));
  } else t.term.scrollLines(lines);
});
agents.onPicker(() => ($('picker-panel').hidden ? openPicker() : closePanels()));

// ---- ＋：作業空間のエージェントを開く（このPCの作業空間の一覧から） ----------------------------------------------
$('add').addEventListener('click', async event => {
  const menu = $('menu'); menu.replaceChildren();
  const head = document.createElement('div'); head.className = 'head'; head.textContent = '読み込んでいます…'; menu.append(head);
  const r = event.currentTarget.getBoundingClientRect();
  menu.hidden = false; menu.style.left = Math.max(8, Math.min(r.left, innerWidth - 260)) + 'px'; menu.style.top = (r.bottom + 2) + 'px';
  event.stopPropagation();
  const list = await agents.workspaces();
  head.textContent = list.length ? '作業空間（タスクブランチのものだけ開けます）' : '記録した作業空間はありません';
  for (const w of list) {
    const b = document.createElement('button'); b.type = 'button';
    const folder = shortDir(w.path).split('/').pop();
    b.textContent = `${folder}  ${w.branch || ''}${w.task ? `（#${w.task}）` : ''}`; b.title = w.path; b.disabled = !w.task;
    if (!w.task) b.style.opacity = '.45';
    b.addEventListener('click', () => { menu.hidden = true; agents.open({dir: w.path, name: folder + (w.task ? ` #${w.task}` : '')}); });
    menu.append(b);
  }
});

// リングでタブの一覧を操作する（上・左で前、下・右で次、押し込みで決定、ほかで閉じる）
agents.onPickerKey(gesture => {
  if ($('picker-panel').hidden) return;
  if (gesture === 'up' || gesture === 'left') { pickerIndex = Math.max(0, pickerIndex - 1); renderPicker(); }
  else if (gesture === 'down' || gesture === 'right') { pickerIndex = Math.min(pickerItems.length - 1, pickerIndex + 1); renderPicker(); }
  else if (gesture === 'click') pick(pickerIndex);
  else closePanels();
});

// フッターのモデル名：クリックで切り替え（待機中で入力欄が空のときに /model を送る）
function modelMenu(info, x, y) {
  const menu = $('menu'); menu.replaceChildren();
  for (const [label, model] of [['Opus', 'opus'], ['Fable', 'fable'], ['Sonnet', 'sonnet'], ['Haiku', 'haiku'], ['その他…（Claude の選択画面）', '']]) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
    b.addEventListener('click', () => { menu.hidden = true; agents.model(info.id, model); }); menu.append(b);
  }
  menu.hidden = false;
  menu.style.left = Math.min(x, innerWidth - menu.offsetWidth - 8) + 'px'; menu.style.top = Math.max(8, y - menu.offsetHeight - 8) + 'px';
}

// ⚙ の「エージェント」：オペレーターのモデル
let prefs = null;
const NO_ICON = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56"><circle cx="28" cy="28" r="27" fill="#2b303a"/><circle cx="28" cy="22" r="9" fill="#7b808c"/><path d="M11 46c3-9 10-13 17-13s14 4 17 13" fill="#7b808c"/></svg>');
agents.onPrefs(next => {
  prefs = next; renderTabs();
  for (const who of document.querySelectorAll('.persona .who')) {
    const kind = who.dataset.kind, img = who.querySelector('img');
    img.src = prefs.icons?.[kind] || NO_ICON; img.classList.toggle('none', !prefs.icons?.[kind]);
    const area = who.querySelector('textarea');
    if (document.activeElement !== area && !area.dataset.dirty) area.value = prefs.styles?.[kind] || '';
  }
  const select = $('operator-model'); select.replaceChildren();
  for (const m of prefs.operatorModels) { const o = document.createElement('option'); o.value = m; o.textContent = m || 'Claude Code の既定'; select.append(o); }
  select.value = prefs.operatorModel;
});
$('operator-model').addEventListener('change', () => agents.setPrefs({operatorModel: $('operator-model').value}));

for (const who of document.querySelectorAll('.persona .who')) {
  const kind = who.dataset.kind, area = who.querySelector('textarea'), saved = who.querySelector('.saved');
  who.querySelector('.pick').addEventListener('click', () => agents.iconPick(kind));
  who.querySelector('.clear').addEventListener('click', () => agents.iconClear(kind));
  area.addEventListener('input', () => { area.dataset.dirty = '1'; saved.textContent = ''; });
  who.querySelector('.save').addEventListener('click', async () => {
    saved.textContent = '保存しています…';
    const ok = await agents.styleSet(kind, area.value);
    if (ok) delete area.dataset.dirty;
    saved.textContent = ok ? '保存しました（次に起動したときから）' : '保存できませんでした';
  });
}

agents.onOpenSettings(() => { closePanels(); $('settings-panel').hidden = false; });
