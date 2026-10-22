"""作業空間のエージェントの関所（ecobuild agent guard。Claude Code の PreToolUse フック）：ダメなものだけを止める。

エージェントは隔離したコンテナの中で確認なしに動き、ECOBuild・GitHub・ブランチの操作はツール（MCP）でだけ行う。
シェルからの道を止める（ほかはすべて通す。ecoagent.guard.Denied）：
- ecobuild・gh：まるごと。
- git の書き込み：コミット・push・ブランチの切り替え・作り直し・作業空間（worktree）・ブランチ・タグ・設定の書き換え等
  （手伝いのコミットもここで止まる）。見るだけのもの（status・diff・log・show・branch の一覧 等）は通す。
分かっている穴：python -c 等で別のプログラムを動かす道は止めきれない（コンテナに鍵を渡している間は抜けられる）。
"""

from __future__ import annotations

import ecoagent

TOOLS_HINT = "ECOBuild の操作（タスク・ビルド・テスト・コミット・提出・子のエージェント）は MCP のツール（ecobuild）で行います。"
WRITING = frozenset({"commit", "push", "pull", "switch", "checkout", "reset", "rebase", "merge", "worktree",
                     "cherry-pick", "revert", "am", "update-ref", "filter-branch", "filter-repo", "replace", "gc",
                     "prune", "init", "clone", "update-index", "commit-tree", "read-tree", "fast-import"})
_READ_ONLY_SUBCOMMANDS = {"stash": {"list", "show"}, "remote": {"show", "get-url"}, "notes": {"list", "show"},
                          "submodule": {"status", "summary"}, "config": {"get", "list"}}
_BRANCH_WRITES = frozenset({"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
                            "-u", "--set-upstream-to", "--unset-upstream", "--edit-description", "-t", "--track"})
_BRANCH_LISTS = frozenset({"-l", "--list", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"})
_TAG_WRITES = frozenset({"-d", "--delete", "-a", "--annotate", "-s", "--sign", "-f", "--force", "-m", "-F", "-u"})
_TAG_LISTS = frozenset({"-l", "--list", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"})
_CONFIG_READS = frozenset({"--get", "--get-all", "--get-regexp", "--get-urlmatch", "-l", "--list", "--get-color",
                           "--get-colorbool"})
_CONFIG_WRITES = frozenset({"--unset", "--unset-all", "--add", "--replace-all", "--rename-section", "--remove-section",
                            "-e", "--edit"})
_GLOBAL_VALUED = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"})


def git_problem(args: list[str]) -> str | None:
    """git の引数が書き込みなら、止めるわけ（見るだけなら None）。"""
    rest = list(args)
    while rest and rest[0].startswith("-"):
        option = rest[0]
        if option in ("-c", "--config-env") and len(rest) > 1 and rest[1].lower().startswith("alias."):
            return _refused("git の別名（alias）の設定")
        rest = rest[2:] if option in _GLOBAL_VALUED else rest[1:]
    if not rest:
        return None
    sub, more = rest[0], rest[1:]
    positional = [a for a in more if not a.startswith("-")]
    if sub in WRITING:
        return _refused(f"git {sub}")
    if sub in _READ_ONLY_SUBCOMMANDS:
        allowed = _READ_ONLY_SUBCOMMANDS[sub]
        if sub == "config":
            if set(more) & _CONFIG_WRITES or (positional[:1] and positional[0] in ("set", "unset", "rename-section",
                                                                                   "remove-section", "edit")):
                return _refused("git config の書き換え")
            if set(more) & _CONFIG_READS or (positional[:1] and positional[0] in allowed) or len(positional) <= 1:
                return None
            return _refused("git config の書き換え")
        if sub == "remote" and not positional and set(more) <= {"-v", "--verbose"}:
            return None
        if positional[:1] and positional[0] in allowed:
            return None
        return _refused(f"git {sub}" + (f" {positional[0]}" if positional else ""))
    if sub == "branch":
        if set(more) & _BRANCH_WRITES or (positional and not set(more) & _BRANCH_LISTS):
            return _refused("git branch でのブランチの作成・削除・名前の変更")
        return None
    if sub == "tag":
        if set(more) & _TAG_WRITES or (positional and not set(more) & _TAG_LISTS):
            return _refused("git tag でのタグの作成・削除")
        return None
    if sub == "symbolic-ref" and ("-d" in more or "--delete" in more or len(positional) > 1):
        return _refused("git symbolic-ref の書き換え")
    return None


def _refused(what: str) -> str:
    return (f"{what} はシェルからは使えません（git で書き込む操作は止めています）。{TOOLS_HINT}"
            "手伝いはコミット・提出をしません（タスクの持ち主がします）。")


DENIED = ecoagent.guard.Denied(
    programs={"ecobuild": f"シェルから ecobuild は使えません。{TOOLS_HINT}",
              "gh": f"シェルから gh は使えません。GitHub の操作も ECOBuild のツールで行います。{TOOLS_HINT}"},
    commands={"git": git_problem})


def hook(data: str) -> tuple[int, str]:
    """シェルのコマンド（フックの入力の JSON）を調べる。(終了コード, エージェントに伝える文)。止めるときは 2。"""
    return ecoagent.guard.hook_denied(data, DENIED)
