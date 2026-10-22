'use strict';
// node --test agents（gui/electron で）
const test = require('node:test');
const assert = require('node:assert');
const team = require('./team');

test('子の操作は、子のエージェントの ID で ecobuild agent … を呼ぶ（作業空間・名前では呼ばない）', () => {
  const member = {id: 'a-0123456789', name: '画面', path: '/w/calc/.ecobuild/w/12'};
  assert.deepStrictEqual(team.operation('stop', member), ['agent', 'stop', 'a-0123456789']);
  assert.deepStrictEqual(team.operation('restart', member), ['agent', 'restart', 'a-0123456789']);
  assert.deepStrictEqual(team.operation('restart', member, {resume: true}), ['agent', 'restart', 'a-0123456789', '--resume']);
  assert.deepStrictEqual(team.operation('close', member), ['agent', 'close', 'a-0123456789']);
  assert.deepStrictEqual(team.operation('takeover', member), ['agent', 'takeover', 'a-0123456789', '--no-open']);
  assert.deepStrictEqual(team.operation('handback', member), ['agent', 'handback', 'a-0123456789']);
  assert.strictEqual(team.operation('send', member), null);   // 知らない操作
});

test('ID の分からない子は操作しない', async () => {
  assert.deepStrictEqual(await team.operate('stop', {name: '画面', path: '/w'}), {ok: false, error: '子のエージェントの ID が分かりません'});
});
