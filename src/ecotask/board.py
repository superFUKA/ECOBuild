"""ボード（GitHub Projects）：タスクの計画の情報（状態・優先度・期限等）をGitHubに置くための、内部の保存場所。

利用者はタスクだけを扱い、ボードという概念は見せない（コマンド・表示・エラーに出さない）。ECOBuildは、
リポジトリにリンクした決まった形のボード（印：説明の MARKER）を自分で作り、見つけて使う。GitHubのサイトで
直接変えられた値はそのまま読み、作業の段階のずれだけ直す。

タスク＝Issue（1対1）で、ボードの項目はIssueを指すだけ。状態（Status）のうち、作業の段階（未着手・作業中・
レビュー待ち・完了）は作業の流れの操作（task start・task submit・task merge 等）が書き換える。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import model as _model
from .errors import ErrorCode, TaskError

# 作業の段階
TODO, IN_PROGRESS, IN_REVIEW, DONE = "todo", "in_progress", "in_review", "done"
STAGES = (TODO, IN_PROGRESS, IN_REVIEW, DONE)

# ECOBuildのボードの印（ボードの説明の先頭）。リポジトリにリンクしたボードのうち、これで始まるものを使う
MARKER = "ECOBuild"
DESCRIPTION = MARKER + " がタスク管理の情報を置く場所です。ECOBuild のコマンドから使います。"

# 段階に当てる選択肢として探す名前（大文字・小文字・空白は区別しない）。最初に見つかったもの
DEFAULT_OPTIONS = {
    TODO: ("Todo", "To do", "Ready", "Backlog"),
    IN_PROGRESS: ("In Progress", "Doing", "作業中"),
    IN_REVIEW: ("In Review", "Review", "レビュー待ち"),
    DONE: ("Done", "Completed", "完了"),
}

# 決まった形のボード：Status と Priority の選択肢（名前・色・説明）
STANDARD_STATUS = (("Backlog", "GRAY", "計画中"), ("Todo", "BLUE", "未着手"), ("In Progress", "YELLOW", "作業中"),
                   ("In Review", "PURPLE", "レビュー待ち"), ("Done", "GREEN", "完了"))
STANDARD_PRIORITY = (("High", "RED", "高"), ("Middle", "YELLOW", "中"), ("Low", "GRAY", "低"))
PRIORITIES = tuple(name for name, _, _ in STANDARD_PRIORITY)
STATUS_FIELD = "Status"

# 役割に当てる項目の名前（最初のものが決まった形の名前。以前の board create・GitHubの既定の名前も当てる）
DEFAULT_SCHEMA = {_model.PRIORITY: ("Priority",), _model.DUE: ("Due",), _model.ESTIMATE: ("Estimate",),
                  _model.SPRINT: ("Sprint",), _model.PLANNED_START: ("Planned Start", "Start date"),
                  _model.PLANNED_END: ("Planned End", "Target date", "End date"), _model.STARTED: ("Started",)}

_URL = re.compile(r"https://github\.com/(?:users|orgs)/([^/]+)/projects/(\d+)/?")


@dataclass(frozen=True)
class BoardSettings:
    """使うボードと、項目の当て方（ボードの定義から決める。保存しない）。"""
    url: str                                   # https://github.com/users/<所有者>/projects/<番号>
    status_field: str = STATUS_FIELD
    stages: dict[str, str] = field(default_factory=dict)   # 段階 → 選択肢の名前（in_review は省略可）
    schema: dict[str, str] = field(default_factory=dict)   # 役割（ecotask.model.ROLES）→ 項目の名前
    planned: str | None = None                 # 計画中に当てる選択肢（段階に当てていない最初のもの。Backlog）

    @property
    def owner(self) -> str:
        return parse_url(self.url)[0]

    @property
    def number(self) -> int:
        return parse_url(self.url)[1]

    def option(self, stage: str) -> str | None:
        """段階に当てた選択肢。レビュー待ちを当てていなければ作業中のもの。"""
        if stage == IN_REVIEW and not self.stages.get(IN_REVIEW):
            return self.stages.get(IN_PROGRESS)
        return self.stages.get(stage)

    @property
    def stage_options(self) -> set[str]:
        return {name for name in self.stages.values() if name}


def parse_url(url: str) -> tuple[str, int]:
    match = _URL.fullmatch(url.strip())
    if match is None:
        raise TaskError(ErrorCode.INVALID_ARGUMENT, f"GitHubのタスク管理の情報の場所 {url} が読めません。")
    return match.group(1), int(match.group(2))


@dataclass(frozen=True)
class BoardRef:
    """リポジトリにリンクしたボード（見つけるための要約）。"""
    url: str
    description: str = ""
    closed: bool = False

    @property
    def ours(self) -> bool:
        return not self.closed and self.description.startswith(MARKER)


@dataclass(frozen=True)
class BoardOption:
    id: str
    name: str
    start: str | None = None                   # イテレーションの期間の始まり（YYYY-MM-DD）
    duration: int | None = None                # イテレーションの日数


@dataclass(frozen=True)
class BoardField:
    id: str
    name: str
    type: str                                  # TEXT / NUMBER / DATE / SINGLE_SELECT / ITERATION / その他（読むだけ）
    options: tuple[BoardOption, ...] = ()      # 単一選択の選択肢、イテレーションの期間（id・題名）


@dataclass(frozen=True)
class BoardInfo:
    id: str
    number: int
    title: str
    url: str
    fields: tuple[BoardField, ...] = ()
    closed: bool = False
    public: bool = False                       # 公開のボード（誰でも見られる）
    repositories: tuple[str, ...] = ()         # リンクしているリポジトリ（所有者/名前）

    def field(self, name_or_id: str) -> BoardField:
        """名前かIDで項目を探す。名前は大文字・小文字を区別しない。"""
        for f in self.fields:
            if f.id == name_or_id or f.name.casefold() == name_or_id.casefold():
                return f
        raise TaskError(ErrorCode.FIELD_NOT_FOUND, f"GitHubのタスク管理の情報に {name_or_id} がありません。")


def find_option(field_: BoardField, value: str) -> BoardOption:
    """単一選択の選択肢・イテレーションの期間を、名前かIDで探す。"""
    for option in field_.options:
        if option.id == value or option.name.casefold() == value.casefold():
            return option
    raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{value} は使えません。", details=[o.name for o in field_.options])


def standard_fields() -> tuple[tuple[str, str], ...]:
    """決まった形のボードの、計画・記録の項目（名前・型。ROLES の順）。"""
    return tuple((DEFAULT_SCHEMA[role][0], _model.ROLE_TYPES[role]) for role in _model.ROLES)


def default_schema(info: BoardInfo) -> dict[str, str]:
    """役割に当てる項目：決まった名前（以前の名前を含む）で型が合うもの。"""
    result = {}
    for role, kind in _model.ROLE_TYPES.items():
        names = [n.casefold() for n in DEFAULT_SCHEMA[role]]
        named = sorted((f for f in info.fields if f.name.casefold() in names and f.type == kind),
                       key=lambda f: names.index(f.name.casefold()))
        if named:
            result[role] = named[0].name
    return result


def default_stages(status: BoardField) -> dict[str, str]:
    """Status の選択肢から、段階に当てるものを決まった名前で探す。"""
    def key(name: str) -> str:
        return re.sub(r"\s+", "", name).casefold()

    names = {key(o.name): o.name for o in status.options}
    result = {}
    for stage, candidates in DEFAULT_OPTIONS.items():
        found = next((names[key(c)] for c in candidates if key(c) in names), None)
        if found is not None:
            result[stage] = found
    return result


def settings_of(info: BoardInfo) -> BoardSettings:
    """ボードの定義から、項目の当て方を決める。"""
    status = next((f for f in info.fields if f.name.casefold() == STATUS_FIELD.casefold()
                   and f.type == "SINGLE_SELECT"), None)
    stages = {} if status is None else default_stages(status)
    planned = None if status is None else next(
        (o.name for o in status.options if o.name not in stages.values()), None)
    return BoardSettings(info.url, STATUS_FIELD, stages, default_schema(info), planned)


@dataclass(frozen=True)
class BoardItem:
    """ボード上のタスク（Issue）。values は項目の名前 → 表示の値。"""
    id: str
    values: dict[str, str] = field(default_factory=dict)
