'use strict';
// チームの表示（main 側）：人が起動した、子を起動できるエージェントのタブごとに、その子（AI が起動したもの。子の子も入れ子で）
// を見る。どれもエージェントの ID で CLI を呼ぶ。
// - 様子：ecobuild agent children <ID> --recent 3 --json を読み直す（チームを出している窓は 3 秒ごと、出していなければ
//   15 秒ごと。格子・一覧は様子と最新の数行だけ）。
// - 出来事：詳しい表示を開いた1人だけ、ecobuild agent log <子の ID> --follow --json で追う（窓ごとに1つ。20人いても、
//   追うのは開いたものだけ）。
// - 操作も CLI：agent stop・restart・close・takeover・handback <子の ID>（係が持つものは、CLI が係に頼む）。
// GUI は状態の置き場所のファイルを直に読まない（GUI のデータは CLI から）。
const {execFile, spawn} = require('child_process');

const LIST_MS = 3000, LIST_HIDDEN_MS = 15000;
const RECENT = 3;          // 一覧・格子に出す最新の行の数
const LOG_TAIL = 300;      // 詳しい表示を開いたときに読む出来事の数（「前をすべて読む」で全部）
const OP_TIMEOUT = 180000; // 操作を待つ時間（係は返答を終えるのを 60 秒待ってから止める）

let ecobuild = () => 'ecobuild';
let baseEnv = () => ({...process.env});
let onList = () => {};      // (leadId, view) 様子が届いた
let onReplied = () => {};   // (leadId, member) 子の返答が終わった（作業中 → 待機中・止まっている）
const teams = new Map();    // 親のタブの id → {agentId, view, at, busy, shown, states}
const follows = new Map();  // 窓の画面（webContents）→ {proc, id}

function setup(options) {
  ({ecobuild, env: baseEnv, onList, onReplied} = {ecobuild, env: baseEnv, onList, onReplied, ...options});
}

const env = () => ({...baseEnv(), PYTHONIOENCODING: 'utf-8'});

// ecobuild を --json で実行し、{ok, result, error（文）} を返す
function run(args, {timeout = 30000} = {}) {
  return new Promise(resolve => {
    execFile(ecobuild(), [...args, '--json'], {windowsHide: true, timeout, env: env(), encoding: 'utf8', maxBuffer: 32 * 1024 * 1024},
      (error, stdout) => {
        let doc = null;
        try { doc = JSON.parse(String(stdout).trim().split(/\r?\n/).pop()); } catch (e) { /* 出力なし */ }
        if (doc?.ok) return resolve({ok: true, result: doc.result || {}});
        const e = doc?.error;
        resolve({ok: false, error: e ? [e.message, e.hint].filter(Boolean).join('\n') : (error?.killed ? '時間内に終わりませんでした' : error?.message || '失敗しました')});
      });
  });
}

// 見回り（index.js の poll から）：leads は今ある、子を起動できるエージェントのタブ [{id（タブ）, agentId}]。
// 同じタブでも、新しい会話で起動し直すと別のエージェント（ID）になるので、そのときは読み直す
function tick(leads) {
  const now = Date.now(), alive = new Set(leads.map(l => l.id));
  for (const id of [...teams.keys()]) if (!alive.has(id)) teams.delete(id);
  for (const lead of leads) {
    let t = teams.get(lead.id);
    if (!t || t.agentId !== lead.agentId) {
      t = {agentId: lead.agentId, view: null, at: 0, busy: false, shown: !!t?.shown, states: new Map()}; teams.set(lead.id, t);
    }
    if (t.busy || now - t.at < (t.shown ? LIST_MS : LIST_HIDDEN_MS)) continue;
    refresh(lead.id);
  }
}

async function refresh(leadId) {
  const t = teams.get(leadId); if (!t || t.busy) return;
  t.busy = true;
  const got = await run(['agent', 'children', t.agentId, '--recent', String(RECENT)]);
  t.busy = false; t.at = Date.now();
  if (teams.get(leadId) !== t) return;
  t.view = got.ok ? {members: got.result.members || [], error: '', at: t.at} : {members: t.view?.members || [], error: got.error, at: t.at};
  if (got.ok) watchReplies(leadId, t, got.result.members || []);
  onList(leadId, t.view);
}

function watchReplies(leadId, t, members) {
  const seen = new Map();
  const walk = list => { for (const m of list || []) { seen.set(m.id, m); walk(m.members); } };
  walk(members);
  for (const [id, m] of seen) {
    const was = t.states.get(id);
    if (was === 'working' && m.state !== 'working' && m.mode === 'app') onReplied(leadId, m);
    t.states.set(id, m.state);
  }
  for (const id of [...t.states.keys()]) if (!seen.has(id)) t.states.delete(id);
}

