'use strict';
// Claude Code の端末の画面（装飾を除いた文字）から、今の状態を読む。Electron なしで試せるよう分けてある（screen.test.js）。
//   thinking：作業中（入力欄の上に「✻ Sock-hopping… (12s · esc to interrupt)」のような行）
//   waiting ：返答は終えたが、裏で走らせたビルド・テスト等の終わりを待っている（入力欄の下のバーの「· 1 shell」）
//   choice  ：選択肢（質問・権限の確認など、↑↓で選んで Enter）を出している
//   idle    ：入力を待っている
//   starting：まだ入力欄が出ていない（起動中・ログイン中など）

const MENU_ITEM = /^\s*[❯›]\s*\S/m;
const MENU_HINT = /Enter to (select|confirm)|to navigate|Esc to (cancel|exit)|↑\s*\/?\s*↓/i;
const SEPARATOR = /^\s*─{10,}/;

// 作業中の行。行頭から「記号＋英語の動詞＋…」（終わると「✻ Baked for 4s」になり … が無い）。字下げした行や、途中で切れて
// 「…」で終わるだけの行は作業中ではない
function isBusyLine(line) {
  return /^[^\s\w❯>●⎿]\s+[A-Za-z][\w'-]*(?: [A-Za-z][\w'-]*){0,2}…(\s|$)/.test(line) || /esc to interrupt/i.test(line);
}

// 裏で何かを待っている（「⏵⏵ auto mode on · 1 shell」「· 2 background tasks」など、数と種類が出る）
function isWaitingLine(line) {
  return /(?:^|·)\s*\d+\s+(?:background\s+|local\s+)?(?:shells?|agents?|tasks?|monitors?)(?:\s+still\s+running)?\s*(?:·|\(|$)/i.test(line.trim());
}

// 選択肢：操作の案内が画面の一番下（空でない最後の3行以内）にあり、その上の選択肢の行より下に入力欄の区切り線が無いとき
// （会話の履歴に選択肢らしい文字が残っているだけのときに反応しない）
function looksLikeChoice(text) {
  const lines = text.split('\n').filter(l => l.trim());
  const hint = lines.slice(-3).findLastIndex(l => MENU_HINT.test(l));
  if (hint < 0) return false;
  const end = lines.length - 3 + hint;
  for (let i = end - 1; i >= Math.max(0, end - 30); i--) {
    if (SEPARATOR.test(lines[i])) return false;
    if (MENU_ITEM.test(lines[i])) return true;
  }
  return false;
}

// 画面の状態。input：入力欄の文字。reply：最後の返答の1行目あたり（ツールの実行は除く）。question・choice：選択肢のとき
function parse(text) {
  const lines = text.split('\n').map(l => l.replace(/\s+$/, ''));
  if (looksLikeChoice(text)) {
    const item = lines.findLast(l => MENU_ITEM.test(l)) || '';
    const before = lines.slice(0, lines.indexOf(item)).map(l => l.trim()).filter(l => l && !SEPARATOR.test(l));
    return {state: 'choice', choice: item.replace(/^\s*[❯›]\s*/, ''), question: before.at(-2) || before.at(-1) || ''};
  }
  const seps = lines.flatMap((l, i) => (SEPARATOR.test(l) ? [i] : []));
  if (seps.length < 2) return {state: 'starting'};
  const [top, bottom] = seps.slice(-2);
  const box = lines.slice(top + 1, bottom).map(l => l.trim()).filter(Boolean);
  if (!box.length || !/^[❯>]/.test(box[0])) return {state: 'starting'};
  const input = box.map((l, i) => (i ? l : l.replace(/^[❯>]\s?/, ''))).join(' ').replace(/[▀-▟]/g, '').trim();
  const body = lines.slice(0, top), footer = lines.slice(bottom + 1);
  const busy = body.slice(-6).some(isBusyLine);
  let reply = '';
  for (let i = body.length - 1; i >= 0; i--) {
    const m = body[i].match(/^●\s+(.*)/);
    if (!m || /^[A-Za-z]+\(/.test(m[1])) continue;
    const rest = [];
    for (let j = i + 1; j < body.length && /^\s{2,}\S/.test(body[j]) && !/^\s*⎿/.test(body[j]) && rest.length < 3; j++) rest.push(body[j].trim());
    reply = [m[1], ...rest].join(' ');
    break;
  }
  const waiting = !busy && footer.some(isWaitingLine);
  return {state: busy ? 'thinking' : waiting ? 'waiting' : 'idle', input, reply};
}

// 画面の最後の n 行（空行を除く）。タブの一覧・右下の表示に出す
function lastLines(text, n) {
  return text.split('\n').map(l => l.replace(/\s+$/, '')).filter(l => l.trim()).slice(-n).join('\n');
}

module.exports = {isBusyLine, isWaitingLine, looksLikeChoice, parse, lastLines};
