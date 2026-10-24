"""CLI の共通の出力：--help（テキスト・JSON）、誤りの JSON の形、ログ（時刻・長い引数・頼んだ側の run・誤りの記録）。"""

import io
import json

import pytest

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_cli import _catalog, _log, _output, main
from ecobuild_cli._output import Invocation, execute


def run(capsys, *args):
    with pytest.raises(SystemExit) as stop:
        main(list(args))
    captured = capsys.readouterr()
    return stop.value.code, captured.out, captured.err


def document(capsys, *args):
    code, out, _ = run(capsys, *args)
    return code, json.loads(out)


def log_entries():
    directory = _log.global_directory()
    return [json.loads(line) for path in sorted(directory.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def outside(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --help --json（14・57） ----------------------------------------------------------------


def test_help_json_options_have_type_negative_default_and_choices(outside, capsys):
    code, found = document(capsys, "task", "submit", "--help", "--json")
    options = {o["names"][0]: o for o in found["result"]["options"]}
    assert options["--check"] == {**options["--check"], "type": "bool", "negative": "--no-check", "default": True,
                                  "choices": None, "flag": True}
    assert options["--draft"]["default"] is False and options["--draft"]["negative"] == "--no-draft"
    assert options["--note"]["type"] == "str" and options["--note"]["negative"] is None
    assert options["--note"]["default"] is None                 # 既定がない（空の文字列）ものも書く（null）


def test_an_argument_taken_once_is_not_written_as_many(outside, capsys):
    """#9-21・#11：task status 等は位置引数を1つだけ受ける（optional_argument）。使い方に ... を書かない。"""
    code, found = document(capsys, "task", "status", "--help", "--json")
    assert found["result"]["arguments"][0]["multiple"] is False
    code, found = document(capsys, "agent", "status", "--help", "--json")
    assert found["result"]["arguments"][0]["multiple"] is True                 # いくつも受けるもの
    code, out, _ = run(capsys, "task", "status", "--help")
    assert "[NUMBER]" in out and "[NUMBER]..." not in out
    code, out, _ = run(capsys, "agent", "status", "--help")
    assert "[ID]..." in out


def test_examples_are_taken_from_the_help():
    text = "説明。\n\n例：\n  ecobuild task start 12\n  ecobuild task start --name ログイン\n\n別の段落 ecobuild status"
    assert _catalog.examples(text) == ["ecobuild task start 12", "ecobuild task start --name ログイン"]
    assert _catalog.examples("例：ecobuild status で確かめる") == ["ecobuild status で確かめる"]
    assert _catalog.examples("説明だけ") == []


def test_help_json_lists_error_codes(outside, capsys):
    code, found = document(capsys, "--help", "--json")
    errors = {e["code"]: e["retryable"] for e in found["result"]["errors"]}
    assert errors["github_error"] is True and errors["build_failed"] is False
    assert {"usage_error", "unexpected_error", "task_closed", "agent_error"} <= set(errors)   # 拡張の種類も


def test_help_json_tells_the_output_and_the_events(outside, capsys):
    """--help --json に、結果の JSON のキー（output）と標準エラーのイベントの形（events）。結果には log（run・file）。"""
    code, found = document(capsys, "--help", "--json")
    assert set(found["result"]["output"]) == {"ok", "command", "module", "result", "notices", "error", "log"}
    events = found["result"]["events"]
    assert events["kinds"] == ["progress", "notice", "warning", "error", "output"]
    assert {"kind", "text", "time", "stream", "source", "code"} <= set(events["keys"])
    assert set(found["log"]) == {"run", "file"}


# テキストの --help（55・58・64） ----------------------------------------------------------


def test_text_help_shows_only_meaningful_defaults(outside, capsys):
    code, out, _ = run(capsys, "task", "submit", "--help")
    assert code == 0
    out = " ".join(out.split())                    # 折り返しをならす
    assert "[既定値: ]" not in out and "no-complete" not in out and "no-json" not in out
    assert "--check / --no-check" in out and "既定値: --check" in out          # 付けるのが既定のものだけ、外し方と一緒に
    assert "--draft / --no-draft" not in out and " --draft " in out            # 付けないのが既定のものは否定形を出さない


def test_task_help_headings_say_commands(outside, capsys):
    code, out, _ = run(capsys, "task", "--help")
    assert "コマンド（計画）:" in out and "コマンド（提出と完了）:" in out


def test_version(outside, capsys):
    code, out, _ = run(capsys, "--version")
    assert code == 0 and out.startswith("ecobuild ")
    code, found = document(capsys, "--version", "--json")
    assert found["ok"] and found["command"] == "version" and "version" in found["result"]


# --json（24・62） --------------------------------------------------------------------


def test_json_before_the_command_is_accepted(outside, capsys):
    code, found = document(capsys, "--json", "workspace", "list")
    assert code == 0 and found["command"] == "workspace list"


def test_usage_error_has_the_same_shape(outside, capsys):
    code, found = document(capsys, "task", "close", "--bogus", "--json")
    assert code == 2 and found["command"] == "task close" and found["notices"] == []
    assert found["error"]["code"] == "usage_error" and found["error"]["retryable"] is False
    assert set(found["error"]) == {"code", "message", "hint", "details", "retryable"}
    assert [e for e in log_entries() if e["event"] == "command.error"][-1]["data"]["code"] == "usage_error"


def test_unexpected_exception_is_returned_as_json_and_logged(outside, capsys):
    def action(inv):
        raise ValueError("No closing quotation")

    _log.start(["sample", "--json"])
    try:
        code = execute("sample", Invocation(json_output=True, cwd=outside), action)
    finally:
        _log.finish(code)
    found = json.loads(capsys.readouterr().out)
    assert code == 1 and not found["ok"] and found["command"] == "sample"
    assert found["error"]["code"] == "unexpected_error" and "No closing quotation" in found["error"]["message"]
    assert found["error"]["hint"]
    error = next(e for e in log_entries() if e["event"] == "command.error")
    assert error["data"]["code"] == "unexpected_error" and "ValueError" in error["traceback"]


def test_missing_hint_gets_the_default_for_its_code(outside, capsys):
    def action(inv):
        raise EcoBuildError(ErrorCode.BUILD_FAILED, "ビルドに失敗しました。", details="error C2065")

    assert execute("build", Invocation(json_output=True, cwd=outside), action) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["hint"] and error["details"] == "error C2065" and error["retryable"] is False


class _Closed(io.StringIO):
    """読む側が閉じたパイプ（| head の後）。"""

    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")

    def fileno(self):
        raise io.UnsupportedOperation("fileno")


def test_closed_output_ends_quietly(outside, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdout", _Closed())
    with pytest.raises(SystemExit) as stop:
        main(["--help", "--json"])
    assert stop.value.code == 1
    events = [e["event"] for e in log_entries()]
    assert "command.output_closed" in events and "command.crash" not in events


# ログ（23・50・51） -------------------------------------------------------------------


def test_log_times_are_utc(outside):
    _log.start(["sample"])
    _log.finish(0)
    assert all(e["time"].endswith("+00:00") for e in log_entries())


def test_failure_without_a_reason_is_still_logged_as_an_error(outside):
    _log.start(["sample"])
    _log.finish(3)
    error = next(e for e in log_entries() if e["event"] == "command.error")
    assert error["data"]["code"] == "failed" and "3" in error["data"]["message"]


def test_long_arguments_are_shortened(outside):
    brief = "任せる仕事" * 1000
    _log.start(["task", "new", "名前", "--body", brief])
    _log.finish(0)
    start = next(e for e in log_entries() if e["event"] == "command.start")
    shown = start["data"]["args"][-1]
    assert len(shown) < 300 and shown.startswith("任せる仕事") and f"{len(brief)}字" in shown and "sha256" in shown
    assert start["data"]["args"][:4] == ["task", "new", "名前", "--body"]


def test_forwarded_run_is_written(outside, monkeypatch):
    _log.start(["build"])
    passed = _log.forward_environment()
    _log.finish(0)
    assert list(passed) == [_log.FORWARDED_VARIABLE]
    monkeypatch.setenv(_log.FORWARDED_VARIABLE, passed[_log.FORWARDED_VARIABLE])
    _log.start(["build"])
    _log.finish(0)
    starts = [e for e in log_entries() if e["event"] == "command.start"]
    assert starts[-1]["data"]["forwarded_from"] == starts[0]["run"] and "forwarded_from" not in starts[0]["data"]


# 件数の多い一覧（61） -------------------------------------------------------------------


def test_page():
    assert _output.page(range(10), 3, 2) == {"items": [2, 3, 4], "total": 10, "offset": 2, "limit": 3,
                                              "truncated": True}
    assert _output.page(range(3), 0)["items"] == [0, 1, 2] and not _output.page(range(3), 5)["truncated"]


def test_command_run_in_the_container_is_linked_and_its_error_logged(outside, monkeypatch, capsys):
    """コンテナの中の ecobuild に渡したコマンド：中のログに頼んだ側の run（forwarded_from）が入るよう渡し、
    中で失敗したら、このPCのログにも中の誤りを書く。"""
    import ecobuild_container as container
    from ecobuild import workspaces
    from ecobuild_cli import _inside
    from ecobuild_cli.commands.container import _source

    ran = []

    def run_inside(root, args, **options):
        ran.append(args)
        return 1, json.dumps({"ok": False, "error": {"code": "build_failed", "message": "ビルドに失敗しました。",
                                                     "hint": None, "details": "/work/a.cpp: error"}})

    monkeypatch.setattr(workspaces, "module_root", lambda path: outside)
    monkeypatch.setattr(container, "enabled", lambda root: True)
    monkeypatch.setattr(container, "run_inside", run_inside)
    monkeypatch.setattr(_source, "source", lambda: ("url", "commit"))
    _log.start(["build", "--json"])
    try:
        code = _inside.route(["build", "--json"], True)
    finally:
        _log.finish(code)
    run = next(e["run"] for e in log_entries() if e["event"] == "command.start")
    assert code == 1 and ran == [["env", f"{_log.FORWARDED_VARIABLE}={run}", "ecobuild", "build", "--json"]]
    error = next(e for e in log_entries() if e["event"] == "command.error")
    assert error["data"]["code"] == "build_failed" and error["data"]["details"] == f"{outside.as_posix()}/a.cpp: error"
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "build_failed"
