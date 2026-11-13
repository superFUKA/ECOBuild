"""test・run の --env（何度でも書ける）と、test --repeat：オプションのまとめ方・環境の足し方・何度も流す。"""

import os

import click
import pytest

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.execution import added_environment, added_variables, repeat_tests
from ecobuild import results
from ecobuild_cli import _repeat
from ecobuild_cli._output import REPEATED, split_repeated


def _find(words):
    """test・run に似たコマンド（--env・--arguments は値を取る、--json は旗）。"""
    return click.Command("test", params=[click.Option(["--env"]), click.Option(["--arguments"]),
                                         click.Option(["--json"], is_flag=True)])


def test_repeated_env_is_merged_in_the_order_written():
    merged = _repeat.merge(["test", "--env", "A=1", "--json", "--env=B=x=y", "--env", "A=2"], _find)
    assert merged == ["test", "--env", REPEATED + REPEATED.join(["A=1", "B=x=y", "A=2"]), "--json"]
    assert split_repeated(merged[2]) == ("A=1", "B=x=y", "A=2")
    assert split_repeated("") == () and split_repeated("A=1") == ("A=1",)
    # 書いたが空（--env= ・--env ""）も1つと数える（黙って捨てない。split_environment で形の誤りに）
    assert split_repeated(_repeat.merge(["test", "--env="], _find)[2]) == ("",)
    assert split_repeated(_repeat.merge(["test", "--env", ""], _find)[2]) == ("",)


def test_env_is_left_alone_where_it_is_not_the_option():
    # -- の後ろ（プログラムへの引数）・ほかのオプションの値
    assert _repeat.merge(["run", "--env", "A=1", "--", "--env", "B"], _find) == [
        "run", "--env", REPEATED + "A=1", "--", "--env", "B"]
    assert _repeat.merge(["run", "--arguments", "--env", "--env", "A=1"], _find) == [
        "run", "--arguments", "--env", "--env", REPEATED + "A=1"]
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
        assert added_variables() == {"ECOBUILD_TEST_KEPT": "inside", "ECOBUILD_TEST_NEW": "1"}
    assert os.environ["ECOBUILD_TEST_KEPT"] == "before" and "ECOBUILD_TEST_NEW" not in os.environ
    assert added_variables() == {}
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


def test_repeat_shows_progress():
    shown = []
    repeat_tests(lambda: _passed("a"), 3, lambda n, total: shown.append((n, total)))
    assert shown == [(1, 3), (2, 3), (3, 3)]


def test_test_failed_without_failing_cases_stops_with_the_original_error():
    """当てはまるテストがない・テストを集められない（ケースの結果はあるが失敗したケースがない）は、くり返さない。"""
    calls = []
    original = EcoBuildError(ErrorCode.TEST_FAILED, "当てはまるテストがありません（CalcTest）。", hint="名前は…",
                             details={"cases": [], "diagnostics": ["No tests match"]})

    def once():
        calls.append(1)
        raise original

    with pytest.raises(EcoBuildError) as error:
        repeat_tests(once, 4)
    assert error.value is original and len(calls) == 1


def test_failed_run_without_cases_counts_as_one_failure():
    """型 generic（details に cases がない）は全体を失敗1件、counts があればそれを使う。"""
    plain = EcoBuildError(ErrorCode.TEST_FAILED, "テストに失敗しました。（test：終了コード 3）", details={"returncode": 3})
    with pytest.raises(EcoBuildError) as error:
        repeat_tests(lambda: (_ for _ in ()).throw(plain), 2)
    assert [(r.ok, r.passed, r.failed) for r in error.value.details["runs"]] == [(False, 0, 1), (False, 0, 1)]
    counted = EcoBuildError(ErrorCode.TEST_FAILED, "失敗", details={"counts": {"passed": 4, "failed": 2, "skipped": 1}})
    with pytest.raises(EcoBuildError) as error:
        repeat_tests(lambda: (_ for _ in ()).throw(counted), 2)
    assert (error.value.details["runs"][0].passed, error.value.details["runs"][0].failed) == (4, 2)


def test_python_last_failed_reruns_the_cases_of_the_first_run():
    """python の test --last-failed --repeat：2回目からは1回目に流したケースを名前で（--last-failed は外す）。"""
    from ecobuild_python.cli.test import rerun_same
    calls = []

    def test(tests, last_failed):
        calls.append((tests, last_failed))
        return results.TestResult(None, "Debug", 1, 0, 0, (results.TestCaseResult("tests/a.py::test_x", "passed"),))

    once = rerun_same(test, (), True)
    once(), once(), once()
    assert calls == [((), True), (("tests/a.py::test_x",), False), (("tests/a.py::test_x",), False)]
    # 1回目が失敗でも（details の cases から）
    calls.clear()

    def failing(tests, last_failed):
        calls.append((tests, last_failed))
        raise EcoBuildError(ErrorCode.TEST_FAILED, "失敗", details={"cases": [results.TestCaseResult("t.py::b", "failed")]})

    once = rerun_same(failing, ("t.py",), True)
    for _ in range(2):
        with pytest.raises(EcoBuildError):
            once()
    assert calls == [(("t.py",), True), (("t.py::b",), False)]
    # --last-failed でなければ、いつも同じ指定
    calls.clear()
    once = rerun_same(test, ("t.py",), False)
    once(), once()
    assert calls == [(("t.py",), False), (("t.py",), False)]


def test_python_keeps_what_the_user_added(monkeypatch):
    """型 python の子プロセスの環境：決まった値（PYTHONUTF8 等）より、利用者が --env で足したものを優先する。"""
    from ecobuild_python import _python
    assert _python._environment()["PYTHONUTF8"] == "1"
    with added_environment({"PYTHONUTF8": "0", "ECOBUILD_TEST_NEW": "x"}):
        environment = _python._environment()
    assert environment["PYTHONUTF8"] == "0" and environment["ECOBUILD_TEST_NEW"] == "x"
