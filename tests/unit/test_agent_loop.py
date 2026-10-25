"""改善のループと止める条件（登録の evaluation・max_rounds・max_turns・max_cost・lessons）：登録に残り、起動の文に入り、
上限はアプリ用の起動（claude -p）の引数になり、上限で止まったら親に「止まっている」と知らせる。"""

import json
from types import SimpleNamespace

import pytest

from ecobuild.errors import EcoBuildError
from ecobuild_agent import app, children, limits, loop_lines, registry, status


def test_the_loop_fields_are_kept_in_the_registration(tmp_path):
    changed = registry.update(tmp_path, "worker", evaluation="check（only=build,test）", max_rounds=3, max_turns=120,
                              max_cost=2.5, lessons=".ecobuild/agents/lessons")
    loaded = registry.load("worker", tmp_path)
    assert loaded == changed
    assert (loaded.evaluation, loaded.max_rounds, loaded.max_turns, loaded.max_cost, loaded.lessons) == \
        ("check（only=build,test）", 3, 120, 2.5, ".ecobuild/agents/lessons")
    copied = tmp_path / "registration.json"     # コンテナの中の MCP サーバーへ渡す写し
    copied.write_text(json.dumps(registry.to_data(loaded), ensure_ascii=False), encoding="utf-8")
    assert registry.from_file(copied).max_cost == 2.5 and registry.from_file(copied).lessons == loaded.lessons
    plain = registry.update(tmp_path, "manager", model="haiku")     # 書いていなければ決めない
    assert (plain.max_rounds, plain.max_turns, plain.max_cost, plain.evaluation) == (0, 0, 0.0, "")


@pytest.mark.parametrize("fields", [{"max_turns": -1}, {"max_cost": -0.5}, {"lessons": "/etc/lessons"},
                                    {"lessons": "C:/lessons"}, {"lessons": "../outside"}])
def test_bad_limits_and_places_are_refused(tmp_path, fields):
    with pytest.raises(EcoBuildError):
        registry.update(tmp_path, "worker", **fields)


def test_the_worker_sample_runs_the_loop():
    worker = next(r for r in registry.samples() if r.name == "worker")
    assert worker.max_rounds and worker.max_turns and worker.lessons
    assert "評価し直す" in worker.document and "restore" in worker.document


def test_the_briefing_tells_the_loop_and_the_limits():
    r = registry.Registration(name="worker", title="作業役", document="", evaluation="check", max_rounds=3,
                              max_turns=100, max_cost=1.5, lessons=".ecobuild/agents/lessons/")
    text = "\n".join(loop_lines(r, SimpleNamespace(number=42)))
    assert "`check`" in text and "3 回まで" in text and "100 ターン・1.5 ドル" in text
    assert "`.ecobuild/agents/lessons/42.md`" in text
    assert loop_lines(registry.Registration(name="x", title="x", document=""), SimpleNamespace(number=1)) == []
    assert "報告の「教訓」" in "\n".join(loop_lines(registry.Registration(name="x", title="x", document="", max_rounds=2),
                                                   SimpleNamespace(number=1)))
    assert limits(r) == ("--max-turns", "100", "--max-budget-usd", "1.5")
    assert limits(registry.Registration(name="x", title="x", document="")) == ()


def test_reaching_a_limit_is_told_to_the_parent_as_stuck(tmp_path):
    """上限で止まった結果（error_max_turns 等）：最後の返答に「状態：止まっている」を足す（ハーネスが止めたので、子は
    状態の行を書けない）。ほかのエラーは今までどおり。"""
    assert app.limit_reached("error_max_turns") == "ターン数の上限"
    assert app.limit_reached("error_max_budget_usd") == "費用の上限"
    assert app.limit_reached("error_during_execution") == ""
    agent = app.Agent("a-0123456789", tmp_path, tmp_path)
    agent._result({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "途中まで直しました"}, 1.0)
    message = status.read(tmp_path / "replied.json")["message"]
    assert "ターン数の上限に達した" in message and children.reported_state(message) == children.STUCK
    agent._result({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "x"}, 2.0)
    message = status.read(tmp_path / "replied.json")["message"]
    assert "エラーで返答を終えました" in message and children.reported_state(message) == children.UNKNOWN_STATE
