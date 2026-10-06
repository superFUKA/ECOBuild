from typing import Annotated

from ..._output import missing, run_command


def command(
    name: Annotated[str, "Project名（ディレクトリ名にもなる）"],
    kind: Annotated[str, "種類：library／app（実行ファイル）／test／bench（性能測定）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectを追加します。library以外は、モジュールのライブラリをリンクします。"""
    if not kind:
        return missing("--kind")
    return run_command("project add", lambda inv: inv.module.add_project(name, kind),
                       lambda r: f"Project {r.project} を追加しました：" + ", ".join(r.paths), json_output=json)
