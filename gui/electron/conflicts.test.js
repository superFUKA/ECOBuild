'use strict';
// node --test conflicts.test.js（gui/electron で）：衝突を直す画面（gui/static/conflicts.js）が、ファイルの衝突の印を
// 箇所ごとに分け、選んだ側から結果を作る。
const test = require('node:test');
const assert = require('node:assert');
const {parse, build, remaining} = require('../static/conflicts.js');

const FILE = 'a\n<<<<<<< HEAD\nours 1\nours 2\n=======\ntheirs\n>>>>>>> dev\nb\n<<<<<<< HEAD\nx\n||||||| base\nbase\n=======\ny\n>>>>>>> dev\nc\n';

test('衝突の印を箇所ごとに分ける（diff3 の共通の元も・始まる行）', () => {
  const pieces = parse(FILE), hunks = pieces.filter(p => p.text === undefined);
  assert.strictEqual(hunks.length, 2);
  assert.deepStrictEqual([hunks[0].current, hunks[0].base, hunks[0].incoming, hunks[0].line], ['ours 1\nours 2\n', null, 'theirs\n', 2]);
  assert.deepStrictEqual([hunks[1].current, hunks[1].base, hunks[1].incoming, hunks[1].line], ['x\n', 'base\n', 'y\n', 9]);
  assert.strictEqual(remaining(FILE), 2);
});

test('選ばなければ元のまま、選んだ箇所だけ置き換わる', () => {
  const pieces = parse(FILE);
  assert.strictEqual(build(pieces, [null, null]), FILE);
  assert.strictEqual(build(pieces, ['current', 'incoming']), 'a\nours 1\nours 2\nb\ny\nc\n');
  assert.strictEqual(build(pieces, ['both', 'both-incoming-first']), 'a\nours 1\nours 2\ntheirs\nb\ny\nx\nc\n');
  const half = build(pieces, ['incoming', null]);
  assert.strictEqual(remaining(half), 1);
  assert.ok(half.startsWith('a\ntheirs\nb\n<<<<<<< HEAD\n'));
});

test('改行（CRLF）を保つ・終わりの印のないものは衝突にしない', () => {
  const crlf = FILE.replace(/\n/g, '\r\n'), pieces = parse(crlf);
  assert.strictEqual(build(pieces, [null, null]), crlf);
  assert.strictEqual(build(pieces, ['both', 'current']), 'a\r\nours 1\r\nours 2\r\ntheirs\r\nb\r\nx\r\nc\r\n');
  const broken = 'a\n<<<<<<< HEAD\nx\n=======\ny\n';
  assert.deepStrictEqual(parse(broken), [{text: broken}]);
  assert.strictEqual(remaining('<<<<<<<< not a mark\n'), 0);
});

test('最後の行に改行のない側も、両方を採ると行が分かれる', () => {
  const pieces = parse('<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> dev');
  assert.strictEqual(build(pieces, ['both']), 'x\ny\n');
  assert.strictEqual(build(parse('<<<<<<< HEAD\r\nx\r\n=======\r\n>>>>>>> dev\r\n'), ['both-incoming-first']), 'x\r\n');
});
