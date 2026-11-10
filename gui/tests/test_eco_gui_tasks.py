"""eco_gui のタスクの詳細・ボード・日程：画面が、人が打つのと同じ ecobuild のコマンドを呼ぶこと。

ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402

TASKS = [
    {"number": 12, "title": "ログイン画面", "state": "open", "stage": "in_progress", "assignees": ["octocat"], "priority": "High",
     "due": "2026-11-20", "estimate": 3, "sprint": "Sprint 2", "planned_start": "2026-11-09", "planned_end": "2026-11-13"},
    {"number": 13, "title": "ログを残す", "state": "open", "stage": "todo", "assignees": [], "priority": None,
     "due": None, "estimate": None, "sprint": None, "planned_start": None, "planned_end": None},
]


class FakeTasks(FakeEcobuild):
    """タスクのコマンドを足した、ecobuild の代わり。"""

    def _specs(self, text):
        number = {"type": "integer"}
        flag = {"type": "boolean"}

        def spec(weight, properties, required=()):
            return {"description": "タスク", "weight": weight, "args": {"type": "object", "required": list(required), "properties": properties}}

        return {
            **super()._specs(text),
            "task status": spec("read", {"number": number, "issue": number, "body": flag}),
            "task edit": spec("change", {"issue": number, **{name: text for name in (
                "title", "body", "stage", "priority", "due", "estimate", "sprint", "add_assignee", "remove_assignee", "clear")}}, ["issue"]),
            "task comment": spec("change", {"number": number, "issue": number, "message": text}),
            "task reopen": spec("change", {"issue": number}, ["issue"]),
            "task next": spec("read", {"count": number, "mine": flag}),
            "task overdue": spec("read", {"days": number}),
            "task workload": spec("read", {}),
            "sprint list": spec("read", {}),
            "sprint status": spec("read", {"name": text, "sprint": text}),
            "milestone status": spec("read", {}),
        }

    def run(self, name, args, context, on_event):
        given = {key: value for key, value in args.items() if key != "module"}
        if name == "task list":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": [dict(task) for task in TASKS]}
        if name == "task status":
            super().run(name, args, context, on_event)
            task = next(task for task in TASKS if task["number"] == given["number"])
            return {"ok": True, "result": {
                "number": task["number"], "title": task["title"], "state": "open", "body": "本文です。\n- 1つ目", "assignees": task["assignees"],
                "labels": ["bug"], "milestone": None, "branch": None, "base": None, "task": dict(task),
                "comments": [{"author": "octocat", "body": "見ました"}]}}
        if name == "task next":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": [{"task": dict(TASKS[1]), "reasons": ["着手できる"]}]}
        if name == "task overdue":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"overdue": [dict(TASKS[0])], "soon": [], "days": given.get("days")}}
        if name == "task workload":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": [{"assignee": "octocat", "open": 1, "in_progress": 1, "estimate_remaining": 3, "overdue": 0, "tasks": [12]}]}
        if name == "sprint list":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": [{"name": "Sprint 1", "start": "2026-10-19", "end": "2026-11-02"},
                                           {"name": "Sprint 2", "start": "2026-11-02", "end": "2026-11-16"}]}
        if name == "sprint status":
            super().run(name, args, context, on_event)
            chosen = given.get("name") or "Sprint 2"
            return {"ok": True, "result": {"sprint": {"name": chosen, "start": "2026-11-02", "end": "2026-11-16"}, "current": True,
                                           "days_left": 6, "total": 1, "done": 0, "estimate_total": 3, "estimate_done": 0,
                                           "estimate_remaining": 3, "unestimated": [], "tasks": [dict(TASKS[0])], "carried_over": []}}
        if name == "milestone status":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": [{"title": "v1", "due": "2026-12-01", "total": 2, "done": 1, "estimate_remaining": 3,
                                           "overdue_tasks": [], "late": False, "open_tasks": [12]}]}
        return super().run(name, args, context, on_event)


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeTasks(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def notices(relay):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify"]


def open_screen(relay, screen, **args):
    window = relay.execute({"command": "open", "screen": screen, "args": {"module": "C:/work/Calc", **args}})["window"]
    relay.idle()
    return window


def test_bindings_match_the_backend_commands(relay):
    relay.verify()


def test_task_detail_shows_one_status_read_in_every_part(relay):
    window = open_screen(relay, "task", issue=12)
    view = nodes(relay, window)
    assert view["title"]["props"]["text"] == "ログイン画面" and view["nav"]["props"]["current"] == "tasks"
    assert view["state"]["props"]["data"]["labels"] == ["bug"]
    assert view["plan"]["props"]["data"]["stage"] == "in_progress" and view["plan"]["props"]["data"]["due"] == "2026-11-20"
    assert view["body"]["props"]["text"].startswith("本文です。")
    assert view["comments"]["props"]["rows"] == [{"author": "octocat", "body": "見ました"}]
    assert view["edit_text"]["props"]["text"] == "ログイン画面"  # 題の欄には、今の題が入っている
    assert relay.backend.calls.count(("task status", {"number": 12, "body": True})) == 1  # 6つの部品へ出しても、読むのは1回
    assert relay.backend.modules[-1] == "C:/work/Calc"
    assert notices(relay) == []


def test_task_detail_edits_only_the_changed_fields(relay):
    window = open_screen(relay, "task", issue=12)
    relay.input(window, "edit_priority", "changed", {"value": "Low"}, human=True)
    relay.input(window, "edit_due", "changed", {"text": "2026-12-01"}, human=True)
    relay.idle()
    relay.input(window, "save", "pressed", {}, human=True)
    relay.idle()
    assert ("task edit", {"issue": 12, "priority": "Low", "due": "2026-12-01"}) in relay.backend.calls  # 入れていない欄は渡さない
    assert relay.display.values(window)["edit_priority"] is None and relay.display.values(window)["edit_due"] is None
    assert nodes(relay, window)["edit_priority"]["props"]["value"] is None  # 保存したら、選ぶ欄は「変えない」に戻る

    for node, payload in (("edit_text", {"text": "ログインの画面"}), ("edit_stage", {"value": "planned"}), ("edit_estimate", {"text": "5"}),
                          ("edit_add_assignee", {"text": "@me"}), ("edit_remove_assignee", {"text": "octocat"}),
                          ("edit_clear", {"value": "due"})):
        relay.input(window, node, "changed", payload, human=True)
    relay.idle()
    relay.input(window, "save", "pressed", {}, human=True)
    relay.idle()
    assert ("task edit", {"issue": 12, "title": "ログインの画面", "stage": "planned", "estimate": "5", "add_assignee": "@me",
                          "remove_assignee": "octocat", "clear": "due"}) in relay.backend.calls
    assert notices(relay) == []


def test_task_detail_comments_starts_closes_and_reopens(relay):
    window = open_screen(relay, "task", issue=12)
    assert nodes(relay, window)["do_comment"]["wrap"] is None  # 文（任意の引数）は、押してから ecobuild が確かめる
    relay.input(window, "message", "changed", {"text": "あとは試験だけ"}, human=True)
    relay.idle()
    relay.input(window, "do_comment", "pressed", {}, human=True)
    relay.idle()
    assert ("task comment", {"number": 12, "message": "あとは試験だけ"}) in relay.backend.calls
    assert relay.display.values(window)["message"] is None

    relay.input(window, "start_name", "changed", {"text": "login"}, human=True)
    relay.idle()
    relay.input(window, "start", "pressed", {}, human=True)
    relay.idle()
    assert ("task start", {"issue": 12, "name": "login"}) in relay.backend.calls
    relay.input(window, "close", "pressed", {}, human=True)
    assert answer(relay, window, True)["part"] == "confirm-box"  # 閉じるのは、確かめてから
    assert ("task close", {"issue": 12}) in relay.backend.calls
    relay.input(window, "reopen", "pressed", {}, human=True)
    relay.idle()
    assert ("task reopen", {"issue": 12}) in relay.backend.calls
    assert relay.backend.calls.count(("task status", {"number": 12, "body": True})) >= 4  # 変えるたびに読み直す


def test_tasks_row_opens_the_detail_in_the_same_window(relay):
    window = open_screen(relay, "tasks")
    relay.input(window, "tasks", "action", {"id": "13", "action": "open"}, human=True)  # 表は ID を文字で出す
    relay.idle()
    tree = relay.display.tree(window)
    assert tree["screen"] == "task" and tree["args"]["module"] == "C:/work/Calc" and int(tree["args"]["issue"]) == 13
    assert nodes(relay, window)["title"]["props"]["text"] == "ログを残す"
    assert ("task status", {"number": 13, "body": True}) in relay.backend.calls  # コマンドの型（数）で渡る
    assert [w["id"] for w in relay.display.windows()] == [window]  # 窓は増えない
    assert not [call for call in relay.backend.calls if call[0] in ("task start", "task close")]  # 押したボタンのつなぎだけ


def test_values_typed_for_one_task_do_not_leak_into_the_next(relay):
    window = open_screen(relay, "task", issue=12)
    relay.input(window, "edit_text", "changed", {"text": "12 の新しい題"}, human=True)
    relay.input(window, "nav", "selected", {"id": "tasks"}, human=True)
    relay.idle()
    relay.input(window, "tasks", "action", {"id": "13", "action": "open"}, human=True)
    relay.idle()
    relay.input(window, "edit_due", "changed", {"text": "2026-12-01"}, human=True)
    relay.idle()
    relay.input(window, "save", "pressed", {}, human=True)
    relay.idle()
    assert ("task edit", {"issue": 13, "due": "2026-12-01"}) in relay.backend.calls  # 前のタスクで打った題は付いてこない


def test_board_groups_tasks_by_stage_and_changes_the_stage(relay):
    window = open_screen(relay, "board")
    view = nodes(relay, window)
    assert [card["number"] for card in view["board"]["props"]["cards"]] == [12, 13]
    assert view["board"]["props"]["moves"] == ["planned", "todo"] and view["board"]["wrap"] is None
    relay.input(window, "board", "moved", {"id": "13", "to": "planned"}, human=True)
    relay.idle()
    assert ("task edit", {"issue": 13, "stage": "planned"}) in relay.backend.calls
    assert relay.backend.calls.count(("task list", {})) == 2  # 変えたら読み直す
    relay.input(window, "board", "selected", {"id": "12"}, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == "task" and ("task status", {"number": 12, "body": True}) in relay.backend.calls
    with pytest.raises(Exception):
        relay.input(window, "board", "moved", {"id": "12", "to": ""}, human=True)  # 移す先のない入力は断る


def test_schedule_reads_each_command_once_and_opens_tasks(relay):
    window = open_screen(relay, "schedule")
    view = nodes(relay, window)
    assert [row["number"] for row in view["timeline"]["props"]["rows"]] == [12, 13]
    assert view["next"]["props"]["items"][0]["reasons"] == ["着手できる"]
    assert [row["number"] for row in view["overdue"]["props"]["rows"]] == [12] and view["soon"]["props"]["rows"] == []
    assert [row["name"] for row in view["sprints"]["props"]["rows"]] == ["Sprint 1", "Sprint 2"]
    assert view["sprint_range"]["props"]["data"]["name"] == "Sprint 2" and view["sprint_state"]["props"]["data"]["days_left"] == 6
    assert view["sprint_tasks"]["props"]["rows"][0]["number"] == 12
    assert view["milestones"]["props"]["rows"][0]["title"] == "v1" and view["workload"]["props"]["rows"][0]["assignee"] == "octocat"
    for call in [("task list", {}), ("task next", {"count": 10}), ("task overdue", {"days": 7}), ("sprint list", {}),
                 ("sprint status", {}), ("milestone status", {}), ("task workload", {})]:  # 選ぶまでは、今のスプリント
        assert relay.backend.calls.count(call) == 1
    assert notices(relay) == []

    relay.input(window, "sprints", "action", {"id": "Sprint 1", "action": "show"}, human=True)
    relay.idle()
    assert ("sprint status", {"name": "Sprint 1"}) in relay.backend.calls
    assert nodes(relay, window)["sprint_range"]["props"]["data"]["name"] == "Sprint 1"
    assert relay.backend.calls.count(("task list", {})) == 1  # スプリントを選んでも、ほかは読み直さない

    relay.input(window, "next", "selected", {"id": "13"}, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == "task" and nodes(relay, window)["title"]["props"]["text"] == "ログを残す"


@pytest.mark.parametrize("source", ["timeline", "overdue", "sprint_tasks"])
def test_schedule_rows_open_the_task_detail(relay, source):
    window = open_screen(relay, "schedule")
    output, payload = ("selected", {"id": "12"}) if source == "timeline" else ("action", {"id": "12", "action": "open"})
    relay.input(window, source, output, payload, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == "task" and ("task status", {"number": 12, "body": True}) in relay.backend.calls
