'use strict';
// 子を起動できるエージェントの窓のチーム（そのエージェントが AI として起動した子。係が画面なしで動かす）：そのエージェントの
// タブの隣の「チーム」で開く。読むだけで、入力欄は置かない（指示は親のエージェントから）。見方は3つ（窓〔作業空間〕ごとに覚える）：
// - タブ：子ごとのタブで、詳しい表示。
// - 並べて：子ごとの小さな表示（名前・様子・今の一歩・最新の数行）。クリックで大きく（詳しい表示）、「戻る」で格子へ。
// - 一覧：1人1行（名前・登録・様子・今の一歩・報告・届いていない言付け）。選ぶと詳しい表示。
// 止まっている・失敗・作業中が長い・長く道具を使っていないものは目立たせる。詳しい表示は返答の文・道具（1行に畳み、開くと
// 入出力）・届いた言付けと知らせ（誰からか）・返答の終わりの区切り（使用量・断られた権限）。新しい出来事は追いかける（読み
// 返しているときは追いかけない）。操作：止める・起動し直す・引き取る（このアプリのタブで開く。閉じると係に返す）・返す・
// 場所を開く・閉じる。1人はエージェントの ID でつなぐので、起動し直しても・引き取って返しても、同じ表示が続く。
// データは main（team.js）が CLI（agent children・agent log）から読んで送ってくる。window.js の後に読む。
const VIEW_KEY = dir => `ecobuild.teamView:${String(dir || '').toLowerCase()}`;
const TEXT_LIMIT = 6000;      // 長い返答・発言は、ここまで出して「続き」
const OUTPUT_LIMIT = 20000;   // 道具の出力を出す長さ
let teamOpen = false, teamLead = null, teamData = {members: [], error: '', taken: {}}, teamFlat = [];
let teamMode = 'list', teamFocus = null, teamTabSel = null;
let followed = null, eventLog = null, eventItems = new Map(), moreBefore = false, followTimer = null;
const notices = new Map();    // 子の ID → {text, bad}
const pending = new Set();    // 操作中の子の ID

const leadOfWindow = () => tabs.find(t => t.pinned && t.lead) || null;
const ref = m => ({id: m.id, name: m.name, path: m.path});
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

// ---- タブの帯の「チーム」 ----------------------------------------------------------------------------
// window.js の renderTabs から：子を起動できるエージェントの窓なら、そのタブの隣に「チーム」を置く
function teamTab(bar) {
  const lead = leadOfWindow();
  if (!lead) { if (teamOpen) teamClosePane(); return; }
  if (teamLead && teamLead.id !== lead.id) { teamClosePane(); teamData = {members: [], error: '', taken: {}}; teamFlat = []; }
  teamLead = lead;
  const b = el('button', 'tab team-tab'); b.type = 'button'; b.id = 'team-tab';
  b.innerHTML = '<b>◇</b><span class="name">チーム</span><span class="count"></span>';
  b.addEventListener('click', () => (teamOpen ? null : teamOpenPane()));
  const pinned = bar.querySelector('.tab.pinned');
  if (pinned) pinned.after(b); else bar.prepend(b);
  if (teamOpen) for (const t of bar.querySelectorAll('.tab.active')) t.classList.remove('active');
  b.classList.toggle('active', teamOpen);
  updateTeamTab();
}

function updateTeamTab() {
  const b = $('team-tab'); if (!b) return;
  const looks = teamFlat.map(m => TeamView.look(m));
  const alerts = looks.filter(l => l.alert).length, working = looks.filter(l => l.tone === 'working').length;
  b.querySelector('.count').textContent = teamFlat.length ? ` ${teamFlat.length}` : '';
  b.dataset.alert = alerts ? 'yes' : '';
  b.dataset.state = working ? 'waiting' : '';
  b.title = teamFlat.length ? `チーム（AI が起動した子）：${teamFlat.length}人・作業中 ${working}${alerts ? `・要確認 ${alerts}` : ''}`
    : 'チーム（このエージェントが AI として起動した子。まだいません）';
}

