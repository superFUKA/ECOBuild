from typing import Annotated

from ...._output import run_command
from ...container._source import source


def command(agent: Annotated[str, "起動するエージェントのコマンド（引数は空白で区切る。既定は claude。続きからは claude --resume <会話>）"] = "",
            here: Annotated[bool, "新しい画面を開かず、この端末で動かして終わるまで待つ（終了コードはエージェントのもの）"] = False,
            prompt: Annotated[str, "最初の発言（Claude Code のとき）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今いるモジュールの進行役を起動します（タスクは要りません）。

    進行役の作業空間（ECOBUILD_HOME/agents/modules/<所有者>/<名前>。作成元のブランチの clone）がなければ作り、あれば
    作成元の最新へ早送りして、コンテナの中で起動します（Docker が要ります）。進行役は人と話し、管理役を作って仕事を送ります。
    """
    if here:
        return _here(agent, prompt)

    def action(inv):
        place = _place(inv.module, inv.info)
        options = {"source": source(), "progress": inv.info, "prompt": prompt}
        return place.start_agent(agent.split(), **options) if agent.strip() else place.start_agent(**options)

    return run_command("agent module start", action,
                       lambda r: f"進行役を起動しました：{' '.join(r.command)}（{r.directory}）", json_output=json)


def _place(module, progress):
    from ecobuild_agent import module_lead as facilitator
    return facilitator.prepare(module, progress=progress)


def _here(agent: str, prompt: str) -> int:
    """この端末で動かす。失敗は文で出す（画面を持つアプリの端末に、そのまま見える）。"""
    import click
    from ecobuild.errors import WorkError
    from ...._module import Module
    try:
        progress = lambda message: click.echo(message, err=True)
        place = _place(Module.find("."), progress)
        options = {"source": source(), "progress": progress, "prompt": prompt}
        return place.run_agent(agent.split(), **options) if agent.strip() else place.run_agent(**options)
    except WorkError as error:
        click.echo(f"エラー：{error.message}" + (f"\nヒント：{error.hint}" if error.hint else ""), err=True)
        return 1
