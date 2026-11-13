"""流れの ECOBuild の工程（ecobuild.flows）のうち、モジュールなしで確かめられるもの：失敗の出力の末尾・定義の確かめ。"""

from types import SimpleNamespace

from ecobuild import flows
from ecobuild.module import _failure_output


def test_failure_output_takes_the_tail_of_the_build_output():
    assert _failure_output("x" * 5000 + "最後の行").endswith("最後の行")
    assert len(_failure_output("x" * 5000)) == 4000
    assert _failure_output({"output": "テストの出力", "stdout": "使わない"}) == "テストの出力"
    assert _failure_output({"stdout": "標準出力", "stderr": "誤り"}) == "標準出力\n誤り"
    assert _failure_output(None) == "" and _failure_output(["x"]) == ""


def test_failed_items_put_the_output_tail_in_the_log_and_the_message(tmp_path):
    logged = []
    ctx = SimpleNamespace(log=logged.append, dir="runs/r", step=SimpleNamespace(id="verify"))
    items = [{"name": "build", "ok": True, "detail": "", "output": ""},
             {"name": "test", "ok": False, "detail": "テストに失敗しました。", "output": "前半" + "y" * 3000 + "assert 1 == 2"}]
    outcome = flows._items_outcome(items, ctx, "", "通りました", tmp_path)
    assert outcome.status == "failed" and outcome.message.startswith("テスト：テストに失敗しました。")
    # 文には作業空間からの相対の場所（コンテナの中からも読める）。出力は ${run.dir}/<工程>.log にも写す
    assert "（出力：runs/r/verify.log）" in outcome.message and outcome.message.endswith("assert 1 == 2")
    assert str(tmp_path) not in outcome.message
    assert "assert 1 == 2" in (tmp_path / "runs" / "r" / "verify.log").read_text(encoding="utf-8")
    assert "前半" not in outcome.message                          # 末尾だけ
    assert any("assert 1 == 2" in line for line in logged)
    assert outcome.out == {"items": [{"name": "build", "ok": True, "detail": ""},
                                     {"name": "test", "ok": False, "detail": "テストに失敗しました。"}]}
    assert flows._items_outcome(items[:1], ctx, "", "通りました").message == "通りました"


def test_command_and_ecobuild_settings():
    assert flows._check_command({"run": "echo ${inputs.a} ${run.dir}"}) == []
    assert "args（引数の配列）を使います" in flows._check_command({"run": "echo ${out.x}"})[0]
    assert flows._check_command({"args": ["git", "commit", "-m", "${steps.a.message}"]}) == []
    assert flows._check_command({"args": ["python", "x.py", "${inputs.a}", "${run.dir}"]}) == []
    for program in ("python", "C:/Python/python3.12.exe", "bash", "pwsh.exe", "cmd", "node"):
        assert "シェル・インタープリター" in flows._check_command({"args": [program, "-c", "${vars.feedback}"]})[0], program
    assert "args の先頭" in flows._check_command({"args": ["${steps.a.out.tool}"]})[0]
    assert "cwd" in flows._check_command({"args": ["git"], "cwd": "${out.dir}"})[0]
    assert "host は真偽" in flows._check_command({"args": ["git"], "host": "yes"})[0]
    for args in (["${vars.x}", "status"], ["task", "${steps.a.message}"], ["-C", "${out.place}", "status"],
                 ["--directory", "${vars.d}", "track"]):
        assert "コマンドの名前の部分と -C の値" in flows._check_args({"args": args})[0], args
    assert flows._check_args({"args": ["task", "submit", "--note", "${steps.impl.message}"]}) == []
    assert flows._check_args({"args": ["-C", "${inputs.place}", "status"]}) == []
    assert ".bat・.cmd" in flows._check_command({"args": ["x.BAT"]})[0]
    assert flows._check_args({"args": ["task", "status"]}) == []
    for closing in (["task", "drop"], ["-C", "x", "task", "prune"], ["workspace", "close", "--yes"], ["task", "approve", "3"]):
        assert flows._check_args({"args": closing}) != [], closing


def test_empty_check_output_is_not_shown_in_json():
    from ecobuild.results import CheckItem
    from ecobuild_cli._output import to_data
    assert to_data(CheckItem("build", True)) == {"name": "build", "ok": True, "detail": ""}
    assert to_data(CheckItem("test", False, "失敗", "出力"))["output"] == "出力"
