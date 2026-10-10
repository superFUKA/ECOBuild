"""static/icon.svg から icon.ico（ショートカットのアイコン）を作る（開発用。アイコンを変えたら実行してコミットする）。

Edge（ヘッドレス）で大きさごとに PNG に描き、PNG を入れた .ico にまとめる（Windows Vista 以降で使える形）。
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import app

SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
HERE = Path(__file__).parent


def render(edge: str, svg: str, size: int, folder: Path) -> bytes:
    page = folder / f"icon{size}.html"
    page.write_text(f'<html><body style="margin:0;background:transparent">'
                    f'<img src="{Path(svg).as_uri()}" width="{size}" height="{size}" style="display:block"></body></html>',
                    encoding="utf-8")
    png = folder / f"icon{size}.png"
    subprocess.run([edge, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--default-background-color=00000000", f"--window-size={size},{size}",
                    f"--screenshot={png}", page.as_uri()], check=True, capture_output=True, timeout=60)
    return png.read_bytes()


def pack(images: dict[int, bytes]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))
    entries, data = b"", b""
    offset = 6 + 16 * len(images)
    for size, png in images.items():
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return header + entries + data


def main() -> None:
    edge = app._edge()
    if not edge:
        sys.exit("Edge が見つかりません。")
    with tempfile.TemporaryDirectory() as folder:
        images = {size: render(edge, str(HERE / "static" / "icon.svg"), size, Path(folder)) for size in SIZES}
    (HERE / "icon.ico").write_bytes(pack(images))
    print(f"作りました：{HERE / 'icon.ico'}")


if __name__ == "__main__":
    main()
