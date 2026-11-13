from typing import Annotated

from ecoflow import NAMES

from ..._output import lines, run_command
from ._common import flows, when

AGENT = "read"


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """流れの定義（.ecobuild/flows/<名前>.toml）と、この作業空間の実行を表示します。"""
    return run_command("flow list", lambda inv: flows(inv).list(), _render, json_output=json)


def _render(r) -> str:
    if not r.flows:
        defined = "流れの定義はありません（.ecobuild/flows/<名前>.toml に書きます。ecobuild flow show <名前> で確かめられます）"
    else:
        defined = lines("流れ：", "\n".join(
            f"  {f.name}：" + (f"誤り：{f.error}" if f.error else f"{f.description or '（説明なし）'}（{' → '.join(f.steps)}）")
            for f in r.flows))
    rows = []
    for run in r.runs[-20:]:
        where = f"（工程 {run['current']}）" if run.get("current") and run["status"] not in ("done", "cancelled") else ""
        rows.append(f"  {run['id']}：{NAMES.get(run['status'], run['status'])}{where}・{when(run.get('updated'))}")
    return lines(defined, rows and "実行（この作業空間）：\n" + "\n".join(rows))
