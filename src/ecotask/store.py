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
        plan = {}
        status = stage = None
        if self._board is not None:
            status = values.pop(self.info().field(self._board.status_field).name, None)
            stage = self.stage_of(status)
            for role in _model.ROLES:
                field = self.role_field(role)
                if field is not None and field.name in values:
                    plan.update(self._value(role, field, values.pop(field.name)))
        return _model.Task(issue.number, issue.title, issue.url, issue.state, record.closed_reason, stage, status,
                           milestone=issue.milestone, milestone_due=_model.parse_date(record.milestone_due),
                           labels=issue.labels, assignees=issue.assignees, parent=r.parent, subtasks=r.sub_total,
                           subtasks_done=r.sub_completed, blocked_by=r.blocked_by, blocking=r.blocking,
                           on_board=record.item is not None, fields=values,
                           created=_model.local_date(record.created_at), finished=_model.local_date(record.closed_at),
                           **plan)

    def _value(self, role: str, field: _board.BoardField, value: str | None) -> dict:
        """ボードの項目の値（表示の文字）→ Task の値（役割に合わせた型）。"""
        if role == _model.PRIORITY:
            names = [o.name for o in field.options]
            return {"priority": value, "priority_rank": names.index(value) if value in names else None}
        if role == _model.ESTIMATE:
            return {"estimate": None if value is None else float(value)}
        if role == _model.SPRINT:
            return {"sprint": None if value is None else next(
                (s for s in self.sprints() if s.name.casefold() == value.casefold()), None)}
        return {role: _model.parse_date(value)}   # 日付の役割は、役割の名前と Task の属性が同じ

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

    def prepare(self, values: dict[str, str | None], clear: tuple[str, ...] = (),
                current: _model.Task | None = None) -> dict[str, tuple[_board.BoardField, str | None]]:
        """計画の値を書く前に確かめる（書かない）。役割 → (項目, 書く値。消すならNone) を返す。

        values：役割（PLAN_ROLES）→ 値（None は変えない）。sprint は名前か current（今日を含む）。clear：消す役割。
        current：今のタスク（開始予定日と終了予定日の前後を、書かない方の値と合わせて確かめる）。
        """
        values = {role: value for role, value in values.items() if value is not None}
        unknown = [role for role in (*values, *clear) if role not in _model.PLAN_ROLES]
        if unknown:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"計画の値 {', '.join(unknown)} はありません。",
                            hint=f"{'・'.join(_model.PLAN_ROLES)} から選んでください。")
        both = [role for role in clear if role in values]
        if both:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{', '.join(both)} の設定と消去は同時にできません。")
        if not values and not clear:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "設定する値がありません。",
                            hint="--priority・--due・--estimate・--sprint・--planned-start・--planned-end・--clear の"
                                 "どれかを指定してください。")
        self._require()
        result = {}
        for role in (*values, *clear):
            field = self.role_field(role)
            if field is None:
                raise TaskError(ErrorCode.FIELD_NOT_FOUND,
                                f"ボードに{_model.ROLE_NAMES[role]}（{role}）の項目が当てられていません。",
                                hint="ボードに項目を足して、作業空間で board use をやり直してください"
                                     "（board use --add-fields で標準の項目を足せます）。")
            result[role] = (field, values.get(role))
        if values.get(_model.SPRINT) == "current":
            today = _datetime.date.today()
            found = next((s for s in self.sprints() if s.contains(today)), None)
            if found is None:
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"今日（{today.isoformat()}）を含むスプリントがありません。")
            result[_model.SPRINT] = (result[_model.SPRINT][0], found.name)
        for role, (field, value) in result.items():
            if value is not None:
                _github._field_value(field, value)   # 型・選択肢・日付の書き方を確かめる
                if field.type == "DATE":
                    _date(field.name, value)
        start, end = (_planned(role, values, clear, current) for role in (_model.PLANNED_START, _model.PLANNED_END))
        if start is not None and end is not None and start > end:
            raise TaskError(ErrorCode.INVALID_ARGUMENT,
                            f"開始予定日（{start.isoformat()}）が終了予定日（{end.isoformat()}）より後です。")
        return result

    def plan(self, number: int, *, clear: tuple[str, ...] = (), **values: str | None) -> dict[str, str | None]:
        """計画の値（PLAN_ROLES：優先度・期限・見積もり・スプリント・開始予定日・終了予定日）を書く。
        sprint は名前か current（今日を含む）。clear：消す役割。ボードになければ加える。

        書いた値（役割 → 値。消したものは None）を返す。GitHubは書いた直後の読み取りで古い値を返すことがあるため、
        呼び出し側はこれを読み直した Task に重ねる（apply）。
        """
        dated = {_model.PLANNED_START, _model.PLANNED_END} & {*clear, *(r for r, v in values.items() if v is not None)}
        prepared = self.prepare(values, clear, self.task(number) if dated else None)
        item = self.item(number, add=True)
        for field, value in prepared.values():
            if value is None:
                self.clear(item, field)
            else:
                self.write(item, field, value)
        return {role: value for role, (_, value) in prepared.items()}

    def record_started(self, item: _board.BoardItem, day: _datetime.date | None = None) -> bool:
        """開始日がまだなければ、今日（day）を書く。開始日の項目を当てていなければ何もしない。書いたら True。"""
        field = self.role_field(_model.STARTED)
        if field is None or item.values.get(field.name):
            return False
        self.write(item, field, (day or _datetime.date.today()).isoformat())
        return True

    def apply(self, task: _model.Task, written: dict[str, str | None]) -> _model.Task:
        """書いた値を Task に重ねる（書いた直後の読み取りが古くても、正しい値を返すため）。"""
        changes = {}
        for role, value in written.items():
            field = self.role_field(role)
            if role == _model.PRIORITY and value is not None:
                value = _board.find_option(field, value).name
            changes.update(self._value(role, field, value))
        return replace(task, on_board=True, **changes)

    def _require(self) -> _board.BoardSettings:
        if self._board is None:
            raise TaskError(ErrorCode.NO_BOARD, "ボード（GitHub Projects）をつないでいません。",
                            hint="board list で一覧を見て、board use <URL> でつなぎます（なければ board create）。")
        return self._board


def _date(name: str, text: str) -> _datetime.date:
    try:
        return _datetime.date.fromisoformat(text)
    except ValueError:
        raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{name} の日付 {text} がありません（YYYY-MM-DD）。") from None


def _planned(role: str, values: dict, clear: tuple[str, ...], current: _model.Task | None) -> _datetime.date | None:
    """書いた後の開始予定日・終了予定日（書く値、なければ今の値）。"""
    if role in clear:
        return None
    if values.get(role) is not None:
        return _datetime.date.fromisoformat(values[role])
    return None if current is None else getattr(current, role)


def _sprint(option: _board.BoardOption) -> _model.Sprint:
    start = _datetime.date.fromisoformat(option.start)
    return _model.Sprint(option.name, start, start + _datetime.timedelta(days=option.duration))
