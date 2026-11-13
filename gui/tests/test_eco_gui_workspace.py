"""eco_gui の作業空間の窓（エクスプローラー・コミット・Push・提出・ログ・出力欄・ステータスバー・帯・ツールバー）：
窓の作りと、画面が、人が打つのと同じコマンドを正しい引数で呼ぶこと。

ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402

from test_eco_gui import answer, nodes, without_tortoisegit  # noqa: E402
from test_eco_gui_polish import PolishEcobuild, last, notices, opened, press  # noqa: E402

PLACE = "C:/work/Calc/.ecobuild/w/12"


class WorkspaceEcobuild(PolishEcobuild):
    """作業空間の窓が読むものを、場面ごとに変えられる ecobuild の代わり。"""

    def __init__(self):
        super().__init__()
        self.status = {"module": "Calc", "branch": "task/12-login", "task": 12, "base": "main", "base_at": "0123abcdef", "ahead": 2, "behind": 0, "merging": False,
                       "stopped": None, "reviewing": None, "reviewing_task": None, "upstream_gone": False, "finished": False,
                       "staged": [], "unstaged": ["a.py", "b.py"], "untracked": ["new.txt"], "conflicted": [], "eol_only": [], "excluded": [],
                       "pull_request": None, "format": 5, "latest_format": 5}
        self.remote = {"base_behind": 3, "base_conflicts": ["a.py"], "archived": False}

    def run(self, name, args, context, on_event):
        result = super().run(name, args, context, on_event)
        args = {key: value for key, value in args.items() if key != "module"}
        if name == "status":
            return {"ok": True, "result": {**self.status, **(self.remote if args.get("fetch") else {"base_behind": None, "base_conflicts": []})}}
        if name == "task status":
            return {"ok": True, "result": {"number": args.get("number") or args.get("issue"), "title": "ログイン画面を作る", "state": "open",
                                           "base": "main", "commits": ["bbb222 2つ目", "aaa111 1つ目"], "assignees": ["octocat"]}}
        if name == "files":
            return {"ok": True, "result": {"files": ["README.md", "a.py", "b.py", "gone.py", "new.txt", "tests/test_a.py"], "missing": ["gone.py"],
                                           "folders": ["docs/empty"]}}
        if name == "log":
            if args.get("unpushed"):
                return {"ok": True, "result": [{"sha": "bbb222", "subject": "2つ目", "author": "octocat", "date": "2026-11-02T10:00:00+09:00"},
                                               {"sha": "aaa111", "subject": "1つ目", "author": "octocat", "date": "2026-11-01T10:00:00+09:00"}]}
            return {"ok": True, "result": [{"sha": "abc", "subject": "最初", "author": "octocat", "date": "2026-11-01", "pull_request": 31, "issue": 12}]}
        if name == "check":
            return {"ok": True, "result": {"items": [{"name": "build", "ok": True, "detail": ""}, {"name": "test", "ok": False, "detail": "1 failed"}]}}
        if name == "test" and not self.failing:
            return {"ok": True, "result": {"project": None, "configuration": "Debug", "passed": 1, "failed": 1, "skipped": 0, "cases": [
                {"name": "tests/test_a.py::test_ok", "status": "passed"}, {"name": "tests/test_a.py::test_bad", "status": "failed"}]}}
        return result


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=WorkspaceEcobuild(), roles={"confirm": "confirm-box"})
    relay = app.relay(threaded=True)
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    return relay


def shown(relay, window, node):
    return (nodes(relay, window)[node].get("wrap") or {}).get("kind") != "hidden"


def inside(relay, window, screen):
    """窓の中に重ねて開いた画面の窓。"""
    return next(w["id"] for w in relay.display.windows() if w["screen"] == screen and w.get("parent") == window)


def test_the_window_has_the_explorer_the_work_area_the_output_and_the_status_bar(relay):
    window = opened(relay, "workspace", PLACE)
    view = nodes(relay, window)
    assert view["page"]["children"] == ["state", "toolbar", "body", "foot"]
    assert (view["body"]["layout"], view["body"]["props"]) == ("split", {"direction": "column", "sizes": [None, 230]})  # 上と、下の出力欄
    assert (view["upper"]["layout"], view["upper"]["children"]) == ("split", ["explorer", "work"])  # 左：エクスプローラー／右：コミット・共有
    assert (view["explorer"]["part"], view["out"]["part"], view["foot"]["part"]) == ("ws-explorer", "output", "ws-statusbar")
    # 状態は1回だけ読み、見出し・ツールバー・タブ・変更の一覧・エクスプローラー・ステータスバー・帯へ出す
    assert relay.backend.calls.count(("status", {})) == 1 and relay.backend.calls.count(("status", {"fetch": True})) == 1
    for name in ("state", "toolbar", "tabs", "changes", "explorer", "foot", "b_conflict", "b_behind"):
        key = "data" if name == "state" else "status"
        assert view[name]["props"][key]["branch"] == "task/12-login", name
    # ファイルの状態：一覧・消えたファイル・変更の種類が、エクスプローラーと変更の一覧へ
    assert view["explorer"]["props"]["files"][:2] == ["README.md", "a.py"] and view["explorer"]["props"]["missing"] == ["gone.py"]
    assert view["changes"]["props"]["missing"] == ["gone.py"] and view["changes"]["props"]["stashes"] == relay.backend.stashes
    # GitHub の最新を確かめた状態（遅れ・衝突するファイル）は、ツールバーの「取り込む」・ステータスバー・帯へ
    for name in ("toolbar", "foot", "b_behind"):
        assert view[name]["props"]["remote"]["base_behind"] == 3 and view[name]["props"]["remote"]["base_conflicts"] == ["a.py"]
    assert view["state"]["props"]["task"]["title"] and view["state"]["props"]["name"] == "Calc"  # 見出し：モジュールの名前とタスクの題
    assert view["toolbar"]["props"]["profiles"]["selected"] == "fast"
    assert notices(relay) == []


def test_the_tabs_show_one_panel_and_push_moves_to_the_submission(relay):
    window = opened(relay, "workspace", PLACE)
    assert [shown(relay, window, name) for name in ("commit_panel", "push_panel", "submit_panel", "log_panel")] == [True, False, False, False]
    press(relay, window, "tabs", "selected", tab="push")
    assert [shown(relay, window, name) for name in ("commit_panel", "push_panel", "submit_panel", "log_panel")] == [False, True, False, False]
    view = nodes(relay, window)
    assert view["tabs"]["props"]["selected"] == "push" and view["push_state"]["props"]["data"]["ahead"] == 2
    assert [c["sha"] for c in view["push_list"]["props"]["commits"]] == ["bbb222", "aaa111"]  # Push するコミットの一覧
    assert ("log", {"unpushed": True}) in relay.backend.calls
    press(relay, window, "push")
    assert last(relay) == ("task push", {}) and relay.display.values(window)["tab"] == "submit"  # Push の後は、提出へ
    assert shown(relay, window, "submit_panel") and not shown(relay, window, "push_panel")
    # 提出のタブ：このタスクの提出（task status）・アカウント（処理できるか）・提出に入るコミット（作成元にないもの）
    view = nodes(relay, window)
    assert view["pull_request"]["props"]["task"]["number"] == 12 and view["pull_request"]["props"]["access"]["login"] == "superFUKA"
    assert view["tabs"]["props"]["task"]["commits"] == ["bbb222 2つ目", "aaa111 1つ目"]  # タブの数は、提出に入るコミットの数
    assert ("log", {"not_in": "main"}) in relay.backend.calls and view["pr_commits"]["props"]["mode"] == "log"
    # すること：提出・反映・コメントは入力の窓、下書きの解除・取り下げはその場で（取り下げは確かめてから）
    press(relay, window, "pull_request", "action", action="submit", id="12")
    assert inside(relay, window, "task-submit")
    press(relay, window, "pull_request", "action", action="apply", id="12")
    assert inside(relay, window, "task-apply") and [w["args"]["issue"] for w in relay.display.windows() if w["screen"] == "task-apply"] == [12]
    press(relay, window, "pull_request", "action", action="ready", id="12")
    assert last(relay) == ("task submit", {"check": False})
    relay.input(window, "pull_request", "action", {"action": "withdraw", "id": "12"}, human=True)
    answer(relay, window, True)
    relay.idle()
    assert last(relay) == ("task withdraw", {"task": 12})
    press(relay, window, "pull_request", "action", action="full_log", id="12")  # すべてのログは、別の窓
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "ws-log"] == [{"module": PLACE}]


def test_unpushed_commits_are_undone_with_task_reset(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "tabs", "selected", tab="push")
    relay.input(window, "push_list", "action", {"name": "undo", "sha": "bbb222", "before": "bbb222~1"}, human=True)
    relay.idle()  # 入力の窓が確認を兼ねる（もう一度は確かめない）
    relay.idle()
    assert last(relay) == ("task reset", {"commit": "bbb222~1", "keep": True}) and relay.display.values(window)["tab"] == "commit"
    press(relay, window, "tabs", "selected", tab="push")
    relay.input(window, "push_list", "action", {"name": "drop", "sha": "aaa111", "before": "aaa111~1"}, human=True)
    answer(relay, window, False)
    assert ("task reset", {"commit": "aaa111~1"}) not in relay.backend.calls
    press(relay, window, "push_list", "action", name="show", sha="aaa111", before="aaa111~1")  # 変更を見る：TortoiseGit で
    assert relay.backend.calls[-1] == ("show", {"commit": "aaa111", "gui": True})
    without_tortoisegit(relay)  # なければ、窓の中に重ねて開く
    press(relay, window, "push_list", "action", name="show", sha="aaa111", before="aaa111~1")
    dialog = inside(relay, window, "ws-show")
    assert nodes(relay, dialog)["detail"]["props"]["text"].startswith("commit aaa111") and ("show", {"commit": "aaa111"}) in relay.backend.calls
    press(relay, window, "push_list", "more", count=60)
    assert ("log", {"unpushed": True, "count": 60}) in relay.backend.calls and nodes(relay, window)["push_list"]["props"]["count"] == 60


def test_the_conflict_banner_shows_only_while_stopped_and_continues_or_aborts(relay):
    window = opened(relay, "workspace", PLACE)
    assert not shown(relay, window, "b_conflict") and not shown(relay, window, "b_gone")  # 当てはまらない帯は出さない
    relay.backend.status.update(merging=True, stopped="merge", conflicted=["a.py"], upstream_gone=True, finished=True)
    press(relay, window, "foot", "action", name="fetch")  # 読み直す
    assert shown(relay, window, "b_conflict") and shown(relay, window, "b_gone")
    assert nodes(relay, window)["b_conflict"]["props"]["status"]["stopped"] == "merge"
    press(relay, window, "b_conflict", "action", name="continue")
    assert last(relay) == ("sync continue", {})
    relay.input(window, "b_conflict", "action", {"name": "abort"}, human=True)
    answer(relay, window, True)  # やめるのは、確かめてから
    relay.idle()
    assert last(relay) == ("sync abort", {})
    press(relay, window, "b_conflict", "action", name="resolve")
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "conflicts"] == [{"module": PLACE}]
    press(relay, window, "b_gone", "action", name="prune")
    assert last(relay) == ("task prune", {"number": 12})


def test_the_other_banners_run_the_commands_of_their_buttons(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "b_behind", "action", name="sync")
    assert last(relay) == ("sync", {})
    # 最新の仕様にする：入力の窓が、下見（変えるファイル）を見せてから実行する
    relay.backend.preview = lambda name, args: {"ok": True, "result": {"format": 4, "latest_format": 5, "paths": ["ecobuild.toml"], "skipped": []}}
    press(relay, window, "b_format", "action", name="upgrade")
    form = inside(relay, window, "mod-upgrade")
    assert nodes(relay, form)["form"]["props"]["values"]["paths"] == ["ecobuild.toml"]
    relay.input(form, "form", "submitted", {"values": {}}, human=True)
    relay.idle()
    assert last(relay)[0] == "module upgrade" and relay.backend.modules[-1] == PLACE
    relay.input(window, "b_left", "action", {"name": "discard_left", "paths": ["a.py", "new.txt"]}, human=True)
    answer(relay, window, True)
    relay.idle()
    assert last(relay) == ("restore", {"paths": ["a.py", "new.txt"]})
    press(relay, window, "b_review", "action", name="review_done")
    assert last(relay) == ("task review", {"done": True})
    relay.input(window, "b_archived", "action", {"name": "unarchive"}, human=True)
    answer(relay, window, True)
    relay.idle()
    assert last(relay) == ("module unarchive", {"name": "Calc"})
    press(relay, window, "b_notask", "action", name="tasks")
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "tasks"] == [{"module": PLACE}]


def test_the_toolbar_runs_and_the_output_shows_the_title_the_state_and_the_result(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "toolbar", "action", name="configuration", value="Release")
    assert nodes(relay, window)["toolbar"]["props"]["configuration"] == "Release"
    press(relay, window, "toolbar", "action", name="build")
    assert last(relay) == ("build", {"configuration": "Release"})
    out = nodes(relay, window)["out"]["props"]
    assert (out["title"], out["kind"], out["state"]) == ("ビルド", "build", "ok") and out["lines"] == ["構成しています…", "ビルドしています…"]
    assert out["result"]["artifacts"] == ["dist/calc-1.0-py3-none-any.whl"] and nodes(relay, window)["foot"]["props"]["run"] == "ok"
    for name, command in (("rebuild", "rebuild"), ("clean", "clean"), ("run", "run")):
        press(relay, window, "toolbar", "action", name=name)
        assert last(relay) == (command, {"configuration": "Release"}) and nodes(relay, window)["out"]["props"]["kind"] == name
    press(relay, window, "toolbar", "action", name="check")
    out = nodes(relay, window)["out"]["props"]
    assert ("check", {}) in relay.backend.calls and (out["title"], out["result"]["items"][1]["ok"]) == ("提出前の確認", False)
    # 試験：結果（1件ずつ）は出力欄へ。失敗したものは、ツールバーの「失敗だけ再実行」へ
    press(relay, window, "toolbar", "action", name="test")
    view = nodes(relay, window)
    assert last(relay) == ("test", {"configuration": "Release"}) and view["out"]["props"]["result"]["failed"] == 1
    assert view["toolbar"]["props"]["last_test"]["cases"][1] == {"name": "tests/test_a.py::test_bad", "status": "failed"}
    press(relay, window, "toolbar", "action", name="test_failed", tests=["tests/test_a.py::test_bad"])
    assert last(relay) == ("test", {"tests": ["tests/test_a.py::test_bad"], "configuration": "Release"})
    relay.backend.failing = True  # コマンドが失敗した：状態は「失敗」
    press(relay, window, "toolbar", "action", name="test")
    assert nodes(relay, window)["out"]["props"]["state"] == "bad" and nodes(relay, window)["foot"]["props"]["run"] == "bad"
    assert nodes(relay, window)["foot"]["props"]["kind"] == "test"  # ステータスバーも、結果から失敗を読める


def test_the_toolbar_takes_in_and_opens_the_dialogs(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "toolbar", "action", name="profile", value="ship")
    assert last(relay) == ("profile use", {"name": "ship"}) and nodes(relay, window)["toolbar"]["props"]["profiles"]["selected"] == "ship"
    press(relay, window, "toolbar", "action", name="sync")
    assert last(relay) == ("sync", {})
    before = relay.backend.calls.count(("status", {"fetch": True}))
    press(relay, window, "toolbar", "action", name="fetch")  # GitHub の最新を確認：読み直す
    assert relay.backend.calls.count(("status", {"fetch": True})) == before + 1
    # バージョン・ブランチを選んで取り込む
    press(relay, window, "toolbar", "action", name="sync_pick")
    dialog = inside(relay, window, "ws-sync")
    assert nodes(relay, dialog)["now"]["props"]["data"]["base_behind"] == 3 and nodes(relay, dialog)["branch"]["props"]["rows"][0]["name"] == "dev"
    assert nodes(relay, dialog)["take"]["wrap"]["kind"] == "unavailable"  # ブランチとバージョンを選ぶまで押せない
    press(relay, dialog, "branch", "changed", value="dev")
    assert ("log", {"branch": "dev", "count": 50}) in relay.backend.calls
    press(relay, dialog, "versions", "selected", sha="abc")
    press(relay, dialog, "take")
    assert last(relay) == ("sync", {"from_branch": "dev", "at": "abc"})
    assert not [w for w in relay.display.windows() if w["screen"] == "ws-sync"]  # 済んだら閉じる
    # アカウント
    press(relay, window, "toolbar", "action", name="account")
    dialog = inside(relay, window, "ws-account")
    press(relay, dialog, "list", "action", id="hubot", action="use")
    assert last(relay) == ("account use", {"account": "hubot"})
    press(relay, dialog, "clear")
    assert last(relay) == ("account use", {"clear": True})
    press(relay, window, "toolbar", "action", name="container")
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "container"] == [{"module": PLACE}]
    press(relay, window, "toolbar", "action", name="agents")
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "agents"] == [{"module": PLACE}]


def test_the_explorer_renames_removes_and_runs_with_the_file_commands(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "explorer", "selected", path="a.py")
    view = nodes(relay, window)
    assert view["explorer"]["props"]["selected"] == "a.py" and view["changes"]["props"]["selected"] == "a.py"  # 変更の一覧でも同じファイルを強調
    press(relay, window, "explorer", "action", name="rename", path="a.py", paths=["a.py"], to="src/c.py")  # その場で名前を変える
    assert last(relay) == ("file move", {"paths": ["a.py", "src/c.py"]})
    # 削除：入力の窓（対応するテストも削除するか。窓が確認を兼ねる）
    press(relay, window, "explorer", "action", name="remove", path="", paths=["a.py", "tests"])
    dialog = inside(relay, window, "ws-remove")
    assert nodes(relay, dialog)["targets"]["props"]["items"] == ["a.py", "tests"]
    press(relay, dialog, "test", "changed", on=False)
    press(relay, dialog, "remove")
    assert last(relay) == ("file remove", {"paths": ["a.py", "tests"], "test": False})
    assert not [w for w in relay.display.windows() if w["screen"] == "ws-remove"]
    relay.input(window, "explorer", "action", {"name": "restore", "path": "b.py", "paths": ["b.py"]}, human=True)
    answer(relay, window, True)
    relay.idle()
    assert last(relay) == ("restore", {"paths": ["b.py"]})
    press(relay, window, "explorer", "action", name="ignore", path="build/", paths=["build/"])
    assert last(relay) == ("ignore", {"patterns": ["build/"]})
    # テストを作成：入力の窓（--dry-run の場所と名前を見せる）。作ったら、木で選んで開く
    relay.backend.preview = lambda name, args: {"ok": True, "result": {"paths": ["CalcTest/src/AddTest.cpp"]}}
    press(relay, window, "explorer", "action", name="make_test", path="Calc/src/Add.cpp", paths=["Calc/src/Add.cpp"])
    dialog = inside(relay, window, "ws-file-test")
    assert nodes(relay, dialog)["form"]["props"]["plan"] == {"paths": ["CalcTest/src/AddTest.cpp"]}
    press(relay, dialog, "form", "make", to="CalcTest/src/parse/AddTest.cpp")
    assert last(relay) == ("file test", {"paths": ["Calc/src/Add.cpp"], "to": "CalcTest/src/parse/AddTest.cpp"})
    press(relay, window, "explorer", "action", name="take_incoming", path="a.py", paths=["a.py"])
    assert last(relay) == ("sync take", {"paths": ["a.py"], "side": "incoming"})
    press(relay, window, "explorer", "action", name="run_test", path="tests/test_a.py", paths=["tests/test_a.py"])
    assert last(relay) == ("test", {"tests": ["tests/test_a.py"]}) and nodes(relay, window)["out"]["props"]["title"] == "テスト"
    # コミットの対象にする：チェックを付けて、コミットのタブへ
    press(relay, window, "tabs", "selected", tab="log")
    press(relay, window, "explorer", "action", name="commit", path="", paths=["a.py", "new.txt"])
    assert relay.display.values(window)["paths"] == ["a.py", "new.txt"] and shown(relay, window, "commit_panel")


def test_the_explorer_opens_the_new_file_the_diff_the_log_and_the_move_dialogs(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "explorer", "action", name="new_file", path="tests", paths=["tests"])
    dialog = inside(relay, window, "ws-new-file")
    assert nodes(relay, dialog)["form"]["props"]["folder"] == "tests" and "a.py" in nodes(relay, dialog)["form"]["props"]["files"]
    press(relay, dialog, "form", "add", paths=["tests/test_b.py", "tests/test_c.py"], test=False)
    assert last(relay) == ("file add", {"paths": ["tests/test_b.py", "tests/test_c.py"], "test": False})
    assert not [w for w in relay.display.windows() if w["screen"] == "ws-new-file"]
    press(relay, window, "explorer", "action", name="move", path="a.py", paths=["a.py"])
    dialog = inside(relay, window, "ws-move")
    assert nodes(relay, dialog)["move"]["wrap"]["kind"] == "unavailable"  # 移動先を書くまで押せない
    press(relay, dialog, "destination", "changed", text="src/a.py")
    press(relay, dialog, "move")
    assert last(relay) == ("file move", {"paths": ["a.py", "src/a.py"]})
    # 差分・注釈履歴：TortoiseGit で開く（前の GUI と同じ）
    told = len(notices(relay))
    press(relay, window, "explorer", "action", name="diff", path="a.py", paths=["a.py"])
    press(relay, window, "explorer", "action", name="blame", path="a.py", paths=["a.py"])
    assert relay.backend.calls[-2:] == [("diff", {"paths": ["a.py"], "gui": True}), ("blame", {"path": "a.py", "gui": True})]
    assert not [w for w in relay.display.windows() if w["screen"] in ("ws-file-diff", "blame")] and len(notices(relay)) == told
    # TortoiseGit がなければ、GUI の中で：差分は比べ方ごと（ステージしていない／ステージ済み／作成元との差分）
    without_tortoisegit(relay)
    press(relay, window, "explorer", "action", name="diff", path="a.py", paths=["a.py"])
    dialog = inside(relay, window, "ws-file-diff")
    assert nodes(relay, dialog)["unstaged"]["props"]["text"].startswith("diff --git a/a.py")
    for args in ({"paths": ["a.py"]}, {"paths": ["a.py"], "staged": True}, {"paths": ["a.py"], "base": True}):
        assert ("diff", args) in relay.backend.calls
    # ログ・注釈履歴は、別の窓
    press(relay, window, "explorer", "action", name="log", path="tests", paths=["tests"])
    log = next(w for w in relay.display.windows() if w["screen"] == "ws-log")
    assert log["args"] == {"module": PLACE, "paths": ["tests"]} and ("log", {"paths": ["tests"]}) in relay.backend.calls
    press(relay, window, "explorer", "action", name="blame", path="a.py", paths=["a.py"])
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "blame"] == [{"module": PLACE, "path": "a.py"}]


def test_the_log_tab_lists_commits_and_shows_the_chosen_one(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "tabs", "selected", tab="log")
    view = nodes(relay, window)
    assert view["log:list"]["props"]["commits"][0]["pull_request"] == 31 and view["log:detail"]["props"]["text"] == ""
    press(relay, window, "log:list", "selected", sha="abc")
    view = nodes(relay, window)
    assert view["log:detail"]["props"]["text"].startswith("commit abc") and view["log:detail"]["props"]["sha"] == "abc"
    assert view["log:list"]["props"]["selected"] == "abc"
    press(relay, window, "log:list", "more", count=60)  # さらに読み込む
    assert ("log", {"paths": [], "count": 60}) in relay.backend.calls and nodes(relay, window)["log:list"]["props"]["count"] == 60
    relay.input(window, "log:list", "action", {"name": "reset", "sha": "abc"}, human=True)
    answer(relay, window, True)  # ここまで戻すのは、確かめてから
    relay.idle()
    assert last(relay) == ("task reset", {"commit": "abc"})


def test_the_changes_menu_and_the_stash_menu_run_their_commands(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "changes", "action", name="stash")
    assert last(relay) == ("stash", {})
    press(relay, window, "changes", "action", name="stash_pop")
    assert last(relay) == ("stash pop", {})
    relay.input(window, "changes", "action", {"name": "stash_drop"}, human=True)
    answer(relay, window, True)
    relay.idle()
    assert last(relay) == ("stash drop", {})
    press(relay, window, "changes", "action", name="ignore", path="new.txt", paths=["new.txt"])
    assert last(relay) == ("ignore", {"patterns": ["new.txt"]})
    press(relay, window, "changes", "action", name="diff_dialog", path="", paths=[])  # 選んでいなければ、全部のファイル（TortoiseGit で）
    assert relay.backend.calls[-1] == ("diff", {"paths": [], "gui": True})
    without_tortoisegit(relay)  # なければ、窓の中に比べ方ごとのタブで
    press(relay, window, "changes", "action", name="diff_dialog", path="", paths=[])
    dialog = inside(relay, window, "ws-file-diff")
    assert nodes(relay, dialog)["target"]["props"]["items"] == [] and ("diff", {"paths": [], "staged": True}) in relay.backend.calls


def test_the_output_starts_hidden_and_a_run_shows_it(relay):
    window = opened(relay, "workspace", PLACE)
    assert not shown(relay, window, "out")  # 最初はしまっておく（前の GUI と同じ）
    press(relay, window, "foot", "action", name="show_output")
    assert shown(relay, window, "out") and nodes(relay, window)["foot"]["props"]["output_shown"] is True
    press(relay, window, "foot", "action", name="hide_output")
    assert not shown(relay, window, "out") and nodes(relay, window)["foot"]["props"]["output_shown"] is None
    press(relay, window, "toolbar", "action", name="build")  # 動かすと出る
    assert shown(relay, window, "out") and nodes(relay, window)["foot"]["props"]["output_shown"] is True


def test_a_new_file_shows_its_content_instead_of_a_diff(relay):
    """まだ git の管理に入っていないファイル：TortoiseGit の差分には送らず、中身をこの GUI で見せる（前の GUI と同じ）。"""
    window = opened(relay, "workspace", PLACE)
    for node in ("changes", "explorer"):
        press(relay, window, node, "action", name="view_new", path="new.txt", paths=["new.txt"])
        dialog = inside(relay, window, "ws-untracked")
        assert nodes(relay, dialog)["target"]["props"]["items"] == ["new.txt"] and ("diff", {"paths": ["new.txt"]}) in relay.backend.calls
        press(relay, dialog, "close")
    assert ("diff", {"paths": ["new.txt"], "gui": True}) not in relay.backend.calls


def test_amending_without_files_asks_first_and_a_pushed_amend_tells_to_force_push(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "commit_box", "changed", text="直す")
    press(relay, window, "commit_box", "amend", on=True)
    # ファイルを選ばずに修正：すべての変更を含めてよいか、入力の窓で確かめる（まだ実行しない）
    before = len(relay.backend.calls)
    press(relay, window, "commit_box", "commit", amend=True, all=True, pushed=True)
    dialog = inside(relay, window, "ws-amend-all")
    assert not [call for call in relay.backend.calls[before:] if call[0] == "task commit"]
    assert "強制Push" in nodes(relay, dialog)["hint"]["props"]["text"]
    press(relay, dialog, "amend")
    assert last(relay) == ("task commit", {"message": "直す", "amend": True})
    assert relay.display.values(window)["amend"] is None and relay.display.values(window)["message"] is None
    # Push 済みのコミットを修正：強制Push の案内と、Push のタブへ
    press(relay, window, "changes", "changed", paths=["a.py"])
    press(relay, window, "commit_box", "changed", text="もう一度")
    press(relay, window, "commit_box", "amend", on=True)
    press(relay, window, "commit_box", "commit", amend=True, all=False, pushed=True)
    assert last(relay) == ("task commit", {"paths": ["a.py"], "message": "もう一度", "amend": True})
    assert any("強制Push" in text for text in notices(relay)) and relay.display.values(window)["tab"] == "push"


def test_the_review_banner_opens_the_approve_and_reject_dialogs_here(relay):
    relay.backend.status.update(task=None, reviewing=31, reviewing_task=12, branch="review/31")
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "b_review", "action", name="approve")
    assert [w["args"]["issue"] for w in relay.display.windows() if w["screen"] == "task-approve"] == [12]
    press(relay, window, "b_review", "action", name="reject")
    assert [w["args"]["issue"] for w in relay.display.windows() if w["screen"] == "task-reject"] == [12]
    assert not [w for w in relay.display.windows() if w["screen"] == "submission"]  # 別の窓には行かない
    assert nodes(relay, window)["pull_request"]["props"]["review"]["number"] == 12  # 提出のタブは、確認している提出


def test_made_and_moved_files_are_chosen_in_the_explorer(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "explorer", "action", name="new_file", path="tests", paths=["tests"])
    dialog = inside(relay, window, "ws-new-file")
    press(relay, dialog, "form", "add", paths=["tests/test_b.py"], test=True)
    assert nodes(relay, window)["explorer"]["props"]["made"] == ["tests/test_b.py"]  # 木で選んで、開発の道具で開く
    press(relay, window, "explorer", "action", name="revealed", path="tests/test_b.py", paths=["tests/test_b.py"])
    assert nodes(relay, window)["explorer"]["props"]["made"] is None
    # 移動：対応するテストも動かすかを選ぶ。動かした先を、木で選ぶ
    press(relay, window, "explorer", "action", name="move", path="a.py", paths=["a.py"])
    dialog = inside(relay, window, "ws-move")
    press(relay, dialog, "destination", "changed", text="src/a.py")
    press(relay, dialog, "test", "changed", on=False)
    press(relay, dialog, "move")
    assert last(relay) == ("file move", {"paths": ["a.py", "src/a.py"], "test": False})
    assert nodes(relay, window)["explorer"]["props"]["moved"] == "src/a.py"
    # ドラッグで、別のフォルダーへ
    press(relay, window, "explorer", "action", name="drop_move", path="b.py", paths=["b.py"], to="tests/b.py")
    assert last(relay) == ("file move", {"paths": ["b.py", "tests/b.py"]})
    assert nodes(relay, window)["explorer"]["props"]["moved"] == "tests/b.py"
    # 一緒に開く・選んだものを開く（ecobuild open にいくつものパス）
    press(relay, window, "explorer", "action", name="open_all", path="", paths=["a.py", "tests/test_a.py"])
    assert last(relay) == ("open", {"path": ["a.py", "tests/test_a.py"], "app": "vs"})
    press(relay, window, "changes", "action", name="open_default", path="a.py", paths=["a.py"])
    assert last(relay) == ("open", {"path": ["a.py"], "app": "default"})


def test_the_project_menu_and_the_run_target(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "explorer", "action", name="project_build", path="Calc", paths=["Calc"], project="Calc")
    assert last(relay) == ("build", {"project": "Calc"})
    press(relay, window, "explorer", "action", name="project_test", path="CalcTest", paths=["CalcTest"], project="CalcTest")
    assert last(relay) == ("test", {"project": "CalcTest"}) and nodes(relay, window)["out"]["props"]["kind"] == "test"
    # ▶ の対象にする（ツールバーの ▾ でも選べる）・実行時の引数
    press(relay, window, "explorer", "action", name="run_target", path="CalcApp", paths=["CalcApp"], project="CalcApp")
    press(relay, window, "toolbar", "action", name="run_args", value="--size 3")
    toolbar = nodes(relay, window)["toolbar"]["props"]
    assert toolbar["run_project"] == "CalcApp" and toolbar["run_args"] == "--size 3"
    press(relay, window, "toolbar", "action", name="run")
    assert last(relay) == ("run", {"project": "CalcApp", "arguments": "--size 3"})
    press(relay, window, "toolbar", "action", name="build")
    assert last(relay) == ("build", {"project": "CalcApp"})
    press(relay, window, "toolbar", "action", name="run_target", value="")  # すべての Project に戻す
    press(relay, window, "toolbar", "action", name="build")
    assert last(relay) == ("build", {})
    for name, screen in (("project_move", "mod-cpp-project-move"), ("project_remove", "mod-cpp-project-remove"),
                         ("project_settings", "mod-cpp-project-settings")):
        press(relay, window, "explorer", "action", name=name, path="Calc", paths=["Calc"], project="Calc")
        assert [w["args"]["name"] for w in relay.display.windows() if w["screen"] == screen] == ["Calc"]
    press(relay, window, "explorer", "action", name="sln", path="", paths=[])
    assert last(relay) == ("project update", {})


def test_the_conflicts_screen_starts_from_the_file_and_opens_tortoisegit(relay):
    window = opened(relay, "workspace", PLACE)
    press(relay, window, "explorer", "action", name="resolve", path="a.py", paths=["a.py"])
    conflicts = next(w for w in relay.display.windows() if w["screen"] == "conflicts")
    assert conflicts["args"] == {"module": PLACE, "path": "a.py"} and nodes(relay, conflicts["id"])["conflict"]["props"]["first"] == "a.py"
    press(relay, conflicts["id"], "conflict", "tortoise", path="a.py")
    assert relay.backend.calls[-1] == ("diff", {"paths": ["a.py"], "gui": True})


def test_the_log_menu_greys_going_back_off_a_task_branch(relay):
    relay.backend.status.update(task=None, branch="main")
    window = opened(relay, "workspace", PLACE)
    assert nodes(relay, window)["log:list"]["props"]["status"]["branch"] == "main"  # 戻す操作は、部品が灰色と理由にする


def test_the_window_title_is_the_module_and_the_branch(relay):
    window = opened(relay, "workspace", PLACE)
    assert next(w["title"] for w in relay.display.windows() if w["id"] == window) == "Calc — task/12-login"
    # モジュールの窓の中に置いたとき：外の窓（frame-workspace）の題のつなぎが使われる（メニューの「Calc — ECOBuild」ではない）
    frame = opened(relay, "frame-workspace", "C:/work/Calc", space=PLACE)
    assert next(w["title"] for w in relay.display.windows() if w["id"] == frame) == "Calc — task/12-login"


def test_several_files_move_and_get_tests_in_one_command_and_a_new_folder_is_made_on_disk(relay):
    window = opened(relay, "workspace", PLACE)
    # 選んだものを、移動先を選んで1回で（ecobuild file move <移動元…> --into <フォルダー>）
    press(relay, window, "explorer", "action", name="move_into", path="", paths=["a.py", "b.py"])
    dialog = inside(relay, window, "ws-move-into")
    assert nodes(relay, dialog)["form"]["props"]["paths"] == ["a.py", "b.py"] and "a.py" in nodes(relay, dialog)["form"]["props"]["files"]
    press(relay, dialog, "form", "move", into="tests")
    assert last(relay) == ("file move", {"paths": ["a.py", "b.py"], "into": "tests"})
    assert nodes(relay, window)["explorer"]["props"]["moved"] == "tests"  # 移動先のフォルダーを選ぶ
    # いくつものドラッグも1回で
    press(relay, window, "explorer", "action", name="drop_move_into", path="", paths=["a.py", "new.txt"], to=".")
    assert last(relay) == ("file move", {"paths": ["a.py", "new.txt"], "into": "."})  # 一番上は「.」
    # テストを作成（いくつも）：確かめてから1回で（ecobuild file test <ファイル…>）。作ったものを木で選んで開く
    press(relay, window, "explorer", "action", name="make_tests", path="", paths=["Calc/src/Add.cpp", "Calc/src/Sub.cpp"])
    dialog = inside(relay, window, "ws-make-tests")
    press(relay, dialog, "make")
    assert last(relay) == ("file test", {"paths": ["Calc/src/Add.cpp", "Calc/src/Sub.cpp"]})
    # 新しいフォルダ：ディスクに作る（ecobuild file add <フォルダー> --folder）。空のフォルダーは files の folders から木へ
    press(relay, window, "explorer", "action", name="make_folder", path="docs/new", paths=["docs/new"])
    assert last(relay) == ("file add", {"paths": ["docs/new"], "folder": True})
    assert nodes(relay, window)["explorer"]["props"]["moved"] == "docs/new"
    assert nodes(relay, window)["explorer"]["props"]["folders"] == ["docs/empty"]


def test_the_parts_refuse_inputs_they_do_not_declare(relay):
    from guiframework.errors import RelayError

    window = opened(relay, "workspace", PLACE)
    for node, output, payload in (("tabs", "selected", {"tab": "other"}), ("explorer", "action", {"name": "rename", "path": "a.py"}),
                                  ("foot", "action", {"name": "delete"}), ("explorer", "selected", {"path": ""})):
        with pytest.raises(RelayError):
            relay.input(window, node, output, payload, human=True)


def test_the_scripts_of_the_parts_are_valid_modules():
    """部品の JS が、モジュールとして読めること（node があるときだけ）。"""
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("node がありません")
    parts = Path(__file__).resolve().parent.parent / "eco_gui" / "parts"
    for script in sorted(parts.glob("ws_*/part.js")) + [parts / "changes" / "part.js", parts / "output" / "part.js"]:
        done = subprocess.run([node, "--check", "--input-type=module"], input=script.read_bytes(), capture_output=True)
        assert done.returncode == 0, f"{script}: {done.stderr.decode('utf-8', 'replace')}"
