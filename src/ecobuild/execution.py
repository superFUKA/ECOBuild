"""テスト・実行の補助：環境変数を足す（test・run の --env）、何度も流す（test --repeat）。

型によらない。型の test・run は子プロセス（ビルドの道具・テスト・プログラム）を、このプロセスの環境
（os.environ）を受け継いで動かす約束なので、その間だけ os.environ に足して、終われば戻す。
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace

from .errors import EcoBuildError, ErrorCode
from .results import TestResult, TestRun

__all__ = ["added_environment", "added_variables", "repeat_tests"]

_added: dict[str, str] = {}   # 今 added_environment で足している環境変数（型が自分の決まった値で上書きしないように）


def added_variables() -> dict[str, str]:
    """今 added_environment で足している環境変数（利用者が --env で書いたもの）。型が子プロセスの環境を作るとき、
    自分の決まった値（PYTHONUTF8 等）より、こちらを優先する。"""
    return dict(_added)


@contextlib.contextmanager
def added_environment(environment: Mapping[str, str] | None) -> Iterator[None]:
    """この中だけ、os.environ に environment を足す（同じ名前は上書き）。終われば元に戻す（なかったものは消す）。

    このプロセスの環境を変えるので、この中で並べて別の操作を動かさない（CLI は1回に1つの操作）。ビルドの道具も
    同じ環境で動く（C++ は CppBuild がビルドとテストを続けて動かすため、分けられない）。子プロセスへは、環境を
    dict(os.environ) で渡す（Windows では空の値を os.environ に入れても、渡さなければ子に届かない）。"""
    if not environment:
        yield
        return
    saved = {name: os.environ.get(name) for name in environment}
    saved_added = dict(_added)
    os.environ.update(environment)
    _added.update(environment)
    try:
        yield
    finally:
        _added.clear()
        _added.update(saved_added)
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def repeat_tests(once: Callable[[], TestResult], repeat: int,
                 on_run: Callable[[int, int], None] | None = None) -> TestResult:
    """once（1回のテスト）を repeat 回流す。全部成功なら最後の回の結果に、回ごとの結果（runs）を付けて返す。
    on_run(何回目, repeat)：各回の前に呼ぶ（進み具合の表示）。

    テストの失敗（TEST_FAILED）でも残りの回を流し、1回でも失敗したら TEST_FAILED（details：最初に失敗した回の
    details に、repeat・runs を足したもの）。テストの失敗でない誤り（ビルドの失敗等）と、ケースの結果があるのに
    失敗したケースがない TEST_FAILED（当てはまるテストがない・テストを集められない）は、その回で元の誤りのまま止める。"""
    if repeat < 1:
        raise ValueError(f"回数は1以上です（{repeat}）。")
    if repeat == 1:
        return once()
    runs: list[TestRun] = []
    last: TestResult | None = None
    first_error: EcoBuildError | None = None
    for number in range(1, repeat + 1):
        if on_run is not None:
            on_run(number, repeat)
        try:
            last = once()
        except EcoBuildError as error:
            if error.code != ErrorCode.TEST_FAILED:
                raise
            run = _failed_run(number, error)
            if run is None:
                raise
            first_error = first_error or error
            runs.append(run)
            continue
        failed = tuple(c.name for c in last.cases if c.status not in ("passed", "skipped"))
        runs.append(TestRun(number, True, last.passed, last.failed, last.skipped, failed))
    if first_error is None:
        return replace(last, runs=tuple(runs))
    bad = [r.number for r in runs if not r.ok]
    details = dict(first_error.details) if isinstance(first_error.details, dict) else {}
    details.update(repeat=repeat, runs=runs)
    names = sorted({name for r in runs for name in r.failed_cases})
    raise EcoBuildError(ErrorCode.TEST_FAILED,
                        f"テストに失敗しました（{repeat} 回のうち {len(bad)} 回：{'・'.join(map(str, bad))} 回目）"
                        + (f"（{'、'.join(names[:3])}" + ("…" if len(names) > 3 else "") + "）" if names else ""),
                        hint=first_error.hint, details=details)


def _failed_run(number: int, error: EcoBuildError) -> TestRun | None:
    """失敗した回。details にケースの結果（cases）があれば、そこから。None（その回で止める）は、テストの失敗ではないと
    確かなときだけ：cases が空（テストを集められない等）か、diagnostics に "No tests match"（C++ の当てはまるテストなし）。
    失敗したケースが残らなかった失敗（実行ファイルが途中で落ちた等）は失敗1件と数える。cases がなければ（型 generic 等）
    counts から、それもなければ全体を失敗1件と数える。"""
    details = error.details if isinstance(error.details, dict) else {}
    message = error.message.splitlines()[0] if error.message else None
    counts = details.get("counts") if isinstance(details.get("counts"), dict) else None
    if "cases" in details:
        status = [(_field(c, "name"), _field(c, "status")) for c in details.get("cases") or []]
        failed = tuple(name for name, state in status if state not in ("passed", "skipped") and name)
        diagnostics = details.get("diagnostics") or ()
        if not failed and (not status or any("No tests match" in str(d) for d in diagnostics)):
            return None
        count = lambda state: sum(1 for _, s in status if s == state)  # noqa: E731
        return TestRun(number, False, count("passed"), len(failed) or 1, count("skipped"), failed, message)
    if counts is not None:
        return TestRun(number, False, counts.get("passed", 0), counts.get("failed", 0) or 1, counts.get("skipped", 0),
                       (), message)
    return TestRun(number, False, 0, 1, 0, (), message)


def _field(case, name: str):
    return case.get(name) if isinstance(case, dict) else getattr(case, name, None)
