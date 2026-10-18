from typing import Annotated

from ..._output import run_command
from ..container._source import source


def command(agent: Annotated[str, "起動するエージェントのコマンド（引数は空白で区切る。既定は claude）"] = "",
            here: Annotated[bool, "新しい画面を開かず、この端末で動かして終わるまで待つ（終了コードはエージェントのもの）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のルートで、エージェントを新しい画面で起動します。

    起動したら待たずに戻ります。エージェントは開いた画面で動き続けます。
    作業空間をコンテナにしていれば、コンテナの中で確認なしに起動します（中はその作業空間だけ。使わせない道具・
    コマンドは ecobuild config set agent_deny で）。ログインは最初の1回だけ（すべてのコンテナで共有）。
    """
    if here:
        return _here(agent)

    def action(inv):
        options = {"source": source(), "progress": inv.info}
        return inv.module.start_agent(agent.split(), **options) if agent.strip() else inv.module.start_agent(**options)

    return run_command("agent start", action,
                       lambda r: f"エージェントを起動しました：{' '.join(r.command)}（{r.directory}）", json_output=json)


def _here(agent: str) -> int:
    """この端末で動かす。失敗は文で出す（画面を持つアプリの端末に、そのまま見える）。"""
    import click
    from ecobuild.errors import WorkError
    from ..._module import Module
    try:
        module = Module.find(".")
        options = {"source": source(), "progress": lambda message: click.echo(message, err=True)}
        return module.run_agent(agent.split(), **options) if agent.strip() else module.run_agent(**options)
    except WorkError as error:
        click.echo(f"エラー：{error.message}" + (f"\nヒント：{error.hint}" if error.hint else ""), err=True)
        return 1
