'use strict';
// Module page エージェント: what the module tells its agents (ecobuild agent rules), kept in the repository
// (.ecobuild/agents/, committed on a task branch and taken in by a PR): a text for every agent, a text for each
// registration (role), and the tools a registration may not use (only narrowing what the registration allows).
// The agents started get what the default branch has; a place on a task branch shows what will be taken in.
(() => {
  const {esc} = ECO;
  const $ = id => document.getElementById(id);
  const section = () => $('agents-content'), main = () => section().querySelector('.ar-main');
  const MARKS = {read: '見る', change: '変える', owner: '持ち主だけ（ブランチを変える）', children: '子のエージェント'};
  let place = null, data = null, loading = 0;
  const here = () => place || MOD.root;
  const editable = () => !!MOD.states.get(MOD.keyOf(here()))?.task;

  // The place shown: the module's folder (the default branch: what the agents get) or a workspace.
  function placeSelect() {
    const places = [MOD.root, ...MOD.places.filter(p => MOD.keyOf(p) !== MOD.keyOf(MOD.root))];
    if (places.length < 2) return '';
    const label = p => MOD.keyOf(p) === MOD.keyOf(MOD.root) ? 'モジュールのフォルダ（既定のブランチ）'
      : esc(MOD.states.get(MOD.keyOf(p))?.branch || p) + '（' + esc(p.split(/[\\/]/).pop()) + '）';
    return `<label class="mi-place">表示<select id="ar-place">${places.map(p =>
      `<option value="${esc(p)}" ${MOD.keyOf(p) === MOD.keyOf(here()) ? 'selected' : ''}>${label(p)}</option>`).join('')}</select></label>`;
  }
  // fnmatch (* ? [..]) as the registration's tools are written.
  const glob = pattern => new RegExp('^' + pattern.replace(/[.+^${}()|\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
  const matches = (name, patterns) => patterns.some(p => glob(p).test(name));

  function banners() {
    let out = `<p class="mi-note">ここに書いた文は、エージェントを起動するときに渡します（登録の文書の後に）。保存すると <code>.ecobuild/agents/</code> に書いてタスクブランチでコミットします。起動したエージェントに効くのは、提出して既定のブランチ（${esc(data.in_force || '—')}）に取り込まれてからです。</p>`;
    if (data.pending) out += '<div class="eco-banner mi-info"><span>この場所の内容は、まだ起動するエージェントに効いていません（取り込まれると効きます）。</span></div>';
    if (!editable()) out += `<div class="eco-banner mi-info"><span>変更はタスクブランチの作業空間で行います。${MOD.workspacePlaces().length ? '上の「表示」でタスクブランチを選んでください。' : '作業空間がないので、今は見るだけです。'}</span>${MOD.workspacePlaces().length ? '' : '<button type="button" class="sm" data-ar-tasks>タスク管理を開く</button>'}</div>`;
    return out;
  }
  function toolList(role) {
    const allowed = data.tools.filter(t => matches(t.name, role.tools));
    if (!allowed.length) return '<p class="mi-note">この登録には渡すツールがありません。</p>';
    const exact = new Set(data.tools.map(t => t.name));
    const others = role.deny.filter(p => !exact.has(p));
    const groups = Object.keys(MARKS).map(mark => [mark, allowed.filter(t => t.mark === mark)]).filter(([, tools]) => tools.length);
    const off = editable() ? '' : ' disabled';
    return `<details class="ar-tools"${role.deny.length ? ' open' : ''}><summary>使わせないツール（${role.deny.length ? esc(role.deny.join(', ')) : 'なし'}）</summary>
      <p class="mi-note">チェックしたツールは、この登録のエージェントに渡しません。登録で許したもの（${esc(role.tools.join(', ') || 'なし')}）を絞るだけです。</p>
      ${groups.map(([mark, tools]) => `<fieldset class="ar-group"><legend>${esc(MARKS[mark])}</legend>${tools.map(t =>
        `<label class="ar-tool" title="${esc(t.summary)}"><input type="checkbox" data-ar-deny="${esc(t.name)}"${matches(t.name, role.deny) ? ' checked' : ''}${matches(t.name, others) ? ' disabled' : off}><code>${esc(t.name)}</code></label>`).join('')}</fieldset>`).join('')}
      <label class="ar-patterns">そのほか（パターン。カンマ区切り。例：children_*）<input type="text" data-ar-patterns value="${esc(others.join(', '))}"${off}></label>
    </details>`;
  }
  function card(key, title, sub, text, placeholder, extra = '') {
    const off = editable() ? '' : ' disabled';
    return `<section class="mi-section ar-card" data-ar-card="${esc(key)}">
      <div class="mi-head"><div><h3>${esc(title)}</h3>${sub ? `<p class="mi-note">${sub}</p>` : ''}</div></div>
      <textarea class="ar-text" rows="${text ? Math.min(14, text.split('\n').length + 2) : 4}" placeholder="${esc(placeholder)}"${off}>${esc(text)}</textarea>
      ${extra}
      <div class="mi-actions"><button type="button" class="primary sm" data-ar-save="${esc(key)}"${editable() ? '' : ' disabled title="タスクブランチの作業空間で変えます"'}>保存してコミット</button></div>
    </section>`;
  }
  function draw() {
    const top = section().querySelector('.mi-place-slot');
    if (top && !top.contains(document.activeElement)) top.innerHTML = placeSelect();
    if (!data) return;
    main().innerHTML = banners()
      + card('', '全エージェント共通', 'このモジュールで起動するどのエージェントにも渡します。', data.common,
             '例：前後がつながった段階（調べる→設計→実装）は分けずに自分で進める。子に任せるのは、互いに独立した仕事と検証だけ。')
      + '<h3 class="mi-subhead">登録ごと</h3><p class="mi-note">登録（エージェントの種類）は ECOBuild の設定（ハブの設定の「エージェント」）で、このPC全体のものです。ここでは、このモジュールでその登録に足す文と、使わせないツールを決めます。</p>'
      + data.roles.map(role => card(role.name, `${role.title}（${role.name}）`, '', role.text,
          '例：仕事を分けるのは、互いに独立していて並列にできるときだけ。子には目的・完了の条件・関係するファイルを渡す。', toolList(role))).join('');
  }
  async function load() {
    const mine = ++loading;
    main().innerHTML = ECO.loading();
    const doc = await ECO.cli(here(), ['agent', 'rules', 'show', '--tools'], {quiet: true});
    if (mine !== loading) return;
    if (!doc.ok) {
      main().innerHTML = `<div class="eco-banner bad">表示できませんでした：${esc(doc.error?.message || '')}<button type="button" class="sm" data-ar-reload>読み直す</button></div>`;
      return;
    }
    data = doc.result; draw();
  }
  async function save(key) {
    const box = main().querySelector(`[data-ar-card="${CSS.escape(key)}"]`);
    const text = box.querySelector('.ar-text').value;
    let args = key ? ['agent', 'rules', 'set', '--role', key, '--text', text] : ['agent', 'rules', 'set', '--common', text];
    if (key) {
      const patterns = (box.querySelector('[data-ar-patterns]')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
      const checked = [...box.querySelectorAll('[data-ar-deny]:checked:not(:disabled)')].map(b => b.dataset.arDeny);
      if (box.querySelector('.ar-tools')) args = [...args, '--deny', [...new Set([...patterns, ...checked])].join(',')];
    }
    const doc = await ECO.run(here(), args, {success: r => r?.changed?.length ? `保存してコミットしました（${(r.committed || '').slice(0, 7)}。提出して取り込まれると効きます）。` : '変わったところはありません。'});
    if (doc) { await MOD.reloadPlace?.(here()); await read(); }
  }

  section().addEventListener('click', e => {
    const saveKey = e.target.closest('[data-ar-save]')?.dataset.arSave;
    if (saveKey !== undefined) save(saveKey);
    else if (e.target.closest('[data-ar-reload]')) read();
    else if (e.target.closest('[data-ar-tasks]')) showModulePage('tasks');
  });
  section().addEventListener('change', e => { if (e.target.id === 'ar-place') { place = e.target.value; read(); } });
  // Something typed and not saved is kept: a change made elsewhere is read when the page is shown next (or 更新).
  let typed = false, stale = true;
  section().addEventListener('input', e => { if (e.target.closest('.ar-card')) typed = true; });
  const read = () => { typed = false; stale = false; return load(); };
  $('agents-reload').addEventListener('click', read);
  pageHooks.agents = () => { if (stale && !typed) MOD.ready.then(read); else draw(); };
  const changed = pageHooks.changed;   // tasks.js's (this script comes after it)
  pageHooks.changed = () => { changed?.(); stale = true; if (!section().hidden && !typed) read(); };
})();
