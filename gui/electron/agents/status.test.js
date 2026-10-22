'use strict';
// node --test agents（gui/electron で）
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const status = require('./status');

test('受け箱は古いものから1つずつ取り出し、取ったものは消える', () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'ebinbox'));
  try {
    assert.strictEqual(status.take(folder), null);   // 受け箱がない
    fs.mkdirSync(path.join(folder, 'inbox'));
    fs.writeFileSync(path.join(folder, 'inbox', '00000000000000000002-b.json'), JSON.stringify({text: '二つ目'}));
    fs.writeFileSync(path.join(folder, 'inbox', '00000000000000000001-a.json'), JSON.stringify({text: '一つ目'}));
    assert.strictEqual(status.take(folder).text, '一つ目');
    assert.strictEqual(status.take(folder).text, '二つ目');
    assert.strictEqual(status.take(folder), null);
    assert.deepStrictEqual(fs.readdirSync(path.join(folder, 'inbox')), []);
  } finally {
    fs.rmSync(folder, {recursive: true, force: true});
  }
});

test('置き場所の名前がエージェントの ID なら、それを返す', () => {
  assert.strictEqual(status.agentIdOf('C:/Users/u/.ecobuild/agents/status/calc-1a2b/a-0123456789'), 'a-0123456789');
  assert.strictEqual(status.agentIdOf('/home/u/.ecobuild/agents/status/calc/a-abcdef0123/'), 'a-abcdef0123');
  assert.strictEqual(status.agentIdOf(String.raw`C:\Users\u\.ecobuild\agents\status\operator`), null);   // オペレーター
  assert.strictEqual(status.agentIdOf(String.raw`C:\Users\u\.ecobuild\agents\status\calc\a-0123456789`), 'a-0123456789');
  assert.strictEqual(status.agentIdOf('/x/a-XYZ'), null);
  assert.strictEqual(status.agentIdOf(null), null);
  const mark = '\x1b]1337;ECOBuildAgentStatus=C:/h/agents/status/calc/a-0123456789\x07';
  assert.strictEqual(status.agentIdOf(status.found(`前${mark}後`)), 'a-0123456789');
});
