"""モジュールのエージェント向けの決まり：全エージェント共通の文（.ecobuild/agents/common.md。コミットする）。

役ごとの文・渡すツールは、モジュールの登録（registry。.ecobuild/agents/registry/）の文書と tools。
起動したエージェントに効くのは、登録と同じく作成元のブランチに取り込まれたもの（registry.in_force_text）。
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from ecobuild import config as _config
from ecobuild.errors import EcoBuildError

from . import registry
from .errors import ErrorCode

FOLDER = f"{_config.DIRECTORY}/agents"
COMMON_FILE = f"{FOLDER}/common.md"


def read(root: Path | str) -> str:
    """作業ツリーにある共通の文（GUI・CLI で見る・直すもの。なければ空）。"""
    try:
        return (Path(root) / COMMON_FILE).read_text(encoding="utf-8").replace("\r\n", "\n")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{COMMON_FILE} を読めません。", details=str(error)) from error


def in_force(workspace: Path | str) -> str:
    """起動したエージェントに渡す共通の文：作成元のブランチに取り込まれたもの（なければ空）。"""
    return registry.in_force_text(workspace, COMMON_FILE) or ""


def write(root: Path | str, common: str) -> list[str]:
    """作業ツリーに書く（空ならファイルを消す）。変えたファイル（モジュールのルートからのパス）を返す。"""
    target = Path(root) / COMMON_FILE
    body = common.strip()
    try:
        before = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        before = None
    if not body:
        if before is None:
            return []
        target.unlink()
        return [COMMON_FILE]
    body += "\n"
    if before == body:
        return []
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    return [COMMON_FILE]


# ツールのまとまり（何についてのツールか。名前の始まりで分ける。どれにも合わなければ「そのほか」）
TOOL_AREAS = (
    ("状態・履歴を見る", ("status", "diff", "log", "show", "blame", "branch_", "stash_", "module_")),
    ("タスク", ("task_",)),
    ("ファイル", ("file_",)),
    ("ビルド・試験", ("build", "clean", "rebuild", "run", "test", "check", "profile_")),
    ("取り込み（GitHub の最新）", ("sync",)),
    ("CI", ("ci_",)),
    ("子のエージェント・親への報告", ("children_", "report_to_parent")),
)
OTHER_AREA = "そのほか"
TOO_MANY_TOOLS = 30     # ツールの定義がこれを超えると、エージェントのツールの選び方が落ちやすい


def tool_area(name: str) -> str:
    """ツールが何についてのものか（選ぶ画面のまとまりの名前）。"""
    return next((label for label, starts in TOOL_AREAS if name.startswith(starts)), OTHER_AREA)


def tool_fit(root: Path | str, name: str, tools: tuple[str, ...] | None, all_tools: list[tuple[str, str, str]]) -> dict:
    """登録 name に渡すツールを tools にすると、どうなるか（tools が None なら今の並び）。何も変えない。
    count・total・owner：渡るツールの数・今あるツールの数・そのうちブランチを変えるツールの数。
    stronger：この登録より強くなる（子にできない）登録。parents：この登録を子に持つのに、弱くなる登録。"""
    from dataclasses import replace

    current = registry.load(name, root)
    new = current if tools is None else replace(current, tools=tuple(tools))
    given = [(tool, mark) for tool, mark, _ in all_tools if registry.allows_tool(new, tool)]
    others = [r for r in registry.list_registrations(root) if r.name != name]
    return {
        "name": name, "tools": new.tools, "count": len(given), "total": len(all_tools),
        "owner": sum(1 for _, mark in given if mark == "owner"),
        "limit": TOO_MANY_TOOLS, "too_many": len(given) > TOO_MANY_TOOLS,
        "stronger": tuple(r.name for r in others if registry.stronger(r, new)),
        "parents": tuple(r.name for r in others if name in r.children and registry.stronger(new, r)),
    }


def tools_without_owner(patterns: tuple[str, ...], all_tools: list[tuple[str, str, str]]) -> tuple[str, ...]:
    """patterns で渡るツールから、ブランチを変える（コミット・push・提出）ツールを除いた名前の並び。"""
    return tuple(tool for tool, mark, _ in all_tools
                 if mark != "owner" and any(fnmatch.fnmatchcase(tool, pattern) for pattern in patterns))


def tool_list(root: Path | str | None, program) -> list[tuple[str, str, str]]:
    """エージェントに渡せるツールの全部（名前・印〔read・change・owner・children〕・説明。渡すツールを選ぶ画面）。
    コマンドのツールは ecobuild -C <root> --help --json から（MCP サーバーと同じ）、子を扱うツールは children から。
    root がなければ（モジュールの外：プリセット）、すべての型のコマンドのツール。"""
    from . import children, mcp
    catalog = mcp.read_catalog(mcp.runner(program, Path(root) if root else Path.cwd()))
    catalogs = [catalog] if root else [{**catalog, "type": name} for name in [None, *(catalog.get("types") or {})]]
    found = [(tool.name, mark, tool.description) for one in catalogs
             for mark, tool in mcp.command_tools(one, lambda argv: {})]
    found += [(name, "children", children.DESCRIPTIONS.get(name, "")) for name in children.TOOLS]
    return list({name: (name, mark, text) for name, mark, text in found}.values())
