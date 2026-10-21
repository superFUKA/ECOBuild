'use strict';
// node --test agents（gui/electron で）
const test = require('node:test');
const assert = require('node:assert');
const {liveTabIn} = require('./guard');

test('同じ作業空間に生きたタブがあれば見つける（大文字小文字・末尾の区切りは無視）', () => {
  const tab = {id: 1, kind: 'workspace', dir: '/work/Mod', exited: false};
  assert.strictEqual(liveTabIn([tab], '/work/mod/'), tab);
});

test('終わったタブ・オペレーター・別の作業空間は対象外', () => {
  const sessions = [
    {id: 1, kind: 'workspace', dir: '/work/a', exited: true},
    {id: 2, kind: 'operator', dir: '/work/a', exited: false},
    {id: 3, kind: 'workspace', dir: '/work/b', exited: false},
    {id: 4, kind: 'workspace', exited: false},
  ];
  assert.strictEqual(liveTabIn(sessions, '/work/a'), undefined);
});
