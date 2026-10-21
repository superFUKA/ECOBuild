from typing import Annotated

from ecobuild import workspaces as _workspaces
from ..._output import lines, run_command, usage_error


def command(
    *dir: Annotated[str, "新しい作業空間の場所（まだないフォルダ。省くと既定の場所：ecobuild workspace path）"],
    account: Annotated[str, "新しい作業空間で使う GitHub のアカウント（AI 用のアカウント等。ecobuild account use と同じ）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """今いるモジュールの新しい作業空間（clone）を作り、依存先と生成ファイルを用意します（並行作業用）。

    ブランチは作成元（ecobuild.toml の default_base）です。タスクはそこで ecobuild task start で開始します。
    """

    if len(dir) > 1:
        return usage_error("場所は1つだけ指定します。", json)

    def action(inv):
        target = inv.cwd / dir[0] if dir else inv.module.new_workspace_path()
        module, dependencies = inv.module.create_workspace(target, account=account or None)
        _workspaces.record_quietly(module.root)   # workspace list・GUI のタブに出るように
        inv.use_module(module)
        return module.cloned(dependencies)

    return run_command("workspace create", action, lambda r: lines(
        f"作業空間を作りました：{r.root}",
        "\n".join(f"  依存 {d.name}：{d.action}" for d in r.dependencies) or None,
        f"タスクはそこで開始します（cd {r.root} して ecobuild task start <番号>）",
    ), json_output=json)
