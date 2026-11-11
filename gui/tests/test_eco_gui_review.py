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
        self.stopped = "merge"  # 止まっている操作（続ける・やめるまで）
        self.resolved = set()  # 直して保存した、衝突したファイル
        self.previews = []
        self.submitted = {12: "open", 20: "open", 30: None}  # タスク → 提出の状態（30 は、まだ提出していない）

    def _specs(self, text):
        number, flag = {"type": "integer"}, {"type": "boolean"}
        numbers = {"type": "array", "items": number}
        specs = super()._specs(text)
        specs["task list"] = _spec("read", submitted=flag, to_review=flag)
        specs["task status"] = _spec("read", number=numbers, issue=number)
        specs["task diff"] = _spec("read", number=numbers, task=number)
        specs["task review"] = _spec("change", number=numbers, task=number, done=flag)
        specs["task approve"] = _spec("confirm", ["task"], task=number, message=text, subject=text, ignore_checks=flag)
        specs["task reject"] = _spec("confirm", ["task"], task=number, message=text)
        specs["task comment"] = _spec("change", number=number, issue=number, message=text)
        for name in ("task withdraw", "task revert"):
            specs[name] = _spec("confirm", number=numbers, task=number)
        specs["task finish"] = _spec("confirm", number=numbers, task=number, subject=text, ignore_checks=flag, partial=flag, complete=flag)
        specs["task apply"] = _spec("confirm", number=numbers, task=number, subject=text, partial=flag)
        specs["branch merge"] = {**_spec("confirm", ["name"], name=text, into=text, ignore_checks=flag), "dry_run": True}
        specs["branch submit"] = _spec("confirm", ["name"], name=text, into=text, title=text)
        specs["branch resolve"] = _spec("change", ["name"], name=text, into=text)
        specs["sync take"] = _spec("change", paths={"type": "array", "items": text}, side=text)
        specs["sync conflicts"] = _spec("read", paths={"type": "array", "items": text})
        specs["sync resolve"] = _spec("change", ["path"], path=text, side=text, hunk=text, text=text)
        specs["task submit"] = _spec("confirm", title=text, draft=flag, reviewer=text, partial=flag, complete=flag)
        specs["sync continue"] = _spec("change")
        specs["sync abort"] = _spec("confirm")
        return specs

    def run(self, name, args, context, on_event):
        given = {key: value for key, value in args.items() if key != "module"}
        if name == "task list" and (given.get("submitted") or given.get("to_review")):
            super().run(name, args, context, on_event)
            mine = {"number": 12, "title": "ログイン画面", "assignees": ["superFUKA"], "branch": "task/12-login",
                    "submission": {"number": 13, "state": "open", "base": "main", "draft": True, "partial": False}}
            theirs = {"number": 20, "title": "検索", "assignees": ["octocat"], "branch": "task/20-search",
                      "submission": {"number": 21, "state": "open", "base": "dev", "draft": False, "partial": True}}
            return {"ok": True, "result": [theirs] if given.get("to_review") else [mine, theirs]}
        if name == "task status":
            super().run(name, args, context, on_event)
            state = self.submitted[given["issue"]]
            return {"ok": True, "result": {
                "number": given["issue"], "title": "検索", "assignees": ["octocat"], "branch": "task/20-search", "base": "main",
                "workspace": None, "commits": ["abc 検索を足す"],
                "task_branch": given["issue"] != 20,  # 20 はほかの人の提出（手元にタスクブランチがない）。ほかは、この PC で作業している
                "pull_request": None if state is None else {
                    "number": 21, "url": "https://example.invalid/pull/21", "state": state, "draft": False, "partial": False, "base": "main"},
                "activity": None if state is None else {
                    "reviews": [{"author": "hubot", "state": "COMMENTED", "body": "名前を直して"}], "comments": [{"author": "octocat", "body": "直しました"}],
                    "checks": [{"name": "test", "status": "completed", "conclusion": "success"}], "mergeable": "MERGEABLE"}}}
        if name == "task withdraw":
            self.submitted[given["task"]] = None
        if name == "task diff":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": f"diff --git a/search.py b/search.py\n+#{given['task']} の変更"}
        if name == "status":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"branch": "task/12-login", "task": 12, "stopped": self.stopped,
                                           "merging": bool(self.stopped), "conflicted": list(self.conflicted),
                                           "staged": [], "unstaged": [], "untracked": []}}
        if name == "sync conflicts":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": self.conflicts()}
        if name == "sync resolve":
            self.resolved.add(given["path"])
        if name == "account show":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"login": "superFUKA", "role": "write", "admin": False, "default_base": "main",
                                           "take_in": {"main": {"allowed": False, "owners": "管理者"},
                                                       "dev": {"allowed": True, "owners": "dev を作った superFUKA と管理者"}},
                                           "take_in_other": {"allowed": False, "owners": "管理者"}}}
        if name == "branch list":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": [
                {"name": "dev", "base": "main", "local": True, "remote": True, "merged": False, "submitted_to": "main",
                 "submission": {"number": 40, "url": "https://example.invalid/pull/40", "state": "open", "draft": False, "partial": False}},
                {"name": "main", "base": None, "local": True, "remote": True, "merged": False, "submitted_to": None, "submission": None}]}
        if name == "sync take":
            taken = given.get("paths") or self.conflicted
            self.conflicted = [path for path in self.conflicted if path not in taken]
        if name in ("sync continue", "sync abort"):
            self.conflicted, self.stopped = [], None
        return super().run(name, args, context, on_event)

    def conflicts(self):
        """sync conflicts の結果：直して保存したファイルは、衝突の箇所がない。"""
        files = [{"path": path, "remaining": 0 if path in self.resolved else 1, "reason": "", "reason_text": "",
                  "pieces": [{"text": "fixed", "conflict": False}] if path in self.resolved else [
                      {"text": "<<<<<<< HEAD", "conflict": True, "line": 1, "current": "a", "incoming": "b", "base": None,
                       "both": "ab", "both_incoming_first": "ba"}]} for path in self.conflicted]
        return {"stopped": self.stopped, "current": "このタスクブランチの側", "incoming": "取り込む側",
                "ready": bool(self.stopped) and all(not file["remaining"] for file in files), "files": files}

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


