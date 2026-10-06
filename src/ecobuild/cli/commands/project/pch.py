from typing import Annotated

from ..._output import run_command


def command(
    project: Annotated[str, "対象のProject（既定：今いるProject）"] = "",
    off: Annotated[bool, "PCHを使わないようにする"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """プリコンパイル済みヘッダー（include/<Project>/pch.h）を使うようにします。"""

    def action(inv):
        module = inv.module
        target = project or module.project_at(inv.cwd)
        if target is None:
            from ....errors import EcoBuildError, ErrorCode
            raise EcoBuildError(ErrorCode.NOT_IN_PROJECT, "対象のProjectが決まりません。",
                                hint="Projectのディレクトリの中で実行するか、--project を指定してください。")
        return module.set_pch(target, enable=not off)

    return run_command("project pch", action,
                       lambda r: f"{r.project}：PCHを外しました" if r.action == "pch off"
                       else f"{r.project}：PCH {r.paths[0]} を使います", json_output=json)
