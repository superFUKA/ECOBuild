from typing import Annotated

from ..._output import run_command


def _values(values: dict) -> str:
    return "、".join(f"{key}={value}" for key, value in values.items())


def render(r):
    if not r.profiles:
        return "ビルド設定はありません（ecobuild profile add で追加できます）"
    lines = []
    for name, p in r.profiles.items():
        lines.append(("* " if name == r.selected else "  ")
                     + f"{name}：{p.configuration}、{'共有' if p.shared else '静的'}ライブラリ、並列 {p.parallel}"
                     + (f"、{_values(p.options)}" if p.options else ""))
        lines += [f"      {project}：{_values(values)}" for project, values in p.projects.items()]
    return "\n".join(lines)


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ビルド設定の一覧を表示します（* はこのPCで選んでいるもの）。"""
    return run_command("profile list", lambda inv: inv.module.profiles(), render, json_output=json)
