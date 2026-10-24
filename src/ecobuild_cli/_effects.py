"""コマンドの重さ：見るだけ（read）・変える（change）・確認が要る（confirm）・人がする（human）。

コマンドの一覧（ecobuild --help --json の effect）に出す。GUI のオペレーターは read のものだけを使う。
エージェントに許すかは別の印（コマンドのファイルの AGENT）で、重さでは決めない。
- confirm：消す・取り返しがつかない・ほかの人に届く操作。
- human：人が画面で答える・管理者の権限が要る・エージェント自身を動かす操作（係・人の画面への引き取り）。
  エージェントを閉じる（agent close）は子タスクの作業空間を消すので confirm。
書いていないコマンドは change。重さを上げるオプション（--yes 等）が付けば confirm。
"""

from __future__ import annotations

from ecobuild_agent import CHANGE, CONFIRM, HUMAN, READ

EFFECTS = {
    READ: (
        "account list", "account show", "agent conversations", "agent guide", "agent log", "agent registry list", "agent registry show", "agent rules show", "agent status", "agent list", "agent children", "agent token status", "blame", "branch list", "check", "ci logs", "ci secret list", "ci show", "ci status", "ci wait",
        "config get", "config list", "container dockerfile", "container image list", "container recipe", "container status", "deps list", "deps tree", "diff", "doctor",
        "installer show", "log", "milestone list", "milestone status", "module list", "module settings",
        "module show", "module types", "profile list", "project list", "project show", "release list", "show",
        "sprint list", "sprint status", "stash list", "status", "task diff", "task list", "task next",
        "task overdue", "task status", "task workload", "template list", "track", "workspace list",
    ),
    CONFIRM: (
        "branch delete", "branch merge", "branch submit", "ci remove", "ci secret remove", "container image prune", "container off",
        "agent registry remove", "agent close", "container remove", "file remove", "module adopt", "module archive", "module delete", "module members add",
        "module members remove", "module protect", "module unarchive", "project remove", "release create",
        "restore", "stash drop", "sync abort", "task approve", "task close", "task drop", "task finish",
        "task reject", "task reset", "task revert", "task submit", "task withdraw", "workspace close",
    ),
    HUMAN: (
        "agent guard", "agent registry add", "agent registry set", "agent serve", "agent handback", "agent takeover", "agent token capture", "agent token login", "agent token remove", "agent token set", "ci secret set", "init", "installer add",
        "installer update", "setup",
    ),
}
# 上の表より細かい指定（短い名前が read でも、その下のコマンドは変える）
OVERRIDES = {"track add": CHANGE, "track remove": CHANGE}
# 一覧（--help）に出さないコマンド（エージェントを起動する ECOBuild が使う。人は使わない）
HIDDEN = {"agent mcp": HUMAN}
CONFIRM_OPTIONS = ("--yes", "-y", "--discard-local", "--force", "--remove-workspaces")

_TABLE = {path: effect for effect, paths in EFFECTS.items() for path in paths}
_TABLE.update(OVERRIDES)
_TABLE.update(HIDDEN)


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
    if path == "container dockerfile" and any(o.split("=")[0] == "--write" for o in options):
        found = CHANGE      # --write は環境の Dockerfile を書く
    if found in (READ, CHANGE) and any(o.split("=")[0] in CONFIRM_OPTIONS for o in options):
        found = CONFIRM
    return found

