"""流れ（ecobuild flow）：.ecobuild/flows/*.toml を読み、command・ecobuild・check・approval の工程と CLI を、偽の GitHub の
モジュールで（本物の git と、子の ecobuild は本物のプロセスで）。agent の工程は tests/unit/test_agent_flow.py。"""

import json
import os
import sys
import time
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
    assert _common.program() == (PYTHON, "-m", "ecobuild_cli")   # ecobuild として起動していなければ、この Python で
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
    # 実行の記録は作業空間の外（ECOBuild のホーム）。作業空間の ${run.dir} は工程が結果を書く所だけ
    assert run["dir"] == f".ecobuild/flows/runs/{run['id']}" and (work / run["dir"]).is_dir()
    assert not (work / run["dir"] / "state.json").exists() and (Path(run["folder"]) / "state.json").is_file()
    assert Path(os.environ["ECOBUILD_HOME"]) in Path(run["folder"]).parents

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
                        "p.write_text(str(n)); print('回 ' + str(n)); sys.exit(0 if n >= 2 else 3)")
                 + [str(counter)],
         "on_fail": {"to": "impl", "max": 2, "message": "もう一度：${out.exit_code}"}},
        {"id": "verify", "type": "check", "only": ["conflict_markers"]},
    ])
    result = cli("flow", "run", "fix", "--json")
    failed = as_json(result)["error"]
    assert result.exit_code == 1 and failed["code"] == "flow_failed" and "工程 verify で失敗しました" in failed["message"]
    assert "ecobuild flow retry" in failed["hint"] and failed["details"]["status"] == "failed"
    run = as_json(cli("flow", "status", failed["details"]["id"], "--json"))["result"]
    steps = {s["id"]: s for s in run["steps"]}
    assert run["status"] == "failed" and run["current"] == "verify"
    assert steps["impl"]["attempts"] == 2 and steps["impl"]["backs"] == 1 and steps["impl"]["message"] == "回 2"
    assert run["vars"]["feedback"] == "もう一度：3"
    assert "衝突の印" in steps["verify"]["message"] and "a.txt" in steps["verify"]["message"]
    text = cli("flow", "status", run["id"]).stdout
    assert "失敗" in text and f"ecobuild flow retry {run['id']}" in text

    refused = as_json(cli("flow", "resume", run["id"], "--json"))
    assert refused["error"]["code"] == "flow_run_state" and f"ecobuild flow retry <実行>" in refused["error"]["hint"]
    write(module.root / "a.txt", "a\n")
    write_flow(module.root, "fix", steps=[{"id": "x", "type": "approval"}])   # 定義を変えても、実行は作ったときの写しで
    retried = as_json(cli("flow", "retry", run["id"], "--json"))["result"]
    assert retried["status"] == "done" and {s["id"]: s for s in retried["steps"]}["verify"]["attempts"] == 2


def test_reject_goes_back_and_cancel(cli, module):
    write_flow(module.root, "review", steps=[
        {"id": "impl", "type": "command", "args": python("print('作った')")},
        {"id": "ok", "type": "approval", "message": "[${vars.feedback}]"},
    ])
    run = as_json(cli("flow", "run", "review", "--json"))["result"]
    assert run["status"] == "waiting"
    assert as_json(cli("flow", "reject", run["id"], "--json"))["error"]["code"] == "usage_error"   # --to・-m は必須
    again = as_json(cli("flow", "reject", run["id"], "--to", "impl", "--message", "名前を直して", "--json"))["result"]
    steps = {s["id"]: s for s in again["steps"]}
    assert again["status"] == "waiting" and steps["ok"]["message"] == "[名前を直して]" and steps["impl"]["attempts"] == 2
    cancelled = cli("flow", "cancel", run["id"], "--json")
    assert cancelled.exit_code == 0 and as_json(cancelled)["result"]["status"] == "cancelled"
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
    needs = as_json(cli("flow", "run", "needs", "--json"))["error"]
    assert needs["code"] == "invalid_argument" and "ecobuild flow run <名前> <入力の名前>=<値>" in needs["hint"]
    assert as_json(cli("flow", "run", "needs", "other=1", "goal=x", "--json"))["error"]["code"] == "invalid_argument"
    assert cli("flow", "run", "needs", "goal").exit_code == 2
    assert as_json(cli("flow", "status", "nothing-1", "--json"))["error"]["code"] == "flow_run_not_found"


