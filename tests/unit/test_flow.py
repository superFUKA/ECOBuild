"""ecoflow：定義の確かめ・展開と条件・状態機械（偽の工程の種類で）。"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

import ecoflow

from ecoflow import (CANCELLED, DONE, FAILED, INTERRUPTED, RUNNING, WAITING, Engine, FlowError, Kind, Outcome, Store,
                     check, condition, evaluate, expand, load)
from ecoflow.run import LOCK_FILE, Run, lock


class Script:
    """偽の種類：工程ごとに、決めた結果を順に返す（尽きたら done）。呼ばれた順と、そのときの展開を覚える。"""

    def __init__(self, **plans):
        self.plans = {key: list(value) for key, value in plans.items()}
        self.calls = []

    def __call__(self, step, ctx):
        self.calls.append((step.id, ctx.setting("say", "")))
        plan = self.plans.get(step.id)
        result = plan.pop(0) if plan else ("done", "", {})
        status, message, *rest = result
        out = rest[0] if rest else {}
        return Outcome(status, message, out=out)


def make(steps, inputs=None, **plans):
    script = Script(**plans)
    events = []
    engine = Engine({"fake": script, "approval": lambda step, ctx: Outcome("waiting", ctx.setting("message", ""))},
                    progress=events.append)
    data = {"steps": steps, **({"inputs": inputs} if inputs else {})}
    return engine, load(data, "sample", engine.kinds), script, events


def statuses(run):
    return {key: value["status"] for key, value in run.steps.items()}


# ---- 定義 -------------------------------------------------------------------------------------------------
def test_definition_errors_are_listed():
    kinds = {"fake": Kind(run=lambda s, c: Outcome("done"), settings=("say",), required=("say",))}
    flow, problems = check({"steps": [
        {"id": "a", "type": "fake", "say": "x"},
        {"id": "a", "type": "fake", "say": "x"},                      # 重複
        {"id": "b c", "type": "fake"},                                # id の形
        {"id": "d", "type": "nothing"},                               # ない種類
        {"id": "e", "type": "fake"},                                  # 必須の設定がない
        {"id": "f", "type": "fake", "say": "x", "color": 1},          # 知らない設定
        {"id": "g", "type": "fake", "say": "x", "on_fail": {"to": "h", "max": 3}},   # 後ろの工程へは戻れない
        {"id": "h", "type": "fake", "say": "x", "loop": {"to": "a", "max": 11}},     # 回数の範囲
        {"id": "i", "type": "fake", "say": "${steps.zzz.message}"},  # 定義にない工程
        {"id": "j", "type": "fake", "say": "${foo.x}", "pass_if": "${out.a} >="},   # 知らない頭・条件の構文
        {"id": "k", "type": "fake", "say": "x", "retries": -1, "timeout": 0},
    ], "extra": 1}, "bad", kinds)
    assert flow is None
    text = "\n".join(problems)
    for expected in ("知らない項目があります：extra", "工程 a が重なっています", "id は英数字",
                     "type「nothing」はありません", "工程 e（fake）に say がありません", "知らない項目があります：color",
                     "on_fail.to「h」は、自分か前の工程ではありません", "max は 1〜10", "工程 zzz は定義にありません",
                     "頭は inputs・vars・steps・out・run", "pass_if", "retries は 0〜10", "timeout は正の数"):
        assert expected in text, expected
    with pytest.raises(FlowError) as raised:
        load({"steps": []}, "empty", kinds)
    assert raised.value.code == "invalid_flow" and raised.value.details == ["steps（[[steps]]）が1つもありません。"]


def test_inputs_are_checked_when_a_run_is_made(tmp_path):
    engine, flow, _, _ = make([{"id": "a", "type": "fake"}],
                              inputs={"goal": {"help": "目的", "required": True}, "level": {"default": 2}, "note": "メモ"})
    store = Store(tmp_path)
    with pytest.raises(FlowError) as missing:
        store.create(flow, {})
    assert missing.value.code == "invalid_input" and missing.value.details == {"missing": ["goal"]}
    with pytest.raises(FlowError) as unknown:
        store.create(flow, {"goal": "x", "other": "y"})
    assert "other" in unknown.value.message
    run = store.create(flow, {"goal": "直す"})
    assert run.state["inputs"] == {"level": 2, "goal": "直す"}


# ---- 展開と条件 -----------------------------------------------------------------------------------------
def test_expand():
    scope = {"inputs": {"goal": "直す"}, "vars": {"n": 3, "ok": True, "f": 2.0}, "steps": {"a": {"out": {"list": [1, "x"]}}},
             "out": {}, "run": {"id": "r1"}}
    assert expand("${inputs.goal}・${vars.n}・${vars.ok}・${vars.f}・${missing.x}・${steps.a.out.list}・$${inputs.goal}",
                  scope) == '直す・3・true・2・・[1, "x"]・${inputs.goal}'
    assert expand("${ steps.a.out.list.1 }", scope) == "x"


@pytest.mark.parametrize("text, expected", [
    ("${out.score} >= 80", True), ("${out.score} > 90", False), ("${out.score} == 85.0", True),
    ("${out.name} == 'abc'", True), ('${out.name} != "abc"', False), ("${out.name} < abd", False),
    ("${out.flag}", False), ("!${out.flag}", True), ("${out.empty}", False), ("${out.missing}", False),
    ("${out.no}", False), ("${out.zero}", False), ("${out.name}", True),
    ("${out.score} >= 80 && ${out.flag}", False), ("${out.score} >= 80 || ${out.flag}", True),
    ("!(${out.score} < 80 || ${out.flag}) && ${out.name}", True), ("${out.score}>=80", True),
    # 大小は数どうしだけ（片方が数でなければ偽）
    ("${out.name} >= 80", False), ("${out.empty} < 1", False), ("${out.missing} < 1", False),
    ("${out.under} > 5", False), ("${out.inf} > 1", False), ("${out.nan} != 1", True), ("${out.text_num} > 9", True),
    # 空の配列・表は偽。! は比べより弱い（!a == b は !(a == b)）
    ("${out.list}", False), ("${out.map}", False), ("${out.full}", True), ("!${out.score} == 85", False),
])
def test_conditions(text, expected):
    scope = {"out": {"score": 85, "name": "abc", "flag": False, "empty": "", "no": "No", "zero": "0", "under": "1_0",
                     "inf": "inf", "nan": "nan", "text_num": " 10 ", "list": [], "map": {}, "full": [0]}}
    assert evaluate(text, scope) is expected


@pytest.mark.parametrize("text", ["", "${a} ==", "&& x", "(a == b", "a == b )", "a = b", "a & b", "'${out.a}' == x",
                                  "${out.a", "x${out.a}", "(" * 70 + "a" + ")" * 70, "!" * 70 + "a", "a == " + "b" * 2100])
def test_condition_syntax_errors(text):
    with pytest.raises(ValueError):
        condition(text)


def test_conditions_do_not_evaluate_code():
    with pytest.raises(ValueError):
        evaluate("__import__('os').system('x') == 1", {})
    assert evaluate("__import__ == __import__", {}) is True   # ただの語として比べる


# ---- 状態機械 -------------------------------------------------------------------------------------------
def test_steps_run_in_order_with_when_and_expansion(tmp_path):
    engine, flow, script, events = make([
        {"id": "a", "type": "fake", "say": "${inputs.goal}"},
        {"id": "b", "type": "fake", "when": "${steps.a.out.go}", "say": "b"},
        {"id": "c", "type": "fake", "when": "!${steps.a.out.go}", "say": "${steps.a.message}/${run.id}"},
    ], inputs={"goal": "x"}, a=[("done", "a の文", {"go": False})])
    run = engine.start(Store(tmp_path), flow, {"goal": "目的"}, run_id="r1")
    assert run.status == DONE and statuses(run) == {"a": "done", "b": "skipped", "c": "done"}
    assert script.calls == [("a", "目的"), ("c", "a の文/r1")]
    saved = json.loads((tmp_path / "r1" / "state.json").read_text(encoding="utf-8"))
    assert saved["status"] == "done" and saved["definition"]["steps"][0]["id"] == "a"
    assert [e["event"] for e in saved["history"]][:3] == ["created", "started", "done"]
    assert any("飛ばします" in e for e in events) and not run.locked()


def test_pass_if_and_failure_stop_the_run(tmp_path):
    engine, flow, script, _ = make([
        {"id": "review", "type": "fake", "pass_if": "${out.score} >= 80"},
        {"id": "after", "type": "fake"},
    ], review=[("done", "", {"score": 50})])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == FAILED and run.state["current"] == "review"
    assert run.steps["review"]["message"] == "pass_if（${out.score} >= 80）を満たしません"
    assert [c[0] for c in script.calls] == ["review"]
    engine, flow, _, _ = make([{"id": "review", "type": "fake", "pass_if": "${out.score} >= 80"}],
                              review=[("done", "", {"score": 10, "message": "直すところが多い"})])
    assert engine.start(Store(tmp_path), flow).steps["review"]["message"] == "直すところが多い"


def test_retries_repeat_the_same_step(tmp_path):
    engine, flow, script, _ = make([{"id": "a", "type": "fake", "retries": 2}],
                                   a=[("failed", "1"), ("failed", "2"), ("done", "3")])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == DONE and run.steps["a"]["attempts"] == 3 and run.steps["a"]["retried"] == 2
    engine, flow, script, _ = make([{"id": "a", "type": "fake", "retries": 1}], a=[("failed", "1"), ("failed", "2")])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == FAILED and run.steps["a"]["message"] == "2" and len(script.calls) == 2


def test_on_fail_goes_back_with_feedback_up_to_max(tmp_path):
    engine, flow, script, _ = make([
        {"id": "impl", "type": "fake", "say": "fb=${vars.feedback}"},
        {"id": "verify", "type": "fake", "on_fail": {"to": "impl", "max": 2}},
    ], verify=[("failed", "テスト1"), ("failed", "テスト2"), ("failed", "テスト3")])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == FAILED and run.steps["verify"]["backs"] == 2
    assert script.calls == [("impl", "fb="), ("verify", ""), ("impl", "fb=テスト1"), ("verify", ""), ("impl", "fb=テスト2"),
                            ("verify", "")]
    assert run.steps["impl"]["attempts"] == 3
    # message を書けば、それを feedback に（失敗した工程の out で展開）
    engine, flow, script, _ = make([
        {"id": "impl", "type": "fake", "say": "${vars.feedback}"},
        {"id": "verify", "type": "fake", "on_fail": {"to": "impl", "max": 1, "message": "直す：${out.detail}"}},
    ], verify=[("failed", "x", {"detail": "a.py"})])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == DONE and script.calls[2] == ("impl", "直す：a.py")


def test_retries_come_before_on_fail(tmp_path):
    engine, flow, script, _ = make([
        {"id": "impl", "type": "fake"},
        {"id": "verify", "type": "fake", "retries": 1, "on_fail": {"to": "impl", "max": 1}},
    ], verify=[("failed", "1"), ("failed", "2"), ("done", "3")])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == DONE and [c[0] for c in script.calls] == ["impl", "verify", "verify", "impl", "verify"]


def test_loop_until(tmp_path):
    engine, flow, script, _ = make([
        {"id": "a", "type": "fake"},
        {"id": "b", "type": "fake", "loop": {"to": "a", "max": 5, "until": "${out.n} >= 3"}},
    ], b=[("done", "", {"n": 1}), ("done", "", {"n": 2}), ("done", "", {"n": 3})])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == DONE and run.steps["b"]["loops"] == 2 and len(script.calls) == 6
    engine, flow, script, _ = make([{"id": "a", "type": "fake", "loop": {"to": "a", "max": 2}}])   # until なし：max 回
    assert engine.start(Store(tmp_path), flow).steps["a"]["attempts"] == 3


def test_approval_waits_then_approve_continues(tmp_path):
    engine, flow, script, _ = make([
        {"id": "impl", "type": "fake", "say": "${vars.feedback}"},
        {"id": "ok", "type": "approval", "message": "見てください"},
        {"id": "submit", "type": "fake", "say": "${steps.ok.out.message}"},
    ])
    store = Store(tmp_path)
    run = engine.start(store, flow, run_id="r")
    assert run.status == WAITING and run.state["current"] == "ok" and run.steps["ok"]["message"] == "見てください"
    with pytest.raises(FlowError) as refused:
        engine.resume(store.get("r"))
    assert refused.value.code == "flow_run_state" and refused.value.details["actions"] == ["approve", "reject", "cancel"]
    with pytest.raises(FlowError) as nowhere:
        engine.reject(store.get("r"), "submit", "x")             # 後ろの工程へは差し戻せない
    assert nowhere.value.code == "invalid_input"
    run = engine.reject(store.get("r"), "impl", "名前を直して")
    assert run.status == WAITING and script.calls[-1] == ("impl", "名前を直して") and run.steps["impl"]["attempts"] == 2
    run = engine.approve(store.get("r"), "よし")
    assert run.status == DONE and script.calls[-1] == ("submit", "よし")
    assert run.steps["ok"]["out"]["approved"] is True
    with pytest.raises(FlowError):
        engine.approve(store.get("r"))


def test_retry_after_failure(tmp_path):
    engine, flow, script, _ = make([{"id": "a", "type": "fake"}, {"id": "b", "type": "fake"}], b=[("failed", "x")])
    store = Store(tmp_path)
    run = engine.start(store, flow, run_id="r")
    assert run.status == FAILED
    with pytest.raises(FlowError) as refused:
        engine.resume(store.get("r"))
    assert refused.value.details["actions"] == ["retry", "cancel"]
    run = engine.retry(store.get("r"))
    assert run.status == DONE and [c[0] for c in script.calls] == ["a", "b", "b"]


def test_cancel(tmp_path):
    engine, flow, _, _ = make([{"id": "ok", "type": "approval"}, {"id": "b", "type": "fake"}])
    store = Store(tmp_path)
    run = engine.cancel(engine.start(store, flow, run_id="r"))
    assert run.status == CANCELLED and run.steps["ok"]["status"] == "cancelled"
    with pytest.raises(FlowError):
        engine.cancel(store.get("r"))


def test_cancel_request_stops_a_running_run_at_the_next_step(tmp_path):
    asked = []

    def first(step, ctx):
        (ctx.folder / "cancel").write_text("x")   # ほかのプロセスの cancel が、動いている間に印を置いた
        asked.append(ctx.cancelled())
        return Outcome("done")

    engine = Engine({"fake": first})
    flow = load({"steps": [{"id": "a", "type": "fake"}, {"id": "b", "type": "fake"}]}, "s", engine.kinds)
    run = engine.start(Store(tmp_path), flow)
    assert asked == [True] and run.status == CANCELLED and run.steps["b"]["status"] == "pending"
    assert not (run.folder / "cancel").exists()


def test_cancel_while_another_process_holds_the_lock_leaves_a_request(tmp_path, holder):
    engine, flow, _, _ = make([{"id": "ok", "type": "approval"}])
    store = Store(tmp_path)
    run = engine.start(store, flow, run_id="r")
    child = holder(run)
    assert engine.cancel(store.get("r")).cancel_requested()
    assert store.get("r").status == WAITING
    child.kill()
    child.wait()
    run = engine.approve(store.get("r"), "よし")   # 持ち主がいなくなった後の印は古いもの：消して進める
    assert run.status == DONE and not run.cancel_requested()


@pytest.fixture
def holder(tmp_path):
    """実行のロックを持って眠る子のプロセス（生きている持ち主）。"""
    children = []

    def hold(run, seconds=60.0, code=None):
        ready = tmp_path / f"ready-{len(children)}"
        source = str(Path(ecoflow.__file__).resolve().parent.parent)
        code = code or ("import sys, time; sys.path.insert(0, sys.argv[1]); from ecoflow.run import Run, lock\n"
                        "with lock(Run.load(sys.argv[2])):\n open(sys.argv[3], 'w').close(); time.sleep(float(sys.argv[4]))")
        # venv の python.exe（Windows）は本物の Python を子として起こすので、本物を直接（止めればロックが外れる）
        python = getattr(sys, "_base_executable", sys.executable)
        child = subprocess.Popen([python, "-c", code, source, str(run.folder), str(ready), str(seconds)])
        children.append(child)
        until = time.monotonic() + 30
        while not ready.exists():
            assert child.poll() is None and time.monotonic() < until
            time.sleep(0.05)
        return child

    yield hold
    for child in children:
        child.kill()
        child.wait()


def test_interrupted_run_resumes_from_the_running_step(tmp_path):
    """工程の途中でプロセスが止まった（Ctrl+C）：工程は running のまま、ロックは外れ、表示は中断。resume で、その工程の
    続き（覚え書き data が残る）から。"""
    seen = []

    def slow(step, ctx):
        if not ctx.resumed:
            ctx.data["agent"] = "a-1"
            ctx.save()
            raise KeyboardInterrupt
        seen.append(ctx.data.get("agent"))
        return Outcome("done", "続きから")

    engine = Engine({"slow": slow, "fake": Script()})
    flow = load({"steps": [{"id": "a", "type": "fake"}, {"id": "b", "type": "slow"}, {"id": "c", "type": "fake"}]},
                "s", engine.kinds)
    store = Store(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        engine.start(store, flow, run_id="r")
    run = store.get("r")
    assert run.status == RUNNING and run.shown_status == INTERRUPTED and run.steps["b"]["status"] == "running"
    assert run.summary()["status"] == "interrupted"
    run = engine.resume(run)
    assert run.status == DONE and seen == ["a-1"] and run.steps["b"]["attempts"] == 1
    assert [e["event"] for e in run.state["history"]].count("resumed") == 1


def test_lock_refuses_a_live_holder_and_is_free_after_it_ends(tmp_path, holder):
    engine, flow, _, _ = make([{"id": "a", "type": "fake"}])
    store = Store(tmp_path)
    run = store.create(flow, run_id="r")
    child = holder(run)                              # 生きているプロセスが持っている
    assert run.locked() and run.shown_status == RUNNING
    with pytest.raises(FlowError) as refused:
        engine.resume(run)
    assert refused.value.code == "flow_run_locked" and refused.value.details == {"pid": child.pid}
    child.kill()                                     # 止まったプロセスのロックは OS が外す：中断とみなして続けられる
    child.wait()
    assert not run.locked() and run.shown_status == INTERRUPTED
    assert engine.resume(run).status == DONE
    with lock(run):
        assert Run.load(run.folder).locked()
        with pytest.raises(FlowError):
            with lock(run):
                pass
    assert not run.locked() and (run.folder / LOCK_FILE).exists()


def test_kind_errors_become_step_failures_and_logs(tmp_path):
    def broken(step, ctx):
        ctx.log("始めた")
        raise RuntimeError("こわれた")

    engine = Engine({"broken": broken, "odd": lambda s, c: "結果でない"})
    flow = load({"steps": [{"id": "a", "type": "broken"}]}, "s", engine.kinds)
    run = engine.start(Store(tmp_path), flow)
    assert run.status == FAILED and run.steps["a"]["message"] == "こわれた"
    log = (run.folder / "a.log").read_text(encoding="utf-8")
    assert "始めた" in log and "RuntimeError" in log
    assert run.summary()["steps"][0]["log"].endswith("a.log")
    flow = load({"steps": [{"id": "a", "type": "odd"}]}, "s", engine.kinds)
    assert "知らない結果" in engine.start(Store(tmp_path), flow).steps["a"]["message"]


def test_store_lists_runs_and_makes_unique_ids(tmp_path):
    engine, flow, _, _ = make([{"id": "a", "type": "fake"}])
    store = Store(tmp_path, clock=lambda: 1_700_000_000.0, display=lambda p: f"rel/{p.name}")
    first, second = store.create(flow), store.create(flow)
    assert first.id != second.id and second.id.startswith(first.id)
    assert [r.id for r in store.runs()] == [first.id, second.id] and store.latest().id == second.id
    assert first.state["dir"] == f"rel/{first.id}" and first.scope("a")["run"]["dir"] == f"rel/{first.id}"
    with pytest.raises(FlowError) as missing:
        store.get("../x")
    assert missing.value.code == "flow_run_not_found"
    for bad in ("../x", "a/b", "", ".hidden", "a..b"):
        with pytest.raises(FlowError):
            store.create(flow, run_id=bad)
    (tmp_path / f"{first.id}-3").mkdir()                    # 同じ秒にほかが先に作った名前は飛ばす
    assert store.create(flow).id == f"{first.id}-4"


# ---- 見直しで足したもの -------------------------------------------------------------------------------------
def test_more_definition_errors():
    kinds = {"fake": Kind(run=lambda s, c: Outcome("done")),
             "approval": Kind(run=lambda s, c: Outcome("waiting"), forbid=("pass_if", "retries", "on_fail"))}
    _, problems = check({"inputs": {"goal": "目的"}, "steps": [
        {"id": "a", "type": "fake", "say": "${inputs.goal} ${inputs.other}"},   # 定義にない入力
        {"id": "b", "type": "fake", "say": "${run.id} ${run.secret} ${run}"},     # run の名前
        {"id": "c", "type": "fake", "say": "閉じない ${out.x"},                   # 閉じていない ${
        {"id": "d", "type": "fake", "when": "'${out.x}' == 1"},                   # 引用符の中の ${…}
        {"id": "e", "type": "approval", "pass_if": "x", "retries": 1, "on_fail": {"to": "e", "max": 1}},
    ]}, "bad", kinds)
    text = "\n".join(problems)
    for expected in ("入力 other は定義にありません", "${run.secret}", "${run}", "閉じていない ${", "引用符の中の",
                     "工程 e（approval）には pass_if, retries, on_fail を書けません"):
        assert expected in text, expected
    assert "入力 goal" not in text and "${run.id}" not in text


def test_skipped_and_restarted_steps_do_not_keep_old_values(tmp_path):
    """飛ばした工程・始め直した工程の前の回の out・message は、今の値として読まれない（前の回は prev_out・prev_message）。"""
    engine, flow, script, _ = make([
        {"id": "a", "type": "fake"},
        {"id": "b", "type": "fake", "when": "${steps.a.out.go}"},
        {"id": "c", "type": "fake", "say": "[${steps.b.message}|${steps.b.out.x}|${steps.b.prev_message}]",
         "loop": {"to": "a", "max": 1}},
    ], a=[("done", "", {"go": True}), ("done", "", {"go": False})], b=[("done", "前の b", {"x": 1})])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == DONE and statuses(run)["b"] == "skipped"
    assert [c for c in script.calls if c[0] == "c"] == [("c", "[前の b|1|]"), ("c", "[||前の b]")]
    assert run.steps["b"]["out"] == {} and run.steps["b"]["prev_out"] == {"x": 1}


def test_inner_counts_restart_on_each_outer_round(tmp_path):
    """外側の工程が前へ戻ると、間の工程の戻りの回数は 0 から（周回ごとの上限）。外側の max が全体を抑える。"""
    engine, flow, script, _ = make([
        {"id": "impl", "type": "fake"},
        {"id": "verify", "type": "fake", "on_fail": {"to": "impl", "max": 1}},
        {"id": "review", "type": "fake", "on_fail": {"to": "impl", "max": 2}},
    ], verify=[("failed", "v1"), ("done", ""), ("failed", "v2"), ("done", ""), ("failed", "v3"), ("done", "")],
       review=[("failed", "r")] * 3)
    run = engine.start(Store(tmp_path), flow)
    assert run.status == FAILED and run.state["current"] == "review"
    assert run.steps["review"]["backs"] == 2 and run.steps["verify"]["backs"] == 1
    assert [c[0] for c in script.calls].count("verify") == 6


def test_reject_to_itself_and_retry_after_on_fail_is_used_up(tmp_path):
    engine, flow, script, _ = make([
        {"id": "impl", "type": "fake", "say": "${vars.feedback}"},
        {"id": "verify", "type": "fake", "on_fail": {"to": "impl", "max": 1}},
        {"id": "ok", "type": "approval", "message": "見て"},
    ], verify=[("failed", "1"), ("failed", "2"), ("done", "")])
    store = Store(tmp_path)
    run = engine.start(store, flow, run_id="r")
    assert run.status == FAILED and run.steps["verify"]["backs"] == 1
    run = engine.retry(store.get("r"))                       # 使い切った後の retry は、その工程だけをもう一度
    assert run.status == WAITING and [c[0] for c in script.calls] == ["impl", "verify", "impl", "verify", "verify"]
    run = engine.reject(store.get("r"), "ok", "もう一度見せて")   # 待っている工程そのものへ
    assert run.status == WAITING and run.steps["ok"]["attempts"] == 2 and run.vars["feedback"] == "もう一度見せて"


def test_retries_and_loop_together(tmp_path):
    engine, flow, script, _ = make([
        {"id": "a", "type": "fake", "retries": 1, "loop": {"to": "a", "max": 1}},
    ], a=[("failed", "1"), ("done", ""), ("failed", "2"), ("done", "")])
    run = engine.start(Store(tmp_path), flow)
    assert run.status == DONE and run.steps["a"]["attempts"] == 4 and run.steps["a"]["loops"] == 1


def test_cancel_failed_and_interrupted_runs_cleans_up_the_kind(tmp_path):
    cleaned = []

    def slow(step, ctx):
        ctx.data["agent"] = "a-1"
        ctx.save()
        raise KeyboardInterrupt

    engine = Engine({"slow": Kind(run=slow, cancel=lambda step, ctx: cleaned.append(ctx.data["agent"])),
                     "fake": Script(b=[("failed", "x")])})
    store = Store(tmp_path)
    flow = load({"steps": [{"id": "a", "type": "slow"}]}, "s", engine.kinds)
    with pytest.raises(KeyboardInterrupt):
        engine.start(store, flow, run_id="r")
    run = engine.cancel(store.get("r"))
    assert run.status == CANCELLED and run.steps["a"]["status"] == "cancelled" and cleaned == ["a-1"]
    flow = load({"steps": [{"id": "b", "type": "fake"}]}, "s", engine.kinds)
    run = engine.cancel(engine.start(store, flow, run_id="f"))
    assert run.status == CANCELLED and run.steps["b"]["status"] == "cancelled" and cleaned == ["a-1"]


def test_status_checks_do_not_block_operations(tmp_path, holder):
    """ほかのプロセスが様子（locked）を見続けていても、操作のロックは取れる（見る側は held だけを試す）。"""
    engine, flow, _, _ = make([{"id": "a", "type": "fake"}])
    store = Store(tmp_path / "runs")
    run = store.create(flow, run_id="r")
    watcher = ("import sys, time, pathlib; sys.path.insert(0, sys.argv[1]); from ecoflow.run import Run\n"
               "run = Run.load(sys.argv[2]); open(sys.argv[3], 'w').close()\n"
               "while not pathlib.Path(sys.argv[3] + '.stop').exists(): run.locked()")
    child = holder(run, code=watcher)
    stop = Path(str(tmp_path / "ready-0") + ".stop")
    try:
        for _ in range(100):
            with lock(run):
                pass
    finally:
        stop.write_text("x")
        child.wait(timeout=30)


def test_cancel_retakes_the_lock_when_the_holder_stops_right_away(tmp_path, holder):
    """印を置く間に持ち主が止まったら、その場で取り消す（印が持ち主に消されて残らない）。"""
    engine, flow, _, _ = make([{"id": "ok", "type": "approval"}])
    store = Store(tmp_path / "runs")
    run = engine.start(store, flow, run_id="r")
    holder(run, seconds=0.75)
    run = engine.cancel(store.get("r"))
    assert run.status == CANCELLED and not run.cancel_requested()


def test_definition_and_step_records_must_match(tmp_path):
    engine, flow, _, _ = make([{"id": "a", "type": "fake"}, {"id": "ok", "type": "approval"}])
    store = Store(tmp_path)
    run = engine.start(store, flow, run_id="r")
    del run.state["steps"]["a"]
    run.save()
    with pytest.raises(FlowError) as raised:
        engine.approve(store.get("r"))
    assert raised.value.code == "flow_run_broken" and "工程 a の記録がありません" in raised.value.message


def test_cancel_during_the_last_step_ends_as_done(tmp_path):
    def last(step, ctx):
        (ctx.folder / "cancel").write_text("x")
        return Outcome("done")

    engine = Engine({"fake": last})
    run = engine.start(Store(tmp_path), load({"steps": [{"id": "a", "type": "fake"}]}, "s", engine.kinds))
    assert run.status == DONE and not run.cancel_requested()


def test_cancel_during_a_step_keeps_a_finished_step_as_done(tmp_path):
    def first(step, ctx):
        (ctx.folder / "cancel").write_text("x")
        return Outcome("done", "終わった", out={"n": 1})

    engine = Engine({"fake": first})
    flow = load({"steps": [{"id": "a", "type": "fake"}, {"id": "b", "type": "fake"}]}, "s", engine.kinds)
    run = engine.start(Store(tmp_path), flow)
    assert run.status == CANCELLED and run.steps["a"]["status"] == "done" and run.steps["a"]["out"] == {"n": 1}
    assert run.state["current"] == "b"


def test_cancel_mark_is_dropped_when_the_run_stops(tmp_path):
    engine, flow, _, _ = make([{"id": "ok", "type": "approval"}, {"id": "b", "type": "fake"}])
    store = Store(tmp_path)
    run = engine.start(store, flow, run_id="r")
    (run.folder / "cancel").write_text("古い印")              # 前の取り消しの残り
    assert engine.approve(store.get("r")).status == DONE


def test_broken_state_is_reported(tmp_path):
    engine, flow, _, _ = make([{"id": "a", "type": "approval"}])
    store = Store(tmp_path)
    run = engine.start(store, flow, run_id="r")
    state = json.loads((run.folder / "state.json").read_text(encoding="utf-8"))
    for broken in ({**state, "steps": "x"}, {**state, "current": "zzz"}, {**state, "status": "odd"},
                   {k: v for k, v in state.items() if k != "vars"}, [1, 2]):
        (run.folder / "state.json").write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(FlowError) as raised:
            store.get("r")
        assert raised.value.code == "flow_run_broken"
    (run.folder / "state.json").write_text("{", encoding="utf-8")
    with pytest.raises(FlowError) as raised:
        store.get("r")
    assert raised.value.code == "flow_run_broken" and store.runs() == []


def test_a_missing_kind_is_a_definition_error_not_a_broken_record(tmp_path):
    engine, flow, _, _ = make([{"id": "ok", "type": "approval"}])
    store = Store(tmp_path)
    engine.start(store, flow, run_id="r")
    fewer = Engine({"fake": Script()})                          # 種類が登録されていない（拡張がない ECOBuild 等）
    with pytest.raises(FlowError) as raised:
        fewer.approve(store.get("r"))
    assert raised.value.code == "invalid_flow" and "type「approval」はありません" in raised.value.message
    run = store.get("r")
    run.state["definition"] = {"steps": "壊れた"}
    run.save()
    with pytest.raises(FlowError) as broken:
        engine.approve(store.get("r"))
    assert broken.value.code == "flow_run_broken"
