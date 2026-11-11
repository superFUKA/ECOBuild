// 部品「タスク管理の概要」。数は届いたまま（数えるのは ecobuild）。タイル・バーの幅と色は見せ方だけ。押すと、その表示へ（go）。
export default {
  render(root, props, { h, lib, emit, menu }) {
    const { STAGES } = lib.task;
    const marks = lib.task.marks(h, emit, menu, props.sprints, props.me);
    const { md, open, deleted } = marks;
    if (props.error) return root.replaceChildren(marks.failed(props.error));
    if (props.loading && props.tasks.length === 0) return root.replaceChildren(marks.loading('集計しています…'));
    const go = (screen, filter) => () => emit('go', { screen, filter: filter || {} });
    const opened = props.tasks.filter(open), count = (stage) => opened.filter((t) => marks.stageOf(t) === stage).length;
    const late = props.overdue.overdue || [], soon = props.overdue.soon || [];
    const clock = new Date(Date.now() - 7 * 86400000);
    const weekAgo = new Date(clock.getTime() - clock.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const finished = props.tasks.filter((t) => !open(t) && !deleted(t) && t.finished).sort((a, b) => String(b.finished).localeCompare(String(a.finished)));
    const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
    const width = (node, value) => { node.setAttribute('style', 'width:' + value + '%'); return node; };
    const none = (text) => h('p', { class: 'tk-muted' }, text);
    const card = (title, body, options) => {
      const o = options || {};
      const head = h('div', { class: 'tk-section-head' }, h('h3', {}, title, ...(o.sub ? [h('span', { class: 'tk-muted' }, o.sub)] : [])));
      if (o.go) { const link = h('button', { type: 'button', class: 'tk-link' }, '開く ›'); link.addEventListener('click', go(o.go)); head.append(link); }
      return h('section', { class: 'tk-card dash-card' }, head, ...body);
    };
    // 表示を開くタイルは、押せる形（›）。ほかは平ら
    const big = (label, value, cls, screen) => {
      const inner = [h('b', {}, String(value)), h('span', {}, label)];
      if (!screen) return h('div', { class: 'stat ' + cls }, ...inner);
      const tile = h('button', { type: 'button', class: 'stat go ' + cls }, ...inner);
      tile.addEventListener('click', go(screen));
      return tile;
    };
    const row = (t, ...extra) => {
      const line = h('div', { class: 'tk-next-row', tabindex: '0' }, marks.num(t), h('span', { class: 'tk-grow' }, t.title), ...extra, marks.prio(t), marks.due(t), marks.est(t), ...marks.avatars(t));
      line.setAttribute('aria-selected', String(String(t.number) === String(props.selected || '')));
      return marks.pick(line, t);
    };

    // 段階：開いているタスクを、1本のバーで
    const bar = h('div', { class: 'stagebar' });
    for (const [key, label, cls] of STAGES.slice(0, 4)) {
      if (!count(key)) continue;
      const seg = h('button', { type: 'button', class: 'seg ' + cls, title: label + ' ' + count(key) });
      seg.setAttribute('style', 'flex:' + count(key));
      seg.setAttribute('aria-label', label + ' ' + count(key));
      seg.addEventListener('click', go('board'));
      bar.append(seg);
    }
    const keys = h('div', { class: 'tk-stagekeys' }, ...STAGES.slice(0, 4).map(([key, label]) => marks.stageMark(key, label + ' ' + count(key))));

    const s = props.sprint;
    const sprintBody = !s ? [none(props.sprints.length ? '今日を含むスプリントはありません。' : 'スプリントはまだありません。')] : [
      h('div', { class: 'dash-sprint' }, h('div', {}, h('b', {}, s.done + ' / ' + s.total), h('span', {}, '完了')), h('div', {}, h('b', {}, String(s.estimate_remaining)), h('span', {}, '見積もりの残り')),
        h('div', {}, h('b', {}, String(s.days_left)), h('span', {}, '残り日数'))),
      h('div', { class: 'tk-progress', title: '完了 ' + pct(s.done, s.total) + '%' }, width(h('span', {}), pct(s.estimate_done, s.estimate_total) || pct(s.done, s.total))),
      ...((s.unestimated || []).length ? [h('p', { class: 'tk-note' }, '見積もりのないタスク ' + s.unestimated.length + ' 件')] : []),
      ...((s.carried_over || []).length ? [h('p', { class: 'tk-note' }, '持ち越し ' + s.carried_over.length + ' 件')] : [])];

    const ms = props.milestones.map((m) => {
      const line = h('button', { type: 'button', class: 'dash-row' },
        h('span', { class: 'tk-grow' }, m.title, ...(m.due ? [h('small', { class: m.late ? 'tk-due overdue' : 'tk-muted' }, ' ' + md(m.due) + (m.late ? ' 期日超過' : ''))] : [])),
        h('span', { class: 'minibar' }, width(h('span', {}), pct(m.done, m.total))), h('span', { class: 'tk-muted' }, m.done + '/' + m.total),
        ...((m.overdue_tasks || []).length ? [h('span', { class: 'tk-reason' }, '期限切れ ' + m.overdue_tasks.length)] : []));
      line.addEventListener('click', go('tasks', { milestone: m.title }));
      return line;
    });
    const people = props.workload.filter((w) => w.open), most = Math.max(1, ...people.map((w) => w.open));
    const wl = people.map((w) => {
      const line = h('button', { type: 'button', class: 'dash-row' }, marks.avatarMark(w.assignee),
        h('span', { class: 'dash-name' }, (w.assignee || '担当なし') + (w.assignee && w.assignee === props.me ? '（自分）' : '')),
        h('span', { class: 'minibar' }, width(h('span', {}), pct(w.open, most)), width(h('span', { class: 'doing' }), pct(w.in_progress, most))),
        h('span', { class: 'tk-muted' }, w.open + ' 件・作業中 ' + w.in_progress + (w.estimate_remaining ? '・残り ' + w.estimate_remaining : '')),
        ...(w.overdue ? [h('span', { class: 'tk-reason' }, '期限切れ ' + w.overdue)] : []));
      line.addEventListener('click', w.assignee ? () => emit('dialog', { screen: 'task-person', id: '0', text: w.assignee }) : go('tasks', { assignee: '-' }));
      return line;
    });
    const prRow = (t) => {
      const line = h('div', { class: 'tk-next-row', tabindex: '0' }, marks.num(t), h('span', { class: 'tk-grow' }, t.title), marks.submissionPill(t.submission || {}), ...marks.avatars(t));
      return marks.pick(line, t);
    };
    const asked = props.reviews, openPrs = props.tasks.filter((t) => open(t) && t.submission);
    const h4 = (text) => h('h4', { class: 'dash-h' }, text);

    root.replaceChildren(h('div', { class: 'dash' },
      h('div', { class: 'stats wide' }, big('開いているタスク', opened.length, '', 'tasks'), big('作業中', count('in_progress'), '', 'board'), big('レビュー待ち', count('in_review'), '', 'board'),
        big('期限切れ', late.length, late.length ? 'bad' : '', 'task-next'), big('この1週間に完了', finished.filter((t) => t.finished >= weekAgo).length, ''),
        big('レビューの依頼', asked.length, asked.length ? 'warn' : '')),
      card('段階', [bar, keys], { go: 'board', sub: '開いている ' + opened.length + ' 件' }),
      card(s ? '今のスプリント：' + s.sprint.name : '今のスプリント', sprintBody, { go: 'task-sprint', sub: s ? md(s.sprint.start) + '〜' + md(s.sprint.end) : '' }),
      card('自分の次のタスク', props.next.length ? props.next.map((x, i) => row(x.task, h('span', { class: 'tk-rank' }, String(i + 1)), ...(x.reasons || []).slice(0, 2).map((r) => h('span', { class: 'tk-reason' }, r))))
        : [none('自分が担当していて、着手できるタスクはありません。')], { go: 'task-next' }),
      card('期限', late.length || soon.length ? [...late.map((t) => row(t, h('span', { class: 'tk-reason bad' }, '期限切れ'))), ...soon.map((t) => row(t, h('span', { class: 'tk-reason' }, '7日以内')))]
        : [none('期限切れ・期限が近いタスクはありません。')], { go: 'task-next' }),
      card('マイルストーン', ms.length ? ms : [none('開いているマイルストーンはありません。')]),
      card('担当者ごとの量', wl.length ? wl : [none('開いているタスクはありません。')], { sub: '親タスクは数えません' }),
      card('提出', [...(asked.length ? [h4('見るように頼まれた提出'), ...asked.map(prRow)] : []),
        ...(openPrs.length ? [h4('提出中 ' + openPrs.length), ...openPrs.slice(0, 6).map(prRow)] : [none('提出中のタスクはありません。')])]),
      card('最近完了したタスク', finished.length ? finished.slice(0, 6).map((t) => row(t, h('span', { class: 'tk-muted' }, md(t.finished)))) : [none('まだありません。')])));
  },
};
