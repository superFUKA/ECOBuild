'use strict';
// node --test agents（gui/electron で）
const test = require('node:test');
const assert = require('node:assert');
const screen = require('./screen');

const SEP = '─'.repeat(40);
const frame = (body, input = '', footer = '  ⏵⏵ bypass permissions on') => [...body, SEP, `❯ ${input}`, SEP, footer].join('\n');

test('入力を待っているときは idle で、最後の返答を読む', () => {
  const s = screen.parse(frame(['● 直しました。', '  テストも通りました。', '', '● Bash(ecobuild test)', '  ⎿  ok']));
  assert.deepStrictEqual(s, {state: 'idle', input: '', reply: '直しました。 テストも通りました。'});
});

test('作業中は thinking、裏の待ちは waiting', () => {
  assert.strictEqual(screen.parse(frame(['✻ Sock-hopping… (12s · esc to interrupt)'])).state, 'thinking');
  assert.strictEqual(screen.parse(frame(['✻ Baked for 4s'], '', '  ⏵⏵ bypass permissions on · 1 shell')).state, 'waiting');
  assert.strictEqual(screen.parse(frame(['✻ Baked for 4s'])).state, 'idle');
});

test('選択肢は、案内が一番下にあるときだけ', () => {
  const choice = ['Do you want to proceed?', '❯ 1. Yes', '  2. No', '', 'Enter to confirm · Esc to cancel'].join('\n');
  assert.deepStrictEqual(screen.parse(choice), {state: 'choice', choice: '1. Yes', question: 'Do you want to proceed?'});
  assert.strictEqual(screen.parse(frame(['❯ 1. Yes', 'Enter to confirm'])).state, 'idle');   // 履歴に残っているだけ
});

test('入力欄が出るまでは starting', () => {
  assert.strictEqual(screen.parse('Select login method:').state, 'starting');
});
