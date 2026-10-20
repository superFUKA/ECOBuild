from typing import Annotated

from ..._output import lines, run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """CIの設定（ecobuild.toml の [ci]）と、ワークフローの状態を表示します。"""

    def render(r):
        if not r.supported:
            return "このモジュールの型は CI のワークフローを用意できません"
        state = ("ありません（ecobuild ci init で作ります）" if not r.exists else "手で編集されています" if r.edited
                 else "今の設定のとおりです" if r.current else "今の設定と違います（ecobuild ci init で作り直します）")
        return lines(
            f"ワークフロー：{r.path}",
            f"状態：{state}",
            f"OS：{', '.join(r.os) if r.os else '型の既定'}",
            f"構成：{', '.join(r.configurations)}",
            f"共有ライブラリの構成：{'あり' if r.shared else 'なし'}",
            f"pushで動かすブランチ：{', '.join(r.branches) if r.branches else f'{r.default_base}（default_base）'}",
        )

    return run_command("ci show", lambda inv: inv.module.ci_state(), render, json_output=json)
