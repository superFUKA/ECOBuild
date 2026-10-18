"""外部サブコマンド（git・gh・cargo と同じ）：ecobuild にないコマンド xxx は、PATH にある ecobuild-xxx に引数ごと渡す。

ECOBuild の外のツールが、ecobuild のコマンドとして加われる（例：ECOBuild GUI が置く ecobuild-gui）。
ecobuild はその中身を知らない。-C <パス> は ecobuild が先に受け取り、そのフォルダで外部のコマンドを実行する。
ecobuild --help には「拡張コマンド」として名前が出る（ecobuild <名前> --help で、そのコマンドの使い方）。
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


def effects(name: str, path: str, timeout: float = 20) -> dict[str, str]:
    """外部サブコマンドの操作の重さ（"<名前> <操作>" → read・change・confirm）。拡張は `--help --json` の結果の actions
    （か commands）に {name, effect} を書いて名乗る（書かなければ、ここでは何も分からない＝change として扱われる）。"""
    command = [sys.executable, path] if path.lower().endswith(".py") else [path]
    try:
        done = subprocess.run([*command, "--help", "--json"], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
        document = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else {}
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return {}
    result = document.get("result") if isinstance(document, dict) else None
    items = (result.get("actions") or result.get("commands") or []) if isinstance(result, dict) else []
    return {f"{name} {item['name']}": item["effect"] for item in items
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("effect") in ("read", "change", "confirm", "human")}


def run(path: str, args: list[str]) -> int:
    """外部サブコマンドを実行し、その終了コードを返す（入出力はそのまま）。"""
    command = [sys.executable, path] if path.lower().endswith(".py") else [path]
    try:
        return subprocess.call([*command, *args])
    except OSError as error:
        print(f"エラー：{Path(path).name} を実行できません：{error}", file=sys.stderr)
        return 1
