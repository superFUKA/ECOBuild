// 部品「オペレーターとの会話」。今までの GUI（gui/static/operator.js）と同じ描き方。
// 会話の中身・状態は ecobuild gui conversation の答え（conversation）。送った文（asked）は、返答が記録に入るまで、
// 自分の吹き出しと「考え中…」で見せる。ここで決めるのは見せ方だけ（何も実行しない）。
const STATES = { none: '止まっています', starting: '起動中…', idle: '待機中', thinking: '考え中…', waiting: '裏で実行中…',
  choice: '選択肢を出しています', exited: '終わりました', listening: '聞き取り中…' };
const BUSY = ['thinking', 'waiting', 'starting'];
const FACE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
  + '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01"/></svg>';

// `コード`・**太字**・改行だけ（返答は短い文）。
function rich(h, text) {
  const out = [];
  String(text).split('\n').forEach((line, at) => {
    if (at) out.push(h('br', {}));
    for (const piece of line.split(/(`[^`]+`|\*\*[^*]+\*\*)/)) {
      if (/^`[^`]+`$/.test(piece)) out.push(h('code', {}, piece.slice(1, -1)));
      else if (/^\*\*[^*]+\*\*$/.test(piece)) out.push(h('strong', {}, piece.slice(2, -2)));
      else if (piece) out.push(piece);
    }
  });
  return out;
}

export default {
  render(root, props, { h, emit, state }) {
    const found = props.conversation || {};
    const recorded = Array.isArray(found.messages) ? found.messages : [];
    // 送った文：返答が記録に入って届く（記録が変わる）か、失敗が届くまで、待っている発言として持つ
    const mark = `${recorded.length}/${(recorded[recorded.length - 1] || {}).at ?? ''}`;
    if (props.asked) state.waiting = { text: props.asked, mark };
    else if (state.waiting && (state.waiting.mark !== mark || props.failed)) state.waiting = null;
    const sent = state.waiting ? state.waiting.text : null;
    const last = recorded[recorded.length - 1];
    const messages = [...recorded];
    if (sent && !(last && last.role === 'user' && last.text === sent)) messages.push({ role: 'user', text: sent });
    if (props.failed && !sent && !(last && last.role === 'agent' && last.ok === false)) messages.push({ role: 'agent', ok: false, text: props.failed });
    const mode = sent && !BUSY.includes(found.state) ? 'thinking' : (found.state || 'idle');
    const waiting = Boolean(sent) || BUSY.includes(found.state) || found.queued > 0;
    const doing = (sent && props.doing.length ? props.doing[props.doing.length - 1] : '') || (waiting ? found.doing : '') || '';

    const avatar = () => { const face = h('span', { class: 'face', 'aria-hidden': 'true' }); face.innerHTML = FACE; return face; };
    const item = (message) => {
      const actions = (message.actions || []).filter((action) => action.command);
      const agent = message.role === 'agent';
      const row = h('li', { class: `message ${message.role || 'agent'}${message.ok === false ? ' failed' : ''}` });
      if (agent) row.append(avatar());
      row.append(h('div', { class: 'bubble' }, ...rich(h, message.text || (agent ? '（返答なし）' : ''))));
      if (actions.length) {
        row.append(h('details', { class: 'actions' },
          h('summary', {}, `実行したコマンド（${actions.length}）`),
          h('ul', {}, ...actions.map((action) => {
            const line = h('li', { class: action.ok === false ? 'failed' : '' }, h('code', {}, action.command));
            if (action.ok === false) line.append(h('span', {}, '止められた・失敗'));
            return line;
          }))));
      }
      return row;
    };

    const log = h('ol', { class: 'log', 'aria-live': 'polite' }, ...messages.map(item));
    if (props.error) log.append(h('li', { class: 'empty' }, h('p', { role: 'alert' }, props.error)));
    else if (!messages.length && !waiting) {
      log.append(h('li', { class: 'empty' }, h('p', {}, props.loading ? '読み込み中…' : props.intro)));
    }
    if (waiting) {
      const starting = found.state === 'starting';
      const pending = h('li', { class: 'message agent pending' }, avatar(),
        h('div', { class: 'bubble' }, h('span', { class: 'spinner' }), starting ? '起動しています…' : '考え中…'));
      if (doing) pending.append(h('div', { class: 'doing' }, '実行中：', h('code', {}, doing)));
      // 起動中のまま：オペレーターの画面の最後の数行と、10秒たったら画面を開いて確かめるボタン
      if (starting && found.screen) {
        pending.append(h('pre', { class: 'screen' }, found.screen));
        if (found.starting_for > 10) {
          const open = h('button', { type: 'button', class: 'small' }, 'タブで開いて画面を確かめる');
          open.addEventListener('click', () => emit('show', {}));
          pending.append(open);
        }
      }
      log.append(pending);
    }

    // 選択肢の箱：オペレーターが出している問いと、今の選択。↑・↓・決定・取り消す
    let choice = null;
    if (found.state === 'choice' && found.choice) {
      const key = (name, label, primary) => {
        const button = h('button', { type: 'button', class: primary ? 'primary' : '' }, label);
        button.addEventListener('click', () => emit('key', { key: name }));
        return button;
      };
      choice = h('div', { class: 'choice' },
        h('p', { class: 'q' }, found.choice.question || 'オペレーターが選択肢を出しています'),
        h('p', { class: 'c' }, '❯ ' + (found.choice.choice || '')),
        h('div', { class: 'keys' }, key('up', '↑'), key('down', '↓'), key('enter', '決定', true), key('esc', '取り消す（Esc）')));
    }

    root.className = 'chat';
    root.replaceChildren(
      h('div', { class: 'top' }, h('span', { class: `state${BUSY.includes(mode) ? ' thinking' : ''}`, role: 'status' }, STATES[mode] || mode)),
      log);
    if (choice) root.append(choice);
    log.scrollTop = log.scrollHeight;   // 最後の発言が見えるように
  },
};
