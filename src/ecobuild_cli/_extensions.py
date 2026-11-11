"""外部サブコマンド（git・gh・cargo と同じ）：ecobuild にないコマンド xxx は、PATH にある ecobuild-xxx に引数ごと渡す。

ECOBuild の外のツールが、ecobuild のコマンドとして加われる（例：ECOBuild GUI が置く ecobuild-gui）。
ecobuild はその中身を知らない。-C <パス> は ecobuild が先に受け取り、そのフォルダで外部のコマンドを実行する。
ecobuild --help には「拡張コマンド」として名前が出る（ecobuild <名前> --help で、そのコマンドの使い方）。

拡張コマンドは、自分の中のコマンドの形を答えられる（任意）：`ecobuild-<名前> --help --json` の標準出力の最後の行に
`{"ok": true, "result": {"summary": 短い説明, "commands": [ecobuild の一覧と同じ形のコマンド, …]}}`。
答えたものは、ecobuild --help --json の extensions に入る（引数・重さ。画面・エージェントが、中のコマンドを一覧から知る）。
答えない・形の違う拡張コマンドは、名前だけが出る。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PREFIX = "ecobuild-"
_NAME = re.compile(r"^[a-z][a-z0-9-]*$")


def _suffixes() -> list[str]:
    if os.name == "nt":
        return [s.lower() for s in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if s] + [".py"]
    return [""]


def find(name: str) -> str | None:
    """ecobuild-<name> の場所（PATH）。名前として使えないもの・ないときは None。"""
    if not _NAME.match(name):
        return None
    return shutil.which(PREFIX + name) or (shutil.which(PREFIX + name + ".py") if os.name == "nt" else None)


def available() -> dict[str, str]:
    """PATH にある外部サブコマンド（名前 → 場所。PATH の先にあるものが優先）。"""
    found: dict[str, str] = {}
    suffixes = _suffixes()
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        try:
            entries = list(Path(folder).iterdir()) if folder else []
        except OSError:
            continue
        for entry in entries:
            lower = entry.name.lower()
            if not lower.startswith(PREFIX):
                continue
            stem, suffix = (lower[:-len(entry.suffix)], entry.suffix.lower()) if entry.suffix else (lower, "")
            if suffix not in suffixes:
                continue
            name = stem[len(PREFIX):]
            if _NAME.match(name) and name not in found and entry.is_file():
                found[name] = str(entry)
    return found


DESCRIBE_TIMEOUT = 10   # 形を答えるのを待つ秒数（答えなければ、名前だけ）
EFFECTS = ("read", "change", "confirm", "human")


def describe(name: str, path: str) -> dict:
    """拡張コマンドが答えた自分の形：{"summary": 短い説明, "commands": [中のコマンド]}。答えなければ、どちらも空。"""
    command = [sys.executable, path] if path.lower().endswith(".py") else [path]
    try:
        done = subprocess.run([*command, "--help", "--json"], stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=DESCRIBE_TIMEOUT)
        lines = done.stdout.strip().splitlines()
        document = json.loads(lines[-1]) if lines else None
    except (OSError, ValueError, subprocess.SubprocessError):
        document = None
    result = document.get("result") if isinstance(document, dict) and document.get("ok") else None
    if not isinstance(result, dict):
        return {"summary": "", "commands": []}
    summary = result.get("summary")
    return {"summary": summary if isinstance(summary, str) else "", "commands": _nodes(result.get("commands"), (name,))}


def _nodes(given, above: tuple[str, ...]) -> list[dict]:
    """拡張コマンドが答えたコマンドを、一覧の形にそろえる（path は拡張コマンドの名前から。重さの分からないものは change）。"""
    nodes = []
    for item in given if isinstance(given, list) else ():
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not _NAME.match(name):
            continue
        runnable = bool(item.get("runnable"))
        effect = item.get("effect") if item.get("effect") in EFFECTS else ("change" if runnable else None)
        nodes.append({"name": name, "path": " ".join((*above, name)), "runnable": runnable, "effect": effect,
                      "summary": item.get("summary") if isinstance(item.get("summary"), str) else "",
                      "arguments": [a for a in item.get("arguments") or () if isinstance(a, dict) and isinstance(a.get("param"), str)],
                      "options": [o for o in item.get("options") or () if isinstance(o, dict) and isinstance(o.get("param"), str)],
                      "commands": _nodes(item.get("commands"), (*above, name))})
    return nodes


def run(path: str, args: list[str]) -> int:
    """外部サブコマンドを実行し、その終了コードを返す（入出力はそのまま）。"""
    command = [sys.executable, path] if path.lower().endswith(".py") else [path]
    try:
        return subprocess.call([*command, *args])
    except OSError as error:
        print(f"エラー：{Path(path).name} を実行できません：{error}", file=sys.stderr)
        return 1
