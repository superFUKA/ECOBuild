"""test・run の --env（何度でも書ける）と、test --repeat：オプションのまとめ方・環境の足し方・何度も流す。"""

import os

import click
import pytest

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.execution import added_environment, repeat_tests
from ecobuild import results
from ecobuild_cli import _repeat
from ecobuild_cli._output import REPEATED, split_repeated


def _find(words):
    """test・run に似たコマンド（--env・--arguments は値を取る、--json は旗）。"""
    return click.Command("test", params=[click.Option(["--env"]), click.Option(["--arguments"]),
                                         click.Option(["--json"], is_flag=True)])


def test_repeated_env_is_merged_in_the_order_written():
    merged = _repeat.merge(["test", "--env", "A=1", "--json", "--env=B=x=y", "--env", "A=2"], _find)
    assert merged == ["test", "--env", REPEATED.join(["A=1", "B=x=y", "A=2"]), "--json"]
    assert split_repeated(merged[2]) == ("A=1", "B=x=y", "A=2")
    assert split_repeated("") == ()


def test_env_is_left_alone_where_it_is_not_the_option():
    # -- の後ろ（プログラムへの引数）・ほかのオプションの値
    assert _repeat.merge(["run", "--env", "A=1", "--", "--env", "B"], _find) == ["run", "--env", "A=1", "--", "--env", "B"]
    assert _repeat.merge(["run", "--arguments", "--env", "--env", "A=1"], _find) == [
        "run", "--arguments", "--env", "--env", "A=1"]
    # 打ったコマンドに --env がない・--env がない・値がない（click の誤りのまま）
    without = lambda words: click.Command("status", params=[click.Option(["--json"], is_flag=True)])  # noqa: E731
    assert _repeat.merge(["status", "--env", "A=1"], without) == ["status", "--env", "A=1"]
    assert _repeat.merge(["test", "--json"], _find) == ["test", "--json"]
    assert _repeat.merge(["test", "--env"], _find) == ["test", "--env"]


def test_environment_is_added_only_inside(monkeypatch):
    monkeypatch.setenv("ECOBUILD_TEST_KEPT", "before")
    monkeypatch.delenv("ECOBUILD_TEST_NEW", raising=False)
    with added_environment({"ECOBUILD_TEST_KEPT": "inside", "ECOBUILD_TEST_NEW": "1"}):
        assert os.environ["ECOBUILD_TEST_KEPT"] == "inside" and os.environ["ECOBUILD_TEST_NEW"] == "1"
    assert os.environ["ECOBUILD_TEST_KEPT"] == "before" and "ECOBUILD_TEST_NEW" not in os.environ
    with pytest.raises(RuntimeError), added_environment({"ECOBUILD_TEST_NEW": "1"}):
        raise RuntimeError
    assert "ECOBUILD_TEST_NEW" not in os.environ


def _passed(*names):
    return results.TestResult(None, "Debug", len(names), 0, 0, tuple(results.TestCaseResult(n, "passed") for n in names))


def test_repeat_records_each_run():
    calls = []
    result = repeat_tests(lambda: calls.append(1) or _passed("a", "b"), 3)
    assert len(calls) == 3 and result.passed == 2
    assert [(r.number, r.ok, r.passed, r.failed_cases) for r in result.runs] == [(1, True, 2, ()), (2, True, 2, ()), (3, True, 2, ())]
    assert repeat_tests(lambda: _passed("a"), 1).runs == ()        # 1回なら今までどおり
    with pytest.raises(ValueError):
        repeat_tests(lambda: _passed("a"), 0)


def test_repeat_fails_if_any_run_fails_and_keeps_going():
    count = iter(range(1, 10))

    def once():
        number = next(count)
        if number == 2:
            raise EcoBuildError(ErrorCode.TEST_FAILED, "テストに失敗しました。（a）",
                                details={"cases": [{"name": "a", "status": "failed"}, {"name": "b", "status": "passed"}],
                                         "output": "a failed"})
        return _passed("a", "b")

    with pytest.raises(EcoBuildError) as error:
        repeat_tests(once, 3)
    assert error.value.code == ErrorCode.TEST_FAILED
    assert "3 回のうち 1 回" in error.value.message and "（a）" in error.value.message
    details = error.value.details
    assert details["repeat"] == 3 and details["output"] == "a failed"         # 最初に失敗した回の details も残す
    assert [(r.number, r.ok, r.failed_cases) for r in details["runs"]] == [(1, True, ()), (2, False, ("a",)), (3, True, ())]
    assert details["runs"][1].passed == 1 and details["runs"][1].message.startswith("テストに失敗")


def test_repeat_stops_at_errors_other_than_test_failures():
    calls = []

    def once():
        calls.append(1)
        raise EcoBuildError(ErrorCode.BUILD_FAILED, "ビルドに失敗しました。")

    with pytest.raises(EcoBuildError) as error:
        repeat_tests(once, 5)
    assert error.value.code == ErrorCode.BUILD_FAILED and len(calls) == 1
