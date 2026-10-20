'use strict';
// チームの表示（main 側）：進行役のタブごとに、そのチーム（AI が起動した作業役。下の進行役の作業役も入れ子で）を見る。
// - 様子：ecobuild -C <進行役> agent team list --nested --recent 3 --json を読み直す（チームを出している窓は 3 秒ごと、
//   出していなければ 15 秒ごと。格子・一覧は様子と最新の数行だけ）。
// - 出来事：詳しい表示を開いた1人だけ、ecobuild -C <作った進行役> agent team log <名前> --follow --json で追う
//   （窓ごとに1つ。20人いても、追うのは開いたものだけ）。
// - 操作も CLI（止める・起動し直す・閉じるは係に頼む：ECOBUILD_AGENT_WINDOW を付けると CLI が係に頼み、係がアプリ用で起動する）。
// GUI は状態の置き場所のファイルを直に読まない（GUI のデータは CLI から）。
const {execFile, spawn} = require('child_process');

const LIST_MS = 3000, LIST_HIDDEN_MS = 15000;
const RECENT = 3;          // 一覧・格子に出す最新の行の数
const LOG_TAIL = 300;      // 詳しい表示を開いたときに読む出来事の数（「前をすべて読む」で全部）
const OP_TIMEOUT = 180000; // 操作を待つ時間（係は返答を終えるのを 60 秒待ってから止める）

let ecobuild = () => 'ecobuild';
let baseEnv = () => ({...process.env});
let onList = () => {};      // (leadId, view) 様子が届いた
let onReplied = () => {};   // (leadId, member) 作業役の返答が終わった（作業中 → 待機中・止まっている）
const teams = new Map();    // 進行役のタブの id → {dir, view, at, busy, shown, states}
const follows = new Map();  // 窓の画面（webContents）→ {proc, path}

function setup(options) {
  ({ecobuild, env: baseEnv, onList, onReplied} = {ecobuild, env: baseEnv, onList, onReplied, ...options});
}

function env(forward) {
  const e = {...baseEnv(), PYTHONIOENCODING: 'utf-8'};
  if (forward) e.ECOBUILD_AGENT_WINDOW = '1'; else delete e.ECOBUILD_AGENT_WINDOW;
  return e;
}

// ecobuild を --json で実行し、{ok, result, error（文）} を返す
function run(args, {forward = false, timeout = 30000} = {}) {
  return new Promise(resolve => {
    execFile(ecobuild(), [...args, '--json'], {windowsHide: true, timeout, env: env(forward), encoding: 'utf8', maxBuffer: 32 * 1024 * 1024},
      (error, stdout) => {
        let doc = null;
        try { doc = JSON.parse(String(stdout).trim().split(/\r?\n/).pop()); } catch (e) { /* 出力なし */ }
        if (doc?.ok) return resolve({ok: true, result: doc.result || {}});
        const e = doc?.error;
        resolve({ok: false, error: e ? [e.message, e.hint].filter(Boolean).join('\n') : (error?.killed ? '時間内に終わりませんでした' : error?.message || '失敗しました')});
      });
  });
}

// 見回り（index.js の poll から）：leads は今ある進行役のタブ [{id, dir}]
function tick(leads) {
  const now = Date.now(), alive = new Set(leads.map(l => l.id));
  for (const id of [...teams.keys()]) if (!alive.has(id)) teams.delete(id);
  for (const lead of leads) {
    let t = teams.get(lead.id);
    if (!t) { t = {dir: lead.dir, view: null, at: 0, busy: false, shown: false, states: new Map()}; teams.set(lead.id, t); }
    if (t.busy || now - t.at < (t.shown ? LIST_MS : LIST_HIDDEN_MS)) continue;
    refresh(lead.id);
  }
}

async function refresh(leadId) {
  const t = teams.get(leadId); if (!t || t.busy) return;
  t.busy = true;
  const got = await run(['-C', t.dir, 'agent', 'team', 'list', '--nested', '--recent', String(RECENT)]);
  t.busy = false; t.at = Date.now();
  if (teams.get(leadId) !== t) return;
  t.view = got.ok ? {members: got.result.members || [], error: '', at: t.at} : {members: t.view?.members || [], error: got.error, at: t.at};
  if (got.ok) watchReplies(leadId, t, got.result.members || []);
  onList(leadId, t.view);
}

