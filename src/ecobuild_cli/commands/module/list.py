from typing import Annotated

from ecobuild_bundle import Module
from ..._output import local_time, run_command, usage_error


def command(
    owner: Annotated[str, "リポジトリの所有者（組織名など。既定は設定の owner、なければログイン中のユーザー）"] = "",
    archived: Annotated[bool, "アーカイブしたモジュールだけを表示する"] = False,
    all: Annotated[bool, "アーカイブしたモジュールも表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにあるモジュール（ecobuild.toml があるリポジトリ）の一覧を、新しく更新した順に表示します。

    既定では、アーカイブしたモジュール（ecobuild module archive）は表示しません。
    """
    if archived and all:
        return usage_error("--archived と --all は一緒に使えません。", json)

    def action(inv):
        from ecobuild import tooling
        return list(Module.modules(owner or tooling.load_config().get("owner") or None,
                                   archived=None if all else archived))

    def render(r):
        if not r:
            return ("アーカイブしたモジュールはありません" if archived else
                    "モジュールはありません（ecobuild module new で作れます）")
        return "\n".join(_line(m) for m in r)

    return run_command("module list", action, render, json_output=json)


def _line(m) -> str:
    notes = [m.type or "型不明", "非公開" if m.private else "公開"]
    if m.archived:
        notes.append("アーカイブ済み")
    text = f"{m.repository}（{'・'.join(notes)}、更新 {local_time(m.updated)}）"
    return text + (f"：{m.description}" if m.description else "")
