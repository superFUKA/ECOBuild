'use strict';
// 衝突を直す: the conflicted files of what stopped (sync・rebase・revert・stash), each conflict in a file shown as its
// two sides to choose from (one side, both in either order), and the result to edit by hand before it is saved. It
// only writes the file (the server's write); 続ける (sync continue) registers the files without the conflict marks.
// A file that cannot be read as UTF-8 text (or is too big, or gone on one side) is taken whole from one side
// (sync take) or fixed in TortoiseGit.
// parse・build・remaining are plain functions (node's tests read them: gui/electron/conflicts.test.js).
(() => {
  const START = /^<{7}(?: |\r?\n|$)/, BASE = /^\|{7}(?: |\r?\n|$)/, MIDDLE = /^={7}(?:\r?\n|$)/, END = /^>{7}(?: |\r?\n|$)/;
  const lines = text => text.match(/[^\n]*\n|[^\n]+$/g) || [];
  // The file as pieces: plain text ({text}) and conflicts ({current, base, incoming, line}: line is where it starts,
  // base is null without diff3). An unfinished mark is left as text.
  function parse(text) {
    const out = [], all = lines(text);
    let plain = '', i = 0;
    while (i < all.length) {
      if (!START.test(all[i])) { plain += all[i++]; continue; }
      let j = i + 1, part = 'current';
      const hunk = {current: '', base: null, incoming: '', line: 0};
      for (; j < all.length; j++) {
        const l = all[j];
        if (part === 'current' && BASE.test(l)) { part = 'base'; hunk.base = ''; }
        else if (part !== 'incoming' && MIDDLE.test(l)) part = 'incoming';
        else if (part === 'incoming' && END.test(l)) break;
        else hunk[part] += l;
      }
      if (j >= all.length) { plain += all[i++]; continue; }   // no end mark: not a conflict
      if (plain) out.push({text: plain});
      plain = '';
      hunk.line = out.reduce((n, p) => n + lines(p.text ?? p.raw).length, 1);
      hunk.raw = all.slice(i, j + 1).join('');
      out.push(hunk);
      i = j + 1;
    }
    if (plain) out.push({text: plain});
    return out;
  }
  // A side's text ends with a line break when it is followed by more (the last line of a side may lack one).
  const ended = s => !s || s.endsWith('\n') ? s : s + (/\r\n/.test(s) ? '\r\n' : '\n');
  // The file from the pieces and the choices (per conflict: current・incoming・both・both-incoming-first; none keeps the marks).
  function build(pieces, choices) {
    let k = 0;
    return pieces.map(p => {
      if (p.text !== undefined) return p.text;
      const c = choices[k++];
      return c === 'current' ? p.current : c === 'incoming' ? p.incoming
        : c === 'both' ? ended(p.current) + p.incoming : c === 'both-incoming-first' ? ended(p.incoming) + p.current : p.raw;
    }).join('');
  }
  // How many conflict marks are left in a text (the conflicts not fixed yet).
  const remaining = text => lines(text).filter(l => START.test(l)).length;
  if (typeof module !== 'undefined') { module.exports = {parse, build, remaining}; return; }

  const {esc} = ECO;
  const CHOICES = [['current', 0], ['incoming', 1], ['both', 'both'], ['both-incoming-first', 'both-rev']];
  // Opens the screen on the conflicted files (first: the one to show first).
  WS.resolveConflicts = async first => {
    const sides = WS.sides(), files = [...(WS.status?.conflicted || [])];
    if (!files.length) return ECO.toast('衝突したファイルはありません。');
    const state = new Map();   // path -> {r (read), pieces, choices, saved (the text on disk), text (edited), taken, error}
    let current = files.includes(first) ? first : files[0], continueAfter = false;
    const label = c => c === 'current' ? `${sides[0]}` : c === 'incoming' ? `${sides[1]}` : c === 'both' ? '両方（今の側が先）' : '両方（入ってくる側が先）';
    await ECO.dialog({title: '衝突を直す', wide: true, buttons: [],
      body: `<p class="eco-intro">衝突した箇所ごとに、どちらの側を使うかを選びます。下の結果は直接直せます。保存しても登録はしません：全部のファイルを直したら「続ける」で完了します。</p>
        <div class="cf"><ul class="cf-files" role="listbox" aria-label="衝突したファイル"></ul><section class="cf-main" aria-live="polite"></section></div>`,
      onOpen: d => {
        d.classList.add('conflicts');
        const list = d.querySelector('.cf-files'), main = d.querySelector('.cf-main'), actions = d.querySelector('.eco-actions');
        const button = (text, cls, onClick) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; if (cls) b.className = cls; b.addEventListener('click', onClick); actions.append(b); return b; };
        const dirty = path => { const s = state.get(path); return !!s?.pieces && s.text !== s.saved; };
        const fileState = path => {
          const s = state.get(path);
          if (!s) return ['', '読み込み中'];
          if (s.taken) return ['ok', s.taken];
          if (s.error) return ['bad', 'ここでは直せません'];
          const left = remaining(s.saved);
          return dirty(path) ? ['warn', '未保存'] : left ? ['bad', `残り ${left} 箇所`] : ['ok', '直しました'];
        };
        const done = () => files.every(p => fileState(p)[0] === 'ok');
        const close = async () => {
          const unsaved = files.filter(dirty);
          if (unsaved.length && !await ECO.confirm({title: '保存していない変更', message: `${unsaved.join('、')} の変更を保存せずに閉じます。`, ok: '閉じる', danger: true})) return;
          d.close();
        };
        d.addEventListener('cancel', e => { e.preventDefault(); close(); });
        button('閉じる', '', close);
        const go = button('続ける', 'primary', () => { continueAfter = true; d.close(); });
        const load = async path => {
          let r;
          try { r = await ECO.call('read', {dir: WS.dir, path}); }
          catch (e) { state.set(path, {error: `読めませんでした（${e.message}）。片方の側で消えているのかもしれません。`}); return; }
          const why = r.binary ? 'バイナリのファイルです' : r.truncated ? '大きすぎます' : r.lossy ? 'UTF-8 でない文字コード（Shift_JIS 等）です' : '';
          if (why) { state.set(path, {error: `${why}。ここでは直せません。`}); return; }
          const pieces = parse(r.text);
          state.set(path, {pieces, choices: pieces.filter(p => p.text === undefined).map(() => null), saved: r.text, text: r.text, manual: false});
        };
        const drawList = () => {
          list.innerHTML = files.map(p => { const [kind, note] = fileState(p);
            return `<li role="option" tabindex="0" data-path="${esc(p)}" aria-selected="${p === current}" class="${p === current ? 'on' : ''}"><span class="cf-name" title="${esc(p)}">${esc(p.split('/').pop())}</span><span class="cf-dir">${esc(p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '')}</span><span class="cf-note ${kind}">${esc(note)}</span></li>`; }).join('');
          go.disabled = !done() || files.some(dirty);
          go.title = go.disabled ? '全部のファイルを直して保存すると押せます' : '止まっている操作を完了します（sync continue）';
        };
        const drawFile = () => {
          const s = state.get(current);
          if (!s) { main.innerHTML = '<p class="eco-intro">読み込んでいます…</p>'; return; }
          const takeButtons = `<div class="cf-take"><button type="button" data-take="current">${esc(sides[0])}を採る</button><button type="button" data-take="incoming">${esc(sides[1])}を採る</button><button type="button" data-tortoise>TortoiseGit で直す</button></div>`;
          if (s.taken) { main.innerHTML = `<h3 class="cf-path">${esc(current)}</h3><p>${esc(s.taken)}で解決しました。</p>`; return; }
          if (s.error) { main.innerHTML = `<h3 class="cf-path">${esc(current)}</h3><p class="eco-banner bad">${esc(s.error)}ファイル全体をどちらかの側にするか、TortoiseGit で直してください。</p>${takeButtons}`; return; }
          const hunks = s.pieces.filter(p => p.text === undefined);
          const side = (title, text, cls) => `<div class="cf-side ${cls}"><div class="cf-side-title">${esc(title)}</div><pre>${esc(text) || '<span class="cf-empty">（なし）</span>'}</pre></div>`;
          main.innerHTML = `<h3 class="cf-path">${esc(current)}</h3>`
            + (hunks.length ? `<div class="cf-all">全部の箇所を：<button type="button" data-all="current">${esc(sides[0])}</button><button type="button" data-all="incoming">${esc(sides[1])}</button></div>`
              : `<p class="eco-intro">衝突の印はありません。${remaining(s.text) ? '' : 'このまま「続ける」で登録されます。'}</p>`)
            + hunks.map((h, k) => `<div class="cf-hunk${s.choices[k] ? ' chosen' : ''}" data-hunk="${k}">
                <div class="cf-hunk-head"><span>箇所 ${k + 1}（${h.line} 行目）</span><span class="cf-choose">${CHOICES.map(([c]) => `<button type="button" data-choice="${c}" aria-pressed="${s.choices[k] === c}">${esc(label(c))}</button>`).join('')}</span></div>
                <div class="cf-sides">${side(sides[0], h.current, 'current')}${side(sides[1], h.incoming, 'incoming')}</div>
                ${h.base !== null ? `<details class="cf-base"><summary>共通の元</summary><pre>${esc(h.base)}</pre></details>` : ''}</div>`).join('')
            + `<label class="cf-result-label">結果（直接直せます。<span class="cf-left"></span>）<textarea class="cf-result" spellcheck="false" rows="14"></textarea></label>
               <div class="cf-save"><button type="button" data-revert>読み直す</button><button type="button" class="primary" data-save>保存</button></div>${takeButtons}`;
          const area = main.querySelector('.cf-result');
          area.value = s.text;
          const update = () => {
            const left = remaining(s.text);
            main.querySelector('.cf-left').textContent = left ? `衝突の印が ${left} 箇所に残っています` : '衝突の印はありません';
            main.querySelector('[data-save]').disabled = s.text === s.saved;
            drawList();
          };
          area.addEventListener('input', () => { s.text = area.value; s.manual = true; update(); });
          area.addEventListener('keydown', e => {
            if (e.key === 's' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); }
            if (e.key === 'Tab') { e.preventDefault(); area.setRangeText('\t', area.selectionStart, area.selectionEnd, 'end'); area.dispatchEvent(new Event('input')); }
          });
          update();
        };
        // A choice rebuilds the result from the choices (what was edited by hand is replaced, after asking once).
        const choose = async (indexes, choice) => {
          const s = state.get(current);
          if (s.manual && !await ECO.confirm({title: '手で直した結果', message: '手で直した結果を、選んだ側から作り直します（手で直したところは消えます）。', ok: '作り直す', danger: true})) return;
          for (const k of indexes) s.choices[k] = s.choices[k] === choice && indexes.length === 1 ? null : choice;
          s.text = build(s.pieces, s.choices); s.manual = false;
          drawFile();
        };
        const save = async () => {
          const s = state.get(current), path = current;
          if (!s?.pieces || s.text === s.saved) return;
          try { await ECO.call('write', {dir: WS.dir, path, text: s.text}); }
          catch (e) { return ECO.toast(`保存できませんでした：${e.message}`, 'bad', 0); }
          s.saved = s.text;
          ECO.toast(remaining(s.text) ? `${path} を保存しました（衝突の印が残っています）。` : `${path} を保存しました。`);
          const next = files.find(p => fileState(p)[0] !== 'ok');
          if (next && !remaining(s.text)) return show(next);
          drawFile();
        };
        const show = async path => {
          current = path; drawList();
          if (!state.has(path)) { drawFile(); await load(path); }
          if (current === path) drawFile();
          drawList();
        };
        list.addEventListener('click', e => { const li = e.target.closest('[data-path]'); if (li) show(li.dataset.path); });
        list.addEventListener('keydown', e => {
          const i = files.indexOf(current), next = e.key === 'ArrowDown' ? files[i + 1] : e.key === 'ArrowUp' ? files[i - 1] : null;
          if (next) { e.preventDefault(); show(next).then(() => list.querySelector('.on')?.focus()); }
          else if (e.key === 'Enter') { const li = e.target.closest('[data-path]'); if (li) show(li.dataset.path); }
        });
        main.addEventListener('click', async e => {
          const b = e.target.closest('button');
          if (!b) return;
          if (b.dataset.choice) return choose([+b.closest('[data-hunk]').dataset.hunk], b.dataset.choice);
          if (b.dataset.all) return choose(state.get(current).choices.map((_, k) => k), b.dataset.all);
          if (b.hasAttribute('data-save')) return save();
          if (b.hasAttribute('data-revert')) {
            if (dirty(current) && !await ECO.confirm({title: '読み直す', message: '保存していない変更を捨てて、ファイルを読み直します。', ok: '読み直す', danger: true})) return;
            state.delete(current); return show(current);
          }
          if (b.dataset.take) {
            const incoming = b.dataset.take === 'incoming';
            if (dirty(current) && !await ECO.confirm({title: '片方の側を採る', message: '保存していない変更を捨てて、ファイル全体を片方の側にします。', ok: '採る', danger: true})) return;
            const doc = await WS.takeSide(current, incoming);
            if (doc) { state.set(current, {taken: sides[incoming ? 1 : 0]}); drawFile(); drawList(); }
            return;
          }
          if (b.hasAttribute('data-tortoise')) return WS.openDiff(current, ['conflicted']);
        });
        show(current);
      }});
    await WS.reloadFiles?.();
    if (continueAfter) await WS.continueSync();
  };
})();
