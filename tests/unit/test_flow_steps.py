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
    ctx = SimpleNamespace(log=logged.append, log_path=tmp_path / "verify.log")
    items = [{"name": "build", "ok": True, "detail": "", "output": ""},
             {"name": "test", "ok": False, "detail": "テストに失敗しました。", "output": "前半" + "y" * 3000 + "assert 1 == 2"}]
    outcome = flows._items_outcome(items, ctx, "", "通りました")
    assert outcome.status == "failed" and outcome.message.startswith("テスト：テストに失敗しました。")
    assert f"ログ：{tmp_path / 'verify.log'}" in outcome.message and outcome.message.endswith("assert 1 == 2")
    assert "前半" not in outcome.message                          # 末尾だけ
    assert any("assert 1 == 2" in line for line in logged)
    assert outcome.out == {"items": [{"name": "build", "ok": True, "detail": ""},
                                     {"name": "test", "ok": False, "detail": "テストに失敗しました。"}]}
    assert flows._items_outcome(items[:1], ctx, "", "通りました").message == "通りました"


def test_command_and_ecobuild_settings():
    assert flows._check_command({"run": "echo ${inputs.a} ${run.dir}"}) == []
    assert "args（引数の配列）を使います" in flows._check_command({"run": "echo ${out.x}"})[0]
    assert flows._check_command({"args": ["python", "${steps.a.message}"]}) == []
    assert ".bat・.cmd" in flows._check_command({"args": ["x.BAT"]})[0]
    assert flows._check_args({"args": ["task", "status"]}) == []
    for closing in (["task", "drop"], ["-C", "x", "task", "prune"], ["workspace", "close", "--yes"], ["task", "approve", "3"]):
        assert flows._check_args({"args": closing}) != [], closing