def inside(relay, screen):
    """窓の中に重ねて開いた画面（いちばん新しいもの）。"""
    found = [w for w in relay.display.windows() if w["screen"] == screen and w.get("parent")]
    assert found, f"{screen} が、窓の中に開いていません"
    return found[-1]


def last(relay, name):
    """そのコマンドを最後に呼んだときの引数（呼んでいなければ None）。"""
    found = [args for called, args in relay.backend.calls if called == name]
    return found[-1] if found else None


def test_submissions_lists_what_comes_into_each_branch_and_opens_the_detail_inside(relay):
    window = relay.execute({"command": "open", "screen": "submissions", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "submissions"
    props = view["list"]["props"]
    assert [row["number"] for row in props["tasks"]] == [12, 20] and [row["number"] for row in props["to_review"]] == [20]
    assert [row["name"] for row in props["branches"]] == ["dev", "main"]  # ブランチ同士の提出も、同じ一覧に出す
    assert props["access"]["take_in"]["main"] == {"allowed": False, "owners": "管理者"}  # だれが処理できるかは、ecobuild の答え
    assert ("task list", {"to_review": True}) in relay.backend.calls and ("task list", {"submitted": True}) in relay.backend.calls

    relay.input(window, "list", "selected", {"kind": "task", "id": "20"}, human=True)
    relay.idle()
    opened = inside(relay, "submission")
    assert opened["parent"] == window and opened["args"] == {"module": "C:/work/Calc", "task": "20"}
    assert nodes(relay, opened["id"])["detail"]["props"]["task"]["number"] == 20
    relay.input(opened["id"], "close", "pressed", {}, human=True)
    relay.idle()

    relay.input(window, "list", "selected", {"kind": "branch", "id": "dev"}, human=True)
    relay.idle()
    opened = inside(relay, "review-branch")
    assert opened["args"] == {"module": "C:/work/Calc", "branch": "dev"}
    view = nodes(relay, opened["id"])
    assert view["detail"]["props"]["name"] == "dev" and [row["name"] for row in view["detail"]["props"]["branches"]] == ["dev", "main"]
    assert not [call for call in relay.backend.calls if call == ("task status", {})]  # タスクは読まない（今いる場所のタスクを読まない）
    with pytest.raises(Exception):
        relay.input(window, "list", "selected", {"kind": "pr", "id": "1"}, human=True)
    assert notices(relay) == []


def test_submissions_reverts_a_finished_task_by_its_number(relay):
    window = relay.execute({"command": "open", "screen": "submissions", "args": {"module": "C:/work/Calc"}})["window"]
    relay.idle()
    assert nodes(relay, window)["do_revert"]["wrap"]["kind"] == "unavailable"  # 番号を入れるまで押せない
    relay.input(window, "revert_task", "changed", {"text": "7"}, human=True)
    relay.idle()
    assert nodes(relay, window)["do_revert"]["wrap"] is None
    press(relay, window, "do_revert", yes=False)
    assert ("task revert", {"task": 7}) not in relay.backend.calls
    assert nodes(relay, window)["revert_task"]["props"]["text"] == "7"  # やめたら、欄はそのまま
    press(relay, window, "do_revert", yes=True)
    assert ("task revert", {"task": 7}) in relay.backend.calls
    assert nodes(relay, window)["revert_task"]["props"]["text"] == ""  # 取り消したら、欄は空に戻る


def submission(relay, task=20):
    window = relay.execute({"command": "open", "screen": "submission", "args": {"module": "C:/work/Calc", "task": str(task)}})["window"]
    relay.idle()
    return window


def act(relay, window, action, task=20, **more):
    relay.input(window, "detail", "action", {"action": action, "id": str(task), "base": "main", "partial": False, "workspace": "", **more}, human=True)
    relay.idle()


def test_submission_gives_the_part_the_status_the_account_and_the_workspaces(relay):
    window = submission(relay)
    props = nodes(relay, window)["detail"]["props"]
    assert props["task"]["branch"] == "task/20-search" and props["task"]["pull_request"]["state"] == "open"
    assert props["task"]["activity"]["checks"] == [{"name": "test", "status": "completed", "conclusion": "success"}]
    assert props["task"]["commits"] == ["abc 検索を足す"]
    assert props["access"]["login"] == "superFUKA" and props["access"]["take_in_other"]["allowed"] is False
    assert props["spaces"][0]["path"] == "C:/work/Calc/.ecobuild/w/12"  # 確認中の作業空間があるかは、module show の workspaces から
    assert relay.backend.calls.count(("task status", {"issue": 20})) == 1  # 番号は数で渡る
    assert relay.backend.modules[-1] == "C:/work/Calc" and notices(relay) == []


def test_submission_looks_at_the_diff_the_task_and_the_review_workspace(relay):
    window = submission(relay)
    act(relay, window, "diff")
    opened = inside(relay, "review-diff")
    assert opened["args"] == {"module": "C:/work/Calc", "task": "20"}
    assert nodes(relay, opened["id"])["diff"]["props"]["text"].endswith("#20 の変更") and ("task diff", {"task": 20}) in relay.backend.calls
    relay.input(opened["id"], "close", "pressed", {}, human=True)
    relay.idle()
    assert opened["id"] not in [w["id"] for w in relay.display.windows()]

    act(relay, window, "task")
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "task"] == [{"module": "C:/work/Calc", "issue": 20}]
    act(relay, window, "open_review", workspace="C:/work/Calc/.ecobuild/w/r21")
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "workspace"] == [{"module": "C:/work/Calc/.ecobuild/w/r21"}]
    before = relay.backend.calls.count(("task status", {"issue": 20}))
    act(relay, window, "refresh")
    assert relay.backend.calls.count(("task status", {"issue": 20})) == before + 1


