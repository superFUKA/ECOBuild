'use strict';
// エージェントの窓の画面：タブ（番号・名前・状態）と、タブごとの端末（xterm.js）。表示するのは選んでいるタブだけ。
// タブのダブルクリックで名前を変え、ドラッグで並べ替え、右クリックで「新しい窓へ」「起動し直す」「閉じる」。
// 端末：Ctrl+= / Ctrl+- / Ctrl+0 で文字の大きさ、Ctrl+Shift+C で選んだところをコピー、Ctrl+V で貼り付け。
const $ = id => document.getElementById(id);
const terms = new Map();     // id → {term, fit, el}
let tabs = [], active = null, fontSize = 14;
const STATE_LABELS = {thinking: '考え中', waiting: '裏で実行中', choice: '選択肢', idle: '待機中', starting: '起動中', exited: '終了'};
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
    b.querySelector('.num').textContent = info.num; b.querySelector('.name').textContent = info.name;
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
  $('status').innerHTML = current ? `<span>${STATE_LABELS[current.state] || ''}</span><span class="where"></span>` : '';
  if (current) $('status').querySelector('.where').textContent = current.dir;
  document.title = current ? `${current.num} ${current.name} - エージェント` : 'エージェント - ECOBuild';
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
  if (!info.exited && !confirm(`${info.num}  ${info.name} のエージェントを終わらせて閉じますか？`)) return;
  agents.closeTab(info.id);
}

function tabMenu(info, x, y) {
  const menu = $('menu'); menu.replaceChildren();
  const items = [['名前を変える', () => rename($('tabs').querySelector(`[data-id="${info.id}"]`), info)],
                 ['新しい窓へ', () => agents.newWindow(info.id)],
                 ['起動し直す', () => agents.restart(info.id)],
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
