'use strict';
// The image editor (イメージ（Dockerfile）) of a workspace's container: the module's environment
// .ecobuild/container/Dockerfile (ecobuild container dockerfile) to edit and save (--write -: only on a task branch, as
// files change only there; it only writes the file, the commit is the commit panel's), 試しに作る (container image
// build --workspace <here>: the image from this workspace's Dockerfile), and ECOBuild's layer on it to read (container
// recipe). The GUI only runs ecobuild: what can be done comes from its answer (editable・reason・docker_ready).
// editorState・notes are plain functions (node's tests read them: gui/electron/imageeditor.test.js).
(() => {
  const FILE = '.ecobuild/container/Dockerfile';
  // What the buttons can do now. r: container dockerfile's result (null while it is read). dirty: the text was edited.
  // A button that cannot be used is grey with its reason (the environment cannot: grey, as the menus).
  function editorState(r, {dirty = false, working = false} = {}) {
    if (!r) return {canEdit: false, canSave: false, canBuild: false, saveReason: '読み込んでいます', buildReason: '読み込んでいます'};
    const saveReason = working ? '実行しています' : !r.editable ? (r.reason || 'タスクブランチでだけ書き換えられます') : !dirty ? '変更はありません' : '';
    const buildReason = working ? '実行しています'
      : !r.docker_ready ? `Docker が使えません（${r.docker_detail || '状態が分かりません'}）。ecobuild setup --docker で導入できます` : '';
    return {canEdit: !!r.editable && !working, canSave: !saveReason, canBuild: !buildReason, saveReason, buildReason};
  }
  // What is known of the file and its image, as lines: [text, kind ('' / 'ok' / 'warn')].
  function notes(r) {
    if (!r) return [];
    return [
      [r.exists ? `リポジトリの ${FILE}（材料のハッシュ ${r.hash}）` : `まだ ${FILE} はありません（型のひな型を表示しています。保存するとリポジトリに置きます）`, ''],
      [`イメージ：${r.image}（${r.image_ready ? 'このPCにあります' : 'まだ作っていません'}）`, r.image_ready ? 'ok' : ''],
      ...(r.outdated ? [[`この作業空間のコンテナは古いイメージ（${r.container_image}）です。次に動かすときに作り直します`, 'warn']] : []),
      ...(r.editable ? [] : [[r.reason || 'タスクブランチでだけ書き換えられます', 'warn']]),
    ];
  }
  if (typeof module !== 'undefined') { module.exports = {editorState, notes, FILE}; return; }

  const {esc} = ECO;
  // Opens the editor for the workspace dir. changed(): the file was written (the workspace shows the change to commit).
  function open(dir, {changed = () => {}} = {}) {
    let r = null, dirty = false, working = false;
    return ECO.dialog({title: 'イメージ（Dockerfile）', wide: true, buttons: [],
      body: `<p class="eco-intro">この作業空間のコンテナのイメージは、モジュールの環境（${esc(FILE)}）に ECOBuild を重ねて作ります。環境は解析ツール等を足して、タスクブランチで保存・コミットし、提出してほかのPCと共有します。保存はファイルを書くだけです（コミットは「コミット」の欄で）。</p>
        <ul class="ie-notes"></ul>
        <textarea class="ie-text" spellcheck="false" rows="16" aria-label="${esc(FILE)}" readonly>読み込んでいます…</textarea>
        <p class="ie-reason eco-hint"></p><ol class="ie-progress eco-busy-live"></ol><p class="eco-error" role="alert"></p>
        <details class="ie-layer"><summary>ECOBuild が重ねる層（読むだけ。ECOBuild の版で変わるので、リポジトリには書きません）</summary><pre>読み込んでいます…</pre></details>`,
      onOpen: d => {
        d.classList.add('image-editor');
        const text = d.querySelector('.ie-text'), error = d.querySelector('.eco-error'), reason = d.querySelector('.ie-reason');
        const progress = d.querySelector('.ie-progress'), actions = d.querySelector('.eco-actions');
        const button = (label, cls, onClick) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = label; if (cls) b.className = cls; b.addEventListener('click', onClick); actions.append(b); return b; };
        const close = async () => {
          if (working) return;
          if (dirty && !await ECO.confirm({title: '保存していない変更', message: 'Dockerfile の変更を保存せずに閉じます。', ok: '閉じる', danger: true})) return;
          d.close();
        };
        d.addEventListener('cancel', e => { e.preventDefault(); close(); });   // Esc: the same as 閉じる
        button('閉じる', '', close);
        const build = button('試しに作る', '', () => tryBuild());
        const save = button('保存', 'primary', () => write());
        const draw = () => {
          const s = editorState(r, {dirty, working});
          text.readOnly = !s.canEdit;
          save.disabled = !s.canSave; save.title = s.saveReason || `${FILE} に書きます（ecobuild container dockerfile --write）`;
          build.disabled = !s.canBuild;
          build.title = s.buildReason || (dirty ? '保存してから、この Dockerfile でイメージを作ります（container image build）' : 'この Dockerfile でイメージを作ります（container image build。数分かかります）');
          // Why it is grey: the task branch (the file) first, then Docker (the trial).
          reason.textContent = r && !r.editable ? `保存できません：${s.saveReason}` : r && !s.canBuild && !working ? `試しに作れません：${s.buildReason}` : '';
          d.querySelector('.ie-notes').innerHTML = notes(r).filter(([line]) => !(r && !r.editable && line === r.reason))
            .map(([line, kind]) => `<li class="${kind}">${esc(line)}</li>`).join('');
        };
        const fail = doc => { error.textContent = [doc.error?.message, doc.error?.hint].filter(Boolean).join('\n'); };
        const loadLayer = () => ECO.cli(dir, ['container', 'recipe'], {quiet: true}).then(doc => {
          d.querySelector('.ie-layer pre').textContent = doc.ok ? doc.result.layer : `読めませんでした：${doc.error?.message || ''}`;
        });
        const load = async () => {
          const doc = await ECO.cli(dir, ['container', 'dockerfile'], {quiet: true});
          if (!doc.ok) { fail(doc); text.value = ''; r = null; draw(); return false; }
          r = doc.result; if (!dirty) text.value = r.text;
          draw(); return true;
        };
        text.addEventListener('input', () => { dirty = !!r && text.value !== r.text; draw(); });
        text.addEventListener('keydown', e => {
          if (e.key === 's' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!save.disabled) write(); }
          if (e.key === 'Tab' && !text.readOnly) { e.preventDefault(); text.setRangeText('    ', text.selectionStart, text.selectionEnd, 'end'); text.dispatchEvent(new Event('input')); }
        });
        async function write() {
          working = true; error.textContent = ''; draw();
          const doc = await ECO.cli(dir, ['container', 'dockerfile', '--write', '-'], {stdin: text.value});
          working = false;
          if (!doc.ok) { fail(doc); draw(); return false; }
          r = doc.result; dirty = false; text.value = r.text; draw();
          ECO.toast(r.changed ? `${FILE} を保存しました（コミットは「コミット」の欄で）。` : '同じ中身です。', r.changed ? 'ok' : 'info');
          if (r.changed) { changed(); loadLayer(); }
          return true;
        }
        async function tryBuild() {
          if (dirty && !await write()) return;
          working = true; error.textContent = ''; progress.innerHTML = '<li class="now">イメージを作っています（数分かかることがあります）…</li>'; draw();
          const doc = await ECO.cli(dir, ['container', 'image', 'build', '--workspace', dir], {onProgress: lines => {
            progress.innerHTML = lines.map((line, i) => `<li class="${i === lines.length - 1 ? 'now' : 'past'}">${esc(line)}</li>`).join('');
          }});
          working = false; progress.innerHTML = '';
          if (!doc.ok) fail(doc);
          else ECO.toast(doc.result.built.length ? `イメージを作りました：${doc.result.built.join('、')}` : '今の Dockerfile のイメージはもうあります。');
          await load();
        }
        draw();
        load(); loadLayer();
      }});
  }
  window.IMAGE_EDITOR = {open, editorState, notes};
})();
