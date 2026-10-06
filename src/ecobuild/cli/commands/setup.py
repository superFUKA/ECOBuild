from typing import Annotated

from ... import tooling
from .._output import Invocation, execute, lines


def command(
    name: Annotated[str, "gitに設定する名前（コミットの作者）"] = "",
    email: Annotated[str, "gitに設定するメール"] = "",
    install: Annotated[bool, "足りないツールを winget（Windows）／apt（Linux）で導入する"] = False,
    yes: Annotated[bool, "確認せずに実行する（--install のとき）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """前提ツールの準備：gitが gh の認証を使うようにし、gitの名前・メールを設定します。--install でツールも導入します。"""

    def action(inv):
        if install:
            inv.confirm("足りないツールを導入しますか？（管理者の権限が必要なことがあります）")
        return tooling.setup(name=name, email=email, install=install)

    def render(r):
        return lines(
            "\n".join(f"行いました：{d}" for d in r.done) or "直すものはありませんでした",
            "\n".join(f"まだ足りません：{i.name}（{i.hint}）" for i in r.remaining if i.required) or None,
            ("導入するには（または ecobuild setup --install）：\n" + "\n".join(f"  {c}" for c in r.commands))
            if r.commands else None,
        )

    return execute("setup", Invocation(json_output=json, yes=yes), action, render)
