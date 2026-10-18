'use strict';
// Hub「AI に頼む」: a conversation with the operator (the agent that operates ECOBuild with ecobuild commands; it writes
// no code). Each message is one `ecobuild agent ask` (the text on stdin, --session to go on with the conversation).
// The conversation (its session and the messages shown) is kept in this window's localStorage: a convenience only,
// the conversation itself is the agent's.
const OPERATOR = (() => {
  const $ = id => document.getElementById(id);
  const {esc} = ECO;
  const KEY = 'ecobuild.operator', KEEP = 100;
  let state = load(), busy = false, shown = false;

  function load() {
    try { const s = JSON.parse(localStorage.getItem(KEY) || 'null'); if (s && Array.isArray(s.messages)) return s; } catch (e) { /* none */ }
    return {session: null, messages: []};
  }
  function save() {
    state.messages = state.messages.slice(-KEEP);
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* not kept */ }
  }

  // `code`, **bold** and line breaks only: the replies are short plain text.
  const text = s => esc(s).replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
  function item(m) {
    const li = document.createElement('li'); li.className = 'operator-message ' + m.role + (m.ok === false ? ' failed' : '');
    const actions = (m.actions || []).filter(a => a.command);
    li.innerHTML = `<div class="operator-bubble">${text(m.text || (m.role === 'agent' ? '（返答なし）' : ''))}</div>`
      + (actions.length ? `<details class="operator-actions"><summary>実行したコマンド（${actions.length}）</summary><ul>${actions.map(a =>
        `<li class="${a.ok === false ? 'failed' : ''}"><code>${esc(a.command)}</code>${a.ok === false ? '<span>止められた・失敗</span>' : ''}</li>`).join('')}</ul></details>` : '');
    return li;
  }
  function render() {
    const log = $('operator-log');
    log.replaceChildren(...state.messages.map(item));
    if (!state.messages.length) {
      const li = document.createElement('li'); li.className = 'operator-empty';
      li.textContent = 'まだ会話はありません。下の欄に頼むことを書いて送ってください。'; log.append(li);
    }
    if (busy) {
      const li = document.createElement('li'); li.className = 'operator-message agent pending';
      li.innerHTML = '<div class="operator-bubble"><span class="eco-spinner"></span> 考え中…</div>'; log.append(li);
    }
    log.lastElementChild?.scrollIntoView({block: 'end'});
  }
  function setBusy(on) {
    busy = on;
    $('operator-state').textContent = on ? '考え中…' : '待機中';
    $('operator-state').classList.toggle('thinking', on);
    $('operator-send').disabled = on; $('operator-new').disabled = on;
  }

  async function send(message) {
    if (busy || !message.trim()) return;
    state.messages.push({role: 'user', text: message}); save(); setBusy(true); render();
    const args = ['agent', 'ask', ...(state.session ? ['--session', state.session] : [])];
    const doc = await ECO.cli(null, args, {stdin: message, quiet: true});
    setBusy(false);
    if (doc.ok) {
      state.session = doc.result.session || state.session;
      state.messages.push({role: 'agent', text: doc.result.text, ok: doc.result.ok, actions: doc.result.actions});
    } else {
      const e = doc.error || {};
      state.messages.push({role: 'agent', ok: false, text: [e.message || '返答を受け取れませんでした。', e.hint].filter(Boolean).join('\n')});
    }
    save(); render();
    if (doc.ok && (doc.result.actions || []).some(a => a.command)) window.dispatchEvent(new CustomEvent('eco-operator-acted'));
  }

  function wire() {
    const input = $('operator-input');
    $('operator-form').addEventListener('submit', e => { e.preventDefault(); const m = input.value; input.value = ''; send(m); });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('operator-form').requestSubmit(); }
    });
    $('operator-new').addEventListener('click', () => { state = {session: null, messages: []}; save(); render(); input.focus(); });
  }

  wire();
  return {
    show() { if (!shown) { shown = true; render(); } $('operator-input').focus(); },
    send,
  };
})();
