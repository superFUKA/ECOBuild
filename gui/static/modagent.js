'use strict';
// エージェント: the module's 進行役 (lead, with no task). It has no task: it lives in a workspace of its own that ECOBuild keeps
// (agent module prepare: a clone of the base branch, in a container), talks with the user and hands the work to the
// 管理役 it makes (agent team start --manager, a task of its own). Here: start it (a tab of the agent window, a window of its own),
// resume a conversation, its 管理役 and their state, close the workspace. All from the CLI (agent module status …).
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {place: null, docker: null, conversations: null, error: '', loaded: false};
  const shell = () => window.ecobuildShell?.agents || (() => { try { return window.top.ecobuildShell?.agents; } catch (e) { return null; } })();
  const STATE_NAMES = {working: '作業中', idle: '待機中', stopped: '止まっている', unknown: '不明'};

  async function load() {
    const [doc, images] = await Promise.all([
      ECO.cli(MOD.root, ['agent', 'module', 'status'], {quiet: true}),
      st.docker === null ? ECO.cli(MOD.root, ['container', 'image', 'list'], {quiet: true}) : null,
    ]);
    st.place = doc.ok ? doc.result : null; st.error = doc.ok ? '' : doc.error.message;
    if (images) st.docker = images.ok ? {ready: !!images.result.docker_ready, detail: images.result.docker_detail || ''} : {ready: false, detail: images.error.message};
    st.conversations = null;
    if (st.place?.exists) {
      const found = await ECO.cli(st.place.root, ['agent', 'conversations'], {quiet: true});
      st.conversations = found.ok ? found.result.conversations || [] : [];
    }
    st.loaded = true;
    render();
  }

  // Why 進行役 cannot start here (grey with the reason): no agent window (a browser), or no Docker (the container is a must).
  function blocked() {
    if (!shell()) return '進行役はエージェントの窓で開きます（ECOBuild のアプリで使えます）。';
    if (st.docker && !st.docker.ready) return `進行役はコンテナで動きます。Docker が使えません${st.docker.detail ? `（${st.docker.detail}）` : ''}。`;
    return '';
  }

  function render() {
    const box = el('modagent-main'); if (!box || box.hidden) return;
    if (!st.loaded) { box.innerHTML = ECO.loading(); return; }
    if (st.error) { box.innerHTML = `<div class="eco-banner bad">${esc(st.error)}</div>`; return; }
    const p = st.place, why = blocked();
    const state = !p?.exists ? 'まだ用意していません' : p.running ? (STATE_NAMES[p.state] || p.state) : '動いていません';
    const members = (p?.members || []).map(m => `<tr>
      <td><strong>${esc(m.name)}</strong></td><td>#${esc(m.task)}</td><td>${esc(STATE_NAMES[m.state] || m.state || '')}</td>
      <td class="mi-sub">${esc((m.last_reply || '').slice(0, 120))}</td>
      <td class="mi-row-actions"><button type="button" data-ma-send="${esc(m.name)}">言付け…</button></td></tr>`).join('');
    box.innerHTML = `
      <p class="mi-note">進行役は、このモジュールのエージェントです。タスクを持たず、あなたと話して仕事を決め、直下の<strong>管理役</strong>（仕事ごとのタスク）に送ります。作業の割り振り・取り込みは管理役と作業役がします。ブランチ・タスク・提出の管理もでき、消す・取り込む等の重い操作は、あなたが「はい」と答えたときだけ行います。</p>
      <div class="ma-card">
        <div class="ma-head"><h3>進行役</h3><span class="ma-state" data-state="${esc(p?.running ? p.state : 'off')}">${esc(state)}</span></div>
        ${p?.exists ? `<p class="mi-sub">作業空間：<code>${esc(p.root)}</code>（${esc(p.branch || '?')}）</p>` : ''}
        ${p?.last_reply ? `<p class="ma-reply">${esc(p.last_reply)}</p>` : ''}
        ${why ? `<div class="eco-banner">${esc(why)}</div>` : ''}
        <div class="ma-actions">
          <button type="button" class="primary" data-ma-start ${why ? `disabled title="${esc(why)}"` : ''}>進行役と話す</button>
          <button type="button" data-ma-resume ${why || !(st.conversations || []).length ? `disabled title="${esc(why || '続けられる会話はまだありません')}"` : ''}>会話を選んで再開…</button>
          ${p?.exists ? `<button type="button" class="quiet-danger" data-ma-close ${p.running || (p.members || []).length ? 'disabled title="進行役が動いている間・管理役が残っている間は片付けられません"' : ''}>作業空間を片付ける</button>` : ''}
        </div>
      </div>
      <h3 class="ma-sub">管理役</h3>
      ${members ? `<table class="mi-table"><thead><tr><th>名前</th><th>タスク</th><th>様子</th><th>最後の返答</th><th></th></tr></thead><tbody>${members}</tbody></table>`
        : '<p class="mi-sub">まだいません。進行役が、話で決まった仕事を送るときに作ります（既定は1人）。</p>'}`;
  }

  // Open (or bring to front: one agent per workspace) the 進行役's tab. The workspace is prepared first (clone or update).
  async function start(agent = '') {
    const tabs = shell(); if (!tabs) return;
    const doc = await ECO.cli(MOD.root, ['agent', 'module', 'prepare']);
    if (!doc.ok) return ECO.showError(doc, '進行役の作業空間を用意できませんでした');
    try {
      const tab = await tabs.open({dir: doc.result.root, agent, name: `進行役 ${MOD.name}`, role: 'lead', module: true});
      ECO.toast(`エージェントの窓で開きました：${tab?.name || '進行役'}`);
    } catch (e) { ECO.toast(e.message, 'bad'); }
    load();
  }

  async function resume() {
    const list = st.conversations || []; if (!list.length) return;
    const v = await ECO.form({title: '会話を選んで再開', fields: [{name: 'id', label: '会話', type: 'select', value: list[0].id,
      options: list.map(c => [c.id, `${ECO.localTime(c.updated)}　${c.title || c.id}`])}], ok: '再開'});
    if (v?.id) start(`claude --resume ${v.id}`);
  }

  async function send(name) {
    const v = await ECO.form({title: `${name} に言付け`, intro: '管理役が作業中でも、次の区切りで届きます。ふだんは進行役に話せば、進行役が送ります。',
      fields: [{name: 'text', label: '内容', type: 'textarea', required: true, focus: true}], ok: '送る'});
    if (v && await ECO.run(st.place.root, ['agent', 'team', 'send', name, v.text], {success: `${name} に送りました。`})) load();
  }

  async function close() {
    if (await ECO.run(MOD.root, ['agent', 'module', 'close'], {success: '進行役の作業空間を片付けました。',
      confirm: '進行役の作業空間とコンテナを消します（進行役の覚え書きも消えます。会話の記録は残ります）。次に話すときは新しく用意します。'})) load();
  }

  el('modagent-main').addEventListener('click', e => {
    if (e.target.closest('[data-ma-start]')) start();
    else if (e.target.closest('[data-ma-resume]')) resume();
    else if (e.target.closest('[data-ma-close]')) close();
    else if (e.target.closest('[data-ma-send]')) send(e.target.closest('[data-ma-send]').dataset.maSend);
  });
  el('modagent-reload').addEventListener('click', () => { st.docker = null; load(); });
  let timer = null;
  pageHooks.modagent = () => {
    render(); load();
    clearInterval(timer);   // the 進行役 and its 管理役 change outside the GUI: read again while the page shows
    timer = setInterval(() => { if (el('modagent-content').hidden) clearInterval(timer); else load(); }, 15000);
  };
  window.MODAGENT = {load};
})();
