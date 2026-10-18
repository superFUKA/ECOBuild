'use strict';
// A panel window (panel.html?panel=…): a tab dragged out of the workspace's footer, or out of another panel window.
// Its tabs go back by dragging them onto a footer (or into another window); its last tab closed, it closes.
(() => {
  const first = JSON.parse(ECO.params.get('panel') || 'null');
  const module = PANELS.place(ECO.params.get('module') || first?.dir || '');
  const host = PANELS.host(document.getElementById('panels'), {
    closable: true, onEmpty: () => window.close(),
    onChange: () => { document.title = `${host.panels().map(p => `${p.title}・${PANELS.place(p.dir)}`).join('、') || 'パネル'} — ${module}`; },
  });
  document.getElementById('panel-module').textContent = module;
  if (first) host.add(first);
  // Closing the window closes its panels: the workspace shows them in its footer the next time.
  window.addEventListener('pagehide', () => { for (const p of host.panels()) host.close(p.id); });
})();
