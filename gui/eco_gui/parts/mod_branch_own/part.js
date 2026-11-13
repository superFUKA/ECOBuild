// 部品「このブランチの提出」。提出が出ていれば取り込む、出ていなければ提出する（既定のブランチは提出しない）。
// 灰色と理由は account show の答えを引くだけ（今までの GUI のブランチの画面と同じ決め方）。
export default {
  render(root, props, { h, emit }) {
    if (props.error) return root.replaceChildren(h('p', { class: 'note', role: 'alert' }, props.error));
    const b = (props.branches || []).find((one) => one.name === props.name);
    const access = props.access;
    if (!b || !access) {
      return root.replaceChildren(h('p', { class: 'note', role: 'status' }, props.loading || !access ? '読み込み中…' : 'GitHub にないブランチです。'));
    }
    const me = String(access.login || '').toLowerCase();
    const admin = access.admin !== false;
    const creator = String((access.creators || {})[b.name] || '');
    const button = (action, label, off, title) => {
      const item = h('button', { type: 'button', class: 'primary' }, label);
      item.title = [title, off ? '（' + off + '）' : ''].filter(Boolean).join('\n');
      item.disabled = Boolean(off);
      item.addEventListener('click', () => emit('action', { action }));
      return item;
    };
    const s = b.submission;
    if (s && s.state === 'open') {
      const into = b.submitted_to || '';
      const rule = (access.take_in || {})[into] || access.take_in_other || null;
      const off = s.draft ? '下書きの提出は取り込めません' : rule && rule.allowed === false ? into + ' への提出を処理できるのは、' + rule.owners + 'だけです' : '';
      return root.replaceChildren(h('p', { class: 'note' }, (s.draft ? '下書きの' : '') + '提出（→ ' + into + '）が出ています。'),
        button('merge', 'このブランチの提出を取り込む…', off, 'もう作ってある提出（branch submit）を、マージコミットで取り込む'));
    }
    if (b.name === access.default_base) {
      return root.replaceChildren(h('p', { class: 'note' }, '既定のブランチです（ほかのブランチへは提出しません。下のカードで直接取り込めます）。'));
    }
    const may = admin || (!!creator && creator.toLowerCase() === me);
    return root.replaceChildren(h('p', { class: 'note' }, '提出（PR）で、見てもらってから取り込みます。'),
      button('submit', '提出する…', may ? '' : '管理者だけが行えます（このブランチを作った人も）', '取り込み先への提出を作る（ecobuild branch submit）'));
  },
};
