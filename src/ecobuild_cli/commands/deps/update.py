from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *names: Annotated[str, "更新する依存先（--name と同じ）"],
    name: Annotated[str, "更新する依存先（既定：すべて）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先の記録をGitHubの最新にし、手元のcloneと生成ファイルも合わせます。作業空間でコミットし、PRで反映してください。"""
    name = optional_argument(names, name, "--name", json)
    return run_command("deps update", lambda inv: list(inv.module.update_dependencies(name or None)),
                       lambda r: "\n".join(f"{d.name}：{d.action}" + (f"（{d.reason}）" if d.reason else "") for d in r)
                       or "依存先はありません", json_output=json)
