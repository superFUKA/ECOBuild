from typing import Annotated

from ecobuild_cli.kit import run_command

AGENT = "read"


def render(templates: dict) -> str:
    return "\n".join(f"{name}：{t['path']}" + ("（ECOBuildの既定）" if t["builtin"] else "")
                     for name, t in templates.items())


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ファイルテンプレートの一覧を表示します。"""
    return run_command("template list", lambda inv: inv.module.module_settings()["templates"], render,
                       json_output=json)
