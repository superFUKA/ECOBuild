// 部品「このモジュール」。今までの GUI のホームの横の欄（.mi-about）と同じに描く。
export default {
  render(root, props, { h, emit }) {
    const r = props.data;
    const title = h('h3', {}, 'このモジュール');
    if (props.error) {
      const again = h('button', { type: 'button', class: 'small' }, '読み直す');
      again.addEventListener('click', () => emit('reload', {}));
      return root.replaceChildren(title, h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error), again));
    }
    if (!r.name) return root.replaceChildren(title, h('p', { class: 'note', role: 'status' }, h('span', { class: 'spinner' }), ' 読み込んでいます…'));
    const list = h('dl', { class: 'about-list' });
    const item = (label, ...value) => list.append(h('div', {}, h('dt', {}, label), h('dd', {}, ...value)));
    const none = () => h('span', { class: 'sub' }, 'なし');
    const pills = (names, cls) => names.flatMap((name) => [h('span', { class: cls }, name), ' ']);

    if (r.repository || r.url) {
      const marks = [];
      if (r.private === true) marks.push(h('span', { class: 'pill' }, '非公開'), ' ');
      if (r.private === false) marks.push(h('span', { class: 'pill' }, '公開'), ' ');
      if (r.archived) marks.push(h('span', { class: 'pill warn' }, 'アーカイブ済み（読み取り専用）'));
      item('GitHub', r.url ? h('a', { href: r.url, target: '_blank', rel: 'noopener' }, r.repository || r.url) : r.repository, h('br', {}), ...marks);
    } else item('GitHub', h('span', { class: 'sub' }, '不明'));
    const type = [h('span', { class: 'pill' }, r.type || '')];
    if (r.format != null && r.latest_format != null && r.format < r.latest_format) {
      type.push(' ', h('span', { class: 'pill warn', title: '最新にするには：ecobuild module upgrade' }, '以前の仕様（版 ' + r.format + '）'));
    }
    item('型', ...type);
    item('タスクブランチの作成元', h('span', { class: 'mono' }, r.default_base || ''));
    const projects = r.projects || [];
    const dependencies = r.dependencies || [];
    if (r.type === 'cpp' || projects.length || dependencies.length) {  // Project のある型だけ
      item('Project', ...(projects.length ? pills(projects, 'pill') : [none()]));
      if (dependencies.length) {
        const graph = h('button', { type: 'button', class: 'link' }, '依存関係を見る');
        graph.addEventListener('click', () => emit('opened', { page: 'deps' }));
        item('依存先', ...pills(dependencies, 'pill ok'), h('br', {}), graph);
      } else item('依存先', none());
    }
    item('場所', h('span', { class: 'mono' }, r.root || ''));
    const out = [title, list];
    if (Array.isArray(r.workspaces) && r.workspaces.length === 0) {  // 作業空間がない：変えるにはタスクブランチが要る
      const go = h('button', { type: 'button', class: 'small' }, 'タスク管理を開く');
      go.addEventListener('click', () => emit('opened', { page: 'tasks' }));
      out.push(h('div', { class: 'banner info place' }, h('span', {}, '変更はタスクブランチで行います（今は見るだけ）。タスク管理で「作業を開始」すると、作業空間ができます。'), go));
    }
    root.replaceChildren(...out);
  },
};
