// 部品「構成・ビルド設定」。今までの GUI（static/build.js の showSetting と、構成・ビルド設定のメニュー・実行の対象のピッカー・引数）を、
// 窓の中の欄として並べたもの。文言は同じ。選んだものを出すだけ。
const KIND = { static_library: 'ライブラリ', shared_library: '共有ライブラリ', library: 'ライブラリ', shared: '共有ライブラリ', interface: 'ヘッダーだけ',
  executable: '実行ファイル', app: '実行ファイル', test: 'テスト', bench: '性能測定', benchmark: '性能測定' };
const HELP = { Debug: '開発用：最適化なし・デバッグ情報あり', Release: '配布用：速さ優先で最適化', RelWithDebInfo: 'Release＋デバッグ情報', MinSizeRel: '小ささ優先で最適化' };

export default {
  render(root, props, { h, emit }) {
    const data = props.profiles || {}, profiles = data.profiles || {}, used = data.selected || '';
    const names = Object.keys(profiles), using = used && profiles[used];
    const chosen = props.configuration || '';
    const shown = chosen || (using && using.configuration) || 'Debug';
    const cpp = props.module_type === 'cpp';
    const configurations = ['Debug', 'Release', ...(cpp ? ['RelWithDebInfo', 'MinSizeRel'] : [])];
    const choice = (on, label, hint, pick) => {
      const b = h('button', { type: 'button', class: on ? 'choice on' : 'choice', role: 'radio', 'aria-checked': String(on), ...(hint ? { title: hint } : {}) },
        h('span', { class: 'check', 'aria-hidden': 'true' }, on ? '✓' : ''), h('span', {}, label));
      b.addEventListener('click', () => { if (!on) pick(); });
      return b;
    };
    const group = (label, ...kids) => h('div', { class: 'group' }, h('div', { class: 'label' }, label), h('div', { class: 'choices', role: 'radiogroup', 'aria-label': label }, ...kids));

    const box = h('section', { class: 'setting' });
    const edit = h('button', { type: 'button', class: 'link' }, 'ビルド設定を追加・編集（モジュールの「設定」）');
    edit.addEventListener('click', () => emit('settings', {}));
    box.append(h('div', { class: 'now' }, h('span', { class: 'now-text' }, shown + (used ? ' · ' + used : '')),
      h('span', { class: 'dim' }, used ? '構成・ビルド設定（' + used + '）' : '構成・ビルド設定'), props.loading ? h('span', { class: 'spinner' }) : '', edit));
    if (props.error) box.append(h('div', { class: 'banner bad', role: 'alert' }, h('span', {}, props.error)));

    // 構成：ビルド設定を使っていなければ、既定は Debug そのもの（「ビルド設定のまま」は出さない）
    const rows = [];
    if (using) rows.push(choice(!chosen, 'ビルド設定のまま（' + using.configuration + '）', 'ビルド設定の構成', () => emit('configuration', { value: '' })));
    for (const c of configurations) {
      const on = chosen === c || (!using && !chosen && c === 'Debug');
      rows.push(choice(on, c, HELP[c], () => emit('configuration', { value: !using && c === 'Debug' ? '' : c })));
    }
    if (chosen && !configurations.includes(chosen)) rows.push(choice(true, chosen, '', () => {}));
    box.append(group('構成', ...rows));

    const sets = names.map((name) => choice(used === name, name + '（' + (profiles[name].configuration || 'Debug') + (profiles[name].shared ? '・共有' : '') + '）', '',
      () => emit('profile', { name })));
    if (names.length) sets.push(choice(!used, '使わない', '構成は Debug', () => emit('profile', { name: 'none' })));
    box.append(group('ビルド設定（このPCで使う）', ...(sets.length ? sets : [h('span', { class: 'none' }, 'ありません（モジュールの「設定」で追加できます）')])));

    const fields = h('div', { class: 'fields' });
    if (cpp) {
      const select = h('select', {}, h('option', { value: '' }, 'すべてのProject'));
      for (const p of props.projects || []) {
        const option = h('option', { value: p.name }, p.name + '（' + (KIND[p.kind] || p.kind) + '）');
        if (p.name === (props.target || '')) option.selected = true;
        select.append(option);
      }
      select.addEventListener('change', () => emit('target', { project: select.value }));
      fields.append(h('label', {}, h('span', {}, '対象のProject（ビルド・実行・テスト）'), select));
    }
    const input = h('input', { type: 'text', value: props.arguments || '', placeholder: '例：--size 3', spellcheck: 'false' });
    input.addEventListener('change', () => emit('arguments', { text: input.value.trim() }));
    fields.append(h('label', { class: 'grow' }, h('span', {}, '実行時の引数（この窓を閉じるまで使います）'), input));
    box.append(fields);
    root.replaceChildren(box);
  },
};
