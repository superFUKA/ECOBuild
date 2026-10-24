'use strict';
// 子を起動できるエージェントの窓の、AI が起動した子（係が画面なしで動かす。子の子も）：窓のタブ・横の一覧・一覧に、そのエージェントの
// 後ろへ並べる（window.js の entries）。選ぶと詳しい表示。読むだけで、入力欄は置かない（指示は親のエージェントから）。
// 止まっている・失敗・作業中が長い・長く道具を使っていないものは目立たせる。詳しい表示は返答の文・道具（1行に畳み、開くと
// 入出力）・届いた言付けと知らせ（誰からか）・返答の終わりの区切り（使用量・断られた権限）。新しい出来事は追いかける（読み
// 返しているときは追いかけない）。操作：止める・起動し直す・引き取る（このアプリのタブで開く。閉じると係に返す）・返す・
// 場所を開く・閉じる。1人はエージェントの ID でつなぐので、起動し直しても・引き取って返しても、同じ表示が続く。
// データは main（team.js）が CLI（agent children・agent log）から読んで送ってくる。window.js の後に読む。
const TEXT_LIMIT = 6000;      // 長い返答・発言は、ここまで出して「続き」
const OUTPUT_LIMIT = 20000;   // 道具の出力を出す長さ
let teamLead = null, teamData = {members: [], error: '', taken: {}}, teamFlat = [], activeChild = null, teamSeen = null;
let followed = null, eventLog = null, eventItems = new Map(), moreBefore = false, followTimer = null;
const NARROW = 640;           // 詳しい表示の幅がこれより狭いと、操作を「操作 ▾」1つにまとめる
const notices = new Map();    // 子の ID → {text, bad}
const pending = new Set();    // 操作中の子の ID

const leadOfWindow = () => tabs.find(t => t.pinned && t.lead) || null;
const ref = m => ({id: m.id, name: m.name, path: m.path});
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

// ---- 並べる1つ（window.js の itemButton から）：タブ・横の一覧 ----------------------------------------------------
function childButton(m, style) {
  const look = TeamView.look(m), role = TeamView.roleLabel(m);
  const b = el('button', (style === 'side' ? 'tab side-item child' : 'tab child') + (m.id === activeChild ? ' active' : '')); b.type = 'button';
  b.dataset.tone = look.tone; b.dataset.alert = look.alert ? 'yes' : '';
  b.append(el('span', 'dot'), el('span', 'name', (style === 'side' ? '　'.repeat(m.depth) : '') + (m.depth || style === 'side' ? '└ ' : '') + m.name));
  if (style === 'side') b.append(el('span', 'sub', [role.text, look.label, m.doing ? `今：${m.doing}` : look.alert].filter(Boolean).join('・')));
  b.title = `${role.title}「${m.name}」：${look.label}${look.alert ? `（${look.alert}）` : ''}\nAI が起動した子（${teamLead?.name || ''} の子）`;
  b.addEventListener('click', () => showChild(m.id));
  b.addEventListener('contextmenu', event => { event.preventDefault(); opsMenu(m, event.clientX, event.clientY); });
  return b;
}

// 子を選んだ：端末を隠して、子の詳しい表示
function showChild(id) {
  if (!leadOfWindow()) return;
  activeChild = id; listOpen = false;
  renderTabs();
  renderChild();
}
// 端末を選んだ（window.js の show から）
function hideChild() {
  if (!activeChild) return;
  activeChild = null;
  unfollow();
}
// 子を出しているときは、様子を早めに読み直す（window.js の renderTabs から。横の一覧・一覧でも）
function teamVisible(on) {
  const lead = leadOfWindow(); if (!lead) return;
  const key = `${lead.id}:${!!on}`; if (teamSeen === key) return; teamSeen = key;
  agents.teamShown(lead.id, !!on).then(view => { if (view) setTeamData(view); });
}

function renderChild() {
  if (!activeChild) return;
  renderDetail($('team-body'), activeChild);
}

function setTeamData(view) {
  teamData = {members: view.members || [], error: view.error || '', taken: view.taken || {}};
  teamFlat = TeamView.flatten(teamData.members, teamLead?.agentId || '');
  renderTabs();
  renderChild();
}

agents.onTeamList((leadId, view) => {
  const lead = leadOfWindow();
  if (!lead || lead.id !== leadId) return;
  if (teamLead && teamLead.id !== lead.id) { hideChild(); teamFlat = []; }
  teamLead = lead; setTeamData(view);
});
agents.onTeamFocus(id => showChild(id));
agents.onTeamNotice((id, text, bad) => { notices.set(id, {text, bad}); renderChild(); });

// 詳しい表示の幅が NARROW をまたいだら、操作の並べ方を変える
let teamNarrow = null;
new ResizeObserver(() => {
  const narrow = $('team-body').clientWidth < NARROW;
  if (teamNarrow !== null && narrow !== teamNarrow && activeChild) renderChild();
  teamNarrow = narrow;
}).observe($('team-body'));

