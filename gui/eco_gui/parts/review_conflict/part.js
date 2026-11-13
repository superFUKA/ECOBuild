// 部品「衝突を直す」。左に衝突したファイル（名前・フォルダー・状態）、右に選んだファイルの衝突の箇所。
// 箇所ごとに、今の側と入ってくる側を左右に並べ、どちらを使うか（片方・両方）を選ぶ。選ぶと、下の結果が変わる。
// 結果は手でも直せる（Ctrl+S で保存、Tab は字下げ）。保存しても登録はしない：全部直したら「続ける」。
// 選んだ側・直している途中の文字は、この部品の中だけにある（state）。ファイルに書くのは saved（sync resolve）。
const STOPPED = { merge: '取り込み', rebase: 'タスクブランチの作り直し', revert: '取り消し', stash: '退避した変更の戻し' };
const CHOICES = ['current', 'incoming', 'both', 'both_incoming_first'];
const START = /^<{7}(?: |\r?\n|$)/;

export default {
  render(root, props, { h, emit, state, redraw, menu }) {
    if (props.error) return root.replaceChildren(h('p', { role: 'alert' }, props.error));
    const data = props.data;
    if (!data) return root.replaceChildren(h('p', { role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…'));
    const files = data.files || [];
    const sides = [data.current || '今の側', data.incoming || '入ってくる側'];
    const label = (choice) => (choice === 'current' ? sides[0] : choice === 'incoming' ? sides[1]
      : choice === 'both' ? `両方（${sides[0]}が先）` : `両方（${sides[1]}が先）`);

    // ファイルごとの、直している途中の中身。ファイルの方が変わっていたら（保存した・外で直した）、作り直す
    state.files = state.files || {};
    const savedOf = (file) => (file.pieces || []).map((piece) => piece.text).join('');
    for (const file of files) {
      const saved = savedOf(file), known = state.files[file.path];
      if (known && known.saved === saved) continue;
      const hunks = (file.pieces || []).filter((piece) => piece.conflict).length;
      const keep = known && known.text !== known.saved && known.text !== saved;  // 外で変わったが、未保存の直しがある：直しは残す
      state.files[file.path] = { saved, text: keep ? known.text : saved, choices: Array(hunks).fill(null), manual: keep };
    }
    for (const path of Object.keys(state.files)) if (!files.some((file) => file.path === path)) delete state.files[path];
    const dirty = (path) => { const s = state.files[path]; return !!s && s.text !== s.saved; };
    const left = (text) => (text.match(/[^\n]*\n|[^\n]+$/g) || []).filter((line) => START.test(line)).length;
    const fileState = (file) => (file.reason ? ['bad', 'ここでは直せません'] : dirty(file.path) ? ['warn', '未保存']
      : file.remaining ? ['bad', `残り ${file.remaining} 箇所`] : ['ok', '直しました']);
    // 保存した後は、まだ直していない次のファイルへ
    if (state.saving && !dirty(state.saving)) {
      const done = files.find((file) => file.path === state.saving);
      const next = files.find((file) => fileState(file)[0] !== 'ok');
      if (done && !done.remaining && next) state.current = next.path;
      state.saving = null;
    }
    // 初めは、頼まれたファイル（右クリックしたファイル）から
    if (props.first && state.first !== props.first && files.some((file) => file.path === props.first)) { state.first = props.first; state.current = props.first; }
    if (!files.some((file) => file.path === state.current)) state.current = files.length ? files[0].path : null;
    const current = files.find((file) => file.path === state.current);
    const unsaved = files.filter((file) => dirty(file.path)).map((file) => file.path);
    const scroll = root.querySelector('.main')?.scrollTop || 0;
    const ask = (event, heading, yes) => menu(event, [{ heading }, { id: 'yes', label: yes, danger: true }, { id: 'no', label: 'やめる' }])
      .then((id) => id === 'yes');
    const button = (text, cls, onClick, title) => {
      const b = h('button', { type: 'button', class: cls || '', title: title || '' }, text);
      b.addEventListener('click', onClick);
      return b;
    };

    // 上の帯：何が止まっているか・やめて前に戻す
    const branch = props.status?.branch ? `（${props.status.branch}）` : '';
    const head = data.stopped
      ? h('div', { class: 'banner' }, h('span', {}, `${STOPPED[data.stopped] || '操作'}が衝突で止まっています${branch}。`
        + '衝突した箇所ごとに、どちらの側を使うかを選びます。下の結果は直接直せます。保存しても登録はしません：全部のファイルを直したら「続ける」で完了します。'),
        button('やめて前に戻す', 'small', () => emit('aborted', {}), '止まっている操作をやめて、その前に戻します（sync abort）'))
      : h('p', { class: 'muted' }, '止まっている操作はありません。');
    if (!files.length && !data.stopped) return root.replaceChildren(head, h('p', { class: 'none' }, '衝突したファイルはありません。'));

    // 左：ファイルの一覧
    const list = h('div', { class: 'files', role: 'listbox', 'aria-label': '衝突したファイル' });
    const show = (path) => { state.current = path; redraw(); };
    files.forEach((file, index) => {
      const [kind, note] = fileState(file), at = file.path.lastIndexOf('/');
      const item = h('button', { type: 'button', role: 'option', class: file.path === state.current ? 'on' : '', title: file.path,
        'data-path': file.path },
        h('span', { class: 'name' }, file.path.slice(at + 1)), h('span', { class: 'dir' }, at < 0 ? '' : file.path.slice(0, at)),
        h('span', { class: 'note ' + kind }, note));
      item.setAttribute('aria-selected', String(file.path === state.current));
      item.addEventListener('click', () => show(file.path));
      item.addEventListener('keydown', (event) => {
        const next = event.key === 'ArrowDown' ? files[index + 1] : event.key === 'ArrowUp' ? files[index - 1] : null;
        if (next) { event.preventDefault(); show(next.path); }
      });
      list.append(item);
    });
    if (!files.length) list.append(h('p', { class: 'none' }, '衝突したファイルは、もうありません。'));

    // 下：全部を片方の側に・続ける
    const ready = !!data.ready && unsaved.length === 0;
    const go = button('続ける', 'primary', () => emit('continued', {}),
      ready ? '止まっている操作を完了します（sync continue）' : '全部のファイルを直して保存すると押せます');
    go.disabled = !ready;
    const takeAll = async (event, side) => {
      if (unsaved.length && !await ask(event, `保存していない変更（${unsaved.join('、')}）を捨てます`, '捨てて、全部を片方の側にする')) return;
      emit('taken', { paths: [], side });
    };
    const foot = h('div', { class: 'foot' },
      files.length ? h('span', { class: 'all' }, 'すべてのファイルを：',
        button(sides[0], 'small', (event) => takeAll(event, 'current'), `衝突したファイル全部を、${sides[0]}の中身にします`),
        button(sides[1], 'small', (event) => takeAll(event, 'incoming'), `衝突したファイル全部を、${sides[1]}の中身にします`)) : h('span', {}),
      h('span', { class: 'why' }, ready ? '' : files.length ? '全部のファイルを直して保存すると、続けられます' : ''), go);

    // 右：選んだファイル
    const main = h('section', { class: 'main', 'aria-live': 'polite' });
    const drawList = () => {  // 打っている途中に変わる所だけを直す（入力欄を描き直さない）
      for (const item of list.querySelectorAll('button[data-path]')) {
        const file = files.find((one) => one.path === item.getAttribute('data-path'));
        const [kind, note] = fileState(file), mark = item.querySelector('.note');
        mark.className = 'note ' + kind; mark.textContent = note;
      }
      const ok = !!data.ready && !files.some((file) => dirty(file.path));
      go.disabled = !ok;
      go.title = ok ? '止まっている操作を完了します（sync continue）' : '全部のファイルを直して保存すると押せます';
    };
    if (current) {
      const s = state.files[current.path];
      const take = async (event, side) => {
        if (dirty(current.path) && !await ask(event, '保存していない変更を捨てて、ファイル全体を片方の側にします', '採る')) return;
        emit('taken', { paths: [current.path], side });
      };
      const takeButtons = h('div', { class: 'take' }, 'ファイル全体を：',
        button(`${sides[0]}を採る`, 'small', (event) => take(event, 'current')), button(`${sides[1]}を採る`, 'small', (event) => take(event, 'incoming')),
        button('TortoiseGit で直す', 'small', () => emit('tortoise', { path: current.path }), 'TortoiseGitMerge で、このファイルの衝突を直します（ecobuild diff --gui）'));
      main.append(h('h3', { class: 'path' }, current.path));
      if (current.reason) {
        main.append(h('p', { class: 'banner bad' },
          `${current.reason_text || 'このファイルは箇所に分けられません'}。ここでは直せません。ファイル全体をどちらかの側にするか、TortoiseGit で直してください。`), takeButtons);
      } else {
        const hunks = current.pieces.filter((piece) => piece.conflict);
        // 側を選ぶと、結果を選んだ側から作り直す（手で直したところは消えるので、先に確かめる）
        const choose = async (event, indexes, choice) => {
          if (s.manual && !await ask(event, '手で直した結果を、選んだ側から作り直します（手で直したところは消えます）', '作り直す')) return;
          for (const k of indexes) s.choices[k] = s.choices[k] === choice && indexes.length === 1 ? null : choice;
          let k = 0;
          s.text = current.pieces.map((piece) => (!piece.conflict ? piece.text : ((c) => (c ? piece[c] : piece.text))(s.choices[k++]))).join('');
          s.manual = false;
          redraw();
        };
        if (hunks.length) {
          main.append(h('div', { class: 'all' }, '全部の箇所を：',
            button(sides[0], 'small', (event) => choose(event, hunks.map((_, k) => k), 'current')),
            button(sides[1], 'small', (event) => choose(event, hunks.map((_, k) => k), 'incoming'))));
        } else {
          main.append(h('p', { class: 'intro' }, '衝突の印はありません。' + (left(s.text) ? '' : 'このまま「続ける」で登録されます。')));
        }
        hunks.forEach((hunk, k) => {
          const side = (title, text, cls) => h('div', { class: 'side ' + cls }, h('div', { class: 'side-title' }, title),
            h('pre', {}, text || h('span', { class: 'empty' }, '（なし）')));
          const chooser = h('span', { class: 'choose' }, ...CHOICES.map((choice) => {
            const b = button(label(choice), '', (event) => choose(event, [k], choice));
            b.setAttribute('aria-pressed', String(s.choices[k] === choice));
            return b;
          }));
          const box = h('div', { class: s.choices[k] ? 'hunk chosen' : 'hunk' },
            h('div', { class: 'hunk-head' }, h('span', {}, `箇所 ${k + 1}（${hunk.line} 行目）`), chooser),
            h('div', { class: 'sides' }, side(sides[0], hunk.current, 'current'), side(sides[1], hunk.incoming, 'incoming')));
          if (hunk.base !== null && hunk.base !== undefined) {
            box.append(h('details', { class: 'base' }, h('summary', {}, '共通の元'), h('pre', {}, hunk.base || h('span', { class: 'empty' }, '（なし）'))));
          }
          main.append(box);
        });
        const area = h('textarea', { class: 'result', spellcheck: 'false', rows: 14, 'aria-label': '結果' });
        area.value = s.text;
        const leftNote = h('span', { class: 'left' });
        const save = () => { if (s.text !== s.saved) { state.saving = current.path; emit('saved', { path: current.path, text: s.text }); } };
        const saveButton = button('保存', 'primary', save, 'ファイルに書きます（登録はしません）。Ctrl+S');
        const update = () => {
          const n = left(s.text);
          leftNote.textContent = n ? `衝突の印が ${n} 箇所に残っています` : '衝突の印はありません';
          leftNote.className = n ? 'left bad' : 'left ok';
          saveButton.disabled = s.text === s.saved;
          drawList();
        };
        area.addEventListener('input', () => { s.text = area.value; s.manual = true; update(); });
        area.addEventListener('keydown', (event) => {
          if (event.key === 's' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); save(); }
          if (event.key === 'Tab' && !event.shiftKey) {
            event.preventDefault();
            area.setRangeText('\t', area.selectionStart, area.selectionEnd, 'end');
            s.text = area.value; s.manual = true; update();
          }
        });
        const revert = async (event) => {
          if (dirty(current.path) && !await ask(event, '保存していない変更を捨てて、ファイルの中身に戻します', '戻す')) return;
          delete state.files[current.path];
          redraw();
        };
        main.append(h('label', { class: 'result-label' }, h('span', {}, '結果（直接直せます。', leftNote, '）'), area),
          h('div', { class: 'save' }, button('元に戻す', '', revert, '保存していない変更を捨てて、ファイルの中身に戻します'), saveButton), takeButtons);
        update();
      }
    } else {
      main.append(h('p', { class: 'intro' }, '衝突したファイルは全部、片方の側で解決してあります。「続ける」で完了します。'));
    }

    root.replaceChildren(head, h('div', { class: 'cf' }, list, main), foot);
    main.scrollTop = state.shown === state.current ? scroll : 0;
    state.shown = state.current;
  },
};
