'use strict';
// Tool panels, as Visual Studio's tool windows. A host is a tab bar and the panel shown under it: the workspace's
// footer (PANELS.footer) or a window of its own (panel.html). A tab dragged out and dropped where no host takes it
// becomes a window there; dropped on a host (the footer, or another panel window) it joins that host.
// A panel's content is made by the page it belongs to (the workspace: its outputs, PANELS.source) and reaches every
// window over a BroadcastChannel; each host draws it with the panel's view (出力: OUTPUT.view).
// A panel: {id, kind, dir, module, title}. Messages: at (a host took the panel: the others let it go), gone (a host
// closed it), who (where is it?), want (a host asks for its content), data (the content).
const PANELS = (() => {
  const MIME = 'application/x-ecobuild-panel', FLOAT_SIZE = [900, 440];
  const channel = new BroadcastChannel('ecobuild-panels');
  const hosts = [], sources = new Map(), where = new Map();
  const VIEWS = {output: (box, panel) => OUTPUT.view(box, {dir: panel.dir})};
  const place = dir => String(dir || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop();
  // A message reaches the other pages (the channel) and this page's hosts (the channel does not echo to its sender).
  function send(message) { channel.postMessage(message); receive(message); }
  function receive(message) {
    if (message.type === 'at') where.set(message.id, message.host);
    if (message.type === 'gone' && where.get(message.id) === message.host) where.delete(message.id);
    if (message.type === 'want' && sources.has(message.id)) publish(message.id);
    for (const host of [...hosts]) host.receive(message);
  }
  channel.onmessage = e => receive(e.data);
  const dragging = e => e.dataTransfer && [...e.dataTransfer.types].includes(MIME);

  // A window of its own for the panel, where the tab was dropped (screen coordinates).
  function float(panel, x, y) {
    const [width, height] = FLOAT_SIZE, left = Math.max(0, Math.round((x || window.screenX + 80) - 80)), top = Math.max(0, Math.round((y || window.screenY + 80) - 20));
    ECO.openPage(`panel.html?panel=${encodeURIComponent(JSON.stringify(panel))}&module=${encodeURIComponent(panel.module || '')}`,
      `left=${left},top=${top},width=${width},height=${height}`);
  }

  // A host in el: el has .panel-tabs (the tab bar) and .panel-body. home: the panels' own page (the workspace), whose
  // tabs show only the panel's title; elsewhere the tab names the workspace too. closable: a tab has × (a window).
  // onEmpty: the last panel left (a window closes).
  function host(el, {home = '', closable = false, onEmpty = () => {}, onChange = () => {}} = {}) {
    const id = Math.random().toString(36).slice(2), items = new Map();
    const tabs = el.querySelector('.panel-tabs'), body = el.querySelector('.panel-body');
    let active = null;
    const label = panel => panel.title + (home && panel.dir === home ? '' : `・${place(panel.dir)}`);
    function activate(pid) {
      active = pid;
      for (const [key, item] of items) { item.tab.setAttribute('aria-selected', String(key === pid)); item.box.hidden = key !== pid; }
      onChange();
    }
    function add(panel) {
      if (!items.has(panel.id)) {
        const tab = document.createElement('div'); tab.className = 'panel-tab'; tab.setAttribute('role', 'tab'); tab.draggable = true;
        tab.title = `${panel.dir}\nドラッグで窓にする・ほかの欄へ移す`;
        tab.innerHTML = `<span>${ECO.esc(label(panel))}</span>${closable ? '<button type="button" class="panel-close" aria-label="閉じる" title="閉じる">×</button>' : ''}`;
        const box = document.createElement('div'); box.className = 'panel-content'; box.hidden = true;
        tabs.append(tab); body.append(box);
        items.set(panel.id, {panel, tab, box, view: VIEWS[panel.kind](box, panel)});
        tab.addEventListener('click', e => { if (e.target.closest('.panel-close')) close(panel.id); else activate(panel.id); });
        tab.addEventListener('dragstart', e => {
          e.dataTransfer.setData(MIME, JSON.stringify({...panel, from: id})); e.dataTransfer.effectAllowed = 'move';
          document.body.classList.add('panel-dragging');
        });
        // Dropped where no host took it (dropEffect none): a window there. Taken by a host: that host says "at".
        tab.addEventListener('dragend', e => {
          document.body.classList.remove('panel-dragging');
          if (e.dataTransfer.dropEffect === 'none' && items.has(panel.id)) float(panel, e.screenX, e.screenY);
        });
        send({type: 'want', id: panel.id});
      }
      activate(panel.id);
      send({type: 'at', id: panel.id, host: id});
    }
    function remove(pid) {
      const item = items.get(pid); if (!item) return;
      item.tab.remove(); item.box.remove(); items.delete(pid);
      if (active === pid) { const next = items.keys().next().value; if (next) activate(next); else active = null; }
      if (!items.size) onEmpty(); else onChange();
    }
    function close(pid) { remove(pid); send({type: 'gone', id: pid, host: id}); }
    // A panel dragged over the host joins it when dropped.
    el.addEventListener('dragover', e => { if (!dragging(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; el.classList.add('panel-drop'); });
    el.addEventListener('dragleave', e => { if (!el.contains(e.relatedTarget)) el.classList.remove('panel-drop'); });
    el.addEventListener('drop', e => {
      if (!dragging(e)) return;
      e.preventDefault(); el.classList.remove('panel-drop');
      const {from, ...panel} = JSON.parse(e.dataTransfer.getData(MIME));
      if (from === id) activate(panel.id); else add(panel);
    });
    const self = {
      id, add, remove, close, has: pid => items.has(pid), panels: () => [...items.values()].map(i => i.panel),
      receive(message) {
        const item = items.get(message.id); if (!item) return;
        if (message.type === 'at' && message.host !== id) remove(message.id);
        if (message.type === 'who') send({type: 'at', id: message.id, host: id});
        if (message.type === 'data') item.view.update(message.data);
      },
    };
    hosts.push(self);
    return self;
  }

  // The workspace's footer (under the work area): its panels are at home here. It shows while it has a panel; ×
  // hides it (the panels stay). Its height is dragged at its top edge (kept on this PC); ⤢ enlarges it. While a panel
  // is dragged over the page, the footer shows as the place to drop it.
  function footer(el, {home, heightKey}) {
    const footerHost = host(el, {home, onEmpty: () => { el.hidden = true; }});
    let closed = false;
    const sync = () => { el.hidden = closed || !footerHost.panels().length; };
    try { const h = Number(localStorage.getItem(heightKey)); if (h) el.style.height = h + 'px'; } catch (e) { /* storage blocked */ }
    el.querySelector('.panel-bar-tools').addEventListener('click', e => {
      const what = e.target.closest('[data-footer]')?.dataset.footer;
      if (what === 'close') { closed = true; sync(); }
      if (what === 'max') e.target.closest('button').setAttribute('aria-pressed', String(el.classList.toggle('max')));
    });
    el.querySelector('.panel-resize').addEventListener('pointerdown', e => {
      e.preventDefault();
      const startY = e.clientY, startHeight = el.getBoundingClientRect().height;
      el.classList.remove('max'); el.querySelector('[data-footer=max]').setAttribute('aria-pressed', 'false');
      const move = m => { el.style.height = Math.max(90, Math.min(window.innerHeight - 140, startHeight + startY - m.clientY)) + 'px'; };
      const up = () => {
        window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
        try { localStorage.setItem(heightKey, String(Math.round(el.getBoundingClientRect().height))); } catch (err) { /* storage blocked */ }
      };
      window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
    });
    let over = 0;
    document.addEventListener('dragenter', e => { if (dragging(e) && over++ === 0 && el.hidden) { el.hidden = false; el.classList.add('panel-target'); } });
    const leave = () => { over = 0; if (el.classList.contains('panel-target')) { el.classList.remove('panel-target'); sync(); } };
    document.addEventListener('dragleave', e => { if (dragging(e) && --over <= 0) leave(); });
    document.addEventListener('drop', () => { over = 0; el.classList.remove('panel-target'); closed = false; setTimeout(sync); });
    return {
      ...footerHost,
      // Shows the panel: where it is (a window keeps it), else here with the footer open.
      reveal(panel) {
        const at = where.get(panel.id);
        if (at && at !== footerHost.id) return;
        closed = false;
        if (!footerHost.has(panel.id)) footerHost.add(panel);
        sync();
      },
    };
  }

  // The page that makes a panel's content: data() gives it; publish(id) sends it to the hosts showing the panel.
  function source(panel, data) { sources.set(panel.id, data); send({type: 'who', id: panel.id}); }
  function publish(pid) { const data = sources.get(pid); if (data) send({type: 'data', id: pid, data: data()}); }
  return {host, footer, source, publish, float, place};
})();