function teamOpenPane(focusId = null) {
  const lead = leadOfWindow(); if (!lead) return;
  teamLead = lead; teamOpen = true;
  try { teamMode = localStorage.getItem(VIEW_KEY(lead.dir)) || teamMode; } catch (e) { /* 覚えられなくても開ける */ }
  if (!['tabs', 'grid', 'list'].includes(teamMode)) teamMode = 'list';
  if (focusId) { if (teamMode === 'tabs') teamTabSel = focusId; else teamFocus = focusId; }
  for (const t of terms.values()) t.el.hidden = true;
  $('empty').hidden = true; $('team').hidden = false;
  agents.teamShown(lead.id, true).then(view => { if (view) setTeamData(view); });
  renderTabs(); renderTeam();
}

// window.js の show から（端末のタブを選んだ）
function teamClosePane() {
  if (!teamOpen) return;
  teamOpen = false; $('team').hidden = true;
  if (teamLead) agents.teamShown(teamLead.id, false);
  unfollow();
}

function setTeamData(view) {
  teamData = {members: view.members || [], error: view.error || '', taken: view.taken || {}};
  teamFlat = TeamView.flatten(teamData.members, teamLead?.agentId || '');
  updateTeamTab();
  if (teamOpen) renderTeam();
}

agents.onTeamList((leadId, view) => {
  const lead = leadOfWindow();
  if (!lead || lead.id !== leadId) return;
  teamLead = lead; setTeamData(view);
});
agents.onTeamFocus(id => teamOpenPane(id));
agents.onTeamNotice((id, text, bad) => { notices.set(id, {text, bad}); if (teamOpen) renderTeam(); });

// ---- 全体 ----------------------------------------------------------------------------------------------
for (const b of document.querySelectorAll('#team-views button')) {
  b.addEventListener('click', () => {
    teamMode = b.dataset.mode;
    try { localStorage.setItem(VIEW_KEY(teamLead?.dir), teamMode); } catch (e) { /* 覚えられなくても切り替わる */ }
    teamFocus = null; renderTeam();
  });
}

function renderTeam() {
  if (!teamOpen) return;
  for (const b of document.querySelectorAll('#team-views button')) b.classList.toggle('on', b.dataset.mode === teamMode);
  const counts = {};
  for (const m of teamFlat) { const l = TeamView.look(m); counts[l.tone] = (counts[l.tone] || 0) + 1; if (l.alert) counts.alert = (counts.alert || 0) + 1; }
  $('team-sum').textContent = teamFlat.length ? [['working', '作業中'], ['idle', '待機中'], ['stopped', '止まっている'], ['failed', '失敗'], ['alert', '要確認']]
    .filter(([k]) => counts[k]).map(([k, label]) => `${label} ${counts[k]}`).join('・') : '';
  $('team-err').textContent = teamData.error ? `読み直せませんでした：${teamData.error.split('\n')[0]}` : '';
  $('team-err').title = teamData.error || '';
  const tabsBar = $('team-tabs'), body = $('team-body');
  tabsBar.hidden = teamMode !== 'tabs';
  if (!teamFlat.length) {
    unfollow(); tabsBar.replaceChildren();
    body.replaceChildren(el('p', 'team-empty', 'このエージェントの子はまだいません（エージェントが子を起動すると〔children_start〕、ここに出ます。'
      + 'AI が起動した子は、タブではなくここで見ます）。'));
    return;
  }
  if (teamMode === 'tabs') {
    if (!teamFlat.some(m => m.id === teamTabSel)) teamTabSel = teamFlat[0].id;
    renderSubTabs(tabsBar);
    renderDetail(body, teamTabSel, false);
  } else if (teamFocus) {
    renderDetail(body, teamFocus, true);
  } else {
    unfollow();
    renderOverview(body);
  }
}

