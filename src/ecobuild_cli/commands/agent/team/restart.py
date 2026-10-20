from typing import Annotated

from ecobuild_agent import status as _status
from ecobuild_agent import team as _team

from ...._output import lines, run_command, to_data
from ...container._source import source
from . import _forward


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            resume: Annotated[bool, "前の会話の続きから起動し直す（既定は新しい会話）"] = False,
            no_open: Annotated[bool, "止めて起動のしかたを返すだけで起動しない（係・GUI が起動するとき）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役のエージェントを止めて、起動し直します（進行役が使います）。

    作業空間・タスクブランチ・作業（コミット・未コミットの変更・報告）はそのままです。止まった・迷っている・同じところで
    長く作業中のままの作業役に使います。既定は新しい会話で、任された仕事・報告・git の状態からどこまで進んだかを
    確かめてから続けさせます。--resume は前の会話の続きから（コンテキストが大きいときは新しい会話のほうが確かです）。
    """
    def action(inv):
        return _forward.run(inv, ["agent", "team", "restart", name, *(["--resume"] if resume else [])],
                            lambda inv: _restart(inv))

    def _restart(inv):
        plan = _team.restart_plan(inv.module.root, name, resume=resume)
        if no_open:
            return plan
        pid = _status.running_pid(_team.inbox_of(plan.path))
        if pid is not None:
            inv.info(f"「{plan.name}」のエージェントを止めています…")
            _status.stop(pid)
        from ...._module import Module
        options = {"source": source(), "progress": inv.info, "role": plan.role, "prompt": plan.prompt}
        module = Module.find(plan.path)
        module.start_agent(plan.agent.split(), **options) if plan.agent else module.start_agent(**options)
        return to_data(_team.Member(**{**plan.__dict__, "opened": True}))

    return run_command("agent team restart", action, _render, json_output=json)


def _render(r) -> str:
    role = _team.ROLE_NAMES.get(r.get("role"), "作業役")
    return lines(
        f"{role}「{r.get('name')}」を起動し直しました（{'前の会話の続きから' if r.get('agent') else '新しい会話で'}）。",
        "新しい画面で起動しました" if r.get("opened") else None,
        "係が画面なしで起動しました" if r.get("app") else None,
        r.get("note") or None,
        f"作業空間 {_forward.place(r)} の作業はそのままです。返答が終わると知らせが届きます（係）。",
    )
