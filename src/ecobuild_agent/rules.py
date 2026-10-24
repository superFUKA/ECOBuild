"""モジュールのエージェント向けの決まり：全エージェント共通の文・登録ごとの文・登録ごとに使わせないツール。

登録（このPC全体）とは別に、モジュールのリポジトリに置いてコミットする（チームで共有し、PR で見直す）。
- .ecobuild/agents/common.md         全エージェント共通の文（基準・分け方の決まり 等）
- .ecobuild/agents/roles/<登録>.md    その登録のエージェントだけへの文（管理役への指示 等）
- .ecobuild/agents/tools.toml         [deny] <登録> = ["task_submit", "children_*"]：その登録に使わせないツール（fnmatch）
使わせないツールは、登録の tools で許したものを絞るだけ（広げられない）。

起動したエージェントに効くのは、作成元のブランチ（元の clone の ecobuild.toml の default_base）に取り込まれたもの
（GitHub の写し origin/<作成元>、なければ手元の作成元）。エージェントは自分の作業空間のファイル（タスクブランチ）を
書き換えられるので、作業空間のファイルは使わない。変えたものは、タスクブランチでコミットして PR で取り込むと効く。
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from ecobuild import config as _config
from ecobuild.errors import EcoBuildError, WorkError
from ecowork.git import Git

from . import registry
from .errors import ErrorCode

FOLDER = f"{_config.DIRECTORY}/agents"
COMMON_FILE = f"{FOLDER}/common.md"
ROLES_FOLDER = f"{FOLDER}/roles"
TOOLS_FILE = f"{FOLDER}/tools.toml"
_TOOL = re.compile(r"^[A-Za-z0-9_*?\[\]-]+$")


@dataclass(frozen=True)
class Rules:
    """common：全エージェント共通の文。roles：登録の名前 → その登録への文。deny：登録の名前 → 使わせないツール。"""
    common: str = ""
    roles: dict[str, str] = field(default_factory=dict)
    deny: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def text_for(self, name: str) -> str:
        return self.roles.get(name, "")

    def deny_for(self, name: str) -> tuple[str, ...]:
        return self.deny.get(name, ())


def role_path(name: str) -> str:
    return f"{ROLES_FOLDER}/{name}.md"


def read(root: Path | str) -> Rules:
    """作業ツリーにあるもの（GUI・CLI で見る・直すもの）。"""
    root = Path(root)

    def text(path: str) -> str | None:
        try:
            return (root / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as error:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{path} を読めません。", details=str(error)) from error

    roles = {}
    try:
        names = sorted(p.stem for p in (root / ROLES_FOLDER).glob("*.md") if p.is_file())
    except OSError:
        names = []
    for name in names:
        roles[name] = text(role_path(name)) or ""
    return _rules(text(COMMON_FILE), roles, text(TOOLS_FILE))


def in_force(workspace: Path | str) -> Rules:
    """起動したエージェントに効くもの：作成元のブランチに取り込まれたもの（読めなければ何もなし）。"""
    try:
        git = Git(Path(workspace))
        ref = _base_ref(git)
        if ref is None:
            return Rules()
        listed = git.run("ls-tree", "-r", "--name-only", ref, "--", FOLDER, check=False)
        if not listed.ok:
            return Rules()
        paths = set(listed.stdout.split("\n"))

        def show(path: str) -> str | None:
            if path not in paths:
                return None
            found = git.run("show", f"{ref}:{path}", check=False)
            return found.stdout if found.ok else None

        roles = {Path(p).stem: show(p) or "" for p in sorted(paths)
                 if p.startswith(ROLES_FOLDER + "/") and p.endswith(".md") and p.count("/") == ROLES_FOLDER.count("/") + 1}
        return _rules(show(COMMON_FILE), roles, show(TOOLS_FILE))
    except (WorkError, OSError, EcoBuildError):
        return Rules()


def _base_ref(git: Git) -> str | None:
    """作成元のブランチ（GitHub の写しがあればそちら）。作成元の名前は、元の clone（作業空間のエージェントからは
    見えない・書き換えられない）の ecobuild.toml から。"""
    try:
        base = _config.load(git.common_root() / _config.FILE_NAME).default_base
    except (EcoBuildError, OSError, ValueError):
        return None
    for ref in (f"refs/remotes/origin/{base}", f"refs/heads/{base}"):
        if git.rev_parse(ref):
            return ref
    return None


def _rules(common: str | None, roles: dict[str, str], tools: str | None) -> Rules:
    deny: dict[str, tuple[str, ...]] = {}
    if tools:
        try:
            data = tomllib.loads(tools)
        except tomllib.TOMLDecodeError as error:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{TOOLS_FILE} を読めません。", details=str(error)) from error
        table = data.get("deny", {})
        if not isinstance(table, dict):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{TOOLS_FILE} の deny は表です。")
        for name, values in table.items():
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{TOOLS_FILE} の deny.{name} は文字の並びです。")
            if values:
                deny[str(name)] = tuple(values)
    def lf(text: str) -> str:     # 取り出した作業ツリーは CRLF のことがある：比べられるように LF に
        return text.replace("\r\n", "\n")

    return Rules(common=lf(common or ""), roles={k: lf(v) for k, v in roles.items() if v.strip()}, deny=deny)


def apply(registration: registry.Registration, rules: Rules) -> registry.Registration:
    """登録に、モジュールで使わせないツールを重ねる（登録の tools より広がることはない）。"""
    added = rules.deny_for(registration.name)
    if not added:
        return registration
    return replace(registration, deny=tuple(dict.fromkeys((*registration.deny, *added))))


def effective(registration: registry.Registration, workspace: Path | str) -> registry.Registration:
    """その作業空間で起動したエージェントに効く登録（モジュールで使わせないツールを重ねたもの）。"""
    return apply(registration, in_force(workspace))


def write(root: Path | str, *, common: str | None = None, role: str = "", text: str | None = None,
          deny: tuple[str, ...] | None = None) -> list[str]:
    """作業ツリーに書く（common：共通の文。role と text：その登録への文。role と deny：使わせないツール）。
    空の文はファイルを消す。書いた・消したファイル（モジュールのルートからのパス）を返す。"""
    root = Path(root)
    if (text is not None or deny is not None) and not role:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "どの登録への文・ツールかを指定してください（--role）。")
    if role:
        registry._check_name(role)
    changed: list[str] = []
    if common is not None:
        changed += _put(root, COMMON_FILE, common)
    if text is not None:
        changed += _put(root, role_path(role), text)
    if deny is not None:
        bad = [p for p in deny if not _TOOL.match(p)]
        if bad:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "ツールの名前ではありません：" + "、".join(bad),
                                hint="ツールの名前（task_submit 等）か、* ? [ ] の fnmatch です。")
        current = read(root).deny
        current = {**current, role: tuple(dict.fromkeys(deny))} if deny else {k: v for k, v in current.items() if k != role}
        changed += _put(root, TOOLS_FILE, _toml(current))
    return changed


def tool_list(root: Path | str, program) -> list[tuple[str, str, str]]:
    """エージェントに渡せるツールの全部（名前・印〔read・change・owner・children〕・説明。使わせないものを選ぶ画面）。
    コマンドのツールは ecobuild -C <root> --help --json から（MCP サーバーと同じ）、子を扱うツールは children から。"""
    from . import children, mcp
    catalog = mcp.read_catalog(mcp.runner(program, Path(root)))
    found = [(tool.name, mark, tool.description) for mark, tool in mcp.command_tools(catalog, lambda argv: {})]
    found += [(name, "children", children.DESCRIPTIONS.get(name, "")) for name in children.TOOLS]
    return list({name: (name, mark, text) for name, mark, text in found}.values())


def view(root: Path | str, *, program=None, changed: tuple[str, ...] = (), committed: str = ""):
    """CLI の結果（results.AgentRules）：作業ツリーのもの、効く版、登録ごとの文・使わせないツール。
    program があれば、渡せるツールの一覧も（tool_list）。"""
    from .results import AgentRoleRules, AgentRules, AgentTool
    root = Path(root)
    here, force = read(root), in_force(root)
    try:
        ref = _base_ref(Git(root)) or ""
    except (WorkError, OSError):
        ref = ""
    known = {r.name: r for r in registry.list_registrations()}
    names = sorted({*known, *here.roles, *here.deny})
    roles = tuple(AgentRoleRules(name=name, title=known[name].title if name in known else name, text=here.text_for(name),
                                 deny=here.deny_for(name), tools=known[name].tools if name in known else ())
                  for name in names)
    tools = tuple(AgentTool(*t) for t in tool_list(root, program)) if program else ()
    return AgentRules(root=root, in_force=ref.removeprefix("refs/remotes/").removeprefix("refs/heads/"),
                      pending=here != force, common=here.common, roles=roles, tools=tools, changed=changed,
                      committed=committed)


def _put(root: Path, path: str, text: str) -> list[str]:
    """中身が変わるときだけ書く（空なら消す）。"""
    target = root / path
    body = text.strip()
    try:
        before = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        before = None
    if not body:
        if before is None:
            return []
        target.unlink()
        return [path]
    body += "\n"
    if before == body:
        return []
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    return [path]


def _toml(deny: dict[str, tuple[str, ...]]) -> str:
    if not deny:
        return ""
    lines = ["# 登録ごとに使わせないツール（ecobuild agent rules。登録の tools で許したものを絞るだけ）", "[deny]"]
    lines += [f"{name} = [" + ", ".join(json.dumps(v, ensure_ascii=False) for v in values) + "]"
              for name, values in sorted(deny.items())]
    return "\n".join(lines)