function renderSubTabs(bar) {
  bar.replaceChildren();
  for (const m of teamFlat) {
    const look = TeamView.look(m);
    const b = el('button', 'sub' + (m.id === teamTabSel ? ' on' : '')); b.type = 'button';
    b.dataset.tone = look.tone; b.dataset.alert = look.alert ? 'yes' : '';
    b.append(el('span', 'dot'), el('span', 'name', (m.depth ? '　'.repeat(m.depth - 1) + '└ ' : '') + m.name));
    b.title = `${TeamView.kindName(m)}「${m.name}」：${look.label}${look.alert ? `（${look.alert}）` : ''}`;
    b.addEventListener('click', () => { teamTabSel = m.id; renderTeam(); });
    b.addEventListener('contextmenu', event => { event.preventDefault(); opsMenu(m, event.clientX, event.clientY); });
    bar.append(b);
  }
}

// ---- 一覧・格子 -----------------------------------------------------------------------------------------
function flags(m) {
  const out = [m.reported ? '報告あり' : '報告まだ'];
  if (m.waiting) out.push(`届いていない言付け ${m.waiting}`);
  if (typeof m.context === 'number') out.push(`ctx ${Math.round(m.context)}%`);
  if (teamData.taken[m.id]) out.push(`引き取り中（タブ ${teamData.taken[m.id].num}）`);
  return out.join('・');
}

function renderOverview(body) {
  const box = el('div', teamMode === 'grid' ? 'team-grid' : 'team-list');
  for (const m of teamFlat) {
    const look = TeamView.look(m);
    const item = el('div', teamMode === 'grid' ? 'tile' : 'row');
    item.dataset.tone = look.tone; item.dataset.alert = look.alert ? 'yes' : ''; item.tabIndex = 0;
    item.title = look.alert || '';
    const name = el('span', 'name', m.name);
    if (m.depth) name.style.paddingLeft = `${m.depth * 14}px`;
    const role = el('span', 'role', TeamView.kindName(m));
    const state = el('span', 'state', look.label);
    const doing = el('span', 'doing', m.doing ? `今：${m.doing}` : look.alert || (m.last_reply ? `最後：${m.last_reply}` : ''));
    if (teamMode === 'grid') {
      const head = el('div', 'head'); head.append(name, role, state);
      const recent = el('pre', 'recent', (m.recent || []).join('\n') || '（出来事はまだありません）');
      item.append(head, doing, recent, el('div', 'flags', flags(m)));
    } else {
      item.append(name, role, state, doing, el('span', 'flags', flags(m)));
    }
    const open = () => { teamFocus = m.id; renderTeam(); };
    item.addEventListener('click', open);
    item.addEventListener('keydown', event => { if (event.key === 'Enter') open(); });
    item.addEventListener('contextmenu', event => { event.preventDefault(); opsMenu(m, event.clientX, event.clientY); });
    box.append(item);
  }
  body.replaceChildren(box);
}

