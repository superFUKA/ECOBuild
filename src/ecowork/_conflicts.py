"""衝突したファイルの中身：衝突の箇所（今の側・入ってくる側・共通の元）に分ける・選んだ側で組み立てる。

git が作業ツリーのファイルに書く衝突の印（<<<<<<<・|||||||・=======・>>>>>>>）を読むだけで、git は呼ばない。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import model as wm

_START = re.compile(r"<{7}(?: |\r?\n|\Z)")
_BASE = re.compile(r"\|{7}(?: |\r?\n|\Z)")
_MIDDLE = re.compile(r"={7}(?:\r?\n|\Z)")
_END = re.compile(r">{7}(?: |\r?\n|\Z)")
_LINE = re.compile(r"[^\n]*\n|[^\n]+\Z")

LIMIT = 400_000     # これより大きいファイルは、箇所に分けない（片方の側を採るか、エディターで直す）
SIDES = ("current", "incoming", "both", "both-incoming-first")


def split(text: str) -> tuple[wm.ConflictPiece, ...]:
    """ファイルの中身を、そのままの部分と衝突の箇所に分ける（text をつなぐと元の中身）。終わりの印のない箇所は、
    そのままの部分として扱う。"""
    lines = _LINE.findall(text)
    pieces: list[wm.ConflictPiece] = []
    plain, number, i = "", 1, 0
    while i < len(lines):
        if not _START.match(lines[i]):
            plain += lines[i]
            i += 1
            continue
        sides = {"current": "", "base": None, "incoming": ""}
        part, j = "current", i + 1
        while j < len(lines):
            line = lines[j]
            if part == "current" and _BASE.match(line):
                part, sides["base"] = "base", ""
            elif part != "incoming" and _MIDDLE.match(line):
                part = "incoming"
            elif part == "incoming" and _END.match(line):
                break
            else:
                sides[part] += line
            j += 1
        if j >= len(lines) or part != "incoming":   # 終わりの印がない：衝突の箇所ではない
            plain += lines[i]
            i += 1
            continue
        if plain:
            pieces.append(wm.ConflictPiece(plain))
            number += len(_LINE.findall(plain))
            plain = ""
        raw = "".join(lines[i:j + 1])
        pieces.append(wm.ConflictPiece(raw, True, number, sides["current"], sides["incoming"], sides["base"]))
        number += j + 1 - i
        i = j + 1
    if plain:
        pieces.append(wm.ConflictPiece(plain))
    return tuple(pieces)


def _ended(side: str) -> str:
    """後ろに続きがあるとき、行の終わりを補う（側の最後の行に改行がないことがある）。"""
    if not side or side.endswith("\n"):
        return side
    return side + ("\r\n" if "\r\n" in side else "\n")


def chosen(piece: wm.ConflictPiece, side: str) -> str:
    """衝突の箇所を、選んだ側（SIDES）にした中身。"""
    if side == "current":
        return piece.current
    if side == "incoming":
        return piece.incoming
    if side == "both":
        return _ended(piece.current) + piece.incoming
    return _ended(piece.incoming) + piece.current


def remaining(text: str) -> int:
    """中身に残っている衝突の箇所の数（始まりの印の数）。"""
    return sum(1 for line in _LINE.findall(text) if _START.match(line))


def read(root: Path, path: str) -> wm.ConflictFile:
    """衝突したファイル1つ：箇所に分けた中身。ここで直せないもの（ない・バイナリ・大きすぎる・UTF-8 でない）は理由だけ。"""
    target = root / path
    if not target.is_file():
        return wm.ConflictFile(path, 0, "missing")
    data = target.read_bytes()
    if b"\0" in data[:8000]:
        return wm.ConflictFile(path, 0, "binary")
    if len(data) > LIMIT:
        return wm.ConflictFile(path, 0, "too_large")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return wm.ConflictFile(path, 0, "not_utf8")
    return wm.ConflictFile(path, remaining(text), "", split(text))


def like(text: str, before: bytes) -> str:
    """text の改行を、今のファイル（before）に合わせる：今が CRLF だけで、text が LF だけなら CRLF にする
    （入力欄を通った文は LF になっている）。"""
    if b"\r\n" in before and b"\n" not in before.replace(b"\r\n", b"") and "\r\n" not in text:
        return text.replace("\n", "\r\n")
    return text