def test_submission_checks_here_and_withdraws(relay):
    window = submission(relay)
    act(relay, window, "review")
    assert ("task review", {"task": 20}) in relay.backend.calls
    act(relay, window, "review_done")
    assert ("task review", {"task": 20, "done": True}) in relay.backend.calls
    assert notices(relay)[-1] == "確認を終え、確認用の作業空間を消しました。"

    mine = submission(relay, 12)
    relay.input(mine, "detail", "action", {"action": "withdraw", "id": "12"}, human=True)
    assert answer(relay, mine, False)["part"] == "confirm-box"  # 取り下げは、確かめてから
    assert ("task withdraw", {"task": 12}) not in relay.backend.calls
    relay.input(mine, "detail", "action", {"action": "withdraw", "id": "12"}, human=True)
    answer(relay, mine, True)
    assert ("task withdraw", {"task": 12}) in relay.backend.calls
    assert nodes(relay, mine)["detail"]["props"]["task"]["pull_request"] is None  # 変えたら読み直す
    with pytest.raises(Exception):
        relay.input(mine, "detail", "action", {"action": "delete", "id": "12"}, human=True)  # 決まったボタンだけ


def form(relay, window, action, task=20, **more):
    """提出の詳細のボタンから、入力の窓を開く。"""
    act(relay, window, action, task, **more)
    return inside(relay, "review-form")


