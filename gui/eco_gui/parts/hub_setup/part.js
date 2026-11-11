// 部品「環境の準備の欄と結果」。今までの GUI（gui/static/hub.js の setup-form・setup-status）と同じ。
// 欄は描き直しても作り直さない（打っている途中の文字を残す）。今の名前・メールは placeholder に出すだけ。
export default {
  render(root, props, { h, emit, state }) {
    const author = props.items.find((item) => item.name === 'git の名前・メール');
    const [, name = '', email = ''] = (author && author.ok && /^(.*?)\s*<(.*)>$/.exec(author.detail || '')) || [];
    if (!state.fields) {
      const input = (label, type) => {
        const box = h('input', { type, autocomplete: 'off' });
        box.addEventListener('input', () => state.send());
        return { box, label: h('label', {}, label, box) };
      };
      const who = input('名前', 'text'), mail = input('メールアドレス', 'email');
      const check = h('input', { type: 'checkbox' });
      check.addEventListener('change', () => state.send());
      state.send = () => emit('changed', { name: who.box.value.trim(), email: mail.box.value.trim(), install: check.checked });
      state.fields = { who, mail, form: h('div', { class: 'fields' }, who.label, mail.label),
        install: h('label', { class: 'check' }, check, '不足しているツールもインストールする（winget）'), status: h('div', { class: 'status', role: 'status' }) };
      root.replaceChildren(state.fields.form, state.fields.install, state.fields.status);
    }
    const { who, mail, status } = state.fields;
    who.box.placeholder = name || '変更するときだけ入力';
    mail.box.placeholder = email || '変更するときだけ入力';
    const result = props.result;
    if (!result) return status.replaceChildren();
    const done = result.done || [], remaining = result.remaining || [], commands = result.commands || [];
    const lines = [];
    if (done.length) {
      const text = h('p', {});
      done.forEach((line, at) => { if (at) text.append(h('br', {})); text.append(line); });
      lines.push(text);
    } else lines.push(h('p', {}, '変更はありませんでした（すでに準備できています）。'));
    if (remaining.length) lines.push(h('p', { class: 'left' }, 'まだ足りないもの：' + remaining.map((item) => item.name || item).join('、')));
    if (commands.length) lines.push(h('p', {}, '足りないツールのインストールコマンド：'), h('pre', {}, commands.join('\n')));
    status.replaceChildren(...lines);
  },
};
