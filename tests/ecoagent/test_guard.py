"""ecoagent.guard：シェルのコマンドの関所（許したプログラム・読むだけのコマンド・重さと確認）。"""

import json

from ecoagent import guard
from ecoagent.guard import CHANGE, CONFIRM, HUMAN, READ, Exchange, Policy


def _classify(args):
    weights = {"list": READ, "start": CHANGE, "delete": CONFIRM, "setup": HUMAN}
    return weights.get(args[0] if args else "", CHANGE), args[0] if args else ""


POLICY = Policy(frozenset({"tool"}), _classify, refusals={HUMAN: "人がします"})


def test_allows_the_program_and_reading():
    assert guard.check("tool list --json", POLICY) is None
    assert guard.check('C:/bin/tool.exe start 12 && cat a.txt | grep "x; rm -rf"', POLICY) is None


def test_stops_other_programs_and_writing():
    assert "rm" in guard.check("rm -rf build", POLICY)
    assert guard.check("tool list > out.txt", POLICY).startswith("ファイルへの書き出し")
    assert guard.check("cat $(tool list)", POLICY) is not None
    assert "python" in guard.check("tool list; python -c 1", POLICY)


def test_human_is_never_allowed():
    assert guard.check("tool setup", POLICY, Exchange("tool setup を実行します。よろしいですか？", "はい")) == "人がします"


def test_confirm_needs_the_question_and_a_yes():
    assert guard.check("tool delete Calc", POLICY) is not None
    asked = "`tool delete Calc` を実行します。よろしいですか？"
    assert guard.check("tool delete Calc", POLICY, Exchange(asked, "はい、お願いします")) is None
    assert guard.check("tool delete Calc", POLICY, Exchange(asked, "いや、やめて")) is not None
    assert guard.check("tool delete Calc", POLICY, Exchange("一覧を出しました。", "はい")) is not None


def test_last_exchange_reads_the_transcript(tmp_path):
    lines = [
        {"type": "user", "message": {"content": "Calc を消して"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "`tool delete Calc` でよいですか？"}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "うん"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "user", "isMeta": True, "message": {"content": "<system>"}},
    ]
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines), encoding="utf-8")
    assert guard.last_exchange(transcript) == Exchange("`tool delete Calc` でよいですか？", "うん")
    assert guard.last_exchange(tmp_path / "none.jsonl") == Exchange()


def test_hook_exit_code():
    assert guard.hook(json.dumps({"tool_input": {"command": "tool list"}}), POLICY) == (0, "")
    code, message = guard.hook(json.dumps({"tool_input": {"command": "del a.txt"}}), POLICY)
    assert code == 2 and "del" in message


def test_discarding_output_is_not_writing_a_file():
    assert guard.check("tool list 2>/dev/null", POLICY) is None
    assert guard.check("tool list 2>&1 | grep x", POLICY) is None
    assert guard.check("tool list >$null", POLICY) is None
    assert guard.check("tool list 2>err.txt", POLICY).startswith("ファイルへの書き出し")
    assert guard.check("tool list > /dev/null.txt", POLICY).startswith("ファイルへの書き出し")


def test_loops_and_conditions_check_the_commands_inside():
    assert guard.check("for n in 1 2; do tool list $n; done", POLICY) is None
    assert guard.check("if tool list; then cat a.txt; else echo no; fi", POLICY) is None
    assert "rm" in guard.check("for n in 1 2; do rm $n; done", POLICY)
    assert guard.check("for w in list delete; do tool $w x; done", POLICY) is not None   # 変数の値も重さを調べる
    assert guard.check("for w in setup; do tool ${w}; done", POLICY) == "人がします"
    assert guard.check("for x; do tool list; done", POLICY).startswith("for は")


def test_a_bare_y_is_a_yes():
    asked = "`tool delete Calc` を実行します。よろしいですか？"
    assert guard.check("tool delete Calc", POLICY, Exchange(asked, "y")) is None
    assert guard.check("tool delete Calc", POLICY, Exchange(asked, "yy")) is not None
