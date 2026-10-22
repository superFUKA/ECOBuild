"""シェルのコマンドの関所（エージェントの PreToolUse フック）。止めるものだけを列挙し（Denied）、ほかはすべて通す。
隔離した場所で確認なしに動くエージェントが、決まった道（ツール）を外れないように使う。何を止めるかは使う側が決める。

コマンドの重さ（READ・CHANGE・CONFIRM・HUMAN）は、使う側がコマンドの一覧に付ける印（ここでは使わない）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

READ = "read"           # 見るだけ
CHANGE = "change"       # 変える（戻せる）
CONFIRM = "confirm"     # 消す・取り返しがつかない・ほかの人に届く
HUMAN = "human"         # 人がする操作：エージェントは使わない

_KEYWORDS = frozenset({"do", "then", "else", "elif", "if", "while", "until", "!", "{"})   # 後ろにコマンドが続く
_ENDS = frozenset({"done", "fi", "}"})


# ---- ダメなものの列挙 -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Denied:
    """逆向きの関所：止めるものだけを列挙し、ほかはすべて通す。
    programs：まるごと止めるプログラムの名前（拡張子なし・小文字）→ 止めたわけ。
    commands：引数で決めるプログラム → 関数（引数 → 止めるわけ。通すなら None）。"""
    programs: dict[str, str] = field(default_factory=dict)
    commands: dict[str, Callable[[list[str]], str | None]] = field(default_factory=dict)


SHELLS = frozenset({"sh", "bash", "dash", "zsh", "ksh"})          # -c の文字列の中も調べる
# 後ろのコマンドを動かすだけのもの（その後ろを調べる）。値を1つ取るオプション
_WRAPPERS = {"env": (), "command": (), "builtin": (), "exec": (), "nohup": (), "time": (), "sudo": ("-u", "-g"),
             "nice": ("-n",), "timeout": ("-s", "-k"), "xargs": ("-n", "-I", "-L", "-P", "-d", "-a", "-s", "-E"),
             "stdbuf": ("-i", "-o", "-e"), "watch": ("-n",), "doas": ("-u",)}
_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")


def check_denied(command: str, denied: Denied) -> str | None:
    """通してよければ None、止めるならその理由。コマンドの埋め込み（$(…)・`…`。" の中も）と sh -c・eval の文字列の
    中も調べる。読み取れないもの（引用符が閉じていない等）は止める（ダメなものを見落とさないように）。"""
    try:
        segments = _segments(command)
    except ValueError:
        return "コマンドを読み取れませんでした（引用符が閉じていません）。"
    for words in segments:
        problem = _denied_words(words, denied, depth=0)
        if problem:
            return problem
    return None


def _denied_words(words: list[str], denied: Denied, depth: int) -> str | None:
    words = _command_words(words)
    if not words:
        return None
    name = re.sub(r"\.(exe|cmd|bat|ps1|sh)$", "", Path(words[0].replace("\\", "/")).name, flags=re.IGNORECASE).lower()
    args = words[1:]
    if name in denied.programs:
        return denied.programs[name]
    if name in denied.commands:
        problem = denied.commands[name](args)
        if problem:
            return problem
    inner = None
    if name in SHELLS and "-c" in args[:-1]:
        inner = args[args.index("-c") + 1]
    elif name == "eval":
        inner = " ".join(args)
    if inner is not None:
        if depth > 5:
            return "入れ子が深すぎるコマンドです。分けて実行してください。"
        try:
            segments = _segments(inner)
        except ValueError:
            return "コマンドを読み取れませんでした（引用符が閉じていません）。"
        for found in segments:
            problem = _denied_words(found, denied, depth + 1)
            if problem:
                return problem
    return None


def _command_words(words: list[str]) -> list[str]:
    """前に付いた変数の代入・if/then 等の言葉・後ろのコマンドを動かすだけのもの（env・sudo・xargs 等）を外す。"""
    changed = True
    while words and changed:
        changed = False
        while words and (words[0] in _KEYWORDS or words[0] in _ENDS or _ASSIGNMENT.match(words[0])):
            words = words[1:]
            changed = True
        if words and Path(words[0]).name.lower() in _WRAPPERS:
            valued = _WRAPPERS[Path(words[0]).name.lower()]
            words = words[1:]
            while words and (words[0].startswith("-") or _ASSIGNMENT.match(words[0])):
                words = words[2:] if words[0] in valued else words[1:]
            if words and words[0].replace(".", "").isdigit():   # timeout 10 git …・nice 等の数
                words = words[1:]
            changed = True
    return words


_BREAKS = frozenset(";|&()\n{}")


def _segments(command: str) -> list[list[str]]:
    """コマンドの文字列を、1つずつのコマンドの単語の並びに分ける（区切り ; | & && || 改行 ( ) と、埋め込み $(…)・`…`
    の始まりと終わりで切る）。' の中はそのまま1つの単語。" の中も1つの単語だが、埋め込みの中はコマンドとして読む
    （" の中でも動くので）。"""
    segments: list[list[str]] = [[]]
    word: list[str] | None = None
    i, quote = 0, ""
    embedded: list[list] = []   # 開いている埋め込み：[種類（"$(" か "`"）, 外の引用符, 中の ( の深さ]

    def end_word():
        nonlocal word
        if word is not None:
            segments[-1].append("".join(word))
            word = None

    def end_segment():
        end_word()
        if segments[-1]:
            segments.append([])

    def add(text: str):
        nonlocal word
        word = word if word is not None else []
        word.append(text)

    while i < len(command):
        c = command[i]
        if quote == "'":
            if c == "'":
                quote = ""
            else:
                add(c)
            i += 1
            continue
        if c == "\\" and i + 1 < len(command):
            add(command[i + 1])
            i += 2
            continue
        if c == "$" and command[i + 1:i + 2] == "(" or c == "`" and not (embedded and embedded[-1][0] == "`"):
            end_segment()           # 埋め込みの始まり（" の中でも動く）：中はコマンドとして読む
            embedded.append(["$(" if c == "$" else "`", quote, 0])
            quote = ""
            i += 2 if c == "$" else 1
            continue
        if embedded and not quote and (c == "`" and embedded[-1][0] == "`"
                                       or c == ")" and embedded[-1][0] == "$(" and embedded[-1][2] == 0):
            end_segment()           # 埋め込みの終わり：外の引用符に戻る
            quote = embedded.pop()[1]
            i += 1
            continue
        if quote == '"':
            if c == '"':
                quote = ""
            else:
                add(c)
            i += 1
            continue
        if c in "'\"":
            quote = c
            add("")
            i += 1
            continue
        if embedded and embedded[-1][0] == "$(" and c in "()":
            embedded[-1][2] += 1 if c == "(" else -1
        if c in _BREAKS:
            end_segment()
        elif c.isspace() or c in "<>":   # 書き出し・読み込み：後ろの名前はコマンドではない（単語にして、調べない）
            end_word()
        else:
            add(c)
        i += 1
    if quote or embedded:
        raise ValueError("引用符・埋め込みが閉じていません")
    end_segment()
    return [s for s in segments if s]


def hook_denied(data: str, denied: Denied) -> tuple[int, str]:
    """フックの入力（JSON）のシェルのコマンドを Denied で調べる。(終了コード, stderr に出す文)。止めるときは 2。"""
    try:
        event = json.loads(data or "{}")
    except ValueError:
        return 0, ""
    command = (event.get("tool_input") or {}).get("command") or ""
    problem = check_denied(command, denied) if isinstance(command, str) else None
    return (2, problem) if problem else (0, "")
