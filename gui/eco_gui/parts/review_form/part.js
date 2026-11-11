// 部品「提出まわりの入力の窓」。題・「何が起きるか」の表・入力欄・ボタン。今までの GUI のダイアログ（finishForm・completeForm・
// 承認・差し戻し・コメント・提出・反映）と同じ文言。入れている途中の値は state に持ち、実行で submitted にまとめて出す。
const CLOSE = '閉じて、タスクブランチを片付けます', KEEP = '閉じずに続けます（タスクブランチを作成元の最新から作り直します）';

export default {
  render(root, props, { h, emit, state, redraw }) {
    const kind = props.kind, n = props.id, into = '作成元' + (props.base ? `（${props.base}）` : '');
    if (state.complete === undefined) state.complete = !props.partial;
    const v = state;
    const taskRow = () => (v.complete ? CLOSE : KEEP);
    const forms = {
      finish: { title: `取り込む：#${n}`, ok: '取り込む', fields: ['subject', 'ignore', 'complete'],
        outcome: [['取り込み', `CI を待って、提出を${into}へ取り込みます`], ['タスク', taskRow()]] },
      complete: { title: `完了にする：#${n}`, ok: '完了にする', fields: ['ignore_complete'],
        outcome: [['取り込み', props.submitted ? `出している提出を、CI を待って${into}へ取り込みます`
          : `まだ取り込んでいない変更があれば、提出して${into}へ取り込みます（なければ取り込みません）`], ['タスク', CLOSE]] },
      approve: { title: `承認して取り込む：#${n}`, ok: '承認して取り込む', fields: ['message_optional', 'subject', 'ignore'],
        intro: 'CIが終わるのを待ちます。タスクは提出のとおり閉じるか続けます。',
        outcome: [['取り込み', `提出を承認し、CI を待って${into}へ取り込みます`], ['タスク', props.partial ? KEEP : CLOSE]] },
      reject: { title: `差し戻す：#${n}`, ok: '差し戻す', danger: true, fields: ['message_fix'], intro: 'タスクは作業中に戻ります。' },
      comment: { title: `#${n} にコメント`, ok: 'コメントする', fields: ['message'] },
      apply: { title: `反映：#${n}`, ok: '反映', fields: ['subject', 'complete'],
        outcome: [['反映', `提出（PR）を作らずに、${into}の最新へ1つのコミットにまとめて入れます（CIは待ちません）`], ['反映したら', taskRow()]] },
      submit: { title: '提出', ok: '提出', fields: ['title', 'draft', 'reviewer', 'complete_after'],
        outcome: [['PR', props.submitted ? '出している提出に、Push したコミットが加わります' : `${into}へ出します（Push してから）`],
          ['取り込み', '見る人の承認で取り込まれます'], ['取り込まれたら', taskRow()]] },
      merge: { title: `${n} の提出を取り込む`, ok: '取り込む', fields: ['ignore'], intro: 'ブランチ同士の提出を、マージコミットで取り込みます。' },
    };
    const form = forms[kind];
    const needsMessage = kind === 'reject' || kind === 'comment';
    const ok = h('button', { type: 'submit', class: form.danger ? 'danger' : 'primary' }, form.ok);
    const sync = () => { ok.disabled = needsMessage && !(v.message || '').trim(); };
    const text = (name, label, placeholder) => {
      const input = h('input', { type: 'text', placeholder: placeholder || '' });
      input.value = v[name] || '';
      input.addEventListener('input', () => { v[name] = input.value; });
      return h('label', {}, label, input);
    };
    const area = (label, placeholder) => {
      const input = h('textarea', { rows: 5, placeholder: placeholder || '' });
      input.value = v.message || '';
      input.addEventListener('input', () => { v.message = input.value; sync(); });
      return h('label', {}, label, input);
    };
    const check = (name, label, again) => {
      const input = h('input', { type: 'checkbox' });
      input.checked = !!v[name];
      input.addEventListener('change', () => { v[name] = input.checked; if (again) redraw(); });  // 「何が起きるか」の表を書き直す
      return h('label', { class: 'check' }, input, h('span', {}, label));
    };
    const FIELDS = {
      subject: () => text('subject', '取り込むコミットの件名（空ならタスクの題名）'),
      title: () => text('title', '提出の題名（空ならタスクの題名）'),
      reviewer: () => text('reviewer', '見てもらう人（GitHub のユーザー名。カンマ区切り）'),
      ignore: () => check('ignore_checks', 'CIが失敗していても取り込む'),
      ignore_complete: () => check('ignore_checks', 'CIが失敗していても完了する'),
      draft: () => check('draft', '下書きで提出する（まだ見てもらわない）'),
      complete: () => check('complete', 'タスクを完了する', true),
      complete_after: () => check('complete', '取り込まれたらタスクを完了する', true),
      message: () => area('内容'),
      message_optional: () => area('コメント（任意）'),
      message_fix: () => area('直してほしいこと'),
    };
    const cancel = h('button', { type: 'button' }, 'キャンセル');
    cancel.addEventListener('click', () => emit('cancelled', {}));
    const box = h('form', {},
      h('h2', {}, form.title),
      form.intro ? h('p', { class: 'intro' }, form.intro) : '',
      form.outcome ? h('dl', { class: 'outcome' }, ...form.outcome.flatMap(([k, text]) => [h('dt', {}, k), h('dd', {}, text)])) : '',
      ...form.fields.map((name) => FIELDS[name]()),
      h('div', { class: 'actions' }, cancel, ok));
    box.addEventListener('submit', (event) => {
      event.preventDefault();
      if (ok.disabled) return;
      const complete = kind === 'complete' ? true : !!v.complete;
      emit('submitted', { kind, id: n, message: (v.message || '').trim(), subject: (v.subject || '').trim(), title: (v.title || '').trim(),
        reviewer: (v.reviewer || '').trim(), ignore_checks: !!v.ignore_checks, draft: !!v.draft, complete, partial: !complete });
    });
    sync();
    root.replaceChildren(box);
  },
};
