'use strict';
// エージェントが書き出す状態（ecobuild_agent.status：status.json・replied.json）を読む。
// 置き場所は、端末の出力の見えない印（OSC 1337 の ECOBuildAgentStatus=<場所>）で分かる（found）。作業空間のエージェントの
// 置き場所はエージェントごとで、その名前がエージェントの ID（agentIdOf）。
// 使用量の制限（5時間・週）はアカウント共通なので、どのタブから届いたものも1つにまとめて、最新を持つ。
const fs = require('fs');
const path = require('path');

const MARK = /\x1b\]1337;ECOBuildAgentStatus=([^\x07\x1b]*)(?:\x07|\x1b\\)/;
let limits = {};

// 出力の中の印から、置き場所（なければ null）
function found(data) {
  const m = MARK.exec(data);
  return m ? m[1] : null;
}

// 置き場所の名前がエージェントの ID（a- と16進の10文字）なら、その ID（オペレーター等、ID でなければ null）
function agentIdOf(folder) {
  const name = String(folder || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop();
  return /^a-[0-9a-f]{10}$/.test(name) ? name : null;
}

function read(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { return null; }
}

// タブの状態を読み直す。変わったものを返す：{info（status.json が新しくなった）, replied（返答が終わった：{message}）}
function poll(s) {
  const result = {};
  if (!s.statusDir) return result;
  const info = read(path.join(s.statusDir, 'status.json'));
  if (info && info.at !== s.info?.at) {
    s.info = info; result.info = true;
    for (const [name, value] of Object.entries(info.limits || {})) {
      if (value && (!limits[name] || info.at >= (limits[name].at || 0))) limits[name] = {...value, at: info.at};
    }
  }
  const replied = read(path.join(s.statusDir, 'replied.json'));
  if (replied && replied.at !== s.repliedAt) {
    const first = s.repliedAt === undefined && s.startedAt && replied.at * 1000 < s.startedAt;   // 前の起動のもの
    s.repliedAt = replied.at;
    if (!first) result.replied = {message: replied.message || ''};
  }
  return result;
}

// 下のバーに出すもの：モデル・コンテキスト・制限の残り（%）とリセットの時刻
function summary(s) {
  const now = Date.now() / 1000;
  const limit = name => {
    const w = limits[name];
    return w && w.used_percentage != null && !(w.resets_at && w.resets_at < now)
      ? {remaining: Math.max(0, Math.round(100 - w.used_percentage)), resetsAt: w.resets_at || null} : null;
  };
  return {model: s?.info?.model || null, context: s?.info?.context ?? null, session: s?.info?.session || null,
          fiveHour: limit('five_hour'), weekly: limit('seven_day')};
}

// 受け箱（inbox/。ECOBuild の係が入れる：言付け・子の知らせ）の一番古いものを取り出す（なければ null）。
// ecobuild_agent.status.take と同じ形：名前の順が届いた順、.taken に名前を変えて取ったものだけを使う
function take(folder) {
  const inbox = path.join(folder, 'inbox');
  let names; try { names = fs.readdirSync(inbox).filter(n => n.endsWith('.json')).sort(); } catch (e) { return null; }
  for (const name of names) {
    const file = path.join(inbox, name), taken = file.replace(/\.json$/, '.taken');
    try { fs.renameSync(file, taken); } catch (e) { continue; }   // ほかが取った
    const data = read(taken);
    try { fs.unlinkSync(taken); } catch (e) { /* もうない */ }
    if (data && typeof data === 'object') return data;
  }
  return null;
}

module.exports = {found, agentIdOf, poll, summary, take};
