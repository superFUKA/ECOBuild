"""コマンドの重さ：見るだけ（read）・変える（change）・確認が要る（confirm）・人がする（human）。

コマンドの一覧（ecobuild --help --json の effect）と、オペレーターのフック（ecobuild agent guard）が使う。
- confirm：消す・取り返しがつかない・ほかの人に届く操作。エージェントは実行する前にユーザーに聞く。
- human：人が画面で答える・管理者の権限が要る・エージェント自身を動かす操作（オペレーター・係・人の画面への引き取り）。
  エージェントは使わない。チームの作業役を作る・言付ける・起動し直す（agent team start・send・restart）は進行役・管理役が
  使うので change、閉じる・取り込む（close・accept）は作業空間を消すので confirm。
書いていないコマンドは change。重さを上げるオプション（--yes 等）が付けば confirm。
"""

from __future__ import annotations

from ecobuild_agent.operator import CHANGE, CONFIRM, HUMAN, READ, REQUESTED  # noqa: F401（REQUESTED は拡張が名乗る）

EFFECTS = {
    READ: (
        "account list", "account show", "agent conversations", "agent guide", "agent log", "agent status", "agent team list", "agent team log", "agent token status", "blame", "branch list", "check", "ci logs", "ci secret list", "ci show", "ci status", "ci wait",
        "config get", "config list", "container image list", "container recipe", "container status", "deps list", "deps tree", "diff", "doctor",
        "installer show", "log", "milestone list", "milestone status", "module list", "module settings",
        "module show", "module types", "profile list", "project list", "project show", "release list", "show",
        "sprint list", "sprint status", "stash list", "status", "task diff", "task list", "task next",
        "task overdue", "task status", "task workload", "template list", "track", "workspace list",
    ),
    CONFIRM: (
        "branch delete", "branch merge", "branch submit", "ci remove", "ci secret remove", "container image prune", "container off",
        "agent team accept", "agent team close", "container remove", "file remove", "module adopt", "module archive", "module delete", "module members add",
        "module members remove", "module protect", "module unarchive", "project remove", "release create",
        "restore", "stash drop", "sync abort", "task approve", "task close", "task drop", "task finish",
        "task reject", "task reset", "task revert", "task submit", "task withdraw", "workspace close",
    ),
    HUMAN: (
        "agent ask", "agent context", "agent guard", "agent operator", "agent serve", "agent team handback", "agent team takeover", "agent token capture", "agent token login", "agent token remove", "agent token set", "ci secret set", "init", "installer add",
        "installer update", "setup",
    ),
}
# 上の表より細かい指定（短い名前が read でも、その下のコマンドは変える）
OVERRIDES = {"track add": CHANGE, "track remove": CHANGE}
CONFIRM_OPTIONS = ("--yes", "-y", "--discard-local", "--force", "--remove-workspaces")
GLOBAL_OPTIONS = ("-C", "--directory")

_TABLE = {path: effect for effect, paths in EFFECTS.items() for path in paths}
_TABLE.update(OVERRIDES)


def effect(path: str, options: tuple[str, ...] = ()) -> str:
    """コマンド（"task start" 等）の重さ。options：付けたオプション。"""
    words = path.split()
    found = CHANGE
    for length in range(len(words), 0, -1):
        if " ".join(words[:length]) in _TABLE:
            found = _TABLE[" ".join(words[:length])]
            break
    if path == "module settings" and any(o.startswith("-") and o != "--json" for o in options):
        found = CHANGE      # 値を渡すと設定を変える
    if found in (READ, CHANGE) and any(o.split("=")[0] in CONFIRM_OPTIONS for o in options):
        found = CONFIRM
    return found


def classify(args: list[str], extra: dict[str, str] | None = None) -> tuple[str, str]:
    """ecobuild に渡す引数から (重さ, コマンドの名前)。-C <場所> は飛ばす。--help は見るだけ。
    extra：拡張が名乗った重さ（"<拡張> <操作>" → 重さ。_extensions.effects）。"""
    rest = list(args)
    while rest and (rest[0] in GLOBAL_OPTIONS or rest[0].startswith(("--directory=", "-C"))):
        rest = rest[2:] if rest[0] in GLOBAL_OPTIONS else rest[1:]
    words = [w for w in rest if not w.startswith("-")]
    options = tuple(w for w in rest if w.startswith("-"))
    if "--help" in options or "-h" in options or not words:
        return READ, "help"
    name = " ".join(words[:2])
    if extra and name not in extra and any(key.startswith(words[0] + " ") for key in extra):
        return CONFIRM, name     # 拡張の、名乗っていない呼び方（ほかのコマンドを中で動かす等）：分からないので確認する
    if extra and name in extra:
        found = extra[name]
        return (CONFIRM if found in (READ, CHANGE) and any(o.split("=")[0] in CONFIRM_OPTIONS for o in options) else found), name
    path = _path(words)
    return effect(path, options), path


def _path(words: list[str]) -> str:
    """引数の先頭のうち、表にある一番長いコマンドの名前（なければ先頭の2語まで）。"""
    for length in range(min(len(words), 3), 0, -1):
        name = " ".join(words[:length])
        if name in _TABLE:
            return name
    return " ".join(words[:2])