def submit(relay, opened, yes=None, **values):
    """入力の窓で実行を押す。yes を渡すと、出てきた確認に答える。"""
    props = nodes(relay, opened["id"])["form"]["props"]
    blank = {"message": "", "subject": "", "title": "", "reviewer": "", "ignore_checks": False, "draft": False, "complete": False, "partial": False}
    relay.input(opened["id"], "form", "submitted", {"kind": props["kind"], "id": props["id"], **blank, **values}, human=True)
    if yes is not None:
        answer(relay, opened["id"], yes)
    relay.idle()


def test_submission_opens_the_forms_with_what_they_need(relay):
    window = submission(relay)
    opened = form(relay, window, "approve", partial=True)
    assert opened["parent"] == window
    assert nodes(relay, opened["id"])["form"]["props"] == {"kind": "approve", "id": "20", "base": "main", "partial": True, "submitted": False}
    relay.input(opened["id"], "form", "cancelled", {}, human=True)  # キャンセルは、何もせずに閉じる
    relay.idle()
    assert opened["id"] not in [w["id"] for w in relay.display.windows()] and last(relay, "task approve") is None
    for action, kind in (("reject", "reject"), ("comment", "comment"), ("finish", "finish"), ("apply", "apply")):
        opened = form(relay, window, action)
        assert nodes(relay, opened["id"])["form"]["props"]["kind"] == kind
        relay.input(opened["id"], "form", "cancelled", {}, human=True)
        relay.idle()


def test_forms_approve_reject_and_comment(relay):
    window = submission(relay)
    opened = form(relay, window, "approve")
    submit(relay, opened, yes=False)  # 承認は、確かめてから。やめたら、窓は開いたまま
    assert last(relay, "task approve") is None and opened["id"] in [w["id"] for w in relay.display.windows()]
    submit(relay, opened, yes=True, message="よいと思います", subject="検索を足す", ignore_checks=True)
    assert last(relay, "task approve") == {"task": 20, "message": "よいと思います", "subject": "検索を足す", "ignore_checks": True}
    assert opened["id"] not in [w["id"] for w in relay.display.windows()]  # うまくいったら閉じる
    assert notices(relay)[-1] == "承認して取り込みました。"

    opened = form(relay, window, "approve")
    submit(relay, opened, yes=True)
    assert last(relay, "task approve") in ({"task": 20}, {"task": 20, "ignore_checks": False})  # 書かなかった欄は渡さない

    opened = form(relay, window, "reject")
    with pytest.raises(Exception):
        relay.input(opened["id"], "form", "submitted", {"kind": "reject", "id": "20", "message": " "}, human=True)  # 直してほしいことが要る
    submit(relay, opened, yes=True, message="試験を足してください")
    assert last(relay, "task reject") == {"task": 20, "message": "試験を足してください"}

    opened = form(relay, window, "comment")
    submit(relay, opened, message="あとで見ます")
    assert last(relay, "task comment") == {"issue": 20, "message": "あとで見ます"}
    assert opened["id"] not in [w["id"] for w in relay.display.windows()]