function watchReplies(leadId, t, members) {
  const seen = new Map();
  const walk = list => { for (const m of list || []) { seen.set(m.path, m); walk(m.members); } };
  walk(members);
  for (const [path, m] of seen) {
    const was = t.states.get(path);
    if (was === 'working' && m.state !== 'working' && m.mode === 'app') onReplied(leadId, m);
    t.states.set(path, m.state);
  }
  for (const path of [...t.states.keys()]) if (!seen.has(path)) t.states.delete(path);
}

function shown(leadId, on) {
  const t = teams.get(leadId); if (!t) return null;
  const was = t.shown; t.shown = !!on;
  if (on && !was) refresh(leadId);
  return t.view;
}

// 詳しい表示：member {parent, name, path} の出来事を追う（その窓が前に追っていたものは止める）。all：はじめから。
// deliver(path, events, more〔前にもある〕, reset〔読み直しの始まり〕, ended〔追うのが終わった〕)
function follow(contents, member, all, deliver) {
  unfollow(contents);
  if (!member?.parent || !member.name) return;
  const proc = spawn(ecobuild(), ['-C', member.parent, 'agent', 'team', 'log', member.name, '--follow', '--json',
                                  '--tail', all ? '0' : String(LOG_TAIL)], {windowsHide: true, env: env(false)});
  const entry = {proc, path: member.path};
  follows.set(contents, entry);
  let rest = '', batch = [], timer = null, first = true;
  const flush = () => {
    timer = null;
    if (follows.get(contents) !== entry || !batch.length) return;
    deliver(member.path, batch, first && !all ? batch.length >= LOG_TAIL : false, first);
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
  setTimeout(() => { if (first && follows.get(contents) === entry && !batch.length) { first = false; deliver(member.path, [], false, true); } }, 1500);
  // 止めていないのに終わった（作業役が見つからない等）：知らせて、画面が読み直す
  proc.on('exit', () => {
    if (follows.get(contents) !== entry) return;
    clearTimeout(timer); flush(); follows.delete(contents);
    deliver(member.path, [], false, false, true);
  });
  contents.once?.('destroyed', () => unfollow(contents));
}

function unfollow(contents) {
  const entry = follows.get(contents); if (!entry) return;
  follows.delete(contents);
  kill(entry.proc);
}

// ecobuild.exe は python を子に起動するので、子ごと止める
function kill(proc) {
  if (!proc || proc.exitCode !== null) return;
  if (process.platform === 'win32' && proc.pid) {
    execFile('taskkill', ['/pid', String(proc.pid), '/T', '/F'], {windowsHide: true}, () => {});
  } else {
    try { proc.kill(); } catch (e) { /* 終わっている */ }
  }
}

// 操作。member {parent, name, path}。返すのは {ok, result, error}
function operate(action, member, options = {}) {
  const team = args => ['-C', member.parent, 'agent', 'team', ...args];
  switch (action) {
    case 'stop': return run(['-C', member.path, 'agent', 'stop'], {timeout: OP_TIMEOUT});
    case 'restart': return run(team(['restart', member.name, ...(options.resume ? ['--resume'] : [])]), {forward: true, timeout: OP_TIMEOUT});
    case 'close': return run(team(['close', member.name]), {forward: true, timeout: OP_TIMEOUT});
    case 'takeover': return run(team(['takeover', member.name, '--no-open']), {timeout: OP_TIMEOUT});
    case 'handback': return run(team(['handback', member.name]), {timeout: OP_TIMEOUT});
  }
  return Promise.resolve({ok: false, error: `知らない操作です：${action}`});
}

function stopAll() {
  for (const contents of [...follows.keys()]) unfollow(contents);
}

module.exports = {setup, tick, refresh, shown, follow, unfollow, operate, stopAll, view: leadId => teams.get(leadId)?.view || null};
