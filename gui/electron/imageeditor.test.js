'use strict';
// node --test imageeditor.test.js（gui/electron で）：作業空間のコンテナのイメージのエディター（gui/static/imageeditor.js）が、
// ecobuild container dockerfile --json の答えから、何ができるか（灰色とその理由）を決める。
const test = require('node:test');
const assert = require('node:assert');
const editor = require('../static/imageeditor.js');

const answer = values => ({exists: true, text: 'FROM ubuntu:24.04\n', hash: 'abc123', environment: 'ecobuild-env-calc:abc123',
  image: 'ecobuild-calc:def456', image_ready: false, outdated: false, container: false, container_image: '',
  docker_ready: true, docker_detail: 'Docker 29.1.3', changed: false, editable: true, reason: '', ...values});

test('タスクブランチでないときは、編集・保存を灰色にして CLI の理由を出す（試しに作るのはできる）', () => {
  const reason = 'コンテナの環境（Dockerfile）の変更はタスクブランチ（task/<番号>のブランチ）でだけ行えます。';
  const s = editor.editorState(answer({editable: false, reason}), {dirty: false});
  assert.strictEqual(s.canEdit, false);
  assert.strictEqual(s.canSave, false);
  assert.strictEqual(s.saveReason, reason);
  assert.strictEqual(s.canBuild, true);
  assert.ok(editor.notes(answer({editable: false, reason})).some(([line, kind]) => line === reason && kind === 'warn'));
});

test('タスクブランチでは、変えたときだけ保存できる。実行中はどれもできない', () => {
  assert.strictEqual(editor.editorState(answer(), {dirty: false}).canSave, false);
  assert.strictEqual(editor.editorState(answer(), {dirty: false}).saveReason, '変更はありません');
  const edited = editor.editorState(answer(), {dirty: true});
  assert.ok(edited.canEdit && edited.canSave && edited.canBuild);
  const working = editor.editorState(answer(), {dirty: true, working: true});
  assert.ok(!working.canEdit && !working.canSave && !working.canBuild);
});

test('Docker がなければ試しに作るを灰色にして、導入の案内を出す', () => {
  const s = editor.editorState(answer({docker_ready: false, docker_detail: 'WSL2 がありません'}));
  assert.strictEqual(s.canBuild, false);
  assert.match(s.buildReason, /WSL2 がありません.*setup --docker/);
  assert.strictEqual(editor.editorState(null).canEdit, false);   // 読み込むまでは何もできない
});

test('ファイルがなければ型のひな型と分かり、イメージがあるか・コンテナが古いかを出す', () => {
  const lines = editor.notes(answer({exists: false, image_ready: true, outdated: true, container_image: 'ecobuild-calc:old'})).map(([line]) => line);
  assert.ok(lines[0].includes('型のひな型') && lines[0].includes(editor.FILE));
  assert.ok(lines.some(line => line.includes('このPCにあります')));
  assert.ok(lines.some(line => line.includes('ecobuild-calc:old') && line.includes('作り直します')));
});
