import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ecobuild import config
from ecobuild_cli._output import FAILURE, SUCCESS, Invocation, execute
from ecobuild.errors import EcoBuildError, ErrorCode


@dataclass
class Sample:
    path: Path
    items: tuple[str, ...]


def test_json_success_prints_one_document(tmp_path, capsys):
    config.save(config.ModuleConfig.for_new_module("Calc", "cpp"), tmp_path / config.FILE_NAME)
    invocation = Invocation(json_output=True, cwd=tmp_path)

    def action(inv):
        inv.module  # 対象のモジュールを探す
        inv.info("進捗は標準エラーへ")
        return Sample(tmp_path / "a.cpp", ("x", "y"))

    assert execute("sample", invocation, action, lambda r: "表示") == SUCCESS
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["ok"] is True
    assert document["module"] == tmp_path.resolve().as_posix()
    assert document["result"] == {"path": (tmp_path / "a.cpp").as_posix(), "items": ["x", "y"]}
    assert "進捗" in captured.err


def test_json_failure(tmp_path, capsys):
    invocation = Invocation(json_output=True, cwd=tmp_path)
    assert execute("sample", invocation, lambda inv: inv.module) == FAILURE
    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is False
    assert document["module"] is None
    assert document["error"]["code"] == ErrorCode.NOT_IN_MODULE


def test_human_failure_goes_to_stderr(tmp_path, capsys):
    def action(inv):
        raise EcoBuildError(ErrorCode.GIT_ERROR, "失敗しました", hint="こうしてください")

    assert execute("sample", Invocation(json_output=False, cwd=tmp_path), action) == FAILURE
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "失敗しました" in captured.err and "こうしてください" in captured.err


def test_confirmation_required_without_yes_in_json(tmp_path):
    with pytest.raises(EcoBuildError) as error:
        Invocation(json_output=True, cwd=tmp_path).confirm("消しますか")
    assert error.value.code == ErrorCode.CONFIRMATION_REQUIRED
    Invocation(json_output=True, yes=True, cwd=tmp_path).confirm("消しますか")


def test_human_failure_shows_details_tail(tmp_path, capsys):
    output = "\n".join(f"line {i}" for i in range(100))

    def action(inv):
        raise EcoBuildError(ErrorCode.BUILD_FAILED, "ビルドに失敗しました。", details=output)

    assert execute("build", Invocation(json_output=False, cwd=tmp_path), action) == FAILURE
    err = capsys.readouterr().err
    assert "line 99" in err and "line 0\n" not in err and "省略" in err


def test_detail_keeps_error_lines_before_the_tail():
    """並列ビルドでエラーの行が末尾30行より前にあっても、人向けの表示に残す（仮運用で見つかった）。"""
    from ecobuild_cli._output import _detail_text
    lines = ["building"] * 5 + ["Vec2.cpp(24,1): error C2059: 構文エラー"] + ["gtest.vcxproj -> gtest.lib"] * 40
    text = _detail_text("\n".join(lines))
    assert "error C2059" in text and "前の16行は省略。そのうちエラーの行" in text
    assert text.count("gtest.lib") == 30


def test_local_time_shows_this_pc_time():
    """GitHubの時刻（UTC）・gitの時刻（書いた人の時差）は、このPCの時刻で日付にする（UTCで切ると日本では前日になる）。"""
    import datetime
    from ecobuild_cli._output import local_time
    here = datetime.datetime(2026, 10, 11, 23, 30, tzinfo=datetime.timezone.utc).astimezone()
    assert local_time("2026-10-11T23:30:00Z") == here.strftime("%Y-%m-%d")
    assert local_time("2026-10-12T08:30:00+09:00") == here.strftime("%Y-%m-%d")      # 同じ時刻
    assert local_time("2026-10-11T23:30:00Z", "%Y-%m-%d %H:%M") == here.strftime("%Y-%m-%d %H:%M")
    assert local_time("読めない日時の文字列") == "読めない日時の文字列"


def read_events(text):
    import json
    return [json.loads(line) for line in text.splitlines()]


def test_program_output_is_events_on_stderr_for_json(capsys):
    """--json：ツール・プログラムの出力は標準エラーへ、1行1件の output のイベント（書いたとおりの文字。行の途中で
    切れたら改行なし。stream・source 付き）。標準出力には出さない。"""
    from ecobuild_cli.kit import ProgramOutput
    output = ProgramOutput(True)
    output("a\r\nb")          # 行の途中で切れた
    output("c\n\n", "stderr")
    output.line("  d", source="tool")
    shown = capsys.readouterr()
    events = read_events(shown.err)
    assert shown.out == "" and all(e["kind"] == "output" and e["time"] for e in events)
    assert [(e["text"], e["stream"], e["source"]) for e in events] == [
        ("a\n", "stdout", "program"), ("b", "stdout", "program"), ("c\n", "stderr", "program"),
        ("\n", "stderr", "program"), ("  d\n", "stdout", "tool")]


