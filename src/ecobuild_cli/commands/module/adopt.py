from typing import Annotated

from ecobuild_cli._module import Module
from ..._output import lines, run_command


def command(
    type: Annotated[str, "モジュールの型（ecobuild module types で一覧。既定は cpp）"] = "",
    dry_run: Annotated[bool, "置くファイルを表示するだけ（何も変えない）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """既にある GitHub のリポジトリ（今いる clone）を、ECOBuild のモジュールにします。

    今のブランチに .ecobuild/（ecobuild.toml 等）と型が要るものを置き、.gitignore・.gitattributes には足りない行を足して、
    「ECOBuild のモジュールにする」としてコミットし、GitHub へ push します。今のブランチがタスクブランチの作成元になります。
    名前は GitHub のリポジトリ名です。README・AGENTS.md 等、元からあるファイルは変えません。
    未コミットの変更があるとき・GitHub に遅れているときは止まります。新しく作るなら ecobuild module new。
    """

    def action(inv):
        module, result = Module.adopt(inv.cwd, type=type or None, dry_run=dry_run, progress=inv.info)
        if not dry_run:
            inv.use_module(module)
        return result

    def render(r):
        changed = "\n".join(f"  {p}" for p in r.paths)
        if r.dry_run:
            return lines(f"{r.root} の {r.branch} を、型 {r.type} のモジュール {r.name} にします。置くファイル：\n{changed}",
                         "型が置くもの（C++ の Solution 等）は、実行したときに分かります")
        return lines(
            f"{r.root} を、型 {r.type} のモジュール {r.name} にしました。置いたファイル：\n{changed}",
            f"「ECOBuild のモジュールにする」として {r.branch} にコミットしました（{r.commit[:8]}）"
            + ("。GitHub へ push しました" if r.pushed else ""),
            f"タスクブランチは {r.branch} から作ります。作業を始めるなら ecobuild task new と task start",
        )

    return run_command("module adopt", action, render, json_output=json)
