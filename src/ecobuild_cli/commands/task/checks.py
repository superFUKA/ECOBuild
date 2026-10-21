from typing import Annotated

from ecobuild import config

from ..._output import lines, run_command, split_list

_NAMES = {"generated": "生成ファイル", "conflict_markers": "衝突の印", "build": "ビルド", "test": "テスト"}


def command(
    set: Annotated[str, "行う確認（カンマ区切り：generated・conflict_markers・build・test。何もしないなら none）"] = "",
    tests: Annotated[str, "test で流す試験（カンマ区切り。型が絞れるとき。none で全部に戻す）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出（task submit）の前に行う確認を、表示・設定します。

    既定は何もしません（確かめずに提出します）。--set で、生成ファイル（generated）・衝突の印（conflict_markers）・
    ビルド（build）・テスト（test）から選びます。--tests でテストを絞れます（例：tests/unit,gui/tests）。
    設定は ecobuild.toml の [check] に残るので、変えるのはタスクブランチでだけです（コミットして提出すると共有されます）。
    手で全部を確かめるのは ecobuild check、提出のときに確かめないのは task submit --no-check です。
    """

    def action(inv):
        module = inv.module
        if not set and not tests:
            return module.config.submit_checks
        current = module.config.submit_checks
        items = current.items if not set else () if set == "none" else split_list(set)
        chosen = current.tests if not tests else () if tests == "none" else split_list(tests)
        return module.set_submit_checks(config.SubmitChecks(items=tuple(items), tests=tuple(chosen) if "test" in items else ()))

    def render(r):
        if not r.items:
            return "提出の確認：なし（確かめずに提出します。ecobuild task checks --set build,test 等で設定）"
        return lines(f"提出の確認：{'・'.join(_NAMES.get(name, name) for name in r.items)}",
                     f"流す試験：{', '.join(r.tests)}" if r.tests else "")

    return run_command("task checks", action, render, json_output=json)
