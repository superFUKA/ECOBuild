'use strict';
// 管理 › メンバー: the module's collaborators and the people invited (module members), with their roles — GitHub's
// permissions, which are what ECOBuild's roles are (account show). Inviting, changing a role and removing are for
// admins; GitHub shows the list to admins only, so the others see why. A personal account's repository gives
// collaborators "write" only (GitHub's rule): the role is chosen only in an organization's.
(() => {
  const el = id => document.getElementById(id);
  const {esc} = ECO;
  const st = {members: null, access: null, error: '', loaded: false};
  const roles = () => Object.entries(ECO.roleNames);
  const organization = () => st.access?.owner_type === 'Organization';

  async function load() {
    st.access = await ECO.access(MOD.root);
    if (!ECO.isAdmin(st.access)) { st.loaded = true; render(); return; }
    const doc = await ECO.cli(MOD.root, ['module', 'members'], {quiet: true});
    st.members = doc.ok ? doc.result : null; st.error = doc.ok ? '' : doc.error.message; st.loaded = true;
    render();
  }
  function render() {
    const box = el('members-main'); if (!box || box.hidden) return;
    if (!st.loaded) { box.innerHTML = ECO.loading(); return; }
    const note = st.access ? `あなた：<strong>${esc(st.access.login)}</strong>（${esc(ECO.roleNames[st.access.role] || st.access.role)}）` : '';
    // The head as on the other pages: the title and the note on the left, the button on the right.
    const head = button => `<div class="mi-head"><div><h3>メンバー</h3>${note ? `<p class="mi-note">${note}</p>` : ''}</div><div class="mi-actions">${button}</div></div>`;
    if (!ECO.isAdmin(st.access)) { box.innerHTML = `${head(`<button type="button" class="primary" disabled title="${esc(ECO.adminNote)}">＋ 招待</button>`)}<p class="mi-note">メンバーの一覧と招待・役割の変更は、${ECO.adminNote}。</p>`; return; }
    const me = head('<button type="button" class="primary" data-member-add>＋ 招待</button>');
    if (st.error) { box.innerHTML = `${me}<div class="eco-banner bad">${esc(st.error)}<button type="button" class="sm" data-member-retry>読み直す</button></div>`; return; }
    const owner = st.access?.owner ? `<tr><td><strong>${esc(st.access.owner)}</strong></td><td>${organization() ? '組織' : '持ち主'}</td><td class="mi-sub">${organization() ? '' : '管理者'}</td><td></td></tr>` : '';
    // GitHub lists the owner of a personal account's repository as a collaborator too: it has its own row above.
    const rows = (st.members || []).filter(m => organization() || m.login.toLowerCase() !== (st.access?.owner || '').toLowerCase()).map(m => `<tr>
      <td>${esc(m.login)}${m.login.toLowerCase() === (st.access?.login || '').toLowerCase() ? '（自分）' : ''}</td>
      <td>${esc(ECO.roleNames[m.role] || m.role)}</td><td class="mi-sub">${m.invited ? '招待中' : ''}</td>
      <td class="mi-row-actions">${organization() ? `<button type="button" data-member-role="${esc(m.login)}">役割…</button>` : ''}<button type="button" class="danger-text" data-member-remove="${esc(m.login)}">${m.invited ? '招待を取り消す' : '外す'}</button></td></tr>`).join('');
    box.innerHTML = `${me}
      <table class="mi-table members-table"><thead><tr><th>アカウント</th><th>役割</th><th>状態</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>${owner}${rows ||
        '<tr><td colspan="4" class="mi-sub">共同作業者はまだいません。</td></tr>'}</tbody></table>
      ${organization() ? '' : '<p class="mi-note">個人のアカウントのリポジトリでは、GitHub の決まりで共同作業者の役割は「書き込み」だけです（管理者は持ち主だけ）。管理できる人を増やすなら、組織のリポジトリにします。</p>'}`;
  }

  const roleField = value => organization()
    ? [{name: 'role', label: '役割', type: 'select', value, options: roles().map(([k, v]) => [k, `${v}（${k}）`])}] : [];
  async function invite() {
    return ECO.form({title: 'メンバーを招待', intro: 'GitHub のアカウントを共同作業者に招待します。相手が GitHub の通知・メールから受けると加わり、タスク管理の情報も共有されます。', fields: [
      {name: 'user', label: 'GitHub のユーザー名', required: true, placeholder: '例：octocat'}, ...roleField('write')], ok: '招待',
      submit: async v => {
        const doc = await ECO.run(MOD.root, ['module', 'members', 'add', v.user, ...(v.role ? ['--role', v.role] : [])], {success: `${v.user} を招待しました。`});
        if (!doc) return '招待できませんでした。';
        await load();
      }});
  }
  async function changeRole(login) {
    const now = (st.members || []).find(m => m.login === login)?.role || 'write';
    const v = await ECO.form({title: `${login} の役割`, fields: roleField(now), ok: '変える'});
    if (!v || v.role === now) return;
    if (await ECO.run(MOD.root, ['module', 'members', 'add', login, '--role', v.role], {success: `${login} の役割を変えました。`})) await load();
  }
  async function remove(login) {
    if (await ECO.run(MOD.root, ['module', 'members', 'remove', login], {success: `${login} を外しました。`})) await load();
  }

  el('members-main').addEventListener('click', e => {
    if (e.target.closest('[data-member-add]')) return invite();
    if (e.target.closest('[data-member-retry]')) return window.MANAGE_MEMBERS.reload();
    const role = e.target.closest('[data-member-role]'); if (role) return changeRole(role.dataset.memberRole);
    const gone = e.target.closest('[data-member-remove]'); if (gone) return remove(gone.dataset.memberRemove);
  });
  window.MANAGE_MEMBERS = {show: () => { if (!st.loaded) { render(); load(); } else render(); }, reload: () => { st.loaded = false; render(); load(); }};
})();