def test_unsafe_definitions_are_refused(cli, module):
    """AI の値をシェルに入れない・.bat／.cmd を args の先頭にしない・流れの中で作業空間を消す操作をしない。"""
    write_flow(module.root, "unsafe", steps=[
        {"id": "a", "type": "command", "run": "echo ${inputs.who} ${run.id}"},                 # 入力と run は書ける
        {"id": "b", "type": "command", "run": "echo ${steps.a.message} ${vars.feedback}"},    # 工程・vars は書けない
        {"id": "c", "type": "command", "args": ["build.cmd", "${vars.feedback}"]},
        {"id": "d", "type": "ecobuild", "args": ["task", "finish", "--yes"]},
        {"id": "e", "type": "ecobuild", "args": ["--json", "workspace", "close"]},
    ], inputs={"who": "名前"})
    problems = as_json(cli("flow", "show", "unsafe", "--json"))["result"]["problems"]
    assert len(problems) == 4, problems
    assert "工程 b" in problems[0] and "args（引数の配列）を使います" in problems[0] and "steps.a.message" in problems[0]
    assert "build.cmd" in problems[1] and "ecobuild task finish" in problems[2] and "workspace close" in problems[3]
    batch = module.root / "tool.cmd"
    write(batch, "@echo x\n")
    write_flow(module.root, "batch", steps=[{"id": "a", "type": "command", "args": ["${inputs.tool}"]}],
               inputs={"tool": "道具"})
    failed = as_json(cli("flow", "run", "batch", f"tool={batch}", "--json"))["error"]
    assert failed["code"] == "flow_failed" and ".bat・.cmd" in failed["message"]


def test_ecobuild_step_puts_json_before_the_double_dash(cli, module):
    write_flow(module.root, "dash", steps=[{"id": "a", "type": "ecobuild", "args": ["track", "--"]}])
    run = as_json(cli("flow", "run", "dash", "--json"))["result"]
    assert run["status"] == "done", run


def test_command_timeout_stops_grandchildren(cli, module):
    from ecobuild.fsutil import process_alive
    marker = module.root / "grandchild.txt"
    spawn = ("import subprocess, sys, time; "
             "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
             "open(sys.argv[1], 'w').write(str(c.pid)); time.sleep(60)")
    write_flow(module.root, "slow", steps=[{"id": "a", "type": "command", "args": python(spawn) + [str(marker)],
                                            "timeout": 3}])
    began = time.monotonic()
    failed = as_json(cli("flow", "run", "slow", "--json"))["error"]
    assert failed["code"] == "flow_failed" and "3 秒で終わりませんでした" in failed["message"]
    assert time.monotonic() - began < 40
    pid = int(marker.read_text())
    until = time.monotonic() + 10
    while process_alive(pid) and time.monotonic() < until:
        time.sleep(0.1)
    assert not process_alive(pid)


def test_approval_commands_are_for_people():
    from ecobuild_cli import _effects
    assert _effects.effect("flow approve") == "human" and _effects.effect("flow reject") == "human"
    assert _effects.effect("flow status") == "read" and _effects.effect("flow cancel") == "confirm"


def test_commands_run_inside_the_container_unless_host(cli, module, monkeypatch):
    """コンテナにした作業空間では command の工程を中で動かす（docker exec。印を付けて止められる）。host = true だけこのPCで。"""
    import ecobuild_container
    calls = []
    monkeypatch.setattr(ecobuild_container, "enabled", lambda root: True)
    monkeypatch.setattr(ecobuild_container, "start", lambda root, **options: None)
    monkeypatch.setattr(ecobuild_container, "docker_command", lambda runner, command: ("docker",))

    def exec_command(root, prefix, args, names=(), *, directory=None, tag=""):
        calls.append({"args": list(args), "directory": directory, "tag": tag, "names": names})
        return [PYTHON, "-c", "print('中で')"]

    monkeypatch.setattr(ecobuild_container, "exec_command", exec_command)
    write_flow(module.root, "boxed", steps=[
        {"id": "inside", "type": "command", "args": ["make", "test"], "cwd": "sub"},
        {"id": "shell", "type": "command", "run": "echo ${inputs.who}"},
        {"id": "outside", "type": "command", "args": python("print('外')"), "host": True},
    ], inputs={"who": "名前"})
    (module.root / "sub").mkdir()
    run = as_json(cli("flow", "run", "boxed", "who=山田", "--json"))["result"]
    steps = {s["id"]: s for s in run["steps"]}
    assert steps["inside"]["message"] == "中で" and steps["shell"]["message"] == "中で" and steps["outside"]["message"] == "外"
    assert calls[0]["args"] == ["make", "test"] and calls[0]["directory"].endswith("/sub") and calls[0]["tag"]
    assert calls[1]["args"] == ["sh", "-c", "echo 山田"] and calls[0]["names"] == ()   # 秘密は渡さない
    write_flow(module.root, "escape", steps=[{"id": "a", "type": "command", "args": ["git"], "cwd": "${inputs.place}"}],
               inputs={"place": "場所"})
    failed = as_json(cli("flow", "run", "escape", "place=..", "--json"))["error"]
    assert failed["code"] == "flow_failed" and "作業空間の外" in failed["message"]


def test_a_recreated_workspace_does_not_show_old_runs(cli, module):
    write_flow(module.root, "one", steps=[{"id": "a", "type": "approval"}])
    run = as_json(cli("flow", "run", "one", "--json"))["result"]
    marker = module.root / ".ecobuild" / "flows" / "runs" / ".id"
    assert marker.read_text(encoding="ascii").strip() in Path(run["folder"]).parent.name
    assert len(as_json(cli("flow", "list", "--json"))["result"]["runs"]) == 1
    marker.unlink()                                   # 作業空間を作り直した（印がなくなった）
    assert as_json(cli("flow", "list", "--json"))["result"]["runs"] == []
