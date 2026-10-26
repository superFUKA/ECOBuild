from typing import Annotated

from ..._output import run_command, usage_error

AGENT = "owner"   # sync のツールで衝突したら、持ち主がツールで片方の側を採る
SIDES = {"current": "今の", "incoming": "入ってくる"}


def command(
    *paths: Annotated[str, "衝突したファイル（省くと衝突したファイルすべて）"],
    side: Annotated[str, "採る側：current（今の側。タスクブランチ等の HEAD）・incoming（入ってくる側。取り込むブランチ・"
                         "載せ替える自分のコミット・取り消し・戻す退避）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """衝突したファイルを、片方の側の内容で解決します（git checkout --ours／--theirs と同じ）。

    その側で消えているファイルは消します。続きは ecobuild sync continue。
    """
    if side not in SIDES:
        return usage_error("--side に current（今の側）か incoming（入ってくる側）を指定してください。", json)
    return run_command("sync take", lambda inv: inv.module.take_side(paths, incoming=side == "incoming"),
                       lambda r: f"{'、'.join(r)} を{SIDES[side]}側で解決しました（続きは ecobuild sync continue）",
                       json_output=json)
