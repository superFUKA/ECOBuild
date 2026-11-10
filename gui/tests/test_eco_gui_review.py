"""eco_gui の提出・レビュー・ブランチの取り込み・衝突を直す画面：バックエンドのコマンドを正しく呼ぶこと。

GUIFrameWork が入っていない Python では飛ばす。ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402


def _spec(weight, required=(), **properties):
    return {"description": "", "weight": weight, "args": {"type": "object", "required": list(required), "properties": properties}}


class FakeReview(FakeEcobuild):
    """提出・ブランチの取り込み・衝突のコマンドを足した、ecobuild の代わり。"""

    def __init__(self):
        super().__init__()
        self.conflicted = ["src/app.py", "README.md"]
        self.previews = []

    def _specs(self, text):
        number, flag = {"type": "integer"}, {"type": "boolean"}
        numbers = {"type": "array", "items": number}
        specs = super()._specs(text)
        specs["task list"] = _spec("read", submitted=flag, to_review=flag)
        specs["task status"] = _spec("read", number=numbers, issue=number)
        specs["task diff"] = _spec("read", number=numbers, task=number)
        specs["task review"] = _spec("change", number=numbers, task=number, done=flag)
        specs["task approve"] = _spec("confirm", ["task"], task=number, message=text)
        specs["task reject"] = _spec("confirm", ["task"], task=number, message=text)
        for name in ("task withdraw", "task finish", "task apply", "task revert"):
            specs[name] = _spec("confirm", number=numbers, task=number)
        specs["branch merge"] = {**_spec("confirm", ["name"], name=text, into=text, ignore_checks=flag), "dry_run": True}
        specs["branch submit"] = _spec("confirm", ["name"], name=text, into=text, title=text)
        specs["branch resolve"] = _spec("change", ["name"], name=text, into=text)
        specs["sync take"] = _spec("change", paths={"type": "array", "items": text}, side=text)
        specs["sync continue"] = _spec("change")
        specs["sync abort"] = _spec("confirm")
        return specs

    def run(self, name, args, context, on_event):
        given = {key: value for key, value in args.items() if key != "module"}
        if name == "task list" and (given.get("submitted") or given.get("to_review")):
            super().run(name, args, context, on_event)
            mine = {"number": 12, "title": "ログイン画面", "assignees": ["superFUKA"], "branch": "task/12-login",
                    "submission": {"number": 13, "state": "open", "base": "main"}}
            theirs = {"number": 20, "title": "検索", "assignees": ["octocat"], "branch": "task/20-search",
                      "submission": {"number": 21, "state": "open", "base": "main"}}
            return {"ok": True, "result": [theirs] if given.get("to_review") else [mine, theirs]}
        if name == "task status":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {
                "number": given["issue"], "title": "検索", "assignees": ["octocat"], "branch": "task/20-search", "base": "main",
                "workspace": None, "commits": ["abc 検索を足す"],
                "pull_request": {"number": 21, "url": "https://example.invalid/pull/21", "state": "open", "draft": False,
                                 "partial": False, "base": "main"},
                "activity": {"reviews": [], "comments": [], "checks": [], "mergeable": "MERGEABLE"}}}
        if name == "task diff":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": f"diff --git a/search.py b/search.py\n+#{given['task']} の変更"}
        if name == "status":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"branch": "task/12-login", "task": 12, "stopped": "merge" if self.conflicted else None,
                                           "merging": bool(self.conflicted), "conflicted": list(self.conflicted),
                                           "staged": [], "unstaged": [], "untracked": []}}
        if name == "sync take":
            taken = given.get("paths") or self.conflicted
            self.conflicted = [path for path in self.conflicted if path not in taken]
        return super().run(name, args, context, on_event)

    def dry_run(self, name, args):
        self.previews.append((name, {key: value for key, value in args.items() if key != "module"}))
        return "dev → main：早送り（入るコミット 2 件・変わるファイル 3 件）"


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeReview(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def notices(relay):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify"]


def press(relay, window, button, yes=None):
    """ボタンを押す。yes を渡すと、出てきた確認に答える。"""
    relay.input(window, button, "pressed", {}, human=True)
    if yes is not None:
        return answer(relay, window, yes)
    relay.idle()


def test_bindings_of_the_new_screens_match_the_backend_commands(relay):
    relay.verify()


def test_submissions_lists_both_kinds_and_opens_a_window_per_task(relay):
    window = relay.execute({"command": "open", "screen": "submissions", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "submissions"
    assert [row["number"] for row in view["to_review"]["props"]["rows"]] == [20]
    assert [row["number"] for row in view["submitted"]["props"]["rows"]] == [12, 20]
    assert ("task list", {"to_review": True}) in relay.backend.calls and ("task list", {"submitted": True}) in relay.backend.calls

    relay.input(window, "to_review", "action", {"id": "20", "action": "open"}, human=True)  # 表は ID を文字で出す
    relay.idle()
    opened = [w for w in relay.display.windows() if w["screen"] == "submission"]
    assert [w["args"] for w in opened] == [{"module": "C:/work/Calc", "task": "20"}]
    relay.input(window, "submitted", "action", {"id": "20", "action": "open"}, human=True)  # 同じ提出は、前に出すだけ
    relay.input(window, "submitted", "action", {"id": "12", "action": "open"}, human=True)
    relay.idle()
    assert sorted(w["args"]["task"] for w in relay.display.windows() if w["screen"] == "submission") == ["12", "20"]
    assert notices(relay) == []


def test_submissions_reverts_a_finished_task_by_its_number(relay):
    window = relay.execute({"command": "open", "screen": "submissions", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    relay.input(window, "revert_task", "changed", {"text": "7"}, human=True)
    relay.idle()
    press(relay, window, "do_revert", yes=False)
    assert ("task revert", {"task": 7}) not in relay.backend.calls
    press(relay, window, "do_revert", yes=True)
    assert ("task revert", {"task": 7}) in relay.backend.calls


def submission(relay, task=20):
    window = relay.execute({"command": "open", "screen": "submission", "args": {"module": "C:/work/Calc", "task": str(task)}})["window"]
    relay.idle()
    return window


def test_submission_shows_the_status_and_the_diff_of_the_task(relay):
    window = submission(relay)
    view = nodes(relay, window)
    assert view["info"]["props"]["data"]["branch"] == "task/20-search"
    assert view["pull_request"]["props"]["data"]["state"] == "open"
    assert view["activity"]["props"]["data"]["mergeable"] == "MERGEABLE"
    assert view["diff"]["props"]["text"].endswith("#20 の変更")
    assert relay.backend.calls.count(("task status", {"issue": 20})) == 1  # 3つの部品へ出しても、1回。番号は数で渡る
    assert ("task diff", {"task": 20}) in relay.backend.calls
    assert relay.backend.modules[-1] == "C:/work/Calc" and notices(relay) == []
    assert not [node["id"] for node in view.values() if node.get("wrap")]  # 番号が決まっているので、どのボタンも押せる


def test_submission_reviews_approves_and_rejects_someone_elses(relay):
    window = submission(relay)
    press(relay, window, "review")
    assert ("task review", {"task": 20}) in relay.backend.calls
    press(relay, window, "review_done")
    assert ("task review", {"task": 20, "done": True}) in relay.backend.calls

    assert press(relay, window, "approve", yes=False)["part"] == "confirm-box"  # 承認は、確かめてから
    assert not [call for call in relay.backend.calls if call[0] == "task approve"]
    press(relay, window, "approve", yes=True)
    assert ("task approve", {"task": 20}) in relay.backend.calls  # コメント（任意）は、書かなければ渡さない

    relay.input(window, "message", "changed", {"text": "試験を足してください"}, human=True)
    relay.idle()
    press(relay, window, "reject", yes=True)
    assert ("task reject", {"task": 20, "message": "試験を足してください"}) in relay.backend.calls


def test_submission_withdraws_finishes_and_applies_ones_own(relay):
    window = submission(relay, 12)
    for button, command in (("withdraw", "task withdraw"), ("finish", "task finish"), ("apply", "task apply")):
        press(relay, window, button, yes=False)
        assert (command, {"task": 12}) not in relay.backend.calls
        press(relay, window, button, yes=True)
        assert (command, {"task": 12}) in relay.backend.calls
    assert relay.backend.calls.count(("task status", {"issue": 12})) >= 4  # 変えたら読み直す


def test_branches_opens_the_merge_screen_for_the_branch_in_the_same_window(relay):
    window = relay.execute({"command": "open", "screen": "branches", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    relay.input(window, "list", "action", {"id": "dev", "action": "merge"}, human=True)
    relay.idle()
    tree = relay.display.tree(window)
    assert (tree["screen"], tree["args"]) == ("merge", {"module": "C:/work/Calc", "name": "dev"})
    assert [w["id"] for w in relay.display.windows()] == [window]  # 窓は増えない
    view = nodes(relay, window)
    assert view["source"]["props"]["text"] == "dev" and view["nav"]["props"]["current"] == "branches"
    assert view["targets"]["props"]["rows"][0]["name"] == "dev"
    relay.input(window, "nav", "selected", {"id": "branches"}, human=True)  # メニューで、ブランチの一覧に戻る
    relay.idle()
    assert relay.display.tree(window)["screen"] == "branches"


def merge(relay):
    window = relay.execute({"command": "open", "screen": "merge", "args": {"module": "C:/work/Calc", "name": "dev"}})["window"]
    relay.idle()
    return window


def test_merge_takes_a_branch_into_another_after_showing_what_it_does(relay):
    window = merge(relay)
    relay.input(window, "targets", "action", {"id": "main", "action": "merge"}, human=True)
    shown = answer(relay, window, False)
    assert shown["props"]["preview"].startswith("dev → main：早送り")  # 確認に、入るコミット等（--dry-run の結果）が出る
    assert relay.backend.previews == [("branch merge", {"name": "dev", "into": "main"})]
    assert not [call for call in relay.backend.calls if call[0] == "branch merge"]
    relay.input(window, "targets", "action", {"id": "main", "action": "merge"}, human=True)
    answer(relay, window, True)
    assert ("branch merge", {"name": "dev", "into": "main"}) in relay.backend.calls


def test_merge_submits_resolves_and_takes_in_the_submission(relay):
    window = merge(relay)
    relay.input(window, "targets", "action", {"id": "main", "action": "submit"}, human=True)
    answer(relay, window, True)
    assert ("branch submit", {"name": "dev", "into": "main"}) in relay.backend.calls  # 題名（任意）は、書かなければ渡さない
    relay.input(window, "submit_title", "changed", {"text": "11月の分"}, human=True)
    relay.idle()
    relay.input(window, "targets", "action", {"id": "release", "action": "submit"}, human=True)
    answer(relay, window, True)
    assert ("branch submit", {"name": "dev", "into": "release", "title": "11月の分"}) in relay.backend.calls

    relay.input(window, "targets", "action", {"id": "main", "action": "resolve"}, human=True)
    relay.idle()
    assert ("branch resolve", {"name": "dev", "into": "main"}) in relay.backend.calls

    press(relay, window, "merge_submission", yes=True)  # 取り込み先を付けない：作ってある提出を取り込む
    assert ("branch merge", {"name": "dev"}) in relay.backend.calls


def conflicts(relay):
    window = relay.execute({"command": "open", "screen": "conflicts", "args": {"module": "C:/work/Calc/.ecobuild/w/12"}})["window"]
    relay.idle()
    return window


def test_conflicts_lists_the_files_and_shows_the_selected_one(relay):
    window = conflicts(relay)
    view = nodes(relay, window)
    assert view["files"]["props"]["paths"] == ["src/app.py", "README.md"]
    assert view["state"]["props"]["data"]["stopped"] == "merge"
    assert relay.backend.calls.count(("status", {})) == 1  # 2つの部品へ出しても、status は1回
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"  # その作業空間で読む
    assert not [call for call in relay.backend.calls if call[0] == "diff"]  # 選ぶまで、中身は読まない
    assert view["take_current"]["wrap"]["kind"] == "unavailable" and view["take_incoming"]["wrap"]["kind"] == "unavailable"
    assert view["all_current"]["wrap"] is None and view["continue"]["wrap"] is None

    relay.input(window, "files", "selected", {"path": "src/app.py"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["files"]["props"]["selected"] == "src/app.py" and view["selected"]["props"]["text"] == "src/app.py"
    assert view["diff"]["props"]["text"].startswith("diff --git a/src/app.py")
    assert view["take_current"]["wrap"] is None


def test_conflicts_takes_one_side_then_continues_or_aborts(relay):
    window = conflicts(relay)
    relay.input(window, "files", "selected", {"path": "src/app.py"}, human=True)
    relay.idle()
    press(relay, window, "take_incoming")
    assert ("sync take", {"paths": ["src/app.py"], "side": "incoming"}) in relay.backend.calls
    assert relay.display.values(window)["file"] is None  # 採ったら、選択を空に
    assert nodes(relay, window)["files"]["props"]["paths"] == ["README.md"]  # 変えたら読み直す

    relay.input(window, "files", "selected", {"path": "README.md"}, human=True)
    relay.idle()
    press(relay, window, "take_current")
    assert ("sync take", {"paths": ["README.md"], "side": "current"}) in relay.backend.calls
    press(relay, window, "all_incoming")  # ファイルを付けない：衝突したファイル全部
    press(relay, window, "all_current")
    assert ("sync take", {"side": "incoming"}) in relay.backend.calls and ("sync take", {"side": "current"}) in relay.backend.calls

    press(relay, window, "continue")
    assert ("sync continue", {}) in relay.backend.calls
    press(relay, window, "abort", yes=False)  # やめるのは、確かめてから
    assert ("sync abort", {}) not in relay.backend.calls
    press(relay, window, "abort", yes=True)
    assert ("sync abort", {}) in relay.backend.calls
