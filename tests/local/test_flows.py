"""流れ（ecobuild flow）：.ecobuild/flows/*.toml を読み、command・ecobuild・check・approval の工程と CLI を、偽の GitHub の
モジュールで（本物の git と、子の ecobuild は本物のプロセスで）。agent の工程は tests/unit/test_agent_flow.py。"""

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import ecobuild_cli
from ecobuild_cli import build_cli
from ecobuild_cli.commands.flow import _common
from ecowork import github as _github
from helpers import git, write

pytestmark = pytest.mark.local

PYTHON = sys.executable


@pytest.fixture
def cli(module, monkeypatch):
    monkeypatch.setattr(_github, "default", lambda: module.repository.github)
    monkeypatch.chdir(module.root)
    # ecobuild の工程は、試験中の ECOBuild（この src）を子のプロセスで呼ぶ
    source = str(Path(ecobuild_cli.__file__).resolve().parent.parent)
    monkeypatch.setenv("PYTHONPATH", source)
    monkeypatch.setattr(_common, "program", lambda: (PYTHON, "-m", "ecobuild_cli"))
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(build_cli(), list(args), catch_exceptions=False)

    invoke.chdir = monkeypatch.chdir
    return invoke


def as_json(result):
    return json.loads(result.stdout)


def toml_value(value) -> str:
    """TOML の値（文字列・配列・数・真偽。JSON の書き方がそのまま TOML の基本の文字列になる）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def write_flow(root: Path, name: str, steps: list[dict], description: str = "", inputs: dict | None = None) -> Path:
    parts = [f"description = {toml_value(description)}\n"]
    if inputs:
        parts.append("[inputs]\n" + "".join(f"{k} = {toml_value(v)}\n" for k, v in inputs.items()))
    for step in steps:
        parts.append("[[steps]]\n" + "".join(f"{k} = {toml_value(v)}\n" for k, v in step.items()))
    path = root / ".ecobuild" / "flows" / f"{name}.toml"
    write(path, "\n".join(parts))
    return path


def python(code: str) -> list[str]:
    return [PYTHON, "-c", code]


def statuses(result: dict) -> dict:
    return {s["id"]: s["status"] for s in result["steps"]}


def test_flow_runs_command_ecobuild_check_and_waits_for_approval(cli, module):
    work = Path(as_json(cli("task", "new", "流れ", "--start", "--name", "流れ", "--json"))["result"]["task_branch"]["workspace"])
    cli.chdir(work)
    assert cli("pipeline", "add", "quick", "--steps", "conflict_markers").exit_code == 0
    write_flow(work, "sample", description="試しの流れ", inputs={"who": {"help": "名前", "required": True}}, steps=[
        {"id": "hello", "type": "command", "json": True,
         "args": python("import json, sys; print(json.dumps({'n': 3, 'message': 'こんにちは ' + sys.argv[1]}))") + ["${inputs.who}"]},
        {"id": "track", "type": "ecobuild", "args": ["track"], "pass_if": "${out.patterns}"},
        {"id": "verify", "type": "check", "only": ["conflict_markers"]},
        {"id": "quick", "type": "pipeline", "name": "quick"},
        {"id": "ok", "type": "approval", "message": "${steps.hello.out.n} 件を確かめてください"},
        {"id": "after", "type": "command", "when": "${steps.ok.out.approved}", "run": "echo 済み"},
    ])
    listed = as_json(cli("flow", "list", "--json"))["result"]
    assert listed["flows"][0]["name"] == "sample" and listed["flows"][0]["steps"] == ["hello", "track", "verify", "quick", "ok", "after"]
    assert listed["runs"] == []
    shown = as_json(cli("flow", "show", "sample", "--json"))["result"]
    assert shown["problems"] == [] and "agent" in shown["kinds"] and shown["inputs"][0]["required"] is True

    result = cli("flow", "run", "sample", "who=山田", "--json")
    assert result.exit_code == 0, result.output
    run = as_json(result)["result"]
    assert run["status"] == "waiting" and run["current"] == "ok"
    assert statuses(run) == {"hello": "done", "track": "done", "verify": "done", "quick": "done", "ok": "waiting",
                             "after": "pending"}
    steps = {s["id"]: s for s in run["steps"]}
    assert steps["hello"]["out"] == {"exit_code": 0, "n": 3, "message": "こんにちは 山田"}
    assert steps["hello"]["message"] == "こんにちは 山田" and Path(steps["hello"]["log"]).is_file()
    assert any(p["pattern"] == "/.ecobuild/flows/*.toml" for p in steps["track"]["out"]["patterns"])
    assert steps["ok"]["message"] == "3 件を確かめてください" and steps["quick"]["message"] == "パイプライン quick が通りました"
    assert run["dir"] == f".ecobuild/flows/runs/{run['id']}" and (work / run["dir"] / "state.json").is_file()

    shown = cli("flow", "status")
    assert shown.exit_code == 0 and "人の答え待ち" in shown.stdout and f"ecobuild flow approve {run['id']}" in shown.stdout
    assert as_json(cli("flow", "list", "--json"))["result"]["runs"][0]["status"] == "waiting"

    done = as_json(cli("flow", "approve", run["id"], "--message", "よし", "--json"))["result"]
    assert done["status"] == "done" and statuses(done)["after"] == "done"
    assert {s["id"]: s for s in done["steps"]}["ok"]["out"]["message"] == "よし"

    # 実行の置き場所は git に見えない。定義は管理するファイル（task commit が自動で含める）
    seen = git(work, "status", "--porcelain", "-uall")
    assert "?? .ecobuild/flows/sample.toml" in seen and "runs" not in seen
    committed = as_json(cli("task", "commit", "--message", "流れ", "--json"))["result"]
    assert ".ecobuild/flows/sample.toml" in committed["files"]
    assert "flows" not in git(work, "status", "--porcelain", "-uall")


def test_failed_check_stops_then_retry_and_on_fail_feedback(cli, module):
    write(module.root / "a.txt", "a\n")
    git(module.root, "add", "a.txt")
    git(module.root, "commit", "--quiet", "-m", "a")
    write(module.root / "a.txt", "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> other\n")
    counter = module.root / "count.txt"
    write_flow(module.root, "fix", steps=[
        {"id": "impl", "type": "command",
         "args": python("import sys, pathlib; p = pathlib.Path(sys.argv[1]); n = int(p.read_text()) + 1 if p.exists() else 1; "
                        "p.write_text(str(n)); print('fb=' + sys.argv[2]); sys.exit(0 if n >= 2 else 3)")
                 + [str(counter), "${vars.feedback}"],
         "on_fail": {"to": "impl", "max": 2, "message": "もう一度：${out.exit_code}"}},
        {"id": "verify", "type": "check", "only": ["conflict_markers"]},
    ])
    run = as_json(cli("flow", "run", "fix", "--json"))["result"]
    steps = {s["id"]: s for s in run["steps"]}
    assert run["status"] == "failed" and run["current"] == "verify"
    assert steps["impl"]["attempts"] == 2 and steps["impl"]["backs"] == 1 and steps["impl"]["message"] == "fb=もう一度：3"
    assert "衝突の印" in steps["verify"]["message"] and "a.txt" in steps["verify"]["message"]
    text = cli("flow", "status", run["id"]).stdout
    assert "失敗" in text and f"ecobuild flow retry {run['id']}" in text

    refused = as_json(cli("flow", "resume", run["id"], "--json"))
    assert refused["error"]["code"] == "flow_run_state" and f"ecobuild flow retry <実行>" in refused["error"]["hint"]
    write(module.root / "a.txt", "a\n")
    retried = as_json(cli("flow", "retry", run["id"], "--json"))["result"]
    assert retried["status"] == "done" and {s["id"]: s for s in retried["steps"]}["verify"]["attempts"] == 2


def test_reject_goes_back_and_cancel(cli, module):
    write_flow(module.root, "review", steps=[
        {"id": "impl", "type": "command", "args": python("import sys; print(sys.argv[1])") + ["[${vars.feedback}]"]},
        {"id": "ok", "type": "approval"},
    ])
    run = as_json(cli("flow", "run", "review", "--json"))["result"]
    assert run["status"] == "waiting"
    assert as_json(cli("flow", "reject", run["id"], "--json"))["error"]["code"] == "usage_error"   # --to・-m は必須
    again = as_json(cli("flow", "reject", run["id"], "--to", "impl", "--message", "名前を直して", "--json"))["result"]
    steps = {s["id"]: s for s in again["steps"]}
    assert again["status"] == "waiting" and steps["impl"]["message"] == "[名前を直して]" and steps["impl"]["attempts"] == 2
    cancelled = as_json(cli("flow", "cancel", run["id"], "--json"))["result"]
    assert cancelled["status"] == "cancelled"
    late = as_json(cli("flow", "approve", run["id"], "--json"))
    assert late["error"]["code"] == "flow_run_state" and "取り消し" in late["error"]["message"]


def test_flow_errors(cli, module):
    assert as_json(cli("flow", "status", "--json"))["error"]["code"] == "flow_run_not_found"
    assert cli("flow", "list").stdout.startswith("流れの定義はありません")
    missing = as_json(cli("flow", "run", "nothing", "--json"))
    assert missing["error"]["code"] == "flow_not_found" and "ecobuild flow list" in missing["error"]["hint"]
    write_flow(module.root, "bad", steps=[{"id": "a", "type": "agent", "agent": "worker"},
                                          {"id": "b", "type": "nothing", "pass_if": "${steps.zzz.out.x} >"}])
    shown = as_json(cli("flow", "show", "bad", "--json"))
    assert shown["ok"] and any("prompt がありません" in p for p in shown["result"]["problems"])
    assert any("type「nothing」はありません" in p for p in shown["result"]["problems"])
    text = cli("flow", "show", "bad").stdout
    assert "誤り：" in text and "工程 zzz は定義にありません" in text
    refused = as_json(cli("flow", "run", "bad", "--json"))
    assert refused["error"]["code"] == "invalid_flow" and len(refused["error"]["details"]) >= 3
    assert "誤り" in as_json(cli("flow", "list", "--json"))["result"]["flows"][0]["error"]
    write(module.root / ".ecobuild" / "flows" / "broken.toml", "steps = [\n")
    assert as_json(cli("flow", "show", "broken", "--json"))["error"]["code"] == "invalid_flow"
    write_flow(module.root, "needs", inputs={"goal": {"required": True}}, steps=[{"id": "a", "type": "approval"}])
    assert as_json(cli("flow", "run", "needs", "--json"))["error"]["code"] == "invalid_argument"
    assert as_json(cli("flow", "run", "needs", "other=1", "goal=x", "--json"))["error"]["code"] == "invalid_argument"
    assert cli("flow", "run", "needs", "goal").exit_code == 2
    assert as_json(cli("flow", "status", "nothing-1", "--json"))["error"]["code"] == "flow_run_not_found"
