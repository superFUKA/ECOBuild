from typing import Annotated

from ecobuild_cli.kit import optional_argument, run_command


def command(
    *names: Annotated[str, "更新する依存先（--name と同じ）"],
    name: Annotated[str, "更新する依存先（既定：すべて）"] = "",
    at: Annotated[str, "最新ではなく、この版（ブランチ・タグ・コミット）にする（依存先を1つ指定。候補は deps versions）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先の記録をGitHubの最新（--at で選んだ版）にし、手元のcloneと生成ファイルも合わせます。

    タスクブランチで行い、変えた ECOBuild のファイル（.ecobuild の中）は「依存先を最新に」としてコミットします（Push はしません）。PRで反映してください。
    """
    name = optional_argument(names, name, "--name", json)
    return run_command("deps update", lambda inv: list(inv.module.update_dependencies(name or None, at or None)),
                       lambda r: "\n".join(f"{d.name}：{d.action}" + (f"（{d.reason}）" if d.reason else "") for d in r)
                       or "依存先はありません", json_output=json)