// ---- 詳しい表示 ------------------------------------------------------------------------------------------
function renderDetail(body, id, back) {
  const m = teamFlat.find(x => x.id === id);
  let detail = body.querySelector('.detail');
  if (!detail || detail.dataset.id !== id) {
    detail = el('div', 'detail'); detail.dataset.id = id;
    detail.append(el('div', 'dhead'), el('div', 'dsub'), el('div', 'events'));
    body.replaceChildren(detail);
  }
  const head = detail.querySelector('.dhead'), sub = detail.querySelector('.dsub');
  head.replaceChildren(); sub.replaceChildren();
  if (back) {
    const b = el('button', 'tool back', '← 戻る'); b.type = 'button';
    b.title = teamMode === 'grid' ? '並べた表示に戻る' : '一覧に戻る';
    b.addEventListener('click', () => { teamFocus = null; renderTeam(); });
    head.append(b);
  }
  if (!m) {
    head.append(el('b', 'name', '（閉じた子）'));
    sub.append(el('span', 'note', 'この子はチームの一覧から消えました（閉じられました）。読んだ出来事はそのまま残しています。'));
    unfollow();   // 読んだ出来事は消さずに残す
    return;
  }
  const look = TeamView.look(m);
  const state = el('span', 'state', look.label); state.dataset.tone = look.tone;
  head.append(el('b', 'name', m.name), el('span', 'role', TeamView.kindName(m)), state);
  if (look.alert) head.append(el('span', 'alert', look.alert));
  const ops = el('span', 'ops');
  for (const op of opsFor(m)) {
    if (op.hidden) continue;
    const b = el('button', 'tool', op.label); b.type = 'button'; b.disabled = !!op.disabled || pending.has(m.id);
    b.title = op.title || '';
    b.addEventListener('click', event => { event.stopPropagation(); op.menu ? subMenu(op.menu, b) : op.run(); });
    ops.append(b);
  }
  head.append(ops);
  if (m.doing) sub.append(el('span', 'doing', `今：${m.doing}`));
  sub.append(el('span', '', flags(m)));
  if (m.branch) sub.append(el('span', 'where', `${m.task?.number ? `#${m.task.number} ` : ''}${m.branch}`));
  if (m.model) sub.append(el('span', '', m.model));
  if (m.usage && typeof m.usage.cost_usd === 'number') sub.append(el('span', '', `最後の返答 $${m.usage.cost_usd.toFixed(3)}`));
  const notice = notices.get(m.id);
  if (notice) { const n = el('span', notice.bad ? 'notice bad' : 'notice', notice.text); n.title = notice.text; sub.append(n); }
  if (m.mode !== 'app' && look.human) {
    sub.append(el('span', 'note', teamData.taken[m.id] ? 'このアプリのタブ（対話型）で引き取っています。閉じると係に戻します。'
      : '人の画面（対話型）で動いています。出来事は係が動かしている間だけ記録されます。'));
  }
  follow(m, detail.querySelector('.events'));
}

function follow(m, box) {
  if (followed === m.id && box.dataset.id === m.id) return;
  unfollow();
  followed = m.id; eventLog = new TeamView.EventLog(); eventItems = new Map(); moreBefore = false;
  box.dataset.id = m.id; box.replaceChildren(el('p', 'note', '出来事を読んでいます…'));
  box.dataset.empty = 'yes';
  agents.teamFollow(ref(m));
}
function unfollow() {
  clearTimeout(followTimer); followTimer = null;
  if (followed) agents.teamUnfollow();
  followed = null; eventLog = null;
}

// 出来事が届いた。more：はじめに読んだものより前にもある。reset：読み直しの始まり。ended：追うのが終わった（3 秒後に読み直す）
agents.onTeamEvents((id, events, more, reset, ended) => {
  if (id !== followed || !eventLog) return;
  if (ended) {
    clearTimeout(followTimer);
    followTimer = setTimeout(() => { const m = teamFlat.find(x => x.id === id); if (followed === id && m) agents.teamFollow(ref(m)); }, 3000);
    return;
  }
  const box = document.querySelector(`#team .detail[data-id="${CSS.escape(id)}"] .events`);
  if (!box) return;
  if (reset) { eventLog = new TeamView.EventLog(); eventItems = new Map(); box.replaceChildren(); moreBefore = !!more; box.dataset.empty = ''; }
  if (box.dataset.empty) { box.replaceChildren(); box.dataset.empty = ''; }
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;   // 読み返しているときは追いかけない
  const {added, changed} = eventLog.add(events);
  if (reset && moreBefore) {
    const b = el('button', 'tool more', 'これより前の出来事もすべて読む'); b.type = 'button';
    b.addEventListener('click', () => {
      const m = teamFlat.find(x => x.id === id); if (!m) return;
      box.replaceChildren(el('p', 'note', 'すべての出来事を読んでいます…')); box.dataset.empty = 'yes';
      eventLog = new TeamView.EventLog(); eventItems = new Map();
      agents.teamFollow(ref(m), true);
    });
    box.append(b);
  }
  for (const item of added) { const e = itemEl(item); eventItems.set(item.key, e); box.append(e); }
  for (const item of changed) { const e = eventItems.get(item.key); if (e) e.replaceWith(eventItems.set(item.key, itemEl(item, e.open)).get(item.key)); }
  if (!eventLog.items.length) box.append(el('p', 'note', '出来事はまだありません（係が画面なしで動かしている間の記録です）。'));
  if (atBottom || reset) box.scrollTop = box.scrollHeight;
});

function longText(cls, text) {
  const e = el('div', cls);
  const body = el('div', 'body', text.length > TEXT_LIMIT ? text.slice(0, TEXT_LIMIT) + '…' : text);
  e.append(body);
  if (text.length > TEXT_LIMIT) {
    const b = el('button', 'tool', '続きを見る'); b.type = 'button';
    b.addEventListener('click', () => { body.textContent = text; b.remove(); });
    e.append(b);
  }
  return e;
}

function itemEl(item, open = false) {
  if (item.kind === 'input') {
    const e = longText('ev input', item.text);
    e.prepend(el('span', 'from', `${item.from} から`));
    return e;
  }
  if (item.kind === 'text') return longText('ev text', item.text);
  if (item.kind === 'tool') {
    const e = el('details', 'ev tool' + (item.error ? ' error' : '')); e.open = open;
    const s = el('summary'); s.append(el('span', 'sum', item.summary), el('span', 'st', item.done ? (item.error ? '失敗' : '') : '実行中…'));
    e.append(s);
    const fill = () => {
      if (e.dataset.filled) return; e.dataset.filled = 'yes';
      if (item.input != null) e.append(el('div', 'label', '入力'), el('pre', '', JSON.stringify(item.input, null, 2)));
      if (item.done) {
        const out = item.output || '（出力なし）';
        e.append(el('div', 'label', '出力'), el('pre', '', out.length > OUTPUT_LIMIT ? out.slice(0, OUTPUT_LIMIT) + '\n…（長いので省きました）' : out));
      }
    };
    e.addEventListener('toggle', () => { if (e.open) fill(); });
    if (open) fill();
    return e;
  }
  if (item.kind === 'turn') {
    const e = el('div', 'ev turn' + (item.error ? ' error' : ''));
    e.append(el('span', '', TeamView.turnLine(item)));
    for (const d of item.denials) {
      e.append(el('div', 'denial', `断られた権限：${TeamView.toolSummary(String(d.tool_name || '道具'), d.tool_input)}`));
    }
    return e;
  }
  const e = el('div', 'ev mark', item.text); e.dataset.tone = item.tone || '';
  return e;
}

// ---- 操作 ------------------------------------------------------------------------------------------------
// できない操作は灰色（disabled・title にわけ）、当てはまらない操作は出さない（hidden）
function opsFor(m) {
  const look = TeamView.look(m), app = m.mode === 'app', taken = teamData.taken[m.id];
  const running = m.state === 'working' || m.state === 'idle';
  const otherScreen = look.human && !taken;
  return [
    {label: '止める', hidden: !app || !!taken, disabled: !running, title: running ? '返答を終えさせてから止めます（作業空間・作業はそのまま）' : 'もう止まっています',
     run: () => act(m, 'stop', '止めています（返答を終えてから）…', '止めました')},
    {label: '起動し直す ▾', hidden: !!taken, disabled: otherScreen, title: otherScreen ? '人の画面（対話型）で動いています。その画面を閉じてから' : '',
     menu: [['新しい会話で（どこまで進んだかを確かめてから続けます）', () => act(m, 'restart', '起動し直しています…', '起動し直しました')],
            ['前の会話の続きから', () => act(m, 'restart', '続きから起動し直しています…', '続きから起動し直しました', {resume: true})]]},
    {label: '引き取る', hidden: look.human || !!taken, title: '同じ会話を、この窓のタブ（対話型）で開いて話せます。タブを閉じると係に返します',
     run: () => act(m, 'takeover', '引き取っています（返答を終えてから）…', '引き取りました（タブで開きました）')},
    {label: 'タブを見る', hidden: !taken, title: '引き取ったタブへ', run: () => { agents.select(taken.id); show(taken.id); }},
    {label: '返す', hidden: app && !taken, disabled: otherScreen, title: otherScreen ? '人の画面（対話型）で動いています。その画面を閉じてから' : '係に戻し、前の会話の続きから画面なしで続けさせます',
     run: () => act(m, 'handback', '係に戻しています…', '係に戻しました')},
    {label: '場所 ▾', menu: [['エクスプローラーで開く', () => act(m, 'folder')], ['モジュールの窓で開く', () => act(m, 'module')]]},
    {label: '閉じる…', title: m.kind === 'helper' ? '止めて、記録を消します（親の作業空間はそのまま）' : '止めて、記録と子タスクの作業空間を消します',
     run: () => closeMember(m)},
  ];
}

async function act(m, action, doing = '', done = '', options = {}) {
  if (pending.has(m.id)) return;
  if (doing) { pending.add(m.id); notices.set(m.id, {text: doing}); renderTeam(); }
  const got = await agents.teamOp(teamLead.id, action, ref(m), options);
  pending.delete(m.id);
  // note：係がしなかったこと（子はそのままで、起動していない等）
  const note = got.result?.note;
  if (doing || !got.ok) notices.set(m.id, !got.ok ? {text: got.error || '失敗しました', bad: true} : note ? {text: note, bad: true} : {text: got.message || done});
  renderTeam();
}

function closeMember(m) {
  if (!confirm(`${TeamView.kindName(m)}「${m.name}」を閉じますか？\n止めて、記録を消します。子タスクなら作業空間も場所ごと消します（GitHub にないもの・作業中・届いていない言付けがあれば閉じません）。`)) return;
  act(m, 'close', '閉じています…', '閉じました');
}

function subMenu(items, anchor) {
  const menu = $('menu'); menu.replaceChildren();
  for (const [label, run] of items) {
    const b = el('button', '', label); b.type = 'button';
    b.addEventListener('click', () => { menu.hidden = true; run(); }); menu.append(b);
  }
  const r = anchor.getBoundingClientRect();
  menu.hidden = false;
  menu.style.left = Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8)) + 'px';
  menu.style.top = Math.min(r.bottom + 2, innerHeight - menu.offsetHeight - 8) + 'px';
}

