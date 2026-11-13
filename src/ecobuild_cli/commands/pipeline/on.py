from typing import Annotated

from ecobuild.config import TIMINGS
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.workspaces import same, task_workspaces

from ..._output import run_command, split_list
from ._show import render


def command(
    timing: Annotated[str, f"タイミング（{'・'.join(TIMINGS)}）"],
    names: Annotated[str, "当てるパイプライン（カンマ区切り・この順に走る。外すなら none）"],
    local: Annotated[bool, "このPCだけで足す（ecobuild.local.toml。コミットしない。モジュールの当て方には上乗せするだけ）"] = False,
    everywhere: Annotated[bool, "--local の当て方を、ここだけでなく元の clone とすべての作業空間にも入れる（後から作る作業空間も元の clone から受け継ぐ）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タイミングに当てるパイプラインを決めます（今の当て方を置き換えます）。

    before-○○ はその操作の前に走らせ、失敗したら操作を止めます。after-○○ は後に走らせ、失敗は知らせるだけです。
    モジュールの当て方（既定）は ecobuild.toml を変えるので、タスクブランチでだけ変えられます。--local はどこでも。
    """
    chosen = () if names == "none" else tuple(split_list(names))

    def action(inv):
        module = inv.module
        if everywhere and not local:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--everywhere は --local と一緒に使います。",
                                hint="モジュールの当て方（ecobuild.toml）は、タスクブランチでコミットして共有します。")
        result = module.set_trigger(timing, chosen, local=local)
        if everywhere:
            original = module.workspace_root
            for place in (original, *(w.path for w in task_workspaces(original))):
                if same(place, module.root):
                    continue
                try:   # その場所のブランチにないパイプライン等：入れずに知らせる（ほかの場所は続ける）
                    type(module).find(place).set_trigger(timing, chosen, local=True)
                except EcoBuildError as error:
                    module.repository.notices.append(f"{place} には入れませんでした：{error.message}")
        return result

    return run_command("pipeline on", action, render, json_output=json)
