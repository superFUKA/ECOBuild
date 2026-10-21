'use strict';
// チームの表示（AI が起動した作業役）の、画面に依らない部分：team list の様子を1行・目立たせる印にする、
// team log の出来事（Claude Code の stream-json と係の印）を詳しい表示の項目にする。
// 窓の画面（window.html の <script>）と試験（node）の両方で読む。
(function (root) {
  const STATE_NAMES = {working: '作業中', idle: '待機中', stopped: '止まっている', unknown: '不明'};
  const ROLE_NAMES = {lead: '進行役', manager: '管理役', worker: '作業役'};
  const QUIET_SECONDS = 10 * 60;   // 作業中なのに、これだけ道具を使っていない：止まっているかもしれない
  const LONG_SECONDS = 60 * 60;    // 作業中がこれより長い
  const TOOL_KEYS = ['command', 'file_path', 'notebook_path', 'pattern', 'url', 'query', 'description', 'skill', 'prompt'];

  function duration(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    if (seconds < 60) return `${seconds}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分`;
    return `${Math.floor(seconds / 3600)}時間${Math.floor(seconds % 3600 / 60)}分`;
  }

  // チーム（team list --nested の members）を、入れ子の深さ付きの1列に。parent：その人を作った進行役の作業空間
  // （操作は ecobuild -C <parent> agent team … で）
  function flatten(members, parent, depth = 0, out = []) {
    for (const m of members || []) {
      out.push({...m, parent, depth, members: undefined});
      flatten(m.members, m.path, depth + 1, out);
    }
    return out;
  }

  // 様子：label（作業中 12分・失敗 等）・tone（working・idle・stopped・failed）・alert（目立たせるわけ。なければ ''）
  function look(m, now = Date.now() / 1000) {
    const state = m.state || 'unknown';
    let label = STATE_NAMES[state] || state, tone = state, alert = '';
    if (state === 'stopped' && m.error) { label = '失敗'; tone = 'failed'; alert = '止めていないのに終わりました'; }
    else if (state === 'stopped') alert = m.mode === 'app' ? '止まっています' : '';
    if (typeof m.since === 'number' && (state === 'working' || state === 'idle')) label += ` ${duration(now - m.since)}`;
    if (state === 'working') {
      const quiet = typeof m.doing_at === 'number' ? now - m.doing_at : null;
      if (quiet !== null && quiet > QUIET_SECONDS) alert = `${duration(quiet)} 道具を使っていません`;
      else if (typeof m.since === 'number' && now - m.since > LONG_SECONDS) alert = '作業中が長くなっています';
    }
    const human = m.mode !== 'app' && (state === 'working' || state === 'idle');   // 人の画面（引き取った等）
    return {label, tone, alert, human};
  }

  // 道具を使った1行（ecobuild_agent.app.tool_summary と同じ形：「Bash：ecobuild test」）
  function toolSummary(name, input) {
    const given = input && typeof input === 'object' ? input : {};
    let detail = '';
    for (const key of TOOL_KEYS) if (typeof given[key] === 'string' && given[key].trim()) { detail = given[key]; break; }
    detail = detail.split(/\s+/).filter(Boolean).join(' ');
    if (detail.startsWith('/work/')) detail = detail.slice('/work/'.length);
    if (detail.length > 120) detail = detail.slice(0, 119) + '…';
    return detail ? `${name}：${detail}` : name;
  }

  // 届いた発言の差出人（係が入れる言付けの頭「[進行役「名前」から]」・知らせの「[ECOBuild]」）
  function sender(text) {
    const from = /^\[(.+?)から\]\s*/.exec(text);
    if (from) return {from: from[1], text: text.slice(from[0].length)};
    if (/^\[ECOBuild\]\s*/.test(text)) return {from: 'ECOBuild の知らせ', text: text.replace(/^\[ECOBuild\]\s*/, '')};
    return {from: '係', text};   // 最初の仕事・起動し直し・返したときの発言
  }

  const textOf = content => Array.isArray(content)
    ? content.map(b => (b && typeof b === 'object' ? (b.type === 'text' ? b.text : b.type === 'image' ? '（画像）' : '') : String(b))).join('\n')
    : String(content ?? '');

  function clock(at) {
    if (typeof at !== 'number') return '';
    const d = new Date(at * 1000);
    return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  // 出来事を項目に（少しずつ届くので、続きを足していく）。項目：{key, kind, …}
  //   input（届いた発言：from・text）・text（返答の文）・tool（道具：summary・input・output・error。結果は後から届く）・
  //   turn（返答の終わり：seconds・cost・tokens・denials・error）・mark（起動・終わり・API のやり直し）
  // add は {added：新しい項目, changed：結果が届いて変わった道具の項目} を返す
  class EventLog {
    constructor() { this.items = []; this.tools = new Map(); this.count = 0; }
    add(events) {
      const added = [], changed = [];
      const push = item => { item.key = item.key || `e${this.count++}`; this.items.push(item); added.push(item); };
      for (const e of events || []) {
        if (!e || typeof e !== 'object') continue;
        if (e.type === 'ecobuild') {
          if (e.event === 'start') push({kind: 'mark', text: `起動しました（${clock(e.at)}）`, tone: 'start'});
          else if (e.event === 'exit') {
            push({kind: 'mark', text: `${e.requested ? '止めました' : '終わりました'}（${clock(e.at)}`
              + (e.code != null ? `・終了コード ${e.code}` : '') + '）', tone: e.requested ? 'stop' : 'failed'});
          }
        } else if (e.type === 'system') {
          if (e.subtype === 'init') push({kind: 'mark', text: `会話を始めました${e.model ? `（${e.model}）` : ''}`, tone: 'start'});
          else if (e.subtype === 'api_retry') push({kind: 'mark', text: 'API の一時的な失敗。やり直しています', tone: 'warn'});
        } else if (e.type === 'user') {
          const content = e.message?.content;
          if (typeof content === 'string') { push({kind: 'input', ...sender(content)}); continue; }
          for (const block of content || []) {
            if (block?.type !== 'tool_result') continue;
            const tool = this.tools.get(block.tool_use_id);
            const output = textOf(block.content);
            if (tool) { tool.output = output; tool.error = !!block.is_error; tool.done = true; if (!added.includes(tool)) changed.push(tool); }
            else push({kind: 'tool', summary: '（道具の結果）', input: null, output, error: !!block.is_error, done: true});
          }
        } else if (e.type === 'assistant') {
          for (const block of e.message?.content || []) {
            if (block?.type === 'text' && String(block.text || '').trim()) push({kind: 'text', text: String(block.text)});
            else if (block?.type === 'tool_use') {
              const item = {kind: 'tool', key: block.id ? `t${block.id}` : undefined, name: String(block.name || '道具'),
                            summary: toolSummary(String(block.name || '道具'), block.input), input: block.input ?? null,
                            output: '', error: false, done: false};
              push(item);
              if (block.id) this.tools.set(block.id, item);
            }
          }
        } else if (e.type === 'result') {
          const u = e.usage || {};
          push({kind: 'turn', seconds: (e.duration_ms || 0) / 1000, cost: typeof e.total_cost_usd === 'number' ? e.total_cost_usd : null,
                tokens: {input: (u.input_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0),
                         output: u.output_tokens || 0},
                turns: e.num_turns || 0, denials: Array.isArray(e.permission_denials) ? e.permission_denials : [],
                error: e.is_error ? String(e.subtype || 'エラー') : ''});
        }
      }
      return {added, changed};
    }
  }

  // 返答の終わりの区切りの1行
  function turnLine(item) {
    const parts = [`${Math.round(item.seconds)}秒`];
    if (item.cost != null) parts.push(`$${item.cost.toFixed(3)}`);
    if (item.tokens.input || item.tokens.output) parts.push(`入力 ${tokens(item.tokens.input)}・出力 ${tokens(item.tokens.output)}`);
    if (item.denials.length) parts.push(`断られた権限 ${item.denials.length}`);
    if (item.error) parts.push(`エラー ${item.error}`);
    return `返答の終わり（${parts.join('・')}）`;
  }
  const tokens = n => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n));

  const api = {STATE_NAMES, ROLE_NAMES, duration, flatten, look, toolSummary, sender, EventLog, turnLine};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.TeamView = api;
})(this);
