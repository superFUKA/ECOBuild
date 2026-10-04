from typing import Annotated

from .._output import run_command


def command(
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体）"] = "",
    configuration: Annotated[str, "構成（Debug／Release）"] = "Debug",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """テストします。"""

    def action(inv):
        module = inv.module
        target = project or module.project_at(inv.cwd)
        inv.info(f"テスト中：{target or '全体'}（{configuration}）")
        return module.test(project=target, configuration=configuration)

    return run_command("test", action,
                       lambda r: f"テスト：成功 {r.passed}、失敗 {r.failed}、スキップ {r.skipped}",
                       json_output=json)
