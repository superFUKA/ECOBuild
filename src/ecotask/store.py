"""保存の層：GitHubをタスクのデータベースとして使う。

読み：GitHubのデータ（Issue・親子と依存の要約・マイルストーン・ボードの値）を、まとめて Task にする。
書き：計画の値（優先度・期限・見積もり・スプリント）と状態を、ボードの項目の型を確かめて書く。

ボードは計画の情報を置く内部の保存場所（ecotask.board）。リポジトリにリンクしたECOBuildのボードを見つけて使い、
なければ書くときに決まった形で作る（読むだけなら作らず、計画の値なしとして扱う）。
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import replace
from pathlib import Path

from . import board as _board
from . import github as _github
from . import model as _model
from .errors import ErrorCode, TaskError

SPRINT_DAYS, SPRINT_COUNT = 14, 3   # 作るときのスプリント（今週の月曜日から2週間×3）
SPRINT_AHEAD = 14                    # 最後のスプリントの終わりが、今日からこの日数より近ければ足す


class TaskStore:
    def __init__(self, root: Path, github: _github.TaskGitHub, legacy_board: str | None = None):
        """legacy_board：以前の設定（ecobuild.toml の [board] の url）。印のないボードを引き継ぐときに使う。"""
        self.root = root
        self.github = github
        self.legacy_board = legacy_board
        self._found = False
        self._board: _board.BoardSettings | None = None
        self._info: _board.BoardInfo | None = None
        self.shared: tuple[str, ...] = ()   # 作った・引き継いだときに共有した共同作業者

    # ボード（内部の保存場所） -------------------------------------------------------------

    @property
    def board(self) -> _board.BoardSettings | None:
        """使うボード（項目の当て方）。なければNone（作らない）。1回見つけたら覚える。"""
        if not self._found:
            self._found = True
            self._board = self._find()
        return self._board

    def ensure(self) -> _board.BoardSettings:
        """書く前に：ボードがなければ作り、決まった項目が足りなければ足す。"""
        if self.board is None:
            self._create()
        missing = [(name, kind) for role, (name, kind) in zip(_model.ROLES, _board.standard_fields())
                   if not self._board.schema.get(role)]
        if missing:
            names = {f.name.casefold() for f in self.info().fields}
            clash = [name for name, _ in missing if name.casefold() in names]
            if clash:
                raise TaskError(ErrorCode.INVALID_ARGUMENT,
                                f"GitHubのタスク管理の情報の {'・'.join(clash)} の形が、ECOBuildの決まりと違います。",
                                hint="GitHubで直接変えた場合は、元の形（型）に戻してください。")
            self._create_fields(self.info().id, tuple(missing))
            self._reload()
        if not all(self._board.stages.get(stage) for stage in (_model.TODO, _model.IN_PROGRESS, _model.DONE)):
            raise TaskError(ErrorCode.INVALID_ARGUMENT,
                            "GitHubのタスク管理の情報の段階（Status）の形が、ECOBuildの決まりと違います。",
                            hint="GitHubで直接変えた場合は、Todo・In Progress・Done の選択肢を戻してください。")
        self._extend_sprints()
        return self._board

    def _extend_sprints(self, today: _datetime.date | None = None) -> None:
        """スプリントが尽きないように：最後のスプリントの終わりが近ければ、同じ日数で続きを足す（題名は Sprint <番号>）。"""
        field = self.role_field(_model.SPRINT)
        current = [o for o in field.options if o.start and o.duration] if field is not None else []
        if not current:
            return
        today = today or _datetime.date.today()
        last = max(current, key=lambda o: o.start)
        days = last.duration
        end = _datetime.date.fromisoformat(last.start) + _datetime.timedelta(days=days)
        if (end - today).days > SPRINT_AHEAD:
            return
        added = []
        while (end - today).days <= SPRINT_AHEAD + days:
            added.append((None, f"Sprint {len(current) + len(added) + 1}", end.isoformat(), days))
            end += _datetime.timedelta(days=days)
        self.github.set_iterations(self.root, field.id, tuple(
            (o.id, o.name, o.start, o.duration) for o in sorted(current, key=lambda o: o.start)) + tuple(added))
        self._reload()

    def info(self) -> _board.BoardInfo:
        """使うボードの定義（項目・選択肢）。1回読んだら覚える。"""
        settings = self._require()
        if self._info is None:
            self._info = self.github.get_board(self.root, settings.owner, settings.number)
        return self._info

    def role_field(self, role: str) -> _board.BoardField | None:
        """役割（priority 等）に当てた項目。なければNone。"""
        if self.board is None or not self._board.schema.get(role):
            return None
        return self.info().field(self._board.schema[role])

    def sprints(self) -> list[_model.Sprint]:
        """スプリント（始まりの順）。なければ空。"""
        sprint = self.role_field(_model.SPRINT)
        if sprint is None:
            return []
        return sorted((_sprint(o) for o in sprint.options if o.start and o.duration), key=lambda s: s.start)

    def _find(self) -> _board.BoardSettings | None:
        refs = self.github.repository_boards(self.root)
        ours = next((r for r in refs if r.ours), None)
        if ours is None and self.legacy_board:
            # 以前の設定でつないでいたボードを引き継ぐ：印を付け、共同作業者に共有する
            legacy = self.legacy_board.rstrip("/")
            ours = next((r for r in refs if r.url.rstrip("/") == legacy and not r.closed), None)
            if ours is not None:
                owner, number = _board.parse_url(ours.url)
                info = self.github.get_board(self.root, owner, number)
                self.github.describe_board(self.root, info.id, _board.DESCRIPTION)
                self.shared = self.github.share_board(self.root, info.id)
        if ours is None:
            return None
        owner, number = _board.parse_url(ours.url)
        self._info = self.github.get_board(self.root, owner, number)
        return _board.settings_of(self._info)

    def _create(self) -> None:
        """決まった形のボードを作り、このリポジトリにリンクし、共同作業者に共有する。"""
        title = f"{self.github.repository_name(self.root).split('/')[-1]} タスク"
        created = self.github.create_board(self.root, None, title, _board.DESCRIPTION)
        owner, number = _board.parse_url(created.url)
        status = self.github.get_board(self.root, owner, number).field(_board.STATUS_FIELD)
        self.github.set_board_options(self.root, status.id, _board.STANDARD_STATUS)
        self._create_fields(created.id, _board.standard_fields())
        self.github.link_board(self.root, created.id, link=True)
        self.shared = self.github.share_board(self.root, created.id)
        self._found = True
        self._info = self.github.get_board(self.root, owner, number)
        self._board = _board.settings_of(self._info)

    def _create_fields(self, board_id: str, fields: tuple[tuple[str, str], ...]) -> None:
        today = _datetime.date.today()
        monday = today - _datetime.timedelta(days=today.weekday())
        iterations = tuple((f"Sprint {i + 1}", (monday + _datetime.timedelta(days=SPRINT_DAYS * i)).isoformat(),
                            SPRINT_DAYS) for i in range(SPRINT_COUNT))
        for name, kind in fields:
            if kind == "SINGLE_SELECT":
                self.github.create_board_field(self.root, board_id, name, kind, options=_board.STANDARD_PRIORITY)
            elif kind == "ITERATION":
                self.github.create_board_field(self.root, board_id, name, kind, iterations=iterations)
            else:
                self.github.create_board_field(self.root, board_id, name, kind)

    def _reload(self) -> None:
        settings = self._require()
        self._info = self.github.get_board(self.root, settings.owner, settings.number)
        self._board = _board.settings_of(self._info)

    # 読み ----------------------------------------------------------------------------

    def tasks(self, *, closed: bool = False) -> list[_model.Task]:
        """タスクの一覧（番号の順）。closed なら閉じたものも。"""
        board_id = None if self.board is None else self.info().id
        records = self.github.task_records(self.root, closed=closed, board_id=board_id)
        return sorted((self._task(r) for r in records), key=lambda t: t.number)

    def task(self, number: int) -> _model.Task:
        board_id = None if self.board is None else self.info().id
        return self._task(self.github.task_records(self.root, closed=True, board_id=board_id, number=number)[0])

    def _task(self, record: _github.TaskRecord) -> _model.Task:
        issue, r = record.issue, record.relations
        values = {} if record.item is None else dict(record.item.values)
        plan = {}
        status = stage = None
        if self.board is not None:
            status = values.get(self._board.status_field)
            stage = self.stage_of(status)
            for role in _model.ROLES:
                field = self.role_field(role)
                if field is not None and field.name in values:
                    plan.update(self._value(role, field, values[field.name]))
        return _model.Task(issue.number, issue.title, issue.url, issue.state, record.closed_reason, stage, status,
                           milestone=issue.milestone, milestone_due=_model.parse_date(record.milestone_due),
                           labels=issue.labels, assignees=issue.assignees, parent=r.parent, subtasks=r.sub_total,
                           subtasks_done=r.sub_completed, blocked_by=r.blocked_by, blocking=r.blocking,
                           on_board=record.item is not None,
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

    def item(self, number: int) -> _board.BoardItem:
        """タスクのボードの項目（なければ加える。ボードもなければ作る）。"""
        self.ensure()
        return self.github.add_board_item(self.root, number, self.info().id)

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
        self.ensure()
        result = {role: (self.role_field(role), values.get(role)) for role in (*values, *clear)}
        if values.get(_model.SPRINT) == "current":
            today = _datetime.date.today()
            found = next((s for s in self.sprints() if s.contains(today)), None)
            if found is None:
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"今日（{today.isoformat()}）を含むスプリントがありません。")
            result[_model.SPRINT] = (result[_model.SPRINT][0], found.name)
        for role, (field, value) in result.items():
            if value is not None:
                if field.type == "DATE":
                    _date(_model.ROLE_NAMES[role], value)
                elif role == _model.PRIORITY and value.casefold() not in (p.casefold() for p in _board.PRIORITIES):
                    raise TaskError(ErrorCode.INVALID_ARGUMENT, f"優先度 {value} はありません。",
                                    hint=f"{'・'.join(_board.PRIORITIES)} のどれかを指定してください。")
                _github._field_value(field, value)   # 型・選択肢の書き方を確かめる
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
        item = self.item(number)
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
        if self.board is None:
            raise TaskError(ErrorCode.NO_BOARD, "タスク管理の情報がまだありません。")
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
