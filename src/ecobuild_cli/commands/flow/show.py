from typing import Annotated

from ..._output import lines, run_command
from ._common import flows

AGENT = "read"


def command(name: Annotated[str, "流れの名前（.ecobuild/flows/<名前>.toml）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """流れの定義（読み込んだ形）と、確かめた結果（誤りの一覧）を表示します。誤りがあっても失敗にはしません。"""
    return run_command("flow show", lambda inv: flows(inv).show(name), _render, json_output=json)


def _settings(step: dict) -> str:
    shown = []
    for key, value in step.items():
        if key in ("id", "type"):
            continue
        text = value if isinstance(value, str) else repr(value)
        text = " ".join(text.split())
        shown.append(f"{key}={text if len(text) <= 60 else text[:60] + '…'}")
    return "・".join(shown)


def _render(r) -> str:
    inputs = "\n".join(f"  {i['name']}{'（必須）' if i.get('required') else ''}：{i.get('help', '')}" for i in r.inputs)
    steps = "\n".join(f"  {s.get('id')}（{s.get('type')}）" + (f"：{_settings(s)}" if _settings(s) else "") for s in r.steps)
    problems = ("誤り：\n" + "\n".join(f"  - {p}" for p in r.problems)) if r.problems else "確かめ：誤りはありません"
    return lines(f"流れ {r.name}（{r.path}）", r.description and f"  {r.description}",
                 inputs and f"入力：\n{inputs}", f"工程：\n{steps}", problems)