def test_forms_finish_complete_and_apply(relay):
    window = submission(relay, 12)
    opened = form(relay, window, "finish", 12)
    submit(relay, opened, yes=True, subject="ログイン画面を足す", ignore_checks=True, complete=False, partial=True)
    assert last(relay, "task finish") == {"task": 12, "subject": "ログイン画面を足す", "ignore_checks": True, "partial": True, "complete": False}
    opened = form(relay, window, "finish", 12)
    submit(relay, opened, yes=True, complete=True, partial=False)
    assert last(relay, "task finish") == {"task": 12, "ignore_checks": False, "partial": False, "complete": True}

    opened = form(relay, window, "apply", 12)
    submit(relay, opened, yes=True, complete=False, partial=True)
    assert last(relay, "task apply") == {"task": 12, "partial": True}

    done = relay.execute({"command": "open", "screen": "review-form", "inside": window,
                          "args": {"module": "C:/work/Calc", "kind": "complete", "id": "12", "base": "main", "submitted": True}})["window"]
    relay.idle()
    assert nodes(relay, done)["form"]["props"]["submitted"] is True
    relay.input(done, "form", "submitted", {"kind": "complete", "id": "12", "ignore_checks": True, "complete": True}, human=True)
    answer(relay, done, True)
    assert last(relay, "task finish") == {"task": 12, "ignore_checks": True, "complete": True}  # 完了にする：いつも --complete


