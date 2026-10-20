'use strict';
// node --test agents（gui/electron で）
const test = require('node:test');
const assert = require('node:assert');
const view = require('./teamview');

test('入れ子のチームは、深さと作った進行役の作業空間を付けて1列になる', () => {
  const members = [{name: '下', role: 'lead', path: '/l/a', members: [{name: '画面', role: 'worker', path: '/l/a/b'}]},
                   {name: '試験', role: 'worker', path: '/l/c'}];
  const flat = view.flatten(members, '/l');
  assert.deepStrictEqual(flat.map(m => [m.name, m.depth, m.parent]), [['下', 0, '/l'], ['画面', 1, '/l/a'], ['試験', 0, '/l']]);
  assert.strictEqual(flat[0].members, undefined);
});

test('様子：長さ・失敗・長く道具を使っていない作業中・人の画面', () => {
  const now = 10000;
  assert.deepStrictEqual(view.look({state: 'working', mode: 'app', since: now - 720, doing_at: now - 30}, now),
                         {label: '作業中 12分', tone: 'working', alert: '', human: false});
  assert.strictEqual(view.look({state: 'working', mode: 'app', since: now - 900, doing_at: now - 660}, now).alert, '11分 道具を使っていません');
  assert.strictEqual(view.look({state: 'working', mode: 'app', since: now - 4000, doing_at: now - 5}, now).alert, '作業中が長くなっています');
  assert.deepStrictEqual(view.look({state: 'stopped', mode: 'app', error: '終了コード 1'}, now),
                         {label: '失敗', tone: 'failed', alert: '止めていないのに終わりました', human: false});
  assert.strictEqual(view.look({state: 'stopped', mode: 'app'}, now).alert, '止まっています');
  assert.strictEqual(view.look({state: 'stopped'}, now).alert, '');   // 動いたことがない・人の画面を閉じた
  assert.strictEqual(view.look({state: 'idle', mode: '', since: now - 5}, now).human, true);
});

test('出来事は項目になり、道具の結果は後から同じ項目に入る', () => {
  const log = new view.EventLog();
  const first = log.add([
    {type: 'ecobuild', event: 'start', at: 0},
    {type: 'system', subtype: 'init', model: 'claude-opus'},
    {type: 'user', message: {content: '[進行役「全体」から] 試験も足して'}},
    {type: 'assistant', message: {content: [{type: 'thinking', thinking: '…'}, {type: 'text', text: '足します'},
                                            {type: 'tool_use', id: 'a', name: 'Bash', input: {command: 'ecobuild  test'}}]}},
    {type: 'rate_limit_event'},
  ]);
  assert.deepStrictEqual(first.added.map(i => i.kind), ['mark', 'mark', 'input', 'text', 'tool']);
  assert.deepStrictEqual([first.added[2].from, first.added[2].text], ['進行役「全体」', '試験も足して']);
  assert.strictEqual(first.added[4].summary, 'Bash：ecobuild test');
  assert.strictEqual(first.added[4].done, false);
  const second = log.add([
    {type: 'user', message: {content: [{type: 'tool_result', tool_use_id: 'a', content: [{type: 'text', text: '1 failed'}], is_error: true}]}},
    {type: 'result', duration_ms: 61500, total_cost_usd: 0.1234, num_turns: 3, usage: {input_tokens: 10, cache_read_input_tokens: 12000, output_tokens: 800},
     permission_denials: [{tool_name: 'WebFetch'}]},
    {type: 'user', message: {content: '[ECOBuild] 作業役「画面」の返答が終わりました。'}},
    {type: 'ecobuild', event: 'exit', code: 1, requested: false, at: 0},
  ]);
  assert.deepStrictEqual(second.changed.map(i => [i.summary, i.output, i.error]), [['Bash：ecobuild test', '1 failed', true]]);
  assert.deepStrictEqual(second.added.map(i => i.kind), ['turn', 'input', 'mark']);
  assert.strictEqual(view.turnLine(second.added[0]), '返答の終わり（62秒・$0.123・入力 12k・出力 800・断られた権限 1）');
  assert.strictEqual(second.added[1].from, 'ECOBuild の知らせ');
  assert.strictEqual(second.added[2].tone, 'failed');
  assert.strictEqual(log.items.length, 8);
});

test('道具の1行は ecobuild と同じ形', () => {
  assert.strictEqual(view.toolSummary('Edit', {file_path: '/work/src/x.py'}), 'Edit：src/x.py');
  assert.strictEqual(view.toolSummary('TodoWrite', {todos: []}), 'TodoWrite');
  assert.strictEqual(view.sender('仕事を読んで').from, '係');
});
