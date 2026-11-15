from typing import Annotated

from ecobuild_cli.kit import lines, run_command


def command(
    name: Annotated[str, "依存先の名前（ecobuild deps list の名前）"],
    library: Annotated[str, "そのライブラリへのリンクだけを外す（依存先の記録と clone は残す。既定：依存先ごと外す）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先のリンクを外します。手元のcloneは、記録の版のままなら消します（作業中・変更ありなら残します）。

    --library を付けると、そのライブラリへのリンクだけを外します（ほかのライブラリへのリンク・記録・clone は残ります）。

    タスクブランチで行い、変えた ECOBuild のファイル（.ecobuild の中）は、リンクを外したこととしてコミットします（Push はしません）。
    """
    def render(r):
        if r.libraries:
            return f"{r.name} の {r.libraries[0]} へのリンクを外しました（{', '.join(r.projects)}）。記録と deps/{r.name} は残しています"
        return lines(
            f"{r.name} のリンクを外しました" + (f"（{', '.join(r.projects)}）" if r.projects else ""),
            f"deps/{r.name} を消しました" if r.clone_removed else f"deps/{r.name} は残しました（作業中・変更あり）")

    return run_command("deps remove", lambda inv: inv.module.unlink(name, library or None), render, json_output=json)
