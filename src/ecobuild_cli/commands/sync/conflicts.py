from typing import Annotated

from ecowork._conflicts import chosen
from ecowork.model import CONFLICT_REASONS

from ..._output import lines, run_command
from ..status import STOPPED

AGENT = "owner"   # sync のツールで衝突したら、持ち主が衝突の箇所を読んで直す
# 止まっている操作ごとの、2つの側の呼び名（今の側・入ってくる側）
SIDES = {"merge": ("このタスクブランチの側", "取り込む側"), "rebase": ("作成元の側", "自分のコミットの側"),
         "revert": ("今の内容", "取り消した内容"), "stash": ("今の内容", "退避した変更")}


def _piece(piece) -> dict:
    """ファイルの一部分。衝突の箇所には、両方を採ったときの中身（sync resolve --side both・both-incoming-first）も添える。"""
    if not piece.conflict:
        return {"text": piece.text, "conflict": False}
    return {"text": piece.text, "conflict": True, "line": piece.line, "current": piece.current, "incoming": piece.incoming,
            "base": piece.base, "both": chosen(piece, "both"), "both_incoming_first": chosen(piece, "both-incoming-first")}


def command(
    *paths: Annotated[str, "衝突したファイル（省くと衝突したファイルすべて）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """衝突したファイルと、その衝突の箇所（今の側・入ってくる側・共通の元）を表示します。何も変えません。

    箇所は、ファイルごとに上から 1, 2, … と数えます。直すには ecobuild sync resolve <ファイル> --side <側> [--hunk <番号>]
    （ファイル全体を片方の側にするなら ecobuild sync take）。全部直したら ecobuild sync continue。
    バイナリ・大きすぎる・UTF-8 でないファイルと、片方の側で消えたファイルは、箇所に分けません（sync take で直します）。
    """

    def action(inv):
        found = inv.module.repository.conflicts(paths)
        current, incoming = SIDES.get(found.stopped, ("今の側", "入ってくる側"))
        return {"stopped": found.stopped, "current": current, "incoming": incoming, "ready": found.ready,
                "files": [{"path": f.path, "remaining": f.remaining, "reason": f.reason,
                           "reason_text": CONFLICT_REASONS.get(f.reason, ""), "pieces": [_piece(p) for p in f.pieces]}
                          for f in found.files]}

    def render(r):
        if not r["files"]:
            return "衝突したファイルはありません。" + ("ecobuild sync continue で続けます。" if r["ready"] else "")
        out = [f"{STOPPED.get(r['stopped'], '操作')}が衝突で止まっています（current＝{r['current']}・incoming＝{r['incoming']}）。"
               if r["stopped"] else None]
        for f in r["files"]:
            if f["reason"]:
                out.append(f"{f['path']}：箇所ごとには直せません（{f['reason_text']}）。ecobuild sync take で片方の側にします")
                continue
            out.append(f"{f['path']}：" + (f"残り {f['remaining']} 箇所" if f["remaining"] else "直しました"))
            number = 0
            for piece in f["pieces"]:
                if not piece["conflict"]:
                    continue
                number += 1
                out.append(f"  箇所 {number}（{piece['line']} 行目）")
                for title, text in ((r["current"], piece["current"]), (r["incoming"], piece["incoming"])):
                    out.append(f"    ── {title}")
                    out += [f"    {line}" for line in text.splitlines()] or ["    （なし）"]
        if r["ready"]:
            out.append("全部直してあります。ecobuild sync continue で続けます。")
        return lines(*out)

    return run_command("sync conflicts", action, render, json_output=json)
