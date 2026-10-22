from typing import Annotated

from ..._output import run_command


def command(id: Annotated[str, "止めるエージェントの ID（a- で始まる。agent status で見られます）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントを止めます（ID で指定します）。

    係が画面なしで動かしているもの（agent start --app）は、係が返答を終えさせてから止めます。人の画面で動いているもの
    は、そのプロセスを止めます。
    """
    def action(inv):
        from ecobuild.errors import EcoBuildError
        from ecobuild_agent import agents, children, status
        from ecobuild_agent.errors import ErrorCode
        record = agents.load(id)
        folder = record.folder
        mode = status.running_mode(folder)
        if mode == status.APP:
            return children.ask_serve(record, ["agent", "stop", record.id], inv.info) or {"id": record.id, "stopped": True}
        pid = status.running_pid(folder)
        if pid is None:
            raise EcoBuildError(ErrorCode.AGENT_ERROR, f"エージェント「{record.name}」（{record.id}）は動いていません。")
        status.stop(pid)
        return {"id": record.id, "path": record.workspace, "stopped": True}

    return run_command("agent stop", action, lambda r: f"エージェント {r.get('id')} を止めました。", json_output=json)