def test_forms_submit_and_merge_a_branch_submission(relay):
    window = relay.execute({"command": "open", "screen": "review-form",
                            "args": {"module": "C:/work/Calc/.ecobuild/w/12", "kind": "submit", "base": "main"}})["window"]
    relay.idle()
    relay.input(window, "form", "submitted", {"kind": "submit", "id": "", "title": "ログイン画面", "draft": True, "reviewer": "octocat",
                                              "complete": False, "partial": True}, human=True)
    answer(relay, window, True)
    assert last(relay, "task submit") == {"title": "ログイン画面", "draft": True, "reviewer": "octocat", "partial": True, "complete": False}
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"  # 提出は、その作業空間で

    detail = relay.execute({"command": "open", "screen": "review-branch", "args": {"module": "C:/work/Calc", "branch": "dev"}})["window"]
    relay.idle()
    opened = form(relay, detail, "merge", "dev")
    submit(relay, opened, yes=True, ignore_checks=True)
    assert last(relay, "branch merge") == {"name": "dev", "ignore_checks": True}  # 取り込み先を付けない：作ってある提出を取り込む


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
    view = nodes(relay, window)
    assert [view[button]["wrap"]["kind"] for button in ("merge", "resolve", "submit")] == ["unavailable"] * 3  # 取り込み先を選ぶまで押せない
    with pytest.raises(Exception):
        relay.input(window, "merge", "pressed", {}, human=True)
    relay.input(window, "targets", "action", {"id": "main", "action": "choose"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["chosen"]["props"]["text"] == "main" and [view[button]["wrap"] for button in ("merge", "resolve", "submit")] == [None] * 3

    shown = press(relay, window, "merge", yes=False)
    assert shown["props"]["preview"].startswith("dev → main：早送り")  # 確認に、入るコミット等（--dry-run の結果）が出る
    assert relay.backend.previews == [("branch merge", {"name": "dev", "into": "main"})]
    assert not [call for call in relay.backend.calls if call[0] == "branch merge"]
    assert relay.display.values(window)["merge_into"] == "main"  # やめたら、選んだ取り込み先はそのまま
    press(relay, window, "merge", yes=True)
    assert ("branch merge", {"name": "dev", "into": "main"}) in relay.backend.calls
    assert relay.display.values(window)["merge_into"] is None  # 取り込んだら、選び直す
    assert nodes(relay, window)["merge"]["wrap"]["kind"] == "unavailable"


def test_merge_submits_resolves_and_takes_in_the_submission(relay):
    window = merge(relay)
    relay.input(window, "targets", "action", {"id": "main", "action": "choose"}, human=True)
    relay.idle()
    press(relay, window, "submit", yes=True)
    assert ("branch submit", {"name": "dev", "into": "main"}) in relay.backend.calls  # 題名（任意）は、書かなければ渡さない
    relay.input(window, "submit_title", "changed", {"text": "11月の分"}, human=True)
    relay.input(window, "targets", "action", {"id": "release", "action": "choose"}, human=True)
    relay.idle()
    press(relay, window, "submit", yes=True)
    assert ("branch submit", {"name": "dev", "into": "release", "title": "11月の分"}) in relay.backend.calls
    assert nodes(relay, window)["submit_title"]["props"]["text"] == ""  # 提出したら、題名の欄は空に戻る

    press(relay, window, "resolve")
    assert ("branch resolve", {"name": "dev", "into": "release"}) in relay.backend.calls

    press(relay, window, "merge_submission")  # 作ってある提出の取り込み：入力の窓（CI が失敗していても取り込むか）を重ねて開く
    opened = inside(relay, "review-form")
    assert nodes(relay, opened["id"])["form"]["props"]["kind"] == "merge" and nodes(relay, opened["id"])["form"]["props"]["id"] == "dev"
    submit(relay, opened, yes=True)
    assert last(relay, "branch merge") in ({"name": "dev"}, {"name": "dev", "ignore_checks": False})


def conflicts(relay):
    window = relay.execute({"command": "open", "screen": "conflicts", "args": {"module": "C:/work/Calc/.ecobuild/w/12"}})["window"]
    relay.idle()
    return window


def test_conflicts_reads_the_files_and_their_hunks(relay):
    window = conflicts(relay)
    view = nodes(relay, window)
    data = view["conflict"]["props"]["data"]
    assert [file["path"] for file in data["files"]] == ["src/app.py", "README.md"] and data["stopped"] == "merge" and not data["ready"]
    assert view["conflict"]["props"]["status"]["branch"] == "task/12-login"
    assert relay.backend.calls.count(("sync conflicts", {})) == 1 and relay.backend.calls.count(("status", {})) == 1
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"  # その作業空間で読む
    assert view["conflict"]["wrap"] is None and notices(relay) == []


def test_conflicts_saves_the_fixed_text_and_takes_a_side(relay):
    window = conflicts(relay)
    fixed = "def add(a, b):\n    return a + b\n"
    relay.input(window, "conflict", "saved", {"path": "src/app.py", "text": fixed}, human=True)
    relay.idle()
    assert ("sync resolve", {"path": "src/app.py", "text": fixed}) in relay.backend.calls  # 直した中身を、そのまま渡す
    files = {file["path"]: file for file in nodes(relay, window)["conflict"]["props"]["data"]["files"]}
    assert files["src/app.py"]["remaining"] == 0 and files["README.md"]["remaining"] == 1  # 変えたら読み直す
    assert notices(relay) == ["保存しました。"]

    relay.input(window, "conflict", "taken", {"paths": ["README.md"], "side": "incoming"}, human=True)
    relay.idle()
    assert ("sync take", {"paths": ["README.md"], "side": "incoming"}) in relay.backend.calls
    data = nodes(relay, window)["conflict"]["props"]["data"]
    assert [file["path"] for file in data["files"]] == ["src/app.py"] and data["ready"]
    relay.input(window, "conflict", "taken", {"paths": [], "side": "current"}, human=True)  # ファイルを付けない：衝突したファイル全部
    relay.idle()
    assert last(relay, "sync take") in ({"side": "current"}, {"paths": [], "side": "current"})
    with pytest.raises(Exception):
        relay.input(window, "conflict", "taken", {"paths": [], "side": "left"}, human=True)  # 側は、今の側か入ってくる側だけ


def test_conflicts_continues_or_aborts_and_closes_the_window(relay):
    window = conflicts(relay)
    relay.input(window, "conflict", "continued", {}, human=True)
    relay.idle()
    assert ("sync continue", {}) in relay.backend.calls
    assert window not in [w["id"] for w in relay.display.windows()]  # 終わったら、窓を閉じる

    relay.backend.conflicted, relay.backend.stopped = ["README.md"], "rebase"
    window = conflicts(relay)
    relay.input(window, "conflict", "aborted", {}, human=True)
    answer(relay, window, False)  # やめるのは、確かめてから
    assert ("sync abort", {}) not in relay.backend.calls and window in [w["id"] for w in relay.display.windows()]
    relay.input(window, "conflict", "aborted", {}, human=True)
    answer(relay, window, True)
    assert ("sync abort", {}) in relay.backend.calls and window not in [w["id"] for w in relay.display.windows()]


def test_backend_passes_the_fixed_text_of_a_conflict_through_standard_input():
    """直した中身は長く、改行もあるので、コマンドラインには「-」を書いて、標準入力で渡す。"""
    from eco_gui.backend import EcobuildBackend

    backend = EcobuildBackend(["ecobuild"])
    assert backend.standard_input("sync resolve", {"module": "C:/m", "path": "src/app.py", "text": "one\ntwo\n"}) == "one\ntwo\n"
    assert backend.standard_input("sync take", {"paths": ["a"], "side": "current"}) is None


def test_backend_shows_what_a_person_sees_with_dry_run(tmp_path):
    """確認に出す文は、人が --dry-run を付けて打ったときの出力（--json なし）。"""
    import sys

    from eco_gui.backend import EcobuildBackend

    script = tmp_path / "fake_ecobuild.py"
    script.write_text("import sys\nwords = sys.argv[1:]\n"
                      "if 'broken' in words:\n    sys.stderr.write('エラー：ブランチ broken はありません。\\n'); sys.exit(1)\n"
                      "sys.stdout.write(' '.join(words) + '\\n  abc1234 最初のコミット\\n')\n", encoding="utf-8")

    def option(param, name, flag=False):
        return {"names": [name], "param": param, "help": param, "flag": flag, "type": "bool" if flag else "str",
                "negative": None, "required": False, "multiple": False}

    catalog = {"ok": True, "result": {"commands": [{"name": "branch", "path": "branch", "runnable": False, "commands": [
        {"name": "merge", "path": "branch merge", "summary": "取り込みます", "runnable": True, "effect": "human",
         "arguments": [{"name": "NAME", "param": "name", "help": "取り込むブランチ", "required": True, "multiple": False, "type": "str"}],
         "options": [option("into", "--into"), option("dry_run", "--dry-run", True), option("json", "--json", True)]}]}], "types": {}}}
    backend = EcobuildBackend([sys.executable, str(script)])
    backend.ask = lambda argv: catalog
    assert backend.commands()["branch merge"]["dry_run"] is True
    shown = backend.dry_run("branch merge", {"name": "dev", "into": "main", "module": "C:/m"})
    assert shown == "-C C:/m branch merge --into main --dry-run -- dev\n  abc1234 最初のコミット"  # --json は付けない。文はそのまま
    assert backend.dry_run("branch merge", {"name": "broken", "into": "main"}) == "エラー：ブランチ broken はありません。"  # できない理由
    assert backend.dry_run("no such command", {}) == ""
