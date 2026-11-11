"""eco_gui のモジュールのページ（概要・ブランチ・履歴・CI・パイプライン・メンバー）：
読んだものが部品へ届くこと、押した操作が、人が打つのと同じ ecobuild のコマンドを呼ぶこと。

ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402

BRANCHES = [
    {"name": "main", "is_task_branch": False, "base": None, "local": True, "remote": True, "submission": None, "submitted_to": None,
     "unusable": None, "merged": None, "format": 5, "latest_format": 5},
    {"name": "feature/mvp", "is_task_branch": False, "base": "main", "local": True, "remote": True, "submission": None, "submitted_to": None,
     "unusable": None, "merged": False, "format": 5, "latest_format": 5},
    {"name": "task/12-login", "is_task_branch": True, "base": "feature/mvp", "local": True, "remote": True,
     "submission": {"number": 40, "state": "open", "draft": False}, "submitted_to": None, "unusable": None, "merged": False},
]
RUNS = [
    {"id": 901, "workflow": "ecobuild", "branch": "main", "event": "push", "status": "completed", "conclusion": "failure",
     "created": "2026-11-10T09:00:00Z", "url": "https://github.com/octocat/Calc/actions/runs/901"},
    {"id": 902, "workflow": "ecobuild", "branch": "feature/mvp", "event": "pull_request", "status": "in_progress", "conclusion": None,
     "created": "2026-11-10T10:00:00Z", "url": "https://github.com/octocat/Calc/actions/runs/902"},
]


class FakeModule(FakeEcobuild):
    """モジュールのページのコマンドを足した、ecobuild の代わり。"""

    def __init__(self):
        super().__init__()
        self.readme = {"path": "README.md", "text": "# Calc\n\n足し算をします。\n", "truncated": False}
        self.secrets = ["ECOBUILD_DEPS_TOKEN"]

    def _specs(self, text):
        number = {"type": "integer"}
        flag = {"type": "boolean"}

        def spec(weight, properties=None, required=()):
            return {"description": "モジュール", "weight": weight,
                    "args": {"type": "object", "required": list(required), "properties": dict(properties or {})}}

        return {
            **super()._specs(text),
            "task list": spec("read", {"submitted": flag}),
            "module protection": spec("read"),
            "module protect": spec("confirm", {"approvals": number, "require_ci": flag, "off": flag}),
            "module readme": spec("read"),
            "log": spec("read", {"count": number, "all": flag, "gui": flag, "branch": text}),
            "show": spec("read", {"commit": text, "stat": flag}),
            "ci show": spec("read"),
            "ci status": spec("read", {"all": flag, "branch": text, "count": number}),
            "ci logs": spec("read", {"run": number}),
            "ci rerun": spec("change", {"run": number, "failed": flag}),
            "ci run": spec("change", {"branch": text}),
            "ci init": spec("change", {"os": text, "configuration": text, "shared": text, "branches": text, "force": flag}),
            "ci remove": spec("confirm"),
            "ci secret list": spec("read"),
            "ci secret remove": spec("confirm", {"name": text}, ["name"]),
            "pipeline add": spec("change", {"name": text, "steps": text, "tests": text}, ["name"]),
            "pipeline on": spec("change", {"timing": text, "names": text, "local": flag}, ["timing", "names"]),
            "module members add": spec("confirm", {"user": text, "role": text}, ["user"]),
        }

    def run(self, name, args, context, on_event):
        given = {key: value for key, value in args.items() if key != "module"}
        answers = {
            "branch list": [dict(branch) for branch in BRANCHES],
            "task list": [{"number": 12, "title": "ログイン画面", "submission": {"number": 40, "state": "open", "draft": False, "base": "feature/mvp"}}],
            "account show": {"login": "superFUKA", "role": "admin", "admin": True, "owner": "superFUKA", "owner_type": "User",
                             "default_base": "main", "creators": {"feature/mvp": "octocat"}},
            "module protection": {"branch": "main", "approvals": 1, "checks": ["build"]},
            "module readme": self.readme,
            "module show": {"name": "Calc", "type": "python", "root": "C:/work/Calc", "repository": "octocat/Calc",
                            "url": "https://github.com/octocat/Calc", "private": True, "archived": False, "default_base": "main",
                            "projects": [], "dependencies": [], "format": 5, "latest_format": 5, "workspaces": [
                                {"name": "12", "path": "C:/work/Calc/.ecobuild/w/12", "branch": "task/12-login", "task": 12}]},
            "ci show": {"path": ".github/workflows/ecobuild.yml", "supported": True, "exists": True, "edited": False, "current": True,
                        "os": ["linux"], "configurations": ["Debug", "Release"], "shared": False, "branches": None, "default_base": "main"},
            "ci status": [run for run in RUNS if not given.get("branch") or run["branch"] == given["branch"]],
            "ci logs": {"log": "失敗した手順の出力"},
            "ci secret list": list(self.secrets),
            "pipeline list": {"pipelines": [{"name": "check", "steps": ["generated", "build", "test"], "tests": ["tests/unit"]},
                                            {"name": "quick", "steps": ["conflict_markers"], "tests": []}],
                              "triggers": {"before-submit": ["check"]}, "local": {"before-commit": ["quick"]}},
            "log": [{"sha": "abc1234def", "subject": "最初", "author": "octocat", "date": "2026-11-01T10:00:00+09:00", "pull_request": 7, "issue": 6}],
        }
        if name in answers:
            super().run(name, args, context, on_event)
            return {"ok": True, "result": answers[name]}
        if name == "show" and given.get("stat"):
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"files": [{"path": "src/app.py", "status": "M", "added": 3, "deleted": 1, "eol_only": False}]}}
        if name == "ci secret remove":
            self.secrets = [secret for secret in self.secrets if secret != given["name"]]
        return super().run(name, args, context, on_event)


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeModule(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def open_screen(relay, screen, **args):
    window = relay.execute({"command": "open", "screen": screen, "args": {"module": "C:/work/Calc", **args}})["window"]
    relay.idle()
    return window


def inside(relay, screen):
    """中に重ねて開いた窓（入力の窓）。"""
    return next(w["id"] for w in relay.display.windows() if w["screen"] == screen)


# --- ブランチ ---------------------------------------------------------------
def test_branches_show_the_tree_and_the_detail_of_the_selected_branch(relay):
    window = open_screen(relay, "branches")
    view = nodes(relay, window)
    assert [b["name"] for b in view["tree"]["props"]["branches"]] == ["main", "feature/mvp", "task/12-login"]
    assert view["tree"]["props"]["default_base"] == "main" and view["tree"]["props"]["submissions"][0]["submission"]["base"] == "feature/mvp"
    assert ("task list", {"submitted": True}) in relay.backend.calls  # 届いている提出の件数は、提出中のタスクから
    assert view["detail"]["props"]["creators"] == {"feature/mvp": "octocat"}
    assert view["detail"]["props"]["protection"] == {"branch": "main", "approvals": 1, "checks": ["build"]}
    relay.input(window, "tree", "selected", {"name": "feature/mvp"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["tree"]["props"]["selected"] == "feature/mvp" and view["detail"]["props"]["selected"] == "feature/mvp"


def test_branch_actions_run_the_same_commands_a_person_types(relay):
    window = open_screen(relay, "branches")
    relay.input(window, "detail", "action", {"action": "delete", "name": "feature/mvp"}, human=True)
    answer(relay, window, False)  # 消すのは、確かめてから
    assert ("branch delete", {"name": "feature/mvp"}) not in relay.backend.calls
    relay.input(window, "detail", "action", {"action": "delete", "name": "feature/mvp"}, human=True)
    answer(relay, window, True)
    assert ("branch delete", {"name": "feature/mvp"}) in relay.backend.calls
    relay.input(window, "detail", "action", {"action": "unprotect", "name": "main"}, human=True)
    answer(relay, window, True)
    assert ("module protect", {"off": True}) in relay.backend.calls
    relay.input(window, "log", "pressed", {}, human=True)
    relay.idle()
    assert ("log", {"all": True, "gui": True}) in relay.backend.calls
    relay.input(window, "detail", "action", {"action": "task", "name": "feature/mvp", "task": 12}, human=True)
    relay.idle()
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "task"] == [{"module": "C:/work/Calc", "issue": 12}]
    relay.input(window, "detail", "action", {"action": "merge", "name": "feature/mvp"}, human=True)  # 取り込み・提出の画面へ（同じ窓）
    relay.idle()
    assert relay.display.tree(window)["screen"] == "merge" and relay.display.tree(window)["args"]["name"] == "feature/mvp"


def test_a_branch_is_created_from_the_form_with_the_selected_branch_as_the_base(relay):
    window = open_screen(relay, "branches")
    relay.input(window, "tree", "selected", {"name": "feature/mvp"}, human=True)
    relay.idle()
    relay.input(window, "create", "pressed", {}, human=True)
    relay.idle()
    form = inside(relay, "mod-branch-new")
    view = nodes(relay, form)["form"]["props"]
    assert view["initial"] == {"base": "feature/mvp"} and [row["name"] for row in view["rows"]][:2] == ["main", "feature/mvp"]
    relay.input(form, "form", "submitted", {"values": {"name": "release", "base": "feature/mvp"}}, human=True)
    relay.idle()
    assert ("branch create", {"name": "release", "base": "feature/mvp"}) in relay.backend.calls
    assert not [w for w in relay.display.windows() if w["screen"] == "mod-branch-new"]  # うまくいったら閉じる
    relay.input(window, "create", "pressed", {}, human=True)
    relay.idle()
    form = inside(relay, "mod-branch-new")
    relay.input(form, "form", "submitted", {"values": {"name": "hotfix", "base": ""}}, human=True)  # 作成元を選ばない：既定
    relay.idle()
    assert ("branch create", {"name": "hotfix"}) in relay.backend.calls


# --- CI ---------------------------------------------------------------------
def test_ci_shows_the_settings_the_runs_and_the_secrets(relay):
    window = open_screen(relay, "ci")
    view = nodes(relay, window)
    assert view["config"]["props"]["data"]["current"] is True and view["config"]["props"]["data"]["os"] == ["linux"]
    assert [run["id"] for run in view["runs"]["props"]["rows"]] == [901, 902] and ("ci status", {"all": True, "count": 30}) in relay.backend.calls
    assert view["runs"]["props"]["url"] == "https://github.com/octocat/Calc" and view["runs"]["props"]["branch_rows"] == []
    assert view["secrets"]["props"]["names"] == ["ECOBUILD_DEPS_TOKEN"]
    assert not [call for call in relay.backend.calls if call[0] == "ci status" and "branch" in call[1]]  # 絞るまで、ブランチの実行は読まない
    relay.input(window, "runs", "branch", {"name": "main"}, human=True)  # ブランチで絞る
    relay.idle()
    view = nodes(relay, window)
    assert ("ci status", {"branch": "main", "count": 30}) in relay.backend.calls
    assert view["runs"]["props"]["branch"] == "main" and [run["id"] for run in view["runs"]["props"]["branch_rows"]] == [901]
    relay.input(window, "runs", "branch", {"name": ""}, human=True)  # すべてに戻す
    relay.idle()
    assert nodes(relay, window)["runs"]["props"]["branch_rows"] == []


def test_ci_rows_open_the_log_and_run_again(relay):
    window = open_screen(relay, "ci")
    relay.input(window, "runs", "action", {"action": "logs", "run": 901}, human=True)
    relay.idle()
    log = inside(relay, "mod-ci-log")
    assert nodes(relay, log)["log"]["props"]["text"] == "失敗した手順の出力" and ("ci logs", {"run": 901}) in relay.backend.calls
    relay.input(log, "close", "pressed", {}, human=True)
    relay.idle()
    relay.input(window, "runs", "action", {"action": "rerun", "run": 901}, human=True)
    relay.idle()
    assert ("ci rerun", {"run": 901}) in relay.backend.calls
    relay.input(window, "runs", "action", {"action": "rerun_failed", "run": 901}, human=True)
    relay.idle()
    assert ("ci rerun", {"run": 901, "failed": True}) in relay.backend.calls
    relay.input(window, "runs", "dispatch", {"branch": "main"}, human=True)  # 手動で実行：ブランチを選ぶ窓
    relay.idle()
    form = inside(relay, "mod-ci-run")
    assert nodes(relay, form)["form"]["props"]["initial"] == {"branch": "main"}
    relay.input(form, "form", "submitted", {"values": {"branch": "feature/mvp"}}, human=True)
    relay.idle()
    assert ("ci run", {"branch": "feature/mvp"}) in relay.backend.calls
    relay.input(window, "secrets", "removed", {"name": "ECOBUILD_DEPS_TOKEN"}, human=True)
    answer(relay, window, True)  # 消すのは、確かめてから
    assert ("ci secret remove", {"name": "ECOBUILD_DEPS_TOKEN"}) in relay.backend.calls and nodes(relay, window)["secrets"]["props"]["names"] == []


def test_ci_is_set_up_and_removed_in_the_chosen_workspace(relay):
    window = open_screen(relay, "ci")
    relay.input(window, "config", "action", {"action": "init", "os": "linux", "configuration": "Debug,Release", "shared": "off", "branches": ""}, human=True)
    relay.idle()
    form = inside(relay, "mod-ci-init")
    view = nodes(relay, form)["form"]["props"]
    assert view["initial"] == {"os": "linux", "configuration": "Debug,Release", "shared": "off", "branches": ""}
    assert [row["path"] for row in view["rows"]] == ["C:/work/Calc/.ecobuild/w/12"]  # 作り直す場所は、タスクブランチの作業空間から選ぶ
    relay.input(form, "form", "submitted", {"values": {"place": "C:/work/Calc/.ecobuild/w/12", "os": "windows,linux", "configuration": "Release",
                                                       "shared": "on", "branches": "", "force": False}}, human=True)
    relay.idle()
    call = ("ci init", {"os": "windows,linux", "configuration": "Release", "shared": "on", "force": False})
    assert relay.backend.modules[relay.backend.calls.index(call)] == "C:/work/Calc/.ecobuild/w/12"  # 選んだ作業空間で実行する
    relay.input(window, "config", "action", {"action": "remove"}, human=True)
    relay.idle()
    form = inside(relay, "mod-ci-remove")
    relay.input(form, "form", "submitted", {"values": {"place": "C:/work/Calc/.ecobuild/w/12"}}, human=True)
    answer(relay, form, True)
    assert relay.backend.modules[relay.backend.calls.index(("ci remove", {}))] == "C:/work/Calc/.ecobuild/w/12"


# --- 概要 -------------------------------------------------------------------
def test_overview_shows_the_readme_and_what_the_module_is(relay):
    window = open_screen(relay, "overview")
    view = nodes(relay, window)
    assert view["readme"]["props"]["readme"] == {"path": "README.md", "text": "# Calc\n\n足し算をします。\n", "truncated": False}
    assert ("module readme", {}) in relay.backend.calls and relay.backend.modules[-1] == "C:/work/Calc"
    assert view["about"]["props"]["data"]["repository"] == "octocat/Calc" and view["about"]["props"]["data"]["private"] is True
    assert [row["task"] for row in view["spaces"]["props"]["rows"]] == [12]
    relay.backend.readme = None  # README のないモジュール
    relay.input(window, "reload", "pressed", {}, human=True)
    relay.idle()
    assert nodes(relay, window)["readme"]["props"]["readme"] is None
    relay.input(window, "about", "opened", {"page": "tasks"}, human=True)  # 「タスク管理を開く」：同じ窓で切り替える
    relay.idle()
    assert relay.display.tree(window)["screen"] == "tasks" and relay.display.tree(window)["args"] == {"module": "C:/work/Calc"}


# --- パイプライン -----------------------------------------------------------
def test_pipelines_show_the_cards_and_the_timings_and_run_one(relay):
    window = open_screen(relay, "pipelines")
    view = nodes(relay, window)
    assert [p["name"] for p in view["list"]["props"]["data"]["pipelines"]] == ["check", "quick"]
    assert view["timings"]["props"]["data"]["triggers"] == {"before-submit": ["check"]} and view["timings"]["props"]["data"]["local"] == {"before-commit": ["quick"]}
    relay.input(window, "list", "action", {"action": "run", "name": "check"}, human=True)
    relay.idle()
    assert ("pipeline run", {"name": "check"}) in relay.backend.calls
    assert not [call for call in relay.backend.calls if call[0] in ("pipeline remove", "pipeline add")]  # 押したボタンのコマンドだけ


def test_pipelines_are_made_changed_and_removed_in_the_chosen_workspace(relay):
    window = open_screen(relay, "pipelines")
    place = "C:/work/Calc/.ecobuild/w/12"
    relay.input(window, "list", "action", {"action": "edit", "name": "check", "steps": "generated,build,test", "tests": "tests/unit"}, human=True)
    relay.idle()
    form = inside(relay, "mod-pipeline-edit")
    assert nodes(relay, form)["form"]["props"]["initial"] == {"name": "check", "steps": "generated,build,test", "tests": "tests/unit"}
    relay.input(form, "form", "submitted", {"values": {"place": place, "name": "check", "steps": "build,test", "tests": ""}}, human=True)
    relay.idle()
    call = ("pipeline add", {"name": "check", "steps": "build,test"})  # 空の試験は渡さない
    assert relay.backend.modules[relay.backend.calls.index(call)] == place
    relay.input(window, "list", "action", {"action": "add"}, human=True)  # 作る：空から
    relay.idle()
    form = inside(relay, "mod-pipeline-edit")
    assert nodes(relay, form)["form"]["props"]["initial"] == {"name": "", "steps": "", "tests": ""}
    relay.input(form, "form", "cancelled", {}, human=True)
    relay.idle()
    assert not [w for w in relay.display.windows() if w["screen"] == "mod-pipeline-edit"]
    relay.input(window, "list", "action", {"action": "remove", "name": "check", "used": "今、当てているタイミング：提出の前"}, human=True)
    relay.idle()
    form = inside(relay, "mod-pipeline-remove")
    assert nodes(relay, form)["form"]["props"]["subject"] == "check" and "提出の前" in nodes(relay, form)["form"]["props"]["detail"]
    relay.input(form, "form", "submitted", {"values": {"place": place}}, human=True)
    relay.idle()
    assert relay.backend.modules[relay.backend.calls.index(("pipeline remove", {"name": "check"}))] == place


def test_pipeline_timings_are_changed_for_the_module_or_only_on_this_pc(relay):
    window = open_screen(relay, "pipelines")
    place = "C:/work/Calc/.ecobuild/w/12"
    relay.input(window, "timings", "changed", {"timing": "before-submit", "local": False, "names": "check", "label": "提出の前"}, human=True)
    relay.idle()
    form = inside(relay, "mod-pipeline-timing")
    view = nodes(relay, form)["form"]["props"]
    assert view["subject"] == "提出の前" and view["initial"] == {"names": "check"} and [p["name"] for p in view["more"]] == ["check", "quick"]
    relay.input(form, "form", "submitted", {"values": {"place": place, "names": "check,quick"}}, human=True)
    relay.idle()
    call = ("pipeline on", {"timing": "before-submit", "names": "check,quick"})
    assert relay.backend.modules[relay.backend.calls.index(call)] == place  # モジュールの当て方は、タスクブランチの作業空間で
    relay.input(window, "timings", "changed", {"timing": "before-commit", "local": True, "names": "quick", "label": "コミットの前"}, human=True)
    relay.idle()
    form = inside(relay, "mod-pipeline-local")
    relay.input(form, "form", "submitted", {"values": {"names": "none"}}, human=True)  # 1つも選ばない：外す
    relay.idle()
    call = ("pipeline on", {"timing": "before-commit", "names": "none", "local": True})
    assert relay.backend.modules[relay.backend.calls.index(call)] == "C:/work/Calc"  # この PC だけの分は、その場で


# --- メンバー ---------------------------------------------------------------
def test_members_show_the_account_and_invite_change_and_remove(relay):
    window = open_screen(relay, "members")
    view = nodes(relay, window)
    assert view["members"]["props"]["account"]["login"] == "superFUKA" and view["members"]["props"]["account"]["role"] == "admin"
    assert [m["login"] for m in view["members"]["props"]["members"]] == ["octocat", "hubot"]
    relay.input(window, "members", "action", {"action": "invite", "organization": False}, human=True)
    relay.idle()
    form = inside(relay, "mod-member-invite")
    relay.input(form, "form", "submitted", {"values": {"user": "newbie", "role": ""}}, human=True)
    answer(relay, form, True)  # 招待は、確かめてから（ほかの人に届く）
    assert ("module members add", {"user": "newbie"}) in relay.backend.calls  # 役割を選ばなければ、渡さない
    relay.input(window, "members", "action", {"action": "role", "login": "octocat", "role": "write", "organization": True}, human=True)
    relay.idle()
    form = inside(relay, "mod-member-role")
    assert nodes(relay, form)["form"]["props"]["subject"] == "octocat" and nodes(relay, form)["form"]["props"]["initial"] == {"role": "write"}
    relay.input(form, "form", "submitted", {"values": {"role": "admin"}}, human=True)
    answer(relay, form, True)
    assert ("module members add", {"user": "octocat", "role": "admin"}) in relay.backend.calls
    relay.input(window, "members", "action", {"action": "remove", "login": "octocat"}, human=True)
    answer(relay, window, False)
    assert ("module members remove", {"user": "octocat"}) not in relay.backend.calls
    relay.input(window, "members", "action", {"action": "remove", "login": "octocat"}, human=True)
    answer(relay, window, True)
    assert ("module members remove", {"user": "octocat"}) in relay.backend.calls
    assert [m["login"] for m in nodes(relay, window)["members"]["props"]["members"]] == ["hubot"]  # 変えたら読み直す


# --- 履歴 -------------------------------------------------------------------
def test_history_lists_the_commits_of_a_branch_and_shows_the_selected_one(relay):
    window = open_screen(relay, "history")
    view = nodes(relay, window)
    assert view["log"]["props"]["rows"][0]["sha"] == "abc1234def" and ("log", {"count": 50}) in relay.backend.calls
    assert not [call for call in relay.backend.calls if call[0] == "show"] and view["detail"]["props"]["text"] == ""  # 選ぶまで、読まない
    relay.input(window, "log", "selected", {"sha": "abc1234def"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["log"]["props"]["selected"] == "abc1234def" and view["detail"]["props"]["text"].startswith("commit abc1234def")
    relay.input(window, "log", "branch", {"name": "feature/mvp"}, human=True)  # ブランチを変える：選択は空に戻る
    relay.idle()
    view = nodes(relay, window)
    assert ("log", {"count": 50, "branch": "feature/mvp"}) in relay.backend.calls
    assert view["log"]["props"]["branch"] == "feature/mvp" and view["log"]["props"]["selected"] is None and view["detail"]["props"]["text"] == ""
    relay.input(window, "graph", "pressed", {}, human=True)
    relay.idle()
    assert ("log", {"all": True, "gui": True}) in relay.backend.calls


# --- 部品 -------------------------------------------------------------------
def test_the_parts_of_the_module_pages_are_defined_with_samples():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeModule(), roles={"confirm": "confirm-box"})
    parts = app.relay(threaded=True).parts
    for name in ("mod-branch-tree", "mod-branch-detail", "mod-form", "mod-ci-config", "mod-runs", "mod-secrets", "mod-readme", "mod-about",
                 "mod-pipeline-cards", "mod-timings", "mod-members", "mod-commits", "mod-commit-files"):
        assert name in parts and parts[name].samples
    # シークレットの値を入れる欄は作らない（登録は端末で）
    assert "value" not in parts["mod-secrets"].inputs["properties"] and list(parts["mod-secrets"].outputs) == ["removed"]
