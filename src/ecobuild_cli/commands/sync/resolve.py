import sys
from typing import Annotated

from ..._output import run_command, usage_error

AGENT = "owner"   # sync のツールで衝突したら、持ち主がツールで衝突の箇所を直す
SIDES = ("current", "incoming", "both", "both-incoming-first")


def command(
    path: Annotated[str, "衝突したファイル"],
    side: Annotated[str, "衝突の箇所を、どちらの側にするか：current（今の側）・incoming（入ってくる側）・both（両方。今の側が先）・"
                         "both-incoming-first（両方。入ってくる側が先）"] = "",
    hunk: Annotated[str, "直す箇所の番号（ecobuild sync conflicts の番号。カンマ区切り。省くと残っている箇所すべて）"] = "",
    text: Annotated[str, "ファイルの中身を、直した中身に置き換える（- なら標準入力から読む。--side とは一緒に使えない）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """衝突したファイルの、衝突の箇所を直します（ファイルに書くだけで、登録はしません）。

    --side で、箇所を片方の側か両方にします（--hunk で箇所を選べます。番号は、今残っている箇所を上から 1, 2, …）。
    --text で、手で直した中身に置き換えます（改行は今のファイルに合わせます）。
    全部直したら ecobuild sync continue（やめるなら ecobuild sync abort）。ファイル全体を片方の側にするなら ecobuild sync take。

    例：
      ecobuild sync resolve src/app.py --side incoming --hunk 2,3
      ecobuild sync resolve README.md --side both
    """
    if bool(side) == bool(text):
        return usage_error("--side（採る側）か --text（直した中身）のどちらか1つを指定してください。", json)
    if side and side not in SIDES:
        return usage_error(f"--side に {'・'.join(SIDES)} のどれかを指定してください。", json)
    if text and hunk:
        return usage_error("--hunk は --side と一緒に使います。", json)
    try:
        hunks = tuple(int(n) for n in hunk.split(",") if n.strip())
    except ValueError:
        return usage_error("--hunk には、箇所の番号（1, 2, …）をカンマ区切りで指定してください。", json)

    def action(inv):
        content = (sys.stdin.read() if text == "-" else text) if text else None
        return inv.module.resolve_conflict(path, side=side, hunks=hunks, text=content)

    def render(r):
        return (f"{r.path} を直しました（衝突の箇所が、あと {r.remaining} 箇所残っています）" if r.remaining
                else f"{r.path} を直しました（続きは ecobuild sync continue）")

    return run_command("sync resolve", action, render, json_output=json)
