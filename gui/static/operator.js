'use strict';
// Hub「オペレーター」: a conversation with the operator (the agent that operates ECOBuild with ecobuild commands; it writes
// no code). Two ways, by where the hub runs:
// - In the Electron app: the operator stays running in the app (its terminal, hidden; tab 0 of the agents windows).
//   Messages are typed into it; its replies come from its Stop hook. The conversation shown is the app's (the same in
//   every window). A choice it shows (a question, a permission) is answered here with ↑↓ / 決定, or in its tab.
// - Elsewhere (the Edge window): each message is one `ecobuild agent ask` (the text on stdin, --session to go on).
//   The conversation is kept in this window's localStorage (a convenience only; the conversation itself is the agent's).
const OPERATOR = (() => {
  const $ = id => document.getElementById(id);
  const {esc} = ECO;
  const resident = window.ecobuildShell?.agents?.operator;
  const KEY = 'ecobuild.operator', KEEP = 100;
  const STATES = {none: '止まっています', starting: '起動中…', idle: '待機中', thinking: '考え中…', waiting: '裏で実行中…',
                  choice: '選択肢を出しています', exited: '終わりました', listening: '聞き取り中…'};
  let state = load(), busy = false, shown = false, view = null;

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
    li.innerHTML = (m.role === 'agent' && view?.icon ? `<img class="operator-avatar" alt="" src="${esc(view.icon)}">` : '')
      + `<div class="operator-bubble">${text(m.text || (m.role === 'agent' ? '（返答なし）' : ''))}</div>`
      + (actions.length ? `<details class="operator-actions"><summary>実行したコマンド（${actions.length}）</summary><ul>${actions.map(a =>
        `<li class="${a.ok === false ? 'failed' : ''}"><code>${esc(a.command)}</code>${a.ok === false ? '<span>止められた・失敗</span>' : ''}</li>`).join('')}</ul></details>` : '');
    return li;
  }
  function render() {
    const log = $('operator-log');
    const messages = resident ? (view?.log || []) : state.messages;
    log.replaceChildren(...messages.map(item));
    if (!messages.length) {
      const li = document.createElement('li'); li.className = 'operator-empty';
      li.textContent = 'まだ会話はありません。下の欄に頼むことを書いて送ってください。'; log.append(li);
    }
    // 考え中は、オペレーターが本当に考え中・起動中・待たせているときだけ（返答を取りこぼしても止まって見えないように）
    const waiting = resident ? view && (['thinking', 'waiting', 'starting'].includes(view.state) || view.queued > 0) : busy;
    if (waiting) {
      const li = document.createElement('li'); li.className = 'operator-message agent pending';
      li.innerHTML = `<div class="operator-bubble"><span class="eco-spinner"></span> ${view?.state === 'starting' ? '起動しています…' : '考え中…'}</div>`
        + (resident && view?.doing ? `<div class="operator-doing">実行中：<code>${esc(view.doing)}</code></div>` : '');
      // 起動中のまま：オペレーターの画面の最後の数行と、10秒たったらタブで開いて確かめるボタン
      if (resident && view?.state === 'starting' && view.screen) {
        const pre = document.createElement('pre'); pre.className = 'operator-screen'; pre.textContent = view.screen; li.append(pre);
        if (view.startingFor > 10000) {
          const b = document.createElement('button'); b.type = 'button'; b.className = 'cancel'; b.textContent = 'タブで開いて画面を確かめる';
          b.addEventListener('click', () => resident.show(true)); li.append(b);
        }
      }
      log.append(li);
    }
    renderChoice();
    log.lastElementChild?.scrollIntoView({block: 'end'});
  }
  function renderChoice() {
    const box = $('operator-choice'); if (!box) return;
    const c = resident && view?.state === 'choice' ? view.choice : null;
    box.hidden = !c;
    if (c) {
      box.querySelector('.q').textContent = c.question || 'オペレーターが選択肢を出しています';
      box.querySelector('.c').textContent = '❯ ' + (c.choice || '');
    }
  }
  function setBusy(on) {
    busy = on;
    $('operator-state').textContent = on ? '考え中…' : '待機中';
    $('operator-state').classList.toggle('thinking', on);
    $('operator-send').disabled = on; $('operator-new').disabled = on;
  }
  function showView(next) {
    view = next;
    $('operator-state').textContent = STATES[view.state] || view.state;
    $('operator-state').classList.toggle('thinking', ['thinking', 'waiting', 'starting'].includes(view.state));
    const tab = $('operator-tab'); if (tab) tab.textContent = view.shown ? '裏に戻す' : 'タブで開く';
    // 声：録音中と、聞き取った文（オペレーターの入力欄にある）。送る・消すは聞き取った文があるときだけ
    const mic = $('operator-mic'), heard = $('operator-heard');
    if (mic) {
      mic.classList.toggle('on', view.state === 'listening');
      mic.textContent = view.state === 'listening' ? '■ 止める' : '🎤 声で';
      heard.hidden = !(view.state === 'listening' || view.input);
      heard.querySelector('.t').textContent = view.state === 'listening' ? `聞き取り中…${view.input ? '：' + view.input : ''}` : `聞き取った文：${view.input}`;
    }
    if (shown) render();
    const last = view.log.at(-1);
    if (last?.role === 'agent' && last.at !== lastSeen) { lastSeen = last.at; window.dispatchEvent(new CustomEvent('eco-operator-acted')); }
  }
  let lastSeen = null;

  async function send(message) {
    if (!message.trim()) return;
    if (resident) { resident.send(message); return; }
    if (busy) return;
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
    $('operator-new').addEventListener('click', () => {
      if (resident) { resident.clear(); resident.restart(); }
      else { state = {session: null, messages: []}; save(); render(); }
      input.focus();
    });
    if (!resident) return;
    // The resident operator: its tab, and the choice it shows.
    const tab = document.createElement('button'); tab.type = 'button'; tab.className = 'cancel'; tab.id = 'operator-tab';
    tab.title = 'オペレーターをエージェントの窓のタブで開きます（画面で直接やり取りする・選択肢に答える）'; tab.textContent = 'タブで開く';
    tab.addEventListener('click', () => resident.show(!view?.shown));
    $('operator-new').before(tab);
    const box = document.createElement('div'); box.className = 'operator-choice'; box.id = 'operator-choice'; box.hidden = true;
    box.innerHTML = '<p class="q"></p><p class="c"></p><div class="settings-actions"><button type="button" class="cancel" data-key="up">↑</button><button type="button" class="cancel" data-key="down">↓</button><button type="button" class="add-button" data-key="enter">決定</button><button type="button" class="cancel" data-key="esc">取り消す（Esc）</button></div>';
    box.addEventListener('click', e => { const key = e.target.closest('[data-key]')?.dataset.key; if (key) resident.key(key); });
    $('operator-form').before(box);
    resident.onUpdate(showView);
    const mic = document.createElement('button'); mic.type = 'button'; mic.className = 'cancel operator-mic'; mic.id = 'operator-mic';
    mic.title = '声で頼む（押すと録音、もう一度押すと止める。聞き取った文は確かめてから送る）'; mic.textContent = '🎤 声で';
    mic.addEventListener('click', () => resident.voice(view?.state !== 'listening'));
    $('operator-send').before(mic);
    const heard = document.createElement('div'); heard.className = 'operator-heard'; heard.id = 'operator-heard'; heard.hidden = true;
    heard.innerHTML = '<span class="t"></span><button type="button" class="add-button" data-v="send">送る</button><button type="button" class="cancel" data-v="clear">消す</button>';
    heard.addEventListener('click', e => { const v = e.target.closest('[data-v]')?.dataset.v; if (v === 'send') resident.voiceSubmit(); if (v === 'clear') resident.voiceClear(); });
    $('operator-form').before(heard);
  }

  wire();
  return {
    async show() {
      if (resident && !shown) showView(await resident.watch(true));
      if (!shown) { shown = true; render(); }
      $('operator-input').focus();
    },
    send,
  };
})();
