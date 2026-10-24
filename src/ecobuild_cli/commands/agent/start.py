from typing import Annotated

from ..._output import run_command, usage_error
from ..container._source import source


def command(*task: Annotated[int, "タスクの番号（省けば今の作業空間のタスク。ほかのタスクなら、その作業空間で起動する）"],
            as_:Annotated[str, "起動するエージェントの登録の名前（agent registry list。人が起動できる登録だけ）"] = "",
            here: Annotated[bool, "新しい画面を開かず、この端末で動かして終わるまで待つ（終了コードはエージェントのもの）"] = False,
            app: Annotated[bool, "画面なし（アプリ用の起動）で、ECOBuild の係に動かしてもらう（コンテナの作業空間で。様子は agent status・agent log、止めるのは agent stop）"] = False,
            program: Annotated[str, "起動するコマンド（引数は空白で区切る。既定は claude。claude --resume <会話> なら、その会話のエージェントを続きから）"] = "",
            prompt: Annotated[str, "最初の発言（Claude Code のとき。既定は登録の最初の発言）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """タスクの作業空間のルートで、登録したエージェントを新しい画面で起動します。

    起動したら待たずに戻ります。エージェントは開いた画面で動き続けます。起動のたびに新しいエージェント（ID）になり、
    同じ作業空間に何人でも起動できます（--program "claude --resume <会話>" なら、その会話のエージェントを続きから）。
    エージェントはコンテナの中で確認なしに動きます（中はその作業空間だけ。使わせない道具・コマンドは
    ecobuild config set agent_deny で）。ログインは最初の1回だけ（すべてのコンテナで共有）。
    --app：画面を開かず、このPCの係（ecobuild agent serve。GUI が起動する）が Claude Code を画面なしで動かします。
    """
    if len(task) > 1:
        return usage_error("タスクの番号は1つだけ書けます。", json)
    options = {"task": task[0] if task else None, "program": program or None, "prompt": prompt or None}
    if here:
        return _here(as_, options)

    def action(inv):
        _human_start(as_, program, inv.module.root)
        return inv.module.start_agent(as_, app=app, source=source(), progress=inv.info, **options)

    return run_command("agent start", action, _render, json_output=json)


def _render(record) -> str:
    where = f"タスク #{record.task.get('number')}・" if record.task else ""
    return f"エージェント「{record.name}」（{record.id}）を起動しました（{where}{record.workspace}）。"


def _human_start(name: str, program: str, root) -> None:
    """人が起動できる登録か（人の道だけで確かめる）。続きからの起動（登録を省いたもの）は、その会話の記録の登録。"""
    from ecobuild.errors import EcoBuildError
    from ecobuild_agent import registry
    from ecobuild_agent.errors import ErrorCode
    if not name:
        from ecobuild_agent import agents, resumed_session
        session = resumed_session(tuple(program.split()), lambda: "")
        if session and agents.by_session(session) is not None:   # 記録のある会話の続き：その記録の登録で起動する
            return
        if session is not None:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                "続きから起動する会話にエージェントの記録がない（または会話を Claude Code の一覧で選ぶ）ので、"
                                "登録を --as で指定してください。", hint=_startable_hint(root))
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "起動するエージェントの登録を --as で指定してください。",
                            hint=_startable_hint(root))
    if not registry.effective(name, root).human_start:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"登録「{name}」は、人が起動するものではありません。",
                            hint=_startable_hint(root))


def _startable_hint(root) -> str:
    """人が起動できる登録（作成元に取り込まれたもの：起動するのはこちら）。"""
    from ecobuild_agent import registry
    names = [r.name for r in registry.list_registrations(root, in_force=True) if r.human_start]
    return ("人が起動できる登録：" + "・".join(names)) if names else "人が起動できる登録がありません（agent registry set <名前> --human-start）。"


def _here(name: str, options: dict) -> int:
    """この端末で動かす。失敗は文で出す（画面を持つアプリの端末に、そのまま見える）。"""
    import click
    from ecobuild.errors import WorkError
    from ..._module import Module
    try:
        module = Module.find(".")
        _human_start(name, options["program"] or "", module.root)
        return module.run_agent(name, source=source(), progress=lambda message: click.echo(message, err=True), **options)
    except WorkError as error:
        click.echo(f"エラー：{error.message}" + (f"\nヒント：{error.hint}" if error.hint else ""), err=True)
        return 1
