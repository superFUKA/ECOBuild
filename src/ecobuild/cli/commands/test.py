from typing import Annotated

from .._output import optional_argument, run_command


def command(
    *projects: Annotated[str, "対象のProject（--project と同じ）"],
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """テストします。"""

    project = optional_argument(projects, project, "--project", json)

    def action(inv):
        module = inv.module
        target = project or module.project_at(inv.cwd)
        options, name = module.build_options(configuration, profile or None)
        inv.info(f"テスト中：{target or '全体'}（{options.configuration}" + (f"、{name}" if name else "") + "）")
        return module.test(project=target, configuration=configuration, profile=profile or None)

    return run_command("test", action,
                       lambda r: f"テスト：成功 {r.passed}、失敗 {r.failed}、スキップ {r.skipped}",
                       json_output=json)
