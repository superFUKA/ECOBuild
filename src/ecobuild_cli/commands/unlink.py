from typing import Annotated

from .._output import lines, run_command


def command(
    name: Annotated[str, "依存先の名前（ecobuild deps list の名前）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先のリンクを外します。手元のcloneは、記録の版のままなら消します（作業中・変更ありなら残します）。"""
    return run_command("unlink", lambda inv: inv.module.unlink(name), lambda r: lines(
        f"{r.name} のリンクを外しました" + (f"（{', '.join(r.projects)}）" if r.projects else ""),
        f"deps/{r.name} を消しました" if r.clone_removed else f"deps/{r.name} は残しました（作業中・変更あり）",
    ), json_output=json)