def test_program_output_as_is_for_people(capsys):
    """人向け：印を付けずにそのまま（プログラムの stdout は標準出力へ、stderr は標準エラーへ）。"""
    from ecobuild_cli.kit import ProgramOutput
    output = ProgramOutput(False)
    output("as is\n")
    output("oops\n", "stderr")
    shown = capsys.readouterr()
    assert (shown.out, shown.err) == ("as is\n", "oops\n")


def test_events_for_json_and_text_for_people(capsys):
    """経過・注意・知らせ・誤り：--json では kind の付いたイベント（頭が「注意：」の経過は warning）、人向けは今までどおりの文字。"""
    from ecobuild_cli import _events
    _events.progress("ビルド中", True)
    _events.progress("注意：古い版です", True)
    _events.emit("notice", "閉じました", json_output=True)
    _events.emit("error", "失敗", json_output=True, code="build_failed")
    shown = capsys.readouterr()
    assert shown.out == ""
    assert [(e["kind"], e["text"], e.get("code")) for e in read_events(shown.err)] == [
        ("progress", "ビルド中", None), ("warning", "注意：古い版です", None), ("notice", "閉じました", None),
        ("error", "失敗", "build_failed")]
    _events.progress("ビルド中", False)
    _events.progress("注意：古い版です", False)
    _events.emit("notice", "閉じました", json_output=False)
    _events.emit("error", "失敗", json_output=False)
    assert capsys.readouterr().err == "ビルド中\n注意：古い版です\nお知らせ：閉じました\nエラー：失敗\n"


def test_reading_events_back():
    """ほかの ecobuild の標準エラーを読む側：JSON のイベントでない行は None。messages は出力のイベントを除いた文。"""
    import json
    from ecobuild_cli import _events
    lines = [json.dumps({"kind": "progress", "text": "ビルド中"}), json.dumps({"kind": "output", "text": "cl.exe\n"}),
             "Traceback (most recent call last):", "{not json"]
    assert _events.parse(lines[0])["text"] == "ビルド中" and _events.parse(lines[2]) is None and _events.parse(lines[3]) is None
    assert _events.messages("\n".join(lines)) == "ビルド中\nTraceback (most recent call last):\n{not json\n"


def test_cpp_program_output_streams_child_lines(tmp_path):
    """C++ の型：CppBuild の子プロセスの出力を、1行ずつ (行, stream, source) で渡す（結果の ProcessReport は今までと同じ。
    stdout・stderr を分けて読む）。実行するプログラム（cppbuild.execution.execute に渡したもの）は program、ほかは tool。
    tools=False なら tool の行は渡さない。抜けたら元に戻す。"""
    import os
    import sys
    from cppbuild import engine, execution
    from ecobuild_cpp import _cppbuild
    original, original_execute = engine.process, execution.execute
    command = [sys.executable, "-c", "import sys; print('one', flush=True); print('two', file=sys.stderr)"]
    lines = []
    write = lambda text, stream, source: lines.append((text, stream, source))  # noqa: E731
    with _cppbuild.program_output(write):
        report = engine.process(command, tmp_path)
    assert sorted(lines) == [("one", "stdout", "tool"), ("two", "stderr", "tool")]
    assert (report.returncode, sorted(report.output.splitlines())) == (0, ["one", "two"])
    assert (engine.process, execution.execute) == (original, original_execute)
    lines[:] = []
    with _cppbuild.program_output(write, tools=False):
        engine.process(command, tmp_path)                                  # ビルドのツールの代わり
        execution.execute([(command, tmp_path, dict(os.environ))])        # 実行するプログラム
    assert sorted(lines) == [("one", "stdout", "program"), ("two", "stderr", "program")]


def test_serve_reads_the_events_of_the_command(tmp_path):
    """係（agent serve）が頼みの ecobuild の標準エラーを読む：経過には ECOBuild の文だけ（ツール・プログラムの出力は
    渡さない）、結果の JSON がなければ、出力を除いた文で失敗を返す。"""
    import subprocess
    import sys
    from ecobuild_cli.commands.agent import serve
    say = ("import json, sys; e = lambda **k: print(json.dumps(k), file=sys.stderr, flush=True); "
           "e(kind='progress', text='ビルド中'); e(kind='output', text='cl.exe' + chr(10), stream='stdout', source='tool'); "
           "e(kind='error', text='失敗しました', code='build_failed'); ")

    def wait(code):
        process = subprocess.Popen([sys.executable, "-c", say + code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   encoding="utf-8", errors="replace")
        seen = []
        return serve._wait(process, seen.append, None), seen

    done, seen = wait("print(json.dumps({'ok': True, 'result': 1}))")
    assert done == {"ok": True, "result": 1} and seen == ["ビルド中", "失敗しました"]
    done, _ = wait("")
    assert not done["ok"] and "cl.exe" not in done["error"]["message"] and "失敗しました" in done["error"]["message"]
