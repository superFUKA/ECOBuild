from typing import Annotated

from ..._output import lines, run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今いるモジュールの情報（型・場所・GitHubのリポジトリ・Project・依存先）を表示します。"""

    def render(r):
        notes = [label for label, on in (("非公開", r.private is True), ("公開", r.private is False),
                                         ("アーカイブ済み", r.archived)) if on]
        repository = (f"リポジトリ：{r.url}" + (f"（{'・'.join(notes)}）" if notes else "")) if r.url else None
        return lines(
            f"モジュール {r.name}（型 {r.type}）",
            f"場所：{r.root}",
            repository,
            f"作業空間の作成元：{r.default_base}",
            f"Project：{', '.join(r.projects)}" if r.projects else None,
            f"依存先：{', '.join(r.dependencies)}（依存先の依存先は ecobuild deps tree）" if r.dependencies
            else "依存先：なし",
        )

    return run_command("module show", lambda inv: inv.module.info(), render, json_output=json)
