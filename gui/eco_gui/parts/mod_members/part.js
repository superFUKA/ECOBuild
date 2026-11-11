// 部品「メンバーの表」。今までの GUI のメンバー（見出し・表・注記）と同じに描く。
const ROLE_NAMES = { read: '読む', triage: 'タスクの整理', write: '書き込み', maintain: '管理の一部', admin: '管理者' };
const ADMIN_NOTE = '管理者だけが行えます';
const same = (a, b) => String(a || '').toLowerCase() === String(b || '').toLowerCase();

export default {
  render(root, props, { h, emit }) {
    const me = props.account;
    const organization = me.owner_type === 'Organization';
    const admin = me.admin !== false;  // 分からないあいだは、灰色にしない（押した操作は ecobuild が確かめる）
    const head = h('div', { class: 'head' });
    const who = h('div', {});
    if (me.login) who.append(h('p', { class: 'note' }, 'あなた：', h('strong', {}, me.login), '（' + (ROLE_NAMES[me.role] || me.role || '役割は不明') + '）'));
    const invite = h('button', { type: 'button', class: 'primary' }, '＋ 招待');
    if (!admin) { invite.setAttribute('aria-disabled', 'true'); invite.title = ADMIN_NOTE; }
    invite.addEventListener('click', () => { if (admin) emit('action', { action: 'invite', organization }); });
    head.append(who, h('div', { class: 'actions' }, invite));
    if (!admin) return root.replaceChildren(head, h('p', { class: 'note' }, 'メンバーの一覧と招待・役割の変更は、' + ADMIN_NOTE + '。'));
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      return root.replaceChildren(head, h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    const body = h('tbody', {});
    if (me.owner) {
      body.append(h('tr', {}, h('td', {}, h('strong', {}, me.owner)), h('td', {}, organization ? '組織' : '持ち主'),
        h('td', { class: 'sub' }, organization ? '' : '管理者'), h('td', {})));
    }
    // 個人のリポジトリでは、GitHub は持ち主も共同作業者として返す：上に専用の行があるので、出さない
    const rows = props.members.filter((m) => organization || !same(m.login, me.owner));
    for (const m of rows) {
      const buttons = h('td', { class: 'row-actions' });
      if (organization) {
        const role = h('button', { type: 'button', class: 'small' }, '役割…');
        role.addEventListener('click', () => emit('action', { action: 'role', login: m.login, role: m.role || '', organization }));
        buttons.append(role);
      }
      const remove = h('button', { type: 'button', class: 'small danger-text' }, m.invited ? '招待を取り消す' : '外す');
      remove.addEventListener('click', () => emit('action', { action: 'remove', login: m.login }));
      buttons.append(remove);
      body.append(h('tr', {}, h('td', {}, m.login, same(m.login, me.login) ? h('span', { class: 'self' }, '（自分）') : ''),
        h('td', {}, ROLE_NAMES[m.role] || m.role || ''), h('td', {}, m.invited ? h('span', { class: 'pill warn' }, '招待中') : ''), buttons));
    }
    if (rows.length === 0) body.append(h('tr', {}, h('td', { colspan: '4', class: 'sub' }, props.loading ? '読み込み中…' : '共同作業者はまだいません。')));
    const out = [head, h('table', { class: 'members' }, h('thead', {}, h('tr', {}, h('th', {}, 'アカウント'), h('th', {}, '役割'), h('th', {}, '状態'),
      h('th', {}, h('span', { class: 'sr-only' }, '操作')))), body)];
    if (me.owner_type && !organization) {
      out.push(h('p', { class: 'note after' }, '個人のアカウントのリポジトリでは、GitHub の決まりで共同作業者の役割は「書き込み」だけです（管理者は持ち主だけ）。'
        + '管理できる人を増やすなら、組織のリポジトリにします。'));
    }
    root.replaceChildren(...out);
  },
};
