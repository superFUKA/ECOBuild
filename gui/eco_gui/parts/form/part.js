// 部品「入力の窓（フォーム）」。描く所は、共有のコード（lib.js の form）に1つ。欄を読んだ情報から組む部品も、同じものを使う。
export default {
  render(root, props, tools) {
    tools.lib.form.render(root, props, tools);
  },
};
