"""モジュールのエージェント向けの決まり：全エージェント共通の文（.ecobuild/agents/common.md。コミットする）。

役ごとの文・渡すツールは、モジュールの登録（registry。.ecobuild/agents/registry/）の文書と tools。
起動したエージェントに効くのは、登録と同じく作成元のブランチに取り込まれたもの（registry.in_force_text）。
"""

from __future__ import annotations

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
