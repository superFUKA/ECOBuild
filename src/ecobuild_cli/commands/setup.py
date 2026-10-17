from typing import Annotated

import ecobuild_bundle
from .._module import PROGRAM
from .._output import Invocation, execute, lines


def command(
    name: Annotated[str, "gitに設定する名前（コミットの作者）"] = "",
    email: Annotated[str, "gitに設定するメール"] = "",
    install: Annotated[bool, "足りないツールを winget（Windows）／apt（Linux）で導入する"] = False,
    docker: Annotated[bool, "Docker を導入する（作業空間をコンテナで隔離するため。Windows では WSL2 の中に）"] = False,
    yes: Annotated[bool, "確認せずに実行する（--install・--docker のとき）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """前提ツールの準備：gitが gh の認証を使うようにし、gitの名前・メールを設定します。

    --install でツールも導入します。--docker で Docker も導入します（Windows では WSL2 の有効化に管理者の承認と
    再起動が要ることがあります。再起動の後にもう一度実行すると続きから進みます）。
    """

    def action(inv):
        if install:
            inv.confirm("足りないツールを導入しますか？（管理者の権限が必要なことがあります）")
        if docker:
            inv.confirm("Docker を導入しますか？（Windows では WSL2 の中に。管理者の承認と再起動が要ることがあります）")
        return ecobuild_bundle.setup(name=name, email=email, install=install, docker=docker, progress=inv.info,
                                     command=PROGRAM)

    def render(r):
        return lines(
            "\n".join(f"行いました：{d}" for d in r.done) or "直すものはありませんでした",
            "\n".join(f"まだ足りません：{i.name}（{i.hint}）" for i in r.remaining if i.required) or None,
            ("導入するには（または ecobuild setup --install）：\n" + "\n".join(f"  {c}" for c in r.commands))
            if r.commands else None,
            (f"Docker：使えます（{r.docker.detail}）" if r.docker.ready else
             f"Docker：まだ使えません（{r.docker.detail}）" + (f"\n{r.docker.restart}" if r.docker.restart else ""))
            if r.docker else None,
        )

    return execute("setup", Invocation(json_output=json, yes=yes), action, render)
