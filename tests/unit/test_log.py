import json
import subprocess
import sys

import pytest

import ecobuild_bundle
from ecobuild import config, settings
from ecobuild import module as ecobuild_module
from ecobuild.errors import EcoBuildError
from ecobuild_cli import _log, main
from ecobuild_cli._output import Invocation, execute
from ecotask import process as _process
from helpers import git


def entries(directory):
    return [json.loads(line) for path in sorted(directory.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()]


def events(directory):
    return [entry["event"] for entry in entries(directory)]


@pytest.fixture
def module_root(tmp_path):
    root = tmp_path / "Calc"
    git(tmp_path, "init", "--quiet", "--initial-branch=main", str(root))
    config.save(config.ModuleConfig.for_new_module("Calc", "cpp"), root / config.FILE_NAME)
    git(root, "add", config.FILE_NAME)
    git(root, "commit", "--quiet", "-m", "設定")
    return root


def run_in_module(root, action):
    _log.start(["sample"])
    try:
        code = execute("sample", Invocation(json_output=True, cwd=root), action)
    finally:
        _log.finish(0)
    return code


def test_module_command_is_logged_in_the_module(module_root, capsys):
    def action(inv):
        inv.module
        inv.info("進捗")
        return {"status": _process.run(["git", "status", "--short"], cwd=inv.module.root).returncode}

    run_in_module(module_root, action)
    log = _log.module_directory(module_root)
    found = entries(log)
    # process：実行した git 等（ECOBuild 自身のファイルを調べる git status も記録される）
    assert [e["event"] for e in found if e["event"] != "process"] == ["command.start", "progress", "command.result", "command.end"]
    assert len({e["run"] for e in found}) == 1
    process = next(e["data"] for e in found if e["event"] == "process" and e["data"]["args"] == ["git", "status", "--short"])
    assert process["args"] == ["git", "status", "--short"] and process["returncode"] == 0
    assert "stdout" in process and "seconds" in process
    # ECOBuildのログには要約だけ（詳しいログの場所つき）
    summary = entries(_log.global_directory())
    assert [e["event"] for e in summary] == ["command.summary"]
    assert summary[0]["data"]["module"] == module_root.as_posix()
    assert summary[0]["data"]["log"] == log.as_posix()
    # ログはgitに見えない。.ecobuild/.gitignore はモジュールと同じ中身（ほかに .ecobuild/ に置くものは見える）
    assert git(module_root, "status", "--porcelain").strip() == "?? .ecobuild/.gitignore"
    assert (module_root / ".ecobuild/.gitignore").read_text(encoding="utf-8") == ecobuild_module.GITIGNORE


def test_error_is_logged_with_details(module_root, capsys):
    def action(inv):
        inv.module
        raise EcoBuildError("invalid_argument", "だめです", hint="こうしてください", details="出力の全文")

    run_in_module(module_root, action)
    error = next(e for e in entries(_log.module_directory(module_root)) if e["event"] == "command.error")
    assert error["level"] == "error"
    assert error["data"]["code"] == "invalid_argument" and error["data"]["details"] == "出力の全文"
    assert "Traceback" in error["traceback"]


def test_outside_a_module_everything_goes_to_the_ecobuild_log(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)   # 試験を動かす場所（ECOBuild のリポジトリ等）がモジュールでも、その外で
    with pytest.raises(SystemExit):
        main(["config", "list", "--json"])
    assert events(_log.global_directory()) == ["command.start", "command.type", "command.result", "command.end"]
    chosen = next(e for e in entries(_log.global_directory()) if e["event"] == "command.type")["data"]
    assert chosen["type"] is None and "ecobuild.toml" in chosen["reason"]     # 型のコマンドを重ねなかった理由


def test_level_info_leaves_out_external_commands(module_root, monkeypatch, capsys):
    monkeypatch.setenv(_log.LEVEL_VARIABLE, "info")
    run_in_module(module_root, lambda inv: _process.run(["git", "status"], cwd=inv.module.root).returncode)
    assert events(_log.module_directory(module_root)) == ["command.start", "command.end"]


def test_level_from_the_config_and_off(module_root, capsys):
    ecobuild_bundle.set_config("log_level", "off")
    run_in_module(module_root, lambda inv: inv.module.root)
    assert not _log.module_directory(module_root).exists()
    assert not _log.global_directory().exists()


def test_config_rejects_unknown_values():
    with pytest.raises(EcoBuildError) as raised:
        ecobuild_bundle.set_config("log_level", "loud")
    assert "off・error・info・debug" in raised.value.hint
    with pytest.raises(EcoBuildError):
        ecobuild_bundle.set_config("log_max_mb", "0")
    assert ecobuild_bundle.set_config("log_max_mb", "50")["log_max_mb"] == "50"
    assert _log.max_bytes() == 50 * 1024 * 1024


def test_processes_started_by_other_code_are_logged(module_root, capsys):
    """CppBuild 等、ecotask.process を通らない起動も、引数と場所を書く。"""
    def action(inv):
        inv.module
        subprocess.run([sys.executable, "-c", "pass"], cwd=inv.module.root, check=True)

    run_in_module(module_root, action)
    start = next(e for e in entries(_log.module_directory(module_root)) if e["event"] == "process.start")
    assert " ".join(start["data"]["args"]).endswith("-c pass")  # Windows では1つの文字列
    assert start["data"]["caller"].startswith(__name__)


def test_secrets_are_hidden():
    text = _log.redact('git clone https://x-access-token:abc123@github.com/o/r "token": "ghp_' + "a" * 36 + '"')
    assert "abc123" not in text and "ghp_" not in text
    assert "https://***@github.com/o/r" in text


def test_old_days_are_removed_over_the_limit(tmp_path):
    for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
        (tmp_path / f"{day}.jsonl").write_text("x" * 100, encoding="utf-8")
    _log.prune(tmp_path, 250)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-01-02.jsonl", "2026-01-03.jsonl"]


def test_the_ecobuild_log_is_under_the_tool_home():
    assert _log.global_directory() == settings.home() / "logs"
