"""ボード（GitHub Projects）：タスクの計画の情報（状態・優先度・期限等）を置く場所。

タスク＝Issue（1対1）で、ボードの項目はIssueを指すだけ。状態（Status）のうち、作業の段階（未着手・作業中・
レビュー待ち・完了）は作業の流れの操作（task start・task submit・task merge 等）が書き換え、手では動かさない。
それ以外の選択肢（Backlog 等の計画の段階）と、他のフィールド（優先度・期限等）は人・エージェントが決める。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import ErrorCode, WorkError

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

_URL = re.compile(r"https://github\.com/(?:users|orgs)/([^/]+)/projects/(\d+)/?")


@dataclass(frozen=True)
class BoardSettings:
    """モジュールが使うボード（ecobuild.toml の [board]）。"""
    url: str                                   # https://github.com/users/<所有者>/projects/<番号>
    status_field: str = "Status"
    stages: dict[str, str] = field(default_factory=dict)   # 段階 → 選択肢の名前（in_review は省略可）

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
        raise WorkError(ErrorCode.INVALID_ARGUMENT, f"ボードのURL {url} が読めません。",
                        hint="https://github.com/users/<所有者>/projects/<番号>（組織なら /orgs/）の形で指定してください。")
    return match.group(1), int(match.group(2))


@dataclass(frozen=True)
class BoardOption:
    id: str
    name: str


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

    def field(self, name_or_id: str) -> BoardField:
        """名前かIDでフィールドを探す。名前は大文字・小文字を区別しない（同じ名前が複数あればIDを求める）。"""
        by_id = [f for f in self.fields if f.id == name_or_id]
        if by_id:
            return by_id[0]
        named = [f for f in self.fields if f.name.casefold() == name_or_id.casefold()]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"フィールド {name_or_id} が複数あります。IDで指定してください。",
                            details=[f"{f.id} {f.name}（{f.type}）" for f in named])
        raise WorkError(ErrorCode.FIELD_NOT_FOUND, f"ボードにフィールド {name_or_id} がありません。",
                        details=[f"{f.name}（{f.type}）" for f in self.fields])


def find_option(field_: BoardField, value: str) -> BoardOption:
    """単一選択の選択肢・イテレーションの期間を、名前かIDで探す。"""
    for option in field_.options:
        if option.id == value or option.name.casefold() == value.casefold():
            return option
    raise WorkError(ErrorCode.INVALID_ARGUMENT, f"{field_.name} に選択肢 {value} はありません。",
                    details=[o.name for o in field_.options])


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
