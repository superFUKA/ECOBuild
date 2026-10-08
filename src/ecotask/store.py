"""保存の層：GitHubをタスクのデータベースとして使う。

読み：GitHubのデータ（Issue・親子と依存の要約・マイルストーン・ボードの値）を、まとめて Task にする。
書き：計画の値（優先度・期限・見積もり・スプリント）と状態を、ボードの項目の型を確かめて書く。
どの項目が何の役割か（スキーマ）は、ボードの設定（BoardSettings.schema）で決める。
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import replace
from pathlib import Path

from . import board as _board
from . import github as _github
from . import model as _model
from .errors import ErrorCode, TaskError


class TaskStore:
    def __init__(self, root: Path, github: _github.TaskGitHub, board: _board.BoardSettings | None = None):
        self.root = root
        self.github = github
        self._board = board
        self._info: _board.BoardInfo | None = None

    # ボードの設定と定義 ----------------------------------------------------------------

    @property
    def board(self) -> _board.BoardSettings | None:
        return self._board

    @board.setter
    def board(self, value: _board.BoardSettings | None) -> None:
        self._board = value
        self._info = None

    def info(self) -> _board.BoardInfo:
        """つないでいるボードの定義（項目・選択肢）。1回読んだら覚える。"""
        settings = self._require()
        if self._info is None:
            self._info = self.github.get_board(self.root, settings.owner, settings.number)
        return self._info

    def role_field(self, role: str) -> _board.BoardField | None:
        """役割（priority 等）に当てた項目。当てていなければNone。"""
        if self._board is None or not self._board.schema.get(role):
            return None
        return self.info().field(self._board.schema[role])

    def sprints(self) -> list[_model.Sprint]:
        """スプリント（始まりの順）。スプリントの役割を当てていなければ空。"""
        sprint = self.role_field(_model.SPRINT)
        if sprint is None:
            return []
        return sorted((_sprint(o) for o in sprint.options if o.start and o.duration), key=lambda s: s.start)

    # 読み ----------------------------------------------------------------------------

    def tasks(self, *, closed: bool = False) -> list[_model.Task]:
        """タスクの一覧（番号の順）。closed なら閉じたものも。"""
        board_id = None if self._board is None else self.info().id
        records = self.github.task_records(self.root, closed=closed, board_id=board_id)
        return sorted((self._task(r) for r in records), key=lambda t: t.number)

    def task(self, number: int) -> _model.Task:
        board_id = None if self._board is None else self.info().id
        return self._task(self.github.task_records(self.root, closed=True, board_id=board_id, number=number)[0])

    def _task(self, record: _github.TaskRecord) -> _model.Task:
        issue, r = record.issue, record.relations
        values = {} if record.item is None else dict(record.item.values)
        status = stage = priority = None
        rank = due = estimate = sprint = None
        if self._board is not None:
            info = self.info()
            status = values.pop(info.field(self._board.status_field).name, None)
            stage = self.stage_of(status)
            field = self.role_field(_model.PRIORITY)
            if field is not None:
                priority = values.pop(field.name, None)
                names = [o.name for o in field.options]
                rank = names.index(priority) if priority in names else None
            field = self.role_field(_model.DUE)
            if field is not None:
                due = _model.parse_date(values.pop(field.name, None))
            field = self.role_field(_model.ESTIMATE)
            if field is not None and field.name in values:
                estimate = float(values.pop(field.name))
            field = self.role_field(_model.SPRINT)
            if field is not None and field.name in values:
                name = values.pop(field.name)
                sprint = next((s for s in self.sprints() if s.name == name), None)
        return _model.Task(issue.number, issue.title, issue.url, issue.state, record.closed_reason, stage, status,
                           priority, rank, due, estimate, sprint, issue.milestone,
                           _model.parse_date(record.milestone_due), issue.labels, issue.assignees, r.parent,
                           r.sub_total, r.sub_completed, r.blocked_by, r.blocking, record.item is not None, values)

    def stage_of(self, status: str | None) -> str | None:
        """ボードの状態の選択肢 → 作業の段階（当てていない選択肢は planned）。"""
        if status is None or self._board is None:
            return None
        for stage in (_model.DONE, _model.IN_REVIEW, _model.IN_PROGRESS, _model.TODO):
            if self._board.stages.get(stage) == status:
                return stage
        return _model.PLANNED

    # 書き ----------------------------------------------------------------------------

    def item(self, number: int, *, add: bool = False) -> _board.BoardItem:
        """タスクのボードの項目。add なら、なければ加える（なくて add でなければ not_on_board）。"""
        info = self.info()
        if add:
            return self.github.add_board_item(self.root, number, info.id)
        item = self.github.board_item(self.root, number, info.id)
        if item is None:
            raise TaskError(ErrorCode.NOT_ON_BOARD, f"#{number} はボードにありません。",
                            hint="board sync で、開いているタスクをボードに加えられます。")
        return item

    def write(self, item: _board.BoardItem, field: _board.BoardField, value: str) -> None:
        """項目に値を書く（型に合わなければ invalid_argument）。"""
        self.github.set_board_value(self.root, self.info().id, item.id, field, value)

    def clear(self, item: _board.BoardItem, field: _board.BoardField) -> None:
        self.github.clear_board_value(self.root, self.info().id, item.id, field.id)

    def plan(self, number: int, *, priority: str | None = None, due: str | None = None,
             estimate: str | None = None, sprint: str | None = None, clear: tuple[str, ...] = ()) -> dict[str, str | None]:
        """計画の値を書く。sprint は名前か current（今日を含む）。clear：消す役割。ボードになければ加える。

        書いた値（役割 → 値。消したものは None）を返す。GitHubは書いた直後の読み取りで古い値を返すことがあるため、
        呼び出し側はこれを読み直した Task に重ねる（apply）。
        """
        values = {_model.PRIORITY: priority, _model.DUE: due, _model.ESTIMATE: estimate, _model.SPRINT: sprint}
        unknown = [role for role in clear if role not in _model.ROLES]
        if unknown:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"消す値 {', '.join(unknown)} はありません。",
                            hint=f"{'・'.join(_model.ROLES)} から選んでください。")
        both = [role for role in clear if values[role] is not None]
        if both:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{', '.join(both)} の設定と消去は同時にできません。")
        if all(v is None for v in values.values()) and not clear:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "設定する値がありません。",
                            hint="--priority・--due・--estimate・--sprint・--clear のどれかを指定してください。")
        fields = {}
        for role in [r for r, v in values.items() if v is not None] + list(clear):
            field = self.role_field(role)
            if field is None:
                raise TaskError(ErrorCode.FIELD_NOT_FOUND,
                                f"ボードに{_model.ROLE_NAMES[role]}（{role}）の項目が当てられていません。",
                                hint="ボードに項目を足して、作業空間で board use をやり直してください"
                                     "（board create の標準のボードには、すべてあります）。")
            fields[role] = field
        if sprint == "current":
            today = _datetime.date.today()
            current = next((s for s in self.sprints() if s.contains(today)), None)
            if current is None:
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"今日（{today.isoformat()}）を含むスプリントがありません。")
            values[_model.SPRINT] = current.name
        item = self.item(number, add=True)
        written = {}
        for role, value in values.items():
            if value is not None:
                self.write(item, fields[role], value)
                written[role] = value
        for role in clear:
            self.clear(item, fields[role])
            written[role] = None
        return written

    def apply(self, task: _model.Task, written: dict[str, str | None]) -> _model.Task:
        """書いた値を Task に重ねる（書いた直後の読み取りが古くても、正しい値を返すため）。"""
        changes = {}
        if _model.PRIORITY in written:
            value = written[_model.PRIORITY]
            field = self.role_field(_model.PRIORITY)
            option = None if value is None else _board.find_option(field, value)
            changes["priority"] = None if option is None else option.name
            changes["priority_rank"] = None if option is None else [o.name for o in field.options].index(option.name)
        if _model.DUE in written:
            changes["due"] = _model.parse_date(written[_model.DUE])
        if _model.ESTIMATE in written:
            changes["estimate"] = None if written[_model.ESTIMATE] is None else float(written[_model.ESTIMATE])
        if _model.SPRINT in written:
            value = written[_model.SPRINT]
            changes["sprint"] = None if value is None else next(
                (s for s in self.sprints() if s.name.casefold() == value.casefold()), None)
        return replace(task, on_board=True, **changes)

    def _require(self) -> _board.BoardSettings:
        if self._board is None:
            raise TaskError(ErrorCode.NO_BOARD, "ボード（GitHub Projects）をつないでいません。",
                            hint="board list で一覧を見て、board use <URL> でつなぎます（なければ board create）。")
        return self._board


def _sprint(option: _board.BoardOption) -> _model.Sprint:
    start = _datetime.date.fromisoformat(option.start)
    return _model.Sprint(option.name, start, start + _datetime.timedelta(days=option.duration))
