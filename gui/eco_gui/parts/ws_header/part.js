// 部品「作業空間の窓の見出し」。今までの GUI（workspace.html の header）と同じ：ECOBuild / モジュールの名前、右に今いる場所。
export default {
  render(root, props, { h }) {
    const s = props.data || {};
    const parts = String(props.module || '').split(/[\\/]/).filter(Boolean);
    const at = parts.lastIndexOf('.ecobuild');  // タスクの作業空間（<モジュール>/.ecobuild/w/<名前>）は、モジュールの名前を出す
    const name = props.name || (at > 0 ? parts[at - 1] : parts.pop()) || '';
    const title = props.task && props.task.title ? '　' + props.task.title : '';
    const where = s.reviewing ? `#${s.reviewing_task || '?'} の提出を確認中`
      : s.task ? `タスクブランチ · ${s.branch}${title}`
        : 'branch' in s ? `ブランチ · ${s.branch || '（なし）'}` : '';
    root.replaceChildren(h('header', {}, h('strong', {}, 'ECOBuild'), h('span', { class: 'divider' }, '/'), h('h1', {}, name),
      h('span', { class: 'workspace', title: where }, where)));
  },
};
