"""ボード（GitHub Projects）：タスクの計画の情報（状態・優先度・期限等）を置く場所。

タスク＝Issue（1対1）で、ボードの項目はIssueを指すだけ。状態（Status）のうち、作業の段階（未着手・作業中・
レビュー待ち・完了）は作業の流れの操作（task start・task submit・task merge 等）が書き換え、手では動かさない。
それ以外の選択肢（Backlog 等の計画の段階）と、他のフィールド（優先度・期限等）は人・エージェントが決める。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import model as _model
from .errors import ErrorCode, TaskError

# 作業の段階
TODO, IN_PROGRESS, IN_REVIEW, DONE = "todo", "in_progress", "in_review", "done"
STAGES = (TODO, IN_PROGRESS, IN_REVIEW, DONE)

# 段階に当てる選択肢を省略したときに探す名前（大文字・小文字・空白は区別しない）。最初に見つかったもの
DEFAULT_OPTIONS = {
    TODO: ("Todo", "To do", "Ready", "Backlog"),
    IN_PROGRESS: ("In Progress", "Doing", "作業中"),
    IN_REVIEW: ("In Review", "Review", "レビュー待ち"),
    DONE: ("Done", "Completed", "完了"),
}

# 標準のボード（board create）：Status と Priority の選択肢（名前・色・説明）
STANDARD_STATUS = (("Backlog", "GRAY", "計画中"), ("Todo", "BLUE", "未着手"), ("In Progress", "YELLOW", "作業中"),
                   ("In Review", "PURPLE", "レビュー待ち"), ("Done", "GREEN", "完了"))
STANDARD_PRIORITY = (("High", "RED", "高"), ("Middle", "YELLOW", "中"), ("Low", "GRAY", "低"))

# task field set で設定できるフィールドの型（担当者・ラベル等は task edit で変える）
SETTABLE = ("TEXT", "NUMBER", "DATE", "SINGLE_SELECT", "ITERATION")

_URL = re.compile(r"https://github\.com/(?:users|orgs)/([^/]+)/projects/(\d+)/?")


@dataclass(frozen=True)
class BoardSettings:
    """モジュールが使うボード（ecobuild.toml の [board]）。"""
    url: str                                   # https://github.com/users/<所有者>/projects/<番号>
    status_field: str = "Status"
    stages: dict[str, str] = field(default_factory=dict)   # 段階 → 選択肢の名前（in_review は省略可）
    schema: dict[str, str] = field(default_factory=dict)   # 役割（ecotask.model.ROLES）→ 項目の名前
    shared: bool = False                       # 他のリポジトリと共有するボード（専用でなくてよい）

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
        raise TaskError(ErrorCode.INVALID_ARGUMENT, f"ボードのURL {url} が読めません。",
                        hint="https://github.com/users/<所有者>/projects/<番号>（組織なら /orgs/）の形で指定してください。")
    return match.group(1), int(match.group(2))


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
        """名前かIDでフィールドを探す。名前は大文字・小文字を区別しない（同じ名前が複数あればIDを求める）。"""
        by_id = [f for f in self.fields if f.id == name_or_id]
        if by_id:
            return by_id[0]
        named = [f for f in self.fields if f.name.casefold() == name_or_id.casefold()]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"フィールド {name_or_id} が複数あります。IDで指定してください。",
                            details=[f"{f.id} {f.name}（{f.type}）" for f in named])
        raise TaskError(ErrorCode.FIELD_NOT_FOUND, f"ボードにフィールド {name_or_id} がありません。",
                        details=[f"{f.name}（{f.type}）" for f in self.fields if f.type in SETTABLE])


def find_option(field_: BoardField, value: str) -> BoardOption:
    """単一選択の選択肢・イテレーションの期間を、名前かIDで探す。"""
    for option in field_.options:
        if option.id == value or option.name.casefold() == value.casefold():
            return option
    raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{field_.name} に選択肢 {value} はありません。",
                    details=[o.name for o in field_.options])


# 役割に既定で当てる項目の名前（最初のものが board create の標準。大文字・小文字は区別しない）
DEFAULT_SCHEMA = {_model.PRIORITY: ("Priority",), _model.DUE: ("Due",), _model.ESTIMATE: ("Estimate",),
                  _model.SPRINT: ("Sprint",), _model.PLANNED_START: ("Planned Start", "Start date"),
                  _model.PLANNED_END: ("Planned End", "Target date", "End date"), _model.STARTED: ("Started",)}
# 名前で見つからないとき、その型の項目が1つだけならそれを当てる役割（日付は期限だけ）
_ONLY_OF_TYPE = (_model.DUE, _model.ESTIMATE, _model.SPRINT)


def standard_fields() -> tuple[tuple[str, str], ...]:
    """標準のボードの、計画・記録の項目（名前・型。ROLES の順）。選択肢・期間は board create が決める。"""
    return tuple((DEFAULT_SCHEMA[role][0], _model.ROLE_TYPES[role]) for role in _model.ROLES)


def default_schema(info: "BoardInfo", *, status_field: str = "Status") -> dict[str, str]:
    """役割に当てる項目：既定の名前で型が合うもの、なければ（期限・見積もり・スプリントは）その型の項目が1つだけならそれ。"""
    result = {}
    for role, kind in _model.ROLE_TYPES.items():
        names = [n.casefold() for n in DEFAULT_SCHEMA[role]]
        named = sorted((f for f in info.fields if f.name.casefold() in names and f.type == kind),
                       key=lambda f: names.index(f.name.casefold()))
        typed = [f for f in info.fields if f.type == kind and f.name != status_field]
        found = named[0] if named else (typed[0] if len(typed) == 1 and role in _ONLY_OF_TYPE else None)
        if found is not None:
            result[role] = found.name
    return result


def default_stages(status: BoardField) -> dict[str, str]:
    """Status の選択肢から、段階に当てるものを既定の名前で探す。"""
    def key(name: str) -> str:
        return re.sub(r"\s+", "", name).casefold()

    names = {key(o.name): o.name for o in status.options}
    result = {}
    for stage, candidates in DEFAULT_OPTIONS.items():
        found = next((names[key(c)] for c in candidates if key(c) in names), None)
        if found is not None:
            result[stage] = found
    return result


@dataclass(frozen=True)
class BoardItem:
    """ボード上のタスク（Issue）。values はフィールドの名前 → 表示の値。"""
    id: str
    values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskBoard:
    """タスクのボード上の値（task field set／clear の結果）。"""
    number: int
    item_id: str
    values: dict[str, str]


@dataclass(frozen=True)
class BoardStatus:
    """board show の結果：つないでいるボード、フィールドの定義、作業の段階に当てた選択肢。"""
    url: str
    title: str
    status_field: str
    stages: dict[str, str]
    fields: tuple[BoardField, ...]
    schema: dict[str, str] = field(default_factory=dict)   # 役割 → 項目の名前（当てていない役割は使わない）
    scope: "BoardScope | None" = None          # このリポジトリ専用か（リンク・項目のリポジトリ・公開）


@dataclass(frozen=True)
class BoardScope:
    """ボードがこのリポジトリ専用か。GitHubでは制限できないので、ECOBuildが確かめて守る。"""
    repository: str                            # このリポジトリ（所有者/名前）
    linked: tuple[str, ...]                    # ボードがリンクしているリポジトリ
    items: dict[str, int]                      # 項目のリポジトリごとの数（"" は下書き）
    public: bool                               # ボードが公開
    repository_private: bool
    shared: bool                               # 共有を許した（[board] の shared）
    other_boards: tuple[str, ...] = ()         # このリポジトリにリンクしている、他のボード（URL）

    @property
    def other_links(self) -> tuple[str, ...]:
        return tuple(r for r in self.linked if r != self.repository)

    @property
    def foreign_items(self) -> int:
        """このリポジトリ以外（他のリポジトリ・下書き）の項目の数。"""
        return sum(n for r, n in self.items.items() if r != self.repository)

    @property
    def problems(self) -> tuple[str, ...]:
        """専用でない・公開しすぎている点（共有を許していれば、共有の点は除く）。"""
        result = []
        if not self.shared and self.other_links:
            result.append(f"他のリポジトリにもリンクしています：{', '.join(self.other_links)}")
        if not self.shared and self.foreign_items:
            result.append(f"他のリポジトリの項目・下書きが {self.foreign_items} 件あります")
        if self.repository not in self.linked:
            result.append(f"このリポジトリ（{self.repository}）にリンクしていません")
        if self.other_boards:
            result.append(f"このリポジトリには他のボードもリンクしています：{', '.join(self.other_boards)}"
                          "（使わないなら、GitHubでリンクを外すか削除してください）")
        if self.public and self.repository_private:
            result.append("リポジトリは非公開ですが、ボードは公開されています（ボードの設定で非公開にしてください）")
        return tuple(result)


@dataclass(frozen=True)
class BoardChange:
    number: int
    title: str
    before: str | None
    after: str


@dataclass(frozen=True)
class BoardSyncResult:
    added: tuple[int, ...]                     # ボードに加えたタスク
    changed: tuple[BoardChange, ...]           # 状態を作業の段階に合わせたもの
    dry_run: bool
