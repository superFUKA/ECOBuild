"""eco_gui のタスク管理（一覧・ボード・日程・次にやる・スプリント・概要・詳細・入力の窓）：
画面が、人が打つのと同じ ecobuild のコマンドを呼ぶこと。

ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402

TASKS = [
    {"number": 12, "title": "ログイン画面", "state": "open", "stage": "in_progress", "assignees": ["octocat"], "priority": "High",
     "due": "2026-11-20", "estimate": 3, "sprint": "Sprint 2", "planned_start": "2026-11-09", "planned_end": "2026-11-13",
     "task_branch": True, "remote": True, "workspace": "C:/work/Calc/.ecobuild/w/12"},
    {"number": 13, "title": "ログを残す", "state": "open", "stage": "todo", "assignees": [], "priority": None,
     "due": None, "estimate": None, "sprint": None, "planned_start": None, "planned_end": None, "task_branch": False, "remote": False},
]
CLOSED = {"number": 9, "title": "終わったタスク", "state": "closed", "closed_reason": "completed", "stage": "done", "assignees": ["octocat"],
          "finished": "2026-11-05"}
SPRINTS = [{"name": "Sprint 1", "start": "2026-10-19", "end": "2026-11-02"}, {"name": "Sprint 2", "start": "2026-11-02", "end": "2026-11-16"}]


class FakeTasks(FakeEcobuild):
    """タスクのコマンドを足した、ecobuild の代わり。"""

    def __init__(self):
        super().__init__()
        # 12：手元で作業中。13：まだ始めていない。14：タスクブランチが GitHub にだけある。15：閉じている
        self.states = {12: {"state": "open", "task_branch": True, "remote": True}, 13: {"state": "open", "task_branch": False, "remote": False},
                       14: {"state": "open", "task_branch": False, "remote": True}, 15: {"state": "closed", "task_branch": False, "remote": False}}

    def _specs(self, text):
        number = {"type": "integer"}
        flag = {"type": "boolean"}

        def spec(weight, properties, required=()):
            return {"description": "タスク", "weight": weight, "args": {"type": "object", "required": list(required), "properties": properties}}

        return {
            **super()._specs(text),
            "task list": spec("read", {"all": flag, "ready": flag, "submitted": flag, "to_review": flag}),
            "task status": spec("read", {"number": number, "issue": number, "body": flag}),
            "task new": spec("change", {"parent": number, "start": flag, **{name: text for name in (
                "title", "body", "stage", "assignee", "priority", "estimate", "sprint", "planned_start", "planned_end", "due", "label",
                "milestone", "blocked_by", "name", "base")}}, ["title"]),
            "task start": spec("change", {"issue": number, "no_branch": flag, "ignore_blocked": flag, "take_over": flag,
                                          "name": text, "base": text, "account": text}, ["issue"]),
            "task edit": spec("change", {"issue": number, "parent": number, "clear_parent": flag, "clear_milestone": flag, **{name: text for name in (
                "title", "body", "stage", "priority", "due", "estimate", "sprint", "planned_start", "planned_end", "milestone",
                "add_assignee", "remove_assignee", "add_label", "remove_label", "add_blocked_by", "remove_blocked_by", "clear")}}, ["issue"]),
            "task close": spec("confirm", {"issue": number, "not_planned": flag}, ["issue"]),
            "task comment": spec("change", {"number": number, "issue": number, "message": text}),
            "task reopen": spec("change", {"issue": number}, ["issue"]),
            "task finish": spec("confirm", {"number": number, "subject": text, "ignore_checks": flag, "complete": flag, "partial": flag}),
            "task drop": spec("confirm", {"number": number, "close": flag}),
            "task prune": spec("change", {"number": number}),
            "task withdraw": spec("confirm", {"number": number}),
            "task review": spec("change", {"number": number}),
            "task revert": spec("confirm", {"number": number}),
            "task approve": spec("confirm", {"task": number, "message": text}, ["task"]),
            "task reject": spec("confirm", {"task": number, "message": text}, ["task"]),
            "task next": spec("read", {"count": number, "mine": flag}),
            "task overdue": spec("read", {"days": number}),
            "task workload": spec("read", {}),
            "sprint list": spec("read", {}),
            "sprint status": spec("read", {"name": text, "sprint": text}),
            "milestone list": spec("read", {}),
            "milestone status": spec("read", {}),
            "account list": spec("read", {}),
        }

    def run(self, name, args, context, on_event):
        given = {key: value for key, value in args.items() if key != "module"}
        reads = {
            "task next": [{"task": dict(TASKS[1]), "reasons": ["着手できる"]}],
            "task overdue": {"overdue": [dict(TASKS[0])], "soon": [], "days": given.get("days")},
            "task workload": [{"assignee": "octocat", "open": 1, "in_progress": 1, "estimate_remaining": 3, "overdue": 0, "tasks": [12]}],
            "sprint list": [dict(sprint) for sprint in SPRINTS],
            "milestone list": [{"title": "v1", "due": "2026-12-01"}],
            "milestone status": [{"title": "v1", "due": "2026-12-01", "total": 2, "done": 1, "estimate_remaining": 3,
                                  "overdue_tasks": [], "late": False, "open_tasks": [12]}],
            "account list": [{"login": "superFUKA", "active": True}],
        }
        if name == "task list":
            super().run(name, args, context, on_event)
            if given.get("to_review") or given.get("submitted"):
                return {"ok": True, "result": [dict(TASKS[0], submission={"draft": False})]}
            return {"ok": True, "result": [dict(task) for task in TASKS] + ([dict(CLOSED)] if given.get("all") else [])}
        if name == "task status":
            super().run(name, args, context, on_event)
            task = next((task for task in TASKS if task["number"] == given["number"]), {**TASKS[1], "number": given["number"]})
            return {"ok": True, "result": {
                "number": task["number"], "title": task["title"], "body": "本文です。\n- 1つ目", "assignees": task["assignees"],
                "labels": ["bug"], "milestone": None, "branch": None, "base": "main", "task": dict(task), "pull_request": None,
                "subtasks": [], "blocked_by": [], "blocking": [], "parent": None,
                "comments": [{"author": "octocat", "body": "見ました"}], **self.states[task["number"]]}}
        if name == "sprint status":
            super().run(name, args, context, on_event)
            chosen = given.get("name") or "Sprint 2"
            return {"ok": True, "result": {"sprint": {"name": chosen, "start": "2026-11-02", "end": "2026-11-16"}, "current": True,
                                           "days_left": 6, "total": 1, "done": 0, "estimate_total": 3, "estimate_done": 0, "stages": {"in_progress": 1},
                                           "estimate_remaining": 3, "unestimated": [], "tasks": [dict(TASKS[0])], "carried_over": []}}
        if name in reads:
            super().run(name, args, context, on_event)
            return {"ok": True, "result": reads[name]}
        if name in ("task close", "task reopen", "task start"):  # 状態が変わる（読み直しで、出るボタンが変わる）
            self.states[given["issue"]].update({"task close": {"state": "closed"}, "task reopen": {"state": "open"},
                                                "task start": {"task_branch": True, "remote": True}}[name])
        return super().run(name, args, context, on_event)


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeTasks(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def notices(relay, level=None):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify" and (level is None or event.get("level") == level)]


def open_screen(relay, screen, **args):
    window = relay.execute({"command": "open", "screen": screen, "args": {"module": "C:/work/Calc", **args}})["window"]
    relay.idle()
    return window


def inside(relay, window):
    """窓の中に重ねて開いている窓（入力の窓）。"""
    found = [w for w in relay.display.windows() if w.get("parent") == window]
    assert len(found) == 1, found
    return found[0]


def calls(relay, name):
    return [args for called, args in relay.backend.calls if called == name]


def hidden(relay, window, node):
    return (nodes(relay, window)[node]["wrap"] or {}).get("kind") == "hidden"


def test_bindings_match_the_backend_commands(relay):
    relay.verify()


# --- 一覧 ---------------------------------------------------------------------------------------------
def test_tasks_shows_the_list_the_bar_and_no_detail_until_a_task_is_selected(relay):
    window = open_screen(relay, "tasks")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "tasks" and view["bar"]["props"]["view"] == "tasks"
    assert [task["number"] for task in view["list"]["props"]["tasks"]] == [12, 13] and view["list"]["props"]["foot"] is True
    assert view["list"]["props"]["me"] == "superFUKA" and [s["name"] for s in view["list"]["props"]["sprints"]] == ["Sprint 1", "Sprint 2"]
    assert [task["number"] for task in view["bar"]["props"]["tasks"]] == [12, 13] and view["bar"]["props"]["milestones"][0]["title"] == "v1"
    assert hidden(relay, window, "pane") and calls(relay, "task status") == []  # 選ぶまで、詳細は出ない・読まない
    assert len(calls(relay, "task list")) == 1  # 一覧と上の帯へ出しても、読むのは1回
    assert relay.backend.modules[-1] == "C:/work/Calc" and notices(relay) == []

    relay.input(window, "list", "selected", {"id": "13"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert not hidden(relay, window, "pane") and view["pane"]["props"]["status"]["title"] == "ログを残す"
    assert view["list"]["props"]["selected"] == "13" and view["pane"]["props"]["number"] == "13"
    assert calls(relay, "task status") == [{"number": 13, "body": True}]  # コマンドの型（数）で渡る
    assert view["pane"]["props"]["account"]["login"] == "superFUKA"
    assert len(calls(relay, "task list")) == 1  # 選んでも、一覧は読み直さない

    relay.input(window, "pane", "closed", {}, human=True)
    relay.idle()
    assert hidden(relay, window, "pane") and nodes(relay, window)["list"]["props"]["selected"] is None


def test_the_menu_of_a_row_changes_only_what_was_chosen(relay):
    window = open_screen(relay, "tasks")
    for payload, expected in (({"id": "13", "priority": "High"}, {"issue": 13, "priority": "High"}),
                              ({"id": "13", "clear": "sprint"}, {"issue": 13, "clear": "sprint"}),
                              ({"id": "12", "add_assignee": "@me"}, {"issue": 12, "add_assignee": "@me"}),
                              ({"id": "13", "stage": "planned"}, {"issue": 13, "stage": "planned"})):
        relay.input(window, "list", "edit", payload, human=True)
        relay.idle()
        assert calls(relay, "task edit")[-1] == expected  # 選んでいない値は渡さない
    assert notices(relay, "error") == [] and "保存しました。" in notices(relay)
    assert len(calls(relay, "task list")) == 5  # 変えるたびに読み直す

    relay.input(window, "list", "close", {"id": "13"}, human=True)  # タスクブランチのないタスクの「完了にする」
    assert answer(relay, window, True)["part"] == "confirm-box"  # 確かめるのは本体（画面では聞かない）
    assert calls(relay, "task close") == [{"issue": 13}]
    relay.input(window, "list", "reopen", {"id": "13"}, human=True)
    relay.idle()
    assert calls(relay, "task reopen") == [{"issue": 13}]
    relay.input(window, "list", "remove", {"id": "13"}, human=True)  # 削除＝「対応しない」で閉じる
    answer(relay, window, True)
    assert calls(relay, "task close")[-1] == {"issue": 13, "not_planned": True}
    relay.input(window, "list", "workspace", {"path": "C:/work/Calc/.ecobuild/w/12"}, human=True)  # タスクブランチを開く
    relay.idle()
    opened = [w for w in relay.display.windows() if w["screen"] == "workspace"]
    assert len(opened) == 1 and opened[0]["args"]["module"] == "C:/work/Calc/.ecobuild/w/12"


def test_the_filter_is_kept_in_the_window_and_carried_to_the_next_view(relay):
    window = open_screen(relay, "tasks")
    chosen = {"search": "ログ", "assignee": "@me", "sprint": "", "milestone": "", "ready": False, "closed": False, "deleted": False, "all": False}
    relay.input(window, "bar", "changed", chosen, human=True)  # 検索・担当者などは見せ方：読み直さない
    relay.idle()
    assert nodes(relay, window)["list"]["props"]["filter"] == chosen and len(calls(relay, "task list")) == 1

    closed = {**chosen, "closed": True, "all": True}
    relay.input(window, "bar", "reload", closed, human=True)  # 「完了したタスクも表示」：閉じたタスクも読む
    relay.idle()
    tree = relay.display.tree(window)
    assert tree["screen"] == "tasks" and tree["args"]["closed"] is True and tree["args"]["search"] == "ログ"
    assert calls(relay, "task list")[-1] == {"all": True, "ready": False}
    view = nodes(relay, window)
    assert [task["number"] for task in view["list"]["props"]["tasks"]] == [12, 13, 9]
    assert view["list"]["props"]["start"]["closed"] is True and view["bar"]["props"]["start"]["assignee"] == "@me"

    relay.input(window, "bar", "view", {"id": "board", **closed}, human=True)  # 表示を切り替えても、絞り込みは付いて行く
    relay.idle()
    tree = relay.display.tree(window)
    assert tree["screen"] == "board" and tree["args"]["assignee"] == "@me" and tree["args"]["all"] is True
    assert nodes(relay, window)["board"]["props"]["start"]["search"] == "ログ" and nodes(relay, window)["nav"]["props"]["current"] == "board"
    assert [w["id"] for w in relay.display.windows()] == [window]  # 窓は増えない
    assert notices(relay) == []


@pytest.mark.parametrize("screen", ["tasks", "board", "schedule", "task-next", "task-sprint", "task-summary"])
def test_every_view_has_the_tabs_and_switches_in_the_same_window(relay, screen):
    window = open_screen(relay, screen)
    assert nodes(relay, window)["bar"]["props"]["view"] == screen
    other = "tasks" if screen != "tasks" else "task-summary"
    relay.input(window, "bar", "view", {"id": other}, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == other and notices(relay) == []


# --- 入力の窓 -------------------------------------------------------------------------------------------
def test_new_task_dialog_creates_with_every_field_and_closes(relay):
    window = open_screen(relay, "tasks")
    relay.input(window, "new", "pressed", {}, human=True)
    relay.idle()
    dialog = inside(relay, window)
    assert dialog["screen"] == "task-new"
    form = nodes(relay, dialog["id"])["form"]["props"]
    assert form["kind"] == "new" and [task["number"] for task in form["tasks"]] == [12, 13] and form["account"]["login"] == "superFUKA"
    assert form["sprints"][1]["name"] == "Sprint 2" and form["milestones"][0]["title"] == "v1"
    relay.input(dialog["id"], "form", "new", {
        "title": "検索", "body": "背景", "stage": "planned", "assignee": "octocat,hubot", "priority": "High", "estimate": "2", "sprint": "Sprint 2",
        "planned_start": "2026-11-16", "planned_end": "2026-11-20", "due": "2026-11-30", "label": "bug", "milestone": "v1", "parent": "12",
        "blocked_by": "13"}, human=True)
    relay.idle()
    assert calls(relay, "task new") == [{
        "title": "検索", "body": "背景", "stage": "planned", "assignee": "octocat,hubot", "priority": "High", "estimate": "2", "sprint": "Sprint 2",
        "planned_start": "2026-11-16", "planned_end": "2026-11-20", "due": "2026-11-30", "label": "bug", "milestone": "v1", "parent": 12,
        "blocked_by": "13"}]
    assert [w["id"] for w in relay.display.windows()] == [window] and "タスクを作成しました。" in notices(relay)  # うまくいったら閉じる
    assert len(calls(relay, "task list")) >= 2  # 外の一覧も読み直す

    relay.input(window, "new", "pressed", {}, human=True)
    relay.idle()
    dialog = inside(relay, window)
    relay.input(dialog["id"], "form", "new", {"title": "すぐ始める", "start": True, "name": "すぐ始める"}, human=True)
    relay.idle()
    assert calls(relay, "task new")[-1] == {"title": "すぐ始める", "start": True, "name": "すぐ始める"}  # 入れていない欄は渡さない
    with pytest.raises(Exception):
        relay.input(window, "list", "dialog", {"screen": "settings"}, human=True)  # タスクの入力の窓だけを開ける


def test_start_dialog_reads_the_choices_and_starts(relay):
    window = open_screen(relay, "tasks")
    relay.input(window, "list", "dialog", {"screen": "task-start", "id": "13", "text": ""}, human=True)
    relay.idle()
    dialog = inside(relay, window)
    form = nodes(relay, dialog["id"])["form"]["props"]
    assert (dialog["screen"], form["kind"], form["issue"]) == ("task-start", "start", 13)
    assert form["status"]["title"] == "ログを残す" and form["branches"][0]["name"] == "dev" and form["accounts"][0]["login"] == "superFUKA"
    relay.input(dialog["id"], "form", "cancel", {}, human=True)  # キャンセル：何もせずに閉じる
    relay.idle()
    assert [w["id"] for w in relay.display.windows()] == [window] and calls(relay, "task start") == []

    relay.input(window, "list", "dialog", {"screen": "task-start", "id": "13", "text": ""}, human=True)
    relay.idle()
    dialog = inside(relay, window)
    relay.input(dialog["id"], "form", "start", {"id": "13", "name": "log", "base": "dev", "ignore_blocked": True}, human=True)
    relay.idle()
    assert calls(relay, "task start") == [{"issue": 13, "name": "log", "base": "dev", "ignore_blocked": True}]
    assert [w["id"] for w in relay.display.windows()] == [window] and "作業を開始しました。" in notices(relay)
    relay.input(window, "list", "dialog", {"screen": "task-start", "id": "14", "text": ""}, human=True)
    relay.idle()
    relay.input(inside(relay, window)["id"], "form", "start", {"id": "14", "no_branch": True}, human=True)  # タスクブランチを作らない
    relay.idle()
    assert calls(relay, "task start")[-1] == {"issue": 14, "no_branch": True}


@pytest.mark.parametrize("screen, output, payload, command, expected, confirm", [
    ("task-edit", "edit", {"id": "12", "title": "新しい題", "clear_parent": True, "add_blocked_by": "7,8"},
     "task edit", {"issue": 12, "title": "新しい題", "clear_parent": True, "add_blocked_by": "7,8"}, False),
    ("task-edit", "edit", {"id": "12", "parent": "10", "body": "本文\n2行目"}, "task edit", {"issue": 12, "parent": 10, "body": "本文\n2行目"}, False),
    ("task-assign", "edit", {"id": "12", "add_assignee": "hubot,mona"}, "task edit", {"issue": 12, "add_assignee": "hubot,mona"}, False),
    ("task-label", "edit", {"id": "12", "add_label": "bug,ui"}, "task edit", {"issue": 12, "add_label": "bug,ui"}, False),
    ("task-complete", "finish", {"id": "12", "complete": True, "ignore_checks": True}, "task finish", {"number": 12, "complete": True, "ignore_checks": True}, True),
    ("task-finish", "finish", {"id": "12", "subject": "件名", "partial": True}, "task finish", {"number": 12, "subject": "件名", "partial": True}, True),
    ("task-drop", "drop", {"id": "12", "close": True}, "task drop", {"number": 12, "close": True}, True),
    ("task-prune", "prune", {"id": "12"}, "task prune", {"number": 12}, False),
    ("task-clean", "clean", {}, "task prune", {}, False),
    ("task-approve", "approve", {"id": "12", "message": "よいです"}, "task approve", {"task": 12, "message": "よいです"}, True),
    ("task-reject", "reject", {"id": "12", "message": "直してください"}, "task reject", {"task": 12, "message": "直してください"}, True),
])
def test_each_dialog_runs_its_command_with_what_was_entered(relay, screen, output, payload, command, expected, confirm):
    window = open_screen(relay, "board")
    relay.input(window, "board", "dialog", {"screen": screen, "id": payload.get("id", "0"), "text": ""}, human=True)
    relay.idle()
    dialog = inside(relay, window)
    assert dialog["screen"] == screen and nodes(relay, dialog["id"])["form"]["props"]["kind"] == screen[5:]
    relay.input(dialog["id"], "form", output, payload, human=True)
    if confirm:
        assert answer(relay, dialog["id"], True)["part"] == "confirm-box"  # 重いコマンドは、本体が確かめる
    relay.idle()
    assert calls(relay, command) == [expected]
    assert [w["id"] for w in relay.display.windows()] == [window] and notices(relay, "error") == []


def test_dialog_inputs_that_cannot_be_used_are_refused(relay):
    window = open_screen(relay, "tasks")
    relay.input(window, "list", "dialog", {"screen": "task-reject", "id": "12", "text": ""}, human=True)
    relay.idle()
    dialog = inside(relay, window)
    with pytest.raises(Exception):
        relay.input(dialog["id"], "form", "reject", {"id": "12", "message": "  "}, human=True)  # 直してほしいことが要る
    with pytest.raises(Exception):
        relay.input(dialog["id"], "form", "new", {"title": ""}, human=True)
    with pytest.raises(Exception):
        relay.input(dialog["id"], "form", "start", {"id": "0"}, human=True)
    assert calls(relay, "task reject") == []


# --- ボード・日程 ---------------------------------------------------------------------------------------
def test_board_shows_the_recently_done_and_changes_the_stage(relay):
    window = open_screen(relay, "board")
    view = nodes(relay, window)
    assert [card["number"] for card in view["board"]["props"]["tasks"]] == [12, 13]
    assert [card["number"] for card in view["board"]["props"]["recent"]] == [12, 13, 9]  # 完了の列：閉じたタスクも読んだもの
    assert {"all": True} in calls(relay, "task list") and view["board"]["props"]["me"] == "superFUKA"
    relay.input(window, "board", "edit", {"id": "13", "stage": "planned"}, human=True)  # 計画中の列へ落とす
    relay.idle()
    assert calls(relay, "task edit") == [{"issue": 13, "stage": "planned"}]
    relay.input(window, "board", "close", {"id": "13"}, human=True)  # 完了の列へ落とす（タスクブランチなし）
    assert answer(relay, window, False)["part"] == "confirm-box" and calls(relay, "task close") == []
    relay.input(window, "board", "selected", {"id": "12"}, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == "board" and nodes(relay, window)["pane"]["props"]["status"]["number"] == 12  # 右に詳細
    with pytest.raises(Exception):
        relay.input(window, "board", "selected", {"id": ""}, human=True)


def test_schedule_saves_the_dates_a_bar_was_dragged_to(relay):
    window = open_screen(relay, "schedule")
    view = nodes(relay, window)
    assert [row["number"] for row in view["timeline"]["props"]["tasks"]] == [12, 13] and view["nav"]["props"]["current"] == "schedule"
    relay.input(window, "timeline", "edit", {"id": "12", "planned_start": "2026-11-10", "planned_end": "2026-11-14"}, human=True)
    relay.idle()
    assert calls(relay, "task edit") == [{"issue": 12, "planned_start": "2026-11-10", "planned_end": "2026-11-14"}]
    relay.input(window, "timeline", "selected", {"id": "12"}, human=True)
    relay.idle()
    assert calls(relay, "task status") == [{"number": 12, "body": True}] and not hidden(relay, window, "pane")


# --- 次にやる・スプリント・概要・人 -------------------------------------------------------------------------
def test_next_reads_the_order_for_everyone_and_for_me(relay):
    window = open_screen(relay, "task-next")
    view = nodes(relay, window)
    assert view["next"]["props"]["next"][0]["reasons"] == ["着手できる"] and view["next"]["props"]["mine"][0]["task"]["number"] == 13
    assert [task["number"] for task in view["next"]["props"]["overdue"]["overdue"]] == [12] and view["bar"]["props"]["scope"] == "assignee"
    assert calls(relay, "task next") == [{"count": 10}, {"count": 10, "mine": True}] or calls(relay, "task next") == [{"count": 10, "mine": True}, {"count": 10}]
    assert calls(relay, "task overdue") == [{"days": 7}]
    relay.input(window, "bar", "changed", {"assignee": "@me"}, human=True)
    relay.idle()
    assert nodes(relay, window)["next"]["props"]["filter"]["assignee"] == "@me" and len(calls(relay, "task next")) == 2  # 見せ方だけ


def test_sprint_shows_the_chosen_sprint(relay):
    window = open_screen(relay, "task-sprint")
    view = nodes(relay, window)
    assert view["sprint"]["props"]["status"]["sprint"]["name"] == "Sprint 2" and view["sprint"]["props"]["status"]["days_left"] == 6
    assert [row["number"] for row in view["sprint_tasks"]["props"]["tasks"]] == [12] and view["sprint_tasks"]["props"]["filtered"] is False
    assert calls(relay, "sprint status") == [{}]  # 選ぶまでは、今のスプリント
    relay.input(window, "sprint", "chosen", {"name": "Sprint 1"}, human=True)
    relay.idle()
    assert calls(relay, "sprint status")[-1] == {"name": "Sprint 1"} and nodes(relay, window)["sprint"]["props"]["status"]["sprint"]["name"] == "Sprint 1"
    relay.input(window, "sprint_tasks", "selected", {"id": "12"}, human=True)
    relay.idle()
    assert nodes(relay, window)["pane"]["props"]["status"]["number"] == 12


def test_summary_reads_the_totals_and_opens_the_views(relay):
    window = open_screen(relay, "task-summary")
    props = nodes(relay, window)["summary"]["props"]
    assert [task["number"] for task in props["tasks"]] == [12, 13, 9] and props["sprint"]["sprint"]["name"] == "Sprint 2"
    assert props["workload"][0]["assignee"] == "octocat" and props["milestones"][0]["title"] == "v1" and props["next"][0]["task"]["number"] == 13
    assert props["reviews"][0]["number"] == 12 and props["overdue"]["overdue"][0]["number"] == 12
    for command, expected in (("task next", [{"count": 5, "mine": True}]), ("task overdue", [{"days": 7}]), ("sprint status", [{}]),
                              ("task workload", [{}]), ("milestone status", [{}])):
        assert calls(relay, command) == expected
    assert notices(relay) == []
    relay.input(window, "summary", "go", {"screen": "tasks", "milestone": "v1"}, human=True)  # マイルストーンを押す：それで絞った一覧へ
    relay.idle()
    tree = relay.display.tree(window)
    assert tree["screen"] == "tasks" and nodes(relay, window)["list"]["props"]["start"]["milestone"] == "v1"
    with pytest.raises(Exception):
        relay.input(window, "list", "go", {"screen": "settings"}, human=True)


def test_person_dialog_shows_the_account(relay):
    window = open_screen(relay, "tasks")
    relay.input(window, "list", "dialog", {"screen": "task-person", "id": "0", "text": "octocat"}, human=True)
    relay.idle()
    dialog = inside(relay, window)
    view = nodes(relay, dialog["id"])
    assert view["person"]["props"]["who"] == "octocat" and view["person"]["props"]["workload"][0]["open"] == 1
    assert view["person"]["props"]["submitted"][0]["number"] == 12 and view["list"]["props"]["start"] == {"assignee": "octocat"}
    assert {"submitted": True} in calls(relay, "task list") and {"to_review": True} in calls(relay, "task list")
    relay.input(dialog["id"], "person", "closed", {}, human=True)
    relay.idle()
    assert [w["id"] for w in relay.display.windows()] == [window]


# --- 詳細 ---------------------------------------------------------------------------------------------
def test_detail_changes_the_plan_in_place_and_comments(relay):
    window = open_screen(relay, "tasks")
    relay.input(window, "list", "selected", {"id": "12"}, human=True)
    relay.idle()
    for payload, expected in (({"id": "12", "due": "2026-12-01"}, {"issue": 12, "due": "2026-12-01"}),
                              ({"id": "12", "clear": "estimate"}, {"issue": 12, "clear": "estimate"}),
                              ({"id": "12", "milestone": "v1"}, {"issue": 12, "milestone": "v1"}),
                              ({"id": "12", "clear_milestone": True}, {"issue": 12, "clear_milestone": True}),
                              ({"id": "12", "remove_label": "bug"}, {"issue": 12, "remove_label": "bug"})):
        relay.input(window, "pane", "edit", payload, human=True)
        relay.idle()
        assert calls(relay, "task edit")[-1] == expected
    assert len(calls(relay, "task status")) == 6  # 変えたら、詳細を読み直す
    relay.input(window, "pane", "comment", {"id": "12", "message": "あとは試験だけ"}, human=True)
    relay.idle()
    assert calls(relay, "task comment") == [{"number": 12, "message": "あとは試験だけ"}]
    with pytest.raises(Exception):
        relay.input(window, "pane", "comment", {"id": "12", "message": " "}, human=True)  # 空のコメントは出せない
    relay.input(window, "pane", "selected", {"id": "13"}, human=True)  # つながりのタスクを押す：そのタスクの詳細へ
    relay.idle()
    assert nodes(relay, window)["pane"]["props"]["status"]["number"] == 13 and nodes(relay, window)["list"]["props"]["selected"] == "13"
    assert notices(relay, "error") == []


def test_detail_handles_the_submission(relay):
    window = open_screen(relay, "tasks")
    relay.input(window, "list", "selected", {"id": "12"}, human=True)
    relay.idle()
    relay.input(window, "pane", "review", {"id": "12"}, human=True)
    relay.idle()
    assert calls(relay, "task review") == [{"number": 12}]
    relay.input(window, "pane", "withdraw", {"id": "12"}, human=True)
    assert answer(relay, window, True)["part"] == "confirm-box" and calls(relay, "task withdraw") == [{"number": 12}]
    relay.input(window, "pane", "revert", {"id": "12"}, human=True)
    answer(relay, window, True)
    assert calls(relay, "task revert") == [{"number": 12}]
    relay.input(window, "pane", "dialog", {"screen": "task-finish", "id": "12", "text": ""}, human=True)  # 取り込む：入力の窓
    relay.idle()
    assert inside(relay, window)["screen"] == "task-finish"
    relay.input(inside(relay, window)["id"], "form", "cancel", {}, human=True)
    relay.idle()
    relay.input(window, "pane", "submission", {"id": "12"}, human=True)  # 差分：提出の画面へ
    relay.idle()
    assert relay.display.tree(window)["screen"] == "submission" and str(relay.display.tree(window)["args"]["task"]) == "12"


def test_task_screen_shows_one_task_in_the_whole_window(relay):
    window = open_screen(relay, "task", issue=12)
    view = nodes(relay, window)
    assert view["detail"]["props"]["status"]["title"] == "ログイン画面" and view["detail"]["props"]["closable"] is False
    assert view["nav"]["props"]["current"] == "tasks" and calls(relay, "task status") == [{"number": 12, "body": True}]
    relay.input(window, "detail", "reopen", {"id": "12"}, human=True)
    relay.idle()
    assert calls(relay, "task reopen") == [{"issue": 12}]
    relay.input(window, "detail", "selected", {"id": "13"}, human=True)  # つながりのタスクへ：同じ窓で
    relay.idle()
    tree = relay.display.tree(window)
    assert tree["screen"] == "task" and int(tree["args"]["issue"]) == 13 and nodes(relay, window)["detail"]["props"]["status"]["number"] == 13
    relay.input(window, "back", "pressed", {}, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == "tasks" and notices(relay, "error") == []
