'use strict';
// 右下の表示の画面（dock.html）。出すものは main（dock.js）が決め、ここは描くことと、押されたことを伝えるだけ。
// 横長（chip）：クリックでのぞき見の開け閉め、⤢ で元に戻す、ドラッグで動かす。カード：クリックでそのタブへ、右クリックで消す。
const root = document.getElementById('root');
let lastSize = '';

function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

function render(view) {
  root.replaceChildren();
  for (const card of view.cards) {
    const c = el('div', 'card');
    const head = el('div', 'head'); head.append(el('span', '', `${card.num}  ${card.name}`), el('span', '', '返答'));
    c.append(head, el('div', 'text', card.text || '返答が終わりました'));
    c.addEventListener('click', () => dock.action('open', card.id));
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
    chip.title = 'クリックでのぞき見、⤢ で元に戻す。ドラッグで動かせます';
    chip.append(el('span', 'dot', String(view.chip.num)), el('span', 'name', view.chip.name));
    if (view.chip.badge) chip.append(el('span', 'badge', String(view.chip.badge)));
    const restore = el('button', 'restore', '⤢'); restore.title = '元に戻す';
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
    addEventListener('mouseup', () => { if (!down) return; down = null; dock.dragEnd(); if (!moved) dock.action('peek'); });
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
