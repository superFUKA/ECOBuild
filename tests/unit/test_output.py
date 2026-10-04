import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ecobuild import config
from ecobuild.cli._output import FAILURE, SUCCESS, Invocation, execute
from ecobuild.errors import EcoBuildError, ErrorCode


@dataclass
class Sample:
    path: Path
    items: tuple[str, ...]


def test_json_success_prints_one_document(tmp_path, capsys):
    config.save(config.ModuleConfig.for_new_module("Calc", app=False), tmp_path / config.FILE_NAME)
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
