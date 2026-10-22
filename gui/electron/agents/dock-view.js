'use strict';
// 右下の表示の画面（dock.html）。出すものは main（dock.js）が決め、ここは描くことと、押されたことを伝えるだけ。
// 横長（chip）：クリックでのぞき見の開け閉め、❐ で窓に戻す、ドラッグで動かす。カード：クリックでそのタブへ、× か右クリックで消す。
const root = document.getElementById('root');
let lastSize = '';

function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

function render(view) {
  root.replaceChildren();
  for (const card of view.cards) {
    const c = el('div', 'card');
    const head = el('div', 'head');
    const icon = view.icons?.[card.kind];
    if (icon) { const img = el('img', 'avatar'); img.src = icon; img.alt = ''; head.append(img); }
    head.append(el('span', 'who', `${card.num}  ${card.name}`), el('span', '', card.label || '返答'));
    const close = el('button', 'close', '×'); close.type = 'button'; close.title = '消す'; close.setAttribute('aria-label', '消す');
    close.addEventListener('click', event => { event.stopPropagation(); dock.action('dismiss', card.key); });
    head.append(close);
    c.title = 'クリックで開く・右クリックで消す';
    if (card.key === 'heard') c.classList.add('heard');
    c.append(head, el('div', 'text', card.text || '返答が終わりました'));
    c.addEventListener('click', () => (card.num === '◆' ? dock.action('operator') : dock.action('open', card.id)));
    c.addEventListener('contextmenu', event => { event.preventDefault(); dock.action('dismiss', card.key); });
    root.append(c);
  }
  if (view.peek) {
    const p = el('div', 'peek', view.peek.lines || '（まだ出力はありません）');
    if (view.peek.input) p.append(el('div', 'input', '❯ ' + view.peek.input));
    root.append(p);
  }
  if (view.chip) {
    const chip = el('div', 'chip ' + (view.chip.state || ''));
    chip.title = view.chip.kind === 'operator' ? 'クリックでオペレーターをタブで開く（もう一度で裏に戻す）。ドラッグで動かせます'
      : 'クリックでのぞき見、❐ で窓に戻す。ドラッグで動かせます';
    if (view.chip.kind === 'operator') chip.classList.add('operator');
    chip.append(el('span', 'dot', String(view.chip.num)), el('span', 'name', view.chip.name));
    if (view.chip.badge) chip.append(el('span', 'badge', String(view.chip.badge)));
    const restore = el('button', 'restore', '❐'); restore.title = '窓に戻す';
    restore.addEventListener('click', event => { event.stopPropagation(); dock.action('restore'); });
    chip.append(restore);
    let down = null, moved = false;
    chip.addEventListener('mousedown', event => { if (event.button !== 0 || event.target === restore) return; down = {x: event.screenX, y: event.screenY}; moved = false; dock.dragStart(); });
    addEventListener('mousemove', event => {
      if (!down) return;
      const dx = event.screenX - down.x, dy = event.screenY - down.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      if (moved) dock.dragMove(dx, dy);
    });
    addEventListener('mouseup', () => { if (!down) return; down = null; dock.dragEnd(); if (!moved) dock.action(view.chip.kind === 'operator' ? 'operator' : 'peek'); });
    chip.addEventListener('contextmenu', event => { event.preventDefault(); dock.action('dismiss-all'); });
    root.append(chip);
  }
  requestAnimationFrame(() => {
    const r = root.getBoundingClientRect(), key = `${r.width}x${r.height}`;
    if (key !== lastSize) { lastSize = key; dock.size(r.width, r.height); }
  });
}

dock.onView(render);
dock.onSound(({id, volume}) => ECOSounds.play(id, volume));
dock.ready();
