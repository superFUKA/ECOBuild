from typing import Annotated

import ecobuild_bundle
from ..._module import PROGRAM
from ..._output import Invocation, execute, lines, usage_error

WHAT = {"docker": "Docker（作業空間をコンテナで隔離するため。Windows では WSL2 の中に）",
        "tools": "足りないツール（CMake・コンパイラ・gh 等。winget／apt）"}


def command(
    name: Annotated[str, "入れるもの：docker・tools"],
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """最初に入れなかったものを、あとから入れます（docker・tools）。

    docker：Windows では WSL2 の有効化に管理者の承認と再起動が要ることがあります。再起動の後にもう一度実行すると
    続きから進みます。入っているものは ecobuild installer show で確かめられます。
    """
    if name not in WHAT:
        return usage_error(f"{name} は入れられません。入れられるもの：{'・'.join(WHAT)}", json)

    def action(inv):
        inv.confirm(f"{WHAT[name]} を導入しますか？（管理者の権限が必要なことがあります）")
        return ecobuild_bundle.setup(install=name == "tools", docker=name == "docker", progress=inv.info,
                                     command=PROGRAM)

    def render(r):
        return lines(
            "\n".join(f"行いました：{d}" for d in r.done) or "入れるものはありませんでした",
            "\n".join(f"まだ足りません：{i.name}（{i.hint}）" for i in r.remaining if i.required) or None,
            (f"Docker：使えます（{r.docker.detail}）" if r.docker.ready else
             f"Docker：まだ使えません（{r.docker.detail}）" + (f"\n{r.docker.restart}" if r.docker.restart else ""))
            if r.docker else None,
        )

    return execute("installer add", Invocation(json_output=json, yes=yes), action, render)