function shown(leadId, on) {
  const t = teams.get(leadId); if (!t) return null;
  const was = t.shown; t.shown = !!on;
  if (on && !was) refresh(leadId);
  return t.view;
}

// 詳しい表示：member {id, name} の出来事を追う（その窓が前に追っていたものは止める）。all：はじめから。
// deliver(id, events, more〔前にもある〕, reset〔読み直しの始まり〕, ended〔追うのが終わった〕)
function follow(contents, member, all, deliver) {
  unfollow(contents);
  if (!member?.id) return;
  const proc = spawn(ecobuild(), ['agent', 'log', member.id, '--follow', '--json', '--tail', all ? '0' : String(LOG_TAIL)],
                     {windowsHide: true, env: env()});
  const entry = {proc, id: member.id};
  follows.set(contents, entry);
  let rest = '', batch = [], timer = null, first = true;
  const flush = () => {
    timer = null;
    if (follows.get(contents) !== entry || !batch.length) return;
    deliver(member.id, batch, first && !all ? batch.length >= LOG_TAIL : false, first);
    batch = []; first = false;
  };
  proc.stdout.setEncoding('utf8');
  proc.stdout.on('data', chunk => {
    const lines = (rest + chunk).split(/\r?\n/); rest = lines.pop();
    for (const line of lines) {
      let event; try { event = JSON.parse(line); } catch (e) { continue; }
      if (event && typeof event === 'object' && 'type' in event) batch.push(event);   // 最後の結果の JSON（ok 等）は出来事でない
    }
    if (batch.length && !timer) timer = setTimeout(flush, first ? 300 : 120);
  });
  proc.stderr.on('data', () => {});
  proc.on('error', () => {});
  // 出来事がまだない：読み終わったことを知らせる（「読んでいます…」のままにしない）
  setTimeout(() => { if (first && follows.get(contents) === entry && !batch.length) { first = false; deliver(member.id, [], false, true); } }, 1500);
  // 止めていないのに終わった（子が見つからない等）：知らせて、画面が読み直す
  proc.on('exit', () => {
    if (follows.get(contents) !== entry) return;
    clearTimeout(timer); flush(); follows.delete(contents);
    deliver(member.id, [], false, false, true);
  });
  contents.once?.('destroyed', () => unfollow(contents));
}

function unfollow(contents) {
  const entry = follows.get(contents); if (!entry) return;
  follows.delete(contents);
  kill(entry.proc);
}

// ecobuild.exe は python を子に起動するので、子ごと止める。taskkill はフルパスで（PATH の System32 が展開されていない
// PC では名前で見つからない）
function kill(proc) {
  if (!proc || proc.exitCode !== null) return;
  if (process.platform === 'win32' && proc.pid) {
    execFile(require('path').join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'taskkill.exe'), ['/pid', String(proc.pid), '/T', '/F'], {windowsHide: true}, () => {});
  } else {
    try { proc.kill(); } catch (e) { /* 終わっている */ }
  }
}

// 操作の CLI の引数（member {id}。options.resume：続きから起動し直す）。知らない操作は null
function operation(action, member, options = {}) {
  switch (action) {
    case 'stop': return ['agent', 'stop', member.id];
    case 'restart': return ['agent', 'restart', member.id, ...(options.resume ? ['--resume'] : [])];
    case 'close': return ['agent', 'close', member.id];
    case 'takeover': return ['agent', 'takeover', member.id, '--no-open'];
    case 'handback': return ['agent', 'handback', member.id];
  }
  return null;
}

// 操作。返すのは {ok, result, error}
function operate(action, member, options = {}) {
  if (!member?.id) return Promise.resolve({ok: false, error: '子のエージェントの ID が分かりません'});
  const args = operation(action, member, options);
  return args ? run(args, {timeout: OP_TIMEOUT}) : Promise.resolve({ok: false, error: `知らない操作です：${action}`});
}

function stopAll() {
  for (const contents of [...follows.keys()]) unfollow(contents);
}

// The module (the original clone) a member's place belongs to: a workspace is <the original clone>/.ecobuild/w/<name>
// (a git worktree inside it), and the module window is opened on the original clone (as the GUI server's _module_of).
function moduleRoot(place) {
  const found = /^(.*?)[\\/]\.ecobuild[\\/]w[\\/][^\\/]+[\\/]?$/.exec(String(place || ''));
  return found ? found[1] : place;
}

module.exports = {setup, tick, refresh, shown, follow, unfollow, operation, operate, stopAll, moduleRoot, kill, view: leadId => teams.get(leadId)?.view || null};