// 一覧・格子・タブの右クリック：同じ操作をメニューで
function opsMenu(m, x, y) {
  const menu = $('menu'); menu.replaceChildren();
  menu.append(el('div', 'head', `${TeamView.kindName(m)}「${m.name}」`));
  for (const op of opsFor(m)) {
    if (op.hidden) continue;
    for (const [label, run] of op.menu || [[op.label, op.run]]) {
      const b = el('button', '', op.menu ? `${op.label.replace(' ▾', '')}：${label}` : label); b.type = 'button';
      b.disabled = !!op.disabled || pending.has(m.id); b.title = op.title || '';
      if (b.disabled) b.style.opacity = '.45';
      b.addEventListener('click', () => { menu.hidden = true; run(); }); menu.append(b);
    }
  }
  menu.hidden = false;
  menu.style.left = Math.min(x, innerWidth - menu.offsetWidth - 8) + 'px'; menu.style.top = Math.min(y, innerHeight - menu.offsetHeight - 8) + 'px';
}

// ---- 知らせ（⚙）：子の返答の終わり。既定は知らせない（親のエージェントに届くので） ---------------------------------
agents.onNotify(notify => { $('notify-team').checked = !!notify.team; });
$('notify-team').addEventListener('change', () => agents.setNotify({team: $('notify-team').checked}));