function flags(m) {
  const out = m.reported ? ['報告あり'] : [];   // まだのときは出さない（報告するかは役による）
  if (m.waiting) out.push(`届いていない言付け ${m.waiting}`);
  if (typeof m.context === 'number') out.push(`ctx ${Math.round(m.context)}%`);
  if (teamData.taken[m.id]) out.push(`引き取り中（タブ ${teamData.taken[m.id].num}）`);
  return out.join('・');
}

// ---- 詳しい表示 ------------------------------------------------------------------------------------------
function renderDetail(body, id) {
  const m = teamFlat.find(x => x.id === id);
  let detail = body.querySelector('.detail');
  if (!detail || detail.dataset.id !== id) {
    detail = el('div', 'detail'); detail.dataset.id = id;
    detail.append(el('div', 'dhead'), el('div', 'dsub'), el('div', 'events'));
    body.replaceChildren(detail);
  }
  const head = detail.querySelector('.dhead'), sub = detail.querySelector('.dsub');
  head.replaceChildren(); sub.replaceChildren();
  if (!m) {
    head.append(el('b', 'name', '（閉じた子）'));
    unfollow();   // 読んだ出来事は消さずに残す
    return;
  }
  const look = TeamView.look(m);
  const state = el('span', 'state', look.label); state.dataset.tone = look.tone;
  const roleText = TeamView.roleLabel(m), role = el('span', 'role', roleText.text); role.title = roleText.title;
  head.append(el('b', 'name', m.name), role, state);
  if (look.alert) head.append(el('span', 'alert', look.alert));
  const ops = el('span', 'ops');
  if (head.parentElement.clientWidth < NARROW) {   // 狭いときは「操作 ▾」1つにまとめる（中身は右クリックのメニューと同じ）
    const b = el('button', 'tool', '操作 ▾'); b.type = 'button'; b.disabled = pending.has(m.id);
    b.addEventListener('click', event => { event.stopPropagation(); const r = b.getBoundingClientRect(); opsMenu(m, r.right - 200, r.bottom + 2); });
    ops.append(b);
  } else {
    for (const op of opsFor(m)) {
      if (op.hidden) continue;
      const b = el('button', 'tool' + (op.danger ? ' danger' : ''), op.label); b.type = 'button'; b.disabled = !!op.disabled || pending.has(m.id);
      b.title = op.title || '';
      b.addEventListener('click', event => { event.stopPropagation(); op.menu ? subMenu(op.menu, b) : op.run(); });
      ops.append(b);
    }
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
  if (!eventLog.items.length) box.append(el('p', 'note', '出来事はまだありません。'));
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
    {label: '閉じる…', danger: true, title: m.kind === 'helper' ? '止めて、記録を消します（親の作業空間はそのまま）' : '止めて、記録と子タスクの作業空間を消します',
     run: () => closeMember(m)},
  ];
}

async function act(m, action, doing = '', done = '', options = {}) {
  if (pending.has(m.id)) return;
  if (doing) { pending.add(m.id); notices.set(m.id, {text: doing}); renderChild(); }
  const got = await agents.teamOp(teamLead.id, action, ref(m), options);
  pending.delete(m.id);
  // note：係がしなかったこと（子はそのままで、起動していない等）
  const note = got.result?.note;
  if (doing || !got.ok) notices.set(m.id, !got.ok ? {text: got.error || '失敗しました', bad: true} : note ? {text: note, bad: true} : {text: got.message || done});
  renderChild();
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
  placeMenu(menu, r.left, r.bottom + 2);
}

// タブ・横の一覧・一覧の右クリック：同じ操作をメニューで
function opsMenu(m, x, y) {
  const menu = $('menu'); menu.replaceChildren();
  menu.append(el('div', 'head', `${TeamView.kindName(m)}「${m.name}」`));
  for (const op of opsFor(m)) {
    if (op.hidden) continue;
    if (op.danger) menu.append(el('div', 'sep'));   // 消す操作の前に区切り
    for (const [label, run] of op.menu || [[op.label, op.run]]) {
      const b = el('button', op.danger ? 'danger' : '', op.menu ? `${op.label.replace(' ▾', '')}：${label}` : label); b.type = 'button';
      b.disabled = !!op.disabled || pending.has(m.id); b.title = op.title || '';
      b.addEventListener('click', () => { menu.hidden = true; run(); }); menu.append(b);
    }
  }
  placeMenu(menu, x, y);
}

// ---- 知らせ（⚙）：子の返答の終わり。既定は知らせない（親のエージェントに届くので） ---------------------------------
agents.onNotify(notify => { $('notify-team').checked = !!notify.team; });
$('notify-team').addEventListener('change', () => agents.setNotify({team: $('notify-team').checked}));
