"""入口（-C・--json の用法エラー）とツールの設定・診断（範囲外の機能）。"""

import json

import pytest

from ecobuild import tooling
from ecobuild.cli import main


def run_main(args, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    return exit_info.value.code, capsys.readouterr()


def test_usage_errors_are_json_with_json_flag(capsys):
    code, out = run_main(["nosuch", "--json"], capsys)
    document = json.loads(out.out)
    assert code == 2 and document["error"]["code"] == "usage_error"
    code, out = run_main(["task", "commit", "--json"], capsys)
    assert code == 2 and json.loads(out.out)["error"]["message"] == "--message を指定してください。"
    code, out = run_main(["nosuch"], capsys)
    assert code == 2 and out.out == ""


def test_directory_option(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    code, out = run_main(["-C", "sub", "status", "--json"], capsys)
    document = json.loads(out.out)
    assert code == 1 and document["error"]["code"] == "not_in_module" and "sub" in document["error"]["message"]
    code, out = run_main(["-C", "nosuch", "status", "--json"], capsys)
    assert code == 2 and json.loads(out.out)["error"]["code"] == "usage_error"


def test_tool_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    assert tooling.home() == tmp_path / "home" and tooling.load_config() == {}
    assert tooling.qualify("Calc") == "Calc"
    assert tooling.set_config("owner", "my-org") == {"owner": "my-org"}
    assert tooling.qualify("Calc") == "my-org/Calc" and tooling.qualify("other/Calc") == "other/Calc"
    assert tooling.set_config("owner", None) == {}
    with pytest.raises(Exception) as error:
        tooling.set_config("nosuch", "x")
    assert error.value.code == "invalid_argument"


def test_doctor_reports_missing_tools(monkeypatch):
    """ツールが見つからなければ必須の項目がNGになり、setup が導入コマンドを示す。"""
    monkeypatch.setattr(tooling.shutil, "which", lambda name: None)
    monkeypatch.setattr(tooling._module_type, "available", lambda: [])
    report = tooling.doctor()
    names = {i.name: i.ok for i in report.items}
    assert names["git"] is False and names["gh"] is False and not report.ok
    setup = tooling.setup()
    assert setup.done == () and any("Git.Git" in c or "git" in c for c in setup.commands)
