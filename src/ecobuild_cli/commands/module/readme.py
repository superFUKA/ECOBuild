import re
from pathlib import Path
from typing import Annotated

from ..._output import run_command

AGENT = "read"

LIMIT = 200_000  # これより長い README は、ここまでを出す（truncated が真）


def command(json: Annotated[bool, "結果をJSONで出力する（README がなければ result は null）"] = False) -> int:
    """モジュールの README（いちばん上のフォルダーの README.md 等）の中身を表示します（何も変えません）。

    README.md があればそれ、なければ README・README.txt 等です。JSON は path・text・truncated。
    """
    return run_command("module readme", lambda inv: read(Path(inv.module.root)),
                       lambda r: r["text"] if r else "README はありません", json_output=json)


def read(root: Path) -> dict | None:
    names = sorted(p.name for p in root.iterdir() if p.is_file() and re.match(r"(?i)readme(\.|$)", p.name))
    name = next((n for n in names if n.lower() == "readme.md"), names[0] if names else None)
    if name is None:
        return None
    text = (root / name).read_text(encoding="utf-8", errors="replace")
    return {"path": name, "text": text[:LIMIT], "truncated": len(text) > LIMIT}
