from typing import Annotated

from ..._output import run_command
from ..container._source import source


def command(agent: Annotated[str, "起動するエージェントのコマンド（引数は空白で区切る。既定は claude）"] = "",
            here: Annotated[bool, "新しい画面を開かず、この端末で動かして終わるまで待つ（終了コードはエージェントのもの）"] = False,
            app: Annotated[bool, "画面なし（アプリ用の起動）で、ECOBuild の係に動かしてもらう（コンテナの作業空間で。様子は agent status・agent log、止めるのは agent stop）"] = False,
            role: Annotated[str, "役：lead（進行役。ユーザーと話し、下の管理役に命令する。自分では編集しない）・manager（管理役）か worker（作業役）。既定は作業空間の記録（member.json）、なければ lead（進行役）"] = "",
            prompt: Annotated[str, "最初の発言（Claude Code のとき）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のルートで、エージェントを新しい画面で起動します。

    起動したら待たずに戻ります。エージェントは開いた画面で動き続けます。
    作業空間をコンテナにしていれば、コンテナの中で確認なしに起動します（中はその作業空間だけ。使わせない道具・
    コマンドは ecobuild config set agent_deny で）。ログインは最初の1回だけ（すべてのコンテナで共有）。
    --app：画面を開かず、このPCの係（ecobuild agent serve。GUI が起動する）が Claude Code を画面なしで動かします
    （進行役が作る作業役と同じ）。言付けは agent team send・受け箱で届きます。
    """
    if here:
        return _here(agent, role, prompt)
    if app:
        return _app(role, prompt, json)

    def action(inv):
        options = {"source": source(), "progress": inv.info, "role": role, "prompt": prompt}
        return inv.module.start_agent(agent.split(), **options) if agent.strip() else inv.module.start_agent(**options)

    return run_command("agent start", action,
                       lambda r: f"エージェントを起動しました：{' '.join(r.command)}（{r.directory}）", json_output=json)


def _app(role: str, prompt: str, json: bool) -> int:
    """係にアプリ用で起動してもらう（係が持つ。起動したら戻る）。"""
    from .team import _forward
    args = ["agent", "start", "--app", *(["--role", role] if role else []), *(["--prompt", prompt] if prompt else [])]
    return run_command("agent start", lambda inv: _forward.serve(inv, args),
                       lambda r: f"係がエージェントを画面なしで起動しました（{r.get('path')}・会話 {r.get('session')}）。"
                                 "様子は ecobuild agent status・agent log で見られます。", json_output=json)


def _here(agent: str, role: str, prompt: str) -> int:
    """この端末で動かす。失敗は文で出す（画面を持つアプリの端末に、そのまま見える）。"""
    import click
    from ecobuild.errors import WorkError
    from ..._module import Module
    try:
        module = Module.find(".")
        options = {"source": source(), "progress": lambda message: click.echo(message, err=True), "role": role, "prompt": prompt}
        return module.run_agent(agent.split(), **options) if agent.strip() else module.run_agent(**options)
    except WorkError as error:
        click.echo(f"エラー：{error.message}" + (f"\nヒント：{error.hint}" if error.hint else ""), err=True)
        return 1
