from pathlib import Path
from typing import Annotated

from ecobuild.errors import EcoBuildError
from ecobuild_agent.errors import ErrorCode
from ecobuild_agent import app as _app
from ecobuild_agent import team as _team

from ...._output import run_command, to_data
from .. import _events
from . import _forward


def command(nested: Annotated[bool, "下の進行役のチームも入れる（その人の members に。入れ子のまま）"] = False,
            recent: Annotated[int, "1人ごとに、最新の出来事の人向けの行をこの数だけ入れる（recent。GUI の一覧・格子）"] = 0,
            orphans: Annotated[bool, "作業空間のない子タスク（作りかけで止まった等）も入れる（orphans。GitHub に聞く）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """進行役のチーム（作業役・進行役）と、その様子を表示します。

    この作業空間で作った作業役・進行役の、子タスク・タスクブランチ・報告があるか・モデルと、様子（作業中・待機中・
    止まっている、その長さ、届いていない言付け、コンテキストの使用率）、最後の返答の頭。
    止まった・同じところで長く作業中のままの作業役は、agent team restart で起動し直せます。
    submission（最後の返答の終わりに係が見た提出）・dirty・ahead・messages（送った言付けと届いたか）・replies・
    report_at は手元の記録から読みます（GitHub に聞きません）。
    """
    args = ["agent", "team", "list", *(["--nested"] if nested else []), *(["--recent", str(recent)] if recent > 0 else [])]

    def action(inv):
        root = inv.module.root
        _not_a_worker(root)
        try:
            data = _forward.run(inv, args, lambda inv: listed(root, nested=nested, recent=recent))
        except EcoBuildError as error:   # 係が止まっている：手元の記録（作業空間の中の記録）だけで出す
            if error.code != ErrorCode.AGENT_ERROR or not _team.should_forward():
                raise
            data = {**listed(root, nested=nested), "note": f"{error.message} 様子（作業中・待機中）は分かりません。"}
        if orphans:
            data["orphans"] = _team.orphans(inv.module)
        return data

    return run_command("agent team list", action, _render, json_output=json)


def _not_a_worker(root: Path) -> None:
    """作業役の作業空間で使ったら、そう伝える（作業役のチームはない。上の役の場所はこの中から見えない）。"""
    info = _team.member_info(root)
    if (info.get("role") or "") != _team.WORKER:
        return
    up = _team.ROLE_NAMES.get(info.get("lead_role"), _team.ROLE_NAMES[_team.MANAGER])
    where = "・".join(part for part in (f"「{info['lead_name']}」" if info.get("lead_name") else "",
                                        f"子タスク #{info['lead_task']}" if info.get("lead_task") else "",
                                        info.get("lead_branch") or "") if part)
    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                        f"あなたは作業役です（{up}{('：' + where) if where else ''}）。作業役のチームはありません。",
                        hint=f"任された仕事は {_team.BRIEF_FILE}。{up}の作業空間はこの中から見えません。"
                             f"伝えることは {_team.REPORT_FILE} に書き、ecobuild agent report で知らせます。")


def listed(root: Path, *, nested: bool = False, recent: int = 0, depth: int = 0, owner: str | None = None) -> dict:
    """進行役の作業空間 root のチーム（JSON にできる形）。nested：下の管理役の members も。recent：最新の行の数。"""
    data = to_data(_team.team(root, _team.owner_session() if owner is None else owner))
    for member in data["members"]:
        member.update(to_data(_team.member_details(Path(member["path"]))))   # 手元の記録：提出・未コミット・言付け 等
        if recent > 0:
            folder = _team.inbox_of(Path(member["path"]))
            member["recent"] = [text for text in map(_events.describe, _app.recent_events(folder)) if text][-recent:]
        if nested and member["role"] in _team.LEADING and depth < 8:   # 8段より深いものは、その進行役で list する
            member["members"] = listed(Path(member["path"]), nested=True, recent=recent, depth=depth + 1)["members"]
    return data


_PULL_STATES = {"open": "開いている", "merged": "取り込み済み", "closed": "閉じた"}


def _facts(m: dict) -> str:
    """最後の返答の終わりに係が見た事実の1行（提出・未コミット・push していないコミット）。"""
    parts = []
    if m.get("submission"):
        parts.append(f"提出 PR #{m['submission']['pull']}（{_PULL_STATES.get(m['submission'].get('state'), m['submission'].get('state'))}）")
    if m.get("dirty"):
        parts.append(f"未コミット {len(m['dirty'])}")
    if m.get("ahead"):
        parts.append(f"push していないコミット {m['ahead']}")
    text = ("最後の返答の時点：" + "・".join(parts)) if parts else ""
    if m.get("report_told"):
        text += ("  " if text else "") + "報告済み（agent report）"
    return text


def _render(r, indent: str = "") -> str:
    head = (f"{r['note']}\n" if r.get("note") else "") + "".join(
        f"作業空間のない子タスク #{o['task']}「{o['title']}」（agent team start <名前> --task {o['task']} で作れます）\n"
        for o in r.get("orphans") or ())
    if not r["members"]:
        return head + indent + "作業役はまだいません（ecobuild agent team start <名前> --brief … で作ります）。"
    return head + "\n".join(
        f"{indent}{_team.ROLE_NAMES.get(m['role'], '作業役')}「{m['name']}」 #{m['task']}  {m['branch'] or '（ブランチ不明）'}  "
        f"{'報告あり' if m['reported'] else '報告まだ'}{'  モデル ' + m['model'] if m['model'] else ''}\n{indent}    {_forward.place(m)}"
        + (f"\n{indent}    様子：{_team.describe_activity(m)}" if _team.describe_activity(m) else "")
        + (f"\n{indent}    {_facts(m)}" if _facts(m) else "")
        + (f"\n{indent}    最後の返答：{m['last_reply']}" if m.get("last_reply") else "")
        + "".join(f"\n{indent}    | {line.splitlines()[0] if line else ''}" for line in m.get("recent") or ())
        + (f"\n{_render(m, indent + '    ')}" if m.get("members") else "")
        for m in r["members"])
