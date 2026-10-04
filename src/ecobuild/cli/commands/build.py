from typing import Annotated

from .._output import run_command


def command(
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体）"] = "",
    configuration: Annotated[str, "構成（Debug／Release）"] = "Debug",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルドします。"""

    def action(inv):
        module = inv.module
        target = project or module.project_at(inv.cwd)
        inv.info(f"ビルド中：{target or '全体'}（{configuration}）")
        return module.build(project=target, configuration=configuration)

    return run_command("build", action, lambda r: f"ビルドしました：{r.project or '全体'}（{r.configuration}）",
                       json_output=json)
