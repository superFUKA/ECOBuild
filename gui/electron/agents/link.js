'use strict';
// GUI のサーバーとのつなぎ（Electron の main）：外（ecobuild gui・MCP・オペレーター）からのエージェントの窓の操作を受ける。
// ほかの窓と同じく、サーバーの events を待ち受ける「窓」（kind: agents）として、今のタブの様子を知らせる（サーバーは
// それで agents の一覧に答える）。サーバーが頼んできた操作（type: agents）を handle に渡す。
const ID = 'agents-main';
let base = '', token = '', since, describe = () => [], handle = () => {}, openPage = () => {}, pending = null, stopped = false;

async function post(api, body, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${base}/api/${api}`, {method: 'POST', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-ECOBuild-Token': token}, body: JSON.stringify(body)});
    return (await response.json()).value;
  } finally { clearTimeout(timer); }
}

const windowState = () => ({id: ID, kind: 'agents', tabs: describe()});

async function loop() {
  while (!stopped) {
    try {
      const answer = await post('events', {since, wait: 20, window: windowState()}, 40000);
      if (since === undefined) { since = answer.seq; continue; }
      since = answer.seq;
      for (const event of answer.events || []) {
        if (event.target !== ID) continue;
        try {
          if (event.type === 'agents') await handle(event.op, event.params || {});
          else if (event.type === 'open-window') openPage(event.page);   // 画面の窓がないとき：ハブ・モジュールの窓を開く
        } catch (e) { console.error('agents:', event.type, event.op, e.message); }
      }
    } catch (e) {
      await new Promise(r => setTimeout(r, 3000));   // サーバーが止まっている・まだ起動中
    }
  }
}

// タブが変わったら、すぐ知らせる（まとめて1回）
function changed() {
  if (!base || pending) return;
  pending = setTimeout(() => { pending = null; post('window-state', {window: windowState()}).catch(() => {}); }, 300);
}

function connect(hubUrl, options) {
  const url = new URL(hubUrl);
  base = url.origin; token = url.searchParams.get('t') || '';
  describe = options.describe; handle = options.handle; openPage = options.openPage || openPage;
  loop();
}

function stop() { stopped = true; }

module.exports = {connect, changed, stop};
