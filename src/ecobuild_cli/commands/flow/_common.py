"""流れのコマンドの共通（Flows の作り方と表示）。"""

import datetime

from ecoflow import NAMES

from ..._output import lines

_NEXT = {
    "waiting": "ecobuild flow approve {id} -m \"<文>\"（通す）か ecobuild flow reject {id} --to <工程> -m \"<理由>\"（差し戻す）",
    "failed": "ecobuild flow retry {id}（失敗した工程からやり直す）か ecobuild flow cancel {id}",
    "interrupted": "ecobuild flow resume {id}（中断した工程から続ける）か ecobuild flow cancel {id}",
}


def program() -> tuple[str, ...]:
    """ecobuild の工程で呼ぶ ecobuild（このコマンドを動かしているもの）。"""
    from ..._module import program_path
    return (program_path(),)


def flows(inv):
    return inv.module.flows(program=program(), progress=inv.info)


def when(seconds) -> str:
    if not isinstance(seconds, (int, float)):
        return ""
    return datetime.datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M")


def step_line(step: dict, current: str | None) -> str:
    counts = [f"{step['attempts']} 回"] if step.get("attempts", 0) > 1 else []
    counts += [f"戻り {step['backs']}"] if step.get("backs") else []
    counts += [f"繰り返し {step['loops']}"] if step.get("loops") else []
    mark = "→ " if step["id"] == current and step["status"] not in ("done", "skipped") else "  "
    message = " ".join(str(step.get("message") or "").split())
    message = message if len(message) <= 120 else message[:120] + "…"
    return (f"  {mark}{step['id']}（{step['type']}）：{NAMES.get(step['status'], step['status'])}"
            + (f"・{'・'.join(counts)}" if counts else "") + (f"：{message}" if message else ""))


def render_run(r: dict) -> str:
    status = r["status"]
    head = f"実行 {r['id']}（流れ {r['flow']}）：{NAMES.get(status, status)}"
    if r.get("cancel_requested") and status not in ("cancelled", "done"):
        head += "（止めてほしい印を置きました）"
    feedback = (r.get("vars") or {}).get("feedback")
    following = _NEXT.get(status)
    return lines(head, "\n".join(step_line(s, r.get("current")) for s in r["steps"]),
                 f"  最後の差し戻しの文：{feedback}" if feedback and status != "done" else None,
                 following and "次に：" + following.format(id=r["id"]), f"置き場所：{r['dir']}")
