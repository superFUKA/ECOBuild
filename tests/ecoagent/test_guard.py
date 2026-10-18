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
