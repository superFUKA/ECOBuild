"""推測で打たれた名前への案内（もしかして）と、よく打たれる短いオプションの読み替え。

AI（や人）は、ほかの道具の名前から ECOBuild のコマンドを推測して打つ（task create・task show・commit -m 等）。ない名前は
今までどおり引数の誤りにする（勝手に別のコマンドを実行しない）が、正しいコマンドを「もしかして」で示す。
- よく推測される名前（GUESSES）は、決めた案内を出す。
- ほかは、同じ場所にあるコマンドの名前から似たものを出す（difflib）。
-m だけは、--message を持つコマンドで --message として受ける（git commit -m の慣れで最も多く打たれる。意味が1つに決まる）。
"""

from __future__ import annotations

import difflib

import click

from . import _types, commands

# よく推測で打たれる、ない名前（打った道筋）→ 正しいコマンド（ecobuild の後ろ）か、説明（「…」で始まるもの）
GUESSES: dict[tuple[str, ...], str] = {
    ("task", "create"): "task new", ("task", "make"): "task new", ("task", "show"): "task status",
    ("task", "view"): "task status", ("task", "info"): "task status", ("task", "get"): "task status",
    ("task", "open"): "task start", ("task", "begin"): "task start", ("task", "resume"): "task start",
    ("task", "checkout"): "task start", ("task", "switch"): "task start", ("task", "pr"): "task submit",
    ("task", "merge"): "task finish", ("task", "complete"): "task finish", ("task", "done"): "task finish",
    ("task", "ls"): "task list", ("task", "delete"): "task drop", ("task", "remove"): "task drop",
    ("task", "note"): "task comment", ("task", "log"): "log", ("task", "sync"): "sync",
    ("profile", "show"): "profile list", ("branch", "show"): "branch list", ("module", "status"): "status",
    ("module", "info"): "module show", ("workspace", "show"): "workspace list", ("workspace", "remove"): "workspace close",
    ("file", "list"): "files", ("file", "ls"): "files",
    ("file", "show"): "…ファイルの中身を読む・書くコマンドはありません（エディター等で直接）。一覧は ecobuild files",
    ("file", "read"): "…ファイルの中身を読む・書くコマンドはありません（エディター等で直接）。一覧は ecobuild files",
    ("file", "write"): "…ファイルの中身を読む・書くコマンドはありません（エディター等で直接）。新しいファイルを管理に入れるのは ecobuild file add",
    ("member",): "module members", ("members",): "module members", ("commit",): "task commit",
    ("submit",): "task submit", ("push",): "task push", ("finish",): "task finish", ("start",): "task start",
    ("new",): "task new", ("pr",): "task submit", ("tasks",): "task list", ("branches",): "branch list",
    ("modules",): "module list", ("workspaces",): "workspace list", ("guide",): "agent guide", ("merge",): "task finish",
    ("pull",): "sync", ("fetch",): "status --fetch", ("checkout",): "task start", ("switch",): "task start",
    ("issue",): "task", ("issues",): "task list", ("version",): "--version",
}


def known() -> set[tuple[str, ...]]:
    """コマンドの道筋（共通と、どの型のものも）。"""
    return set(_types.routes(commands)).union(*_types.all_routes().values())


def words_of(args: list[str]) -> list[str]:
    """引数のうち、先頭のオプションでない言葉（コマンドの道筋と、位置引数）。"""
    words = []
    for arg in args:
        if arg.startswith("-"):
            break
        words.append(arg)
    return words


def suggestion(args: list[str]) -> str | None:
    """ない名前を打ったときの「もしかして」の文（なければ None）。args：ecobuild の後ろの引数。"""
    words = words_of(args)
    routes = known()
    length = 0
    while length < len(words) and tuple(words[:length + 1]) in routes:
        length += 1
    if length == len(words):
        return None
    tried = tuple(words[:length + 1])
    guessed = GUESSES.get(tried)
    if guessed is not None:   # 案内先が末端のコマンドなら、打った位置引数も付ける（task show 252 → task status 252）
        if guessed.startswith("…"):
            return guessed[1:]
        target = tuple(guessed.split())
        leaf = not any(len(route) > len(target) and route[:len(target)] == target for route in routes)
        return f"もしかして：ecobuild {' '.join([guessed, *(words[length + 1:] if leaf else ())])}"
    siblings = sorted({route[length] for route in routes if len(route) > length and route[:length] == tried[:-1]})
    close = difflib.get_close_matches(tried[-1], siblings, n=3, cutoff=0.6)
    if not close:
        return None
    prefix = " ".join(tried[:-1])
    return "もしかして：" + "・".join(f"ecobuild {prefix + ' ' if prefix else ''}{name}" for name in close)


def rewrite(args: list[str], find) -> list[str]:
    """-m を --message に読み替える（-- より前で、打ったコマンドに --message があるときだけ。値を取るオプションの値としての
    -m〔--message -m〕は読み替えない）。find(道筋) → click のコマンド。読めなければ（読み込みの失敗も）読み替えない。"""
    if "-m" not in args:
        return args
    try:
        command = find(words_of(args))
        params = command.get_params(click.Context(command)) if command is not None else []   # 遅れて読み込むコマンドも
    except Exception:   # 読み替えのためだけの読み込みでは止めない（実行のときに同じ誤りが出る）
        return args
    options = [p for p in params if isinstance(p, click.Option)]
    if not any("--message" in p.opts for p in options):
        return args
    valued = {name for p in options if not p.is_flag for name in p.opts}   # 後ろに値を取るオプション
    result, value_next, ended = [], False, False
    for arg in args:
        if not ended and not value_next and arg == "-m":
            arg = "--message"
        elif not ended and not value_next and arg == "--":
            ended = True
        result.append(arg)
        value_next = not ended and not value_next and arg in valued
    return result
