from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode, WorkError
from ecobuild_agent import team as _team

from ...._output import lines, run_command, to_data
from ...task.finish import render_finish
from .close import _render as render_close
from .close import close_one


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            wait: Annotated[bool, "CIの結果を待つ（待たない場合、実行中なら止まります）"] = True,
            ignore_checks: Annotated[bool, "CIが失敗していても取り込む（待たない）"] = False,
            timeout: Annotated[int, "CIを待つ時間の上限（秒）"] = 1800,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役の提出を取り込み、作業役を閉じます（finish・sync・close を一度に）。

    先に agent team close と同じことを確かめ（作業中・届いていない言付け・提出の後のコミット・GitHub にないもの）、
    閉じられないときは何もしません。それから子タスクを task finish で取り込み、sync で手元を最新にし、作業空間を閉じます。
    途中で止まったら、どこまで済んだかを失敗の文に書きます（もう一度 accept すると、取り込み済みの子タスクは飛ばします）。
    差分は先に task diff <番号> で確かめてください。
    """

    def action(inv):
        member = _team.find(inv.module.root, name, _team.owner_session())
        check = close_one(inv, name, dry_run=True)
        if check.get("problems"):
            raise EcoBuildError(ErrorCode.UNFINISHED_WORK, f"「{member.name}」はまだ取り込めません（閉じられないため）。",
                                hint="様子を確かめて（agent team list）、取り込むだけなら task finish、閉じるのは後で close。",
                                details=check["problems"])
        done = []
        try:
            inv.info(f"#{member.task}（{member.name}）を取り込みます…")
            finished = to_data(inv.module.finish(member.task, wait=wait, ignore_checks=ignore_checks, timeout=timeout))
            done.append("task finish")
            inv.info("手元を最新にします…")
            synced = to_data(inv.module.sync())
            done.append("sync")
            closed = close_one(inv, name)
        except WorkError as error:
            step = "agent team close" if len(done) == 2 else "sync" if done else "task finish"
            details = error.details if isinstance(error.details, (list, tuple)) else [error.details] if error.details else []
            raise EcoBuildError(error.code, f"「{member.name}」の取り込みが {step} で止まりました：{error.message}",
                                hint=error.hint, details=[*(f"済み：{d}" for d in done), *details]) from error
        return {"name": member.name, "task": member.task, "finish": finished, "sync": synced, "closed": closed}

    return run_command("agent team accept", action, _render, json_output=json)


def _render(r) -> str:
    return lines(render_finish(_Data(r["finish"])), _sync_line(r["sync"]), render_close(r["closed"]))


def _sync_line(sync: dict) -> str:
    merged = sync.get("merged") or []
    return f"{sync.get('branch')}：" + ("、".join(merged) + " を取り込みました" if merged else "最新です")


class _Data:
    """dict を属性で読む（render_finish に渡す形。入れ子の dict も）。"""
    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, _Data(value) if isinstance(value, dict) else
                    [_Data(v) if isinstance(v, dict) else v for v in value] if isinstance(value, list) else value)
