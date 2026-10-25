"""パイプラインの表示（list・add・remove・on で共通）。"""

from ecobuild.config import TIMING_NAMES, TIMINGS
from ecobuild.module import CHECK_NAMES

from ..._output import lines


def steps_text(pipeline) -> str:
    steps = "・".join(CHECK_NAMES.get(s, s) for s in pipeline.steps)
    return steps + (f"（流す試験：{', '.join(pipeline.tests)}）" if pipeline.tests else "")


def render(r) -> str:
    if not r.pipelines:
        return "パイプラインはありません（ecobuild pipeline add <名前> --steps build,test で作ります）"
    rows = []
    for timing in TIMINGS:
        shared, local = r.triggers.get(timing, ()), [n for n in r.local.get(timing, ()) if n not in r.triggers.get(timing, ())]
        if shared or local:
            rows.append(f"  {TIMING_NAMES[timing]}（{timing}）：" + "、".join([*shared, *(f"{n}（このPCだけ）" for n in local)]))
    return lines("パイプライン：", "\n".join(f"  {p.name}：{steps_text(p)}" for p in r.pipelines),
                 "当てているタイミング：", "\n".join(rows) if rows else "  なし（ecobuild pipeline on <タイミング> <名前> で当てます）")
