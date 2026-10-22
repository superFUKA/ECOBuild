"""入口（-C・--json の用法エラー）と、このPCの設定（本体の settings）・準備（ecobuild_bundle.tooling）。"""

import json
import os

import pytest

from ecobuild import settings
from ecobuild.results import DoctorItem
from ecobuild_bundle import tooling
from ecobuild.module_type import ModuleType
from ecobuild_cli import main


def run_main(args, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    return exit_info.value.code, capsys.readouterr()


def test_usage_errors_are_json_with_json_flag(capsys):
    code, out = run_main(["nosuch", "--json"], capsys)
    document = json.loads(out.out)
    assert code == 2 and document["error"]["code"] == "usage_error"
    code, out = run_main(["task", "commit", "--json"], capsys)
    assert code == 2 and json.loads(out.out)["error"]["message"] == "--message を指定してください。"
    code, out = run_main(["nosuch"], capsys)
    assert code == 2 and out.out == ""


def test_directory_option(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    code, out = run_main(["-C", "sub", "status", "--json"], capsys)
    document = json.loads(out.out)
    assert code == 1 and document["error"]["code"] == "not_in_module" and "sub" in document["error"]["message"]
    code, out = run_main(["-C", "nosuch", "status", "--json"], capsys)
    assert code == 2 and json.loads(out.out)["error"]["code"] == "usage_error"


def test_tool_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    assert settings.home() == tmp_path / "home" and settings.load_config() == {}
    assert settings.qualify("Calc") == "Calc"
    assert settings.set_config("owner", "my-org") == {"owner": "my-org"}
    assert settings.qualify("Calc") == "my-org/Calc" and settings.qualify("other/Calc") == "other/Calc"
    assert settings.set_config("owner", None) == {}
    with pytest.raises(Exception) as error:
        settings.set_config("nosuch", "x")
    assert error.value.code == "invalid_argument"


def test_doctor_reports_missing_tools(monkeypatch):
    """ツールが見つからなければ必須の項目がNGになり、setup が導入コマンドを示す。"""
    monkeypatch.setattr(tooling.shutil, "which", lambda name: None)
    report = tooling.doctor()
    names = {i.name: i.ok for i in report.items}
    assert names["git"] is False and names["gh"] is False and not report.ok
    setup = tooling.setup()
    assert setup.done == () and any("Git.Git" in c or "git" in c for c in setup.commands)


def test_doctor_requires_a_new_enough_git(monkeypatch):
    """git は 2.48 以上が要る（作業空間を相対パスの worktree で記録する）。古ければ NG で、Windows では winget upgrade。"""
    monkeypatch.setattr(tooling.shutil, "which", lambda name: "found")
    monkeypatch.setattr(tooling, "_run", lambda args: tooling._process.Completed(tuple(args), 0, "", ""))
    monkeypatch.setattr(tooling, "_version", lambda tool, *args: f"{tool} version 2.45.1.windows.1")
    monkeypatch.setattr(tooling, "git_version", lambda executable="git": (2, 45, 1))
    old = {i.id: i for i in tooling.doctor().items}["git"]
    assert not old.ok and old.required and "2.48 以上が要ります" in old.detail and old.fix == "install"
    if os.name == "nt":
        assert old.install == tooling.UPGRADE_GIT and ("git", list(tooling.UPGRADE_GIT)) in tooling.install_commands(
            tooling.DoctorReport((old,)))
    monkeypatch.setattr(tooling, "git_version", lambda executable="git": (2, 48, 0))
    new = {i.id: i for i in tooling.doctor().items}["git"]
    assert new.ok and new.detail == "git version 2.45.1.windows.1" and new.install == ()


def test_git_version_reads_the_version(monkeypatch):
    from ecowork import git as ecowork_git
    answer = {"text": "git version 2.45.1.windows.1\n", "code": 0}
    monkeypatch.setattr(ecowork_git._process, "run", lambda args, check=False: ecowork_git._process.Completed(
        tuple(args), answer["code"], answer["text"], ""))
    assert ecowork_git.git_version() == (2, 45, 1) and ecowork_git.git_version() < ecowork_git.MINIMUM_VERSION
    answer["text"] = "git version 2.48.0\n"
    assert ecowork_git.git_version() >= ecowork_git.MINIMUM_VERSION
    answer["code"] = 1
    assert ecowork_git.git_version() == (0, 0, 0)


class ToolType(ModuleType):
    """ツールを使う型（試験用）：診断の項目・導入コマンド・設定の項目を本体に足す。"""
    name = "tool"

    @classmethod
    def doctor_items(cls):
        return [DoctorItem("thing", False, True, "見つかりません", "thing を入れてください。", "install",
                                  ("get", "thing"))]

    @classmethod
    def tool_settings(cls):
        return {"thing": "thing のパス"}


def test_types_add_tools(monkeypatch):
    """型が使うツールは、渡された型から集める（本体は型の中身を知らない）。"""
    monkeypatch.setattr(tooling.shutil, "which", lambda name: "found")
    assert "thing" not in {i.name for i in tooling.doctor().items}
    report = tooling.doctor([ToolType])
    assert {i.name: i.ok for i in report.items}["thing"] is False and not report.ok
    assert ("thing", ["get", "thing"]) in tooling.install_commands(report)
    assert "thing" not in settings.config_keys() and settings.config_keys([ToolType])["thing"] == "thing のパス"
    with pytest.raises(Exception):
        settings.set_config("thing", "x")
    assert settings.set_config("thing", "C:/thing", [ToolType])["thing"] == "C:/thing"
    assert settings.load_config()["thing"] == "C:/thing"


class OtherType(ModuleType):
    """別の型（試験用）：必須のツールが足りない。"""
    name = "other"

    @classmethod
    def doctor_items(cls):
        return [DoctorItem("CMake・コンパイラ", False, True, "見つかりません", "入れてください。", "install", ("get", "cmake"))]


def test_inside_a_module_only_its_type_is_required(monkeypatch):
    """モジュールの中では、そのモジュールの型のツールだけを必須にする（ほかの型の分は知らせるだけ）。項目には id。"""
    monkeypatch.setattr(tooling.shutil, "which", lambda name: "found")
    monkeypatch.setattr(tooling, "_run", lambda args: tooling._process.Completed(tuple(args), 0, "", ""))
    monkeypatch.setattr(tooling, "_version", lambda tool, *args: f"{tool} 1.0")
    everywhere = tooling.doctor([ToolType, OtherType])
    assert {i.id: i.required for i in everywhere.items}["other.cmake"] is True
    inside = tooling.doctor([ToolType, OtherType], module_type="tool")
    items = {i.id: i for i in inside.items}
    assert items["tool.thing"].required and not items["other.cmake"].required
    assert "型 other のモジュールで使います" in items["other.cmake"].detail
    assert {"python", "git", "gh", "gh_auth", "git_identity", "docker"} <= set(items)
    assert all(i.id for i in inside.items) and len(items) == len(inside.items)   # どの項目にも、重ならない id


def test_bundle_doctor_reads_the_module_type(tmp_path, monkeypatch):
    import ecobuild_bundle
    seen = []
    monkeypatch.setattr(tooling, "doctor", lambda types, extra, *, command, module_type: seen.append(module_type))
    (tmp_path / ".ecobuild").mkdir()
    (tmp_path / ".ecobuild" / "ecobuild.toml").write_text('format = 1\n[module]\nname = "Calc"\ntype = "python"\n',
                                                         encoding="utf-8")
    (tmp_path / "src").mkdir()
    ecobuild_bundle.doctor(path=tmp_path / "src")
    ecobuild_bundle.doctor(path=tmp_path.parent)
    assert seen == ["python", None]


def test_bundle_adds_cpp_tools():
    import ecobuild_bundle
    assert {"owner", "cmake", "ctest"} <= set(ecobuild_bundle.config_keys())


# このOSで setup が使う導入コマンド（Windows は winget、Linux は apt-get）
INSTALL = tooling.INSTALL["nt" if os.name == "nt" else "posix"]


class Answers(tooling.Questions):
    """決めておいた答え（質問の文の一部 → 答え）。聞かれた質問を覚える。"""

    def __init__(self, answers, *, interactive=True):
        self.answers, self.asked, self.shown, self.interactive = answers, [], [], interactive

    def _answer(self, prompt, default):
        self.asked.append(prompt)
        return next((v for k, v in self.answers.items() if k in prompt), default)

    def confirm(self, prompt, default=True):
        return self._answer(prompt, default)

    def ask(self, prompt, default=""):
        return self._answer(prompt, default)

    def info(self, message):
        self.shown.append(message)


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """足りないものがある手元（git・gh・ログイン・名前とメール）。導入・ログインすると直る。"""
    state = {"git": False, "gh": False, "login": False, "scope": False, "setup-git": False, "identity": False}
    calls = {"interactive": [], "identity": [], "environment": []}

    def doctor(types=(), extra=(), *, command=""):
        items = [DoctorItem("git", state["git"], True, "", "", "install"),
                 DoctorItem("gh", state["gh"], True, "", "", "install")]
        if state["gh"]:
            items.append(DoctorItem("gh の認証", state["login"], True, "", "", "login"))
            if state["login"]:
                items.append(DoctorItem("ボードの権限（GitHub Projects）", state["scope"], False, "", "", "scope"))
                items.append(DoctorItem("git の認証（gh）", state["setup-git"], False, "", "", "setup-git"))
        if state["git"]:
            items.append(DoctorItem("git の名前・メール", state["identity"], True, "", "", "identity"))
        return tooling.DoctorReport(tuple(items))

    def run_interactive(args):
        calls["interactive"].append(args)
        if args == INSTALL["git"]:
            state["git"] = True
        elif args == INSTALL["gh"]:
            state["gh"] = True
        elif args[:3] == ["gh", "auth", "login"]:
            state["login"] = state["scope"] = True
        return True

    def setup_git():
        state["setup-git"] = True
        return True

    def set_identity(name="", email=""):
        calls["identity"].append((name, email))
        state["identity"] = True
        return [f"gitの名前を {name} にしました"] if name else []

    def run(args):
        if args[:3] == ["gh", "api", "user"]:
            return tooling._process.Completed(tuple(args), 0, json.dumps(
                {"login": "fuka", "id": 7, "name": None, "email": None}), "")
        return tooling._process.Completed(tuple(args), 0, "", "")      # git config --get は空

    monkeypatch.setattr(tooling, "doctor", doctor)
    monkeypatch.setattr(tooling, "run_interactive", run_interactive)
    monkeypatch.setattr(tooling, "setup_git", setup_git)
    monkeypatch.setattr(tooling, "set_identity", set_identity)
    monkeypatch.setattr(tooling, "_run", run)
    monkeypatch.setattr(tooling, "refresh_path", lambda: None)
    monkeypatch.setattr(tooling, "persist_environment",
                        lambda name, value: calls["environment"].append((name, value)) or True)
    monkeypatch.setattr(tooling, "default_home", lambda: tmp_path / "default")
    monkeypatch.setattr(settings, "default_home", lambda: tmp_path / "default")
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "old"))
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "config.toml").write_text('owner = "my-org"\n', encoding="utf-8")
    return state, calls, tmp_path


def test_initialize_asks_and_fixes_everything(machine):
    state, calls, tmp_path = machine
    answers = Answers({"設定を置くディレクトリ": str(tmp_path / "new"), "既定の所有者": ""})
    report = tooling.initialize(answers)
    assert report.home == (tmp_path / "new").resolve() and report.remaining == ()
    assert (tmp_path / "new" / "config.toml").is_file()                     # 前の設定を写した
    assert calls["environment"] == [("ECOBUILD_HOME", str((tmp_path / "new").resolve()))]
    assert calls["interactive"][:2] == [INSTALL["git"], INSTALL["gh"]]
    assert calls["interactive"][2][:3] == ["gh", "auth", "login"] and "project" in calls["interactive"][2]
    assert state["setup-git"] and calls["identity"] == [("fuka", "7+fuka@users.noreply.github.com")]
    assert settings.load_config() == {}                                      # 所有者は空にした
    assert any("既定の所有者の設定を消しました" in d for d in report.done)


def test_initialize_keeps_what_is_declined(machine):
    state, calls, tmp_path = machine
    answers = Answers({" ".join(INSTALL["gh"]): False, "既定の所有者": "my-org"})
    report = tooling.initialize(answers)
    assert report.home == tmp_path / "old" and calls["environment"] == []   # 置き場所は今のまま
    assert "gh の導入" in report.skipped and not any(a.startswith("GitHub にログイン") for a in answers.asked)
    assert [i.name for i in report.remaining if i.required] == ["gh"]
    assert settings.load_config() == {"owner": "my-org"}


def test_initialize_without_terminal_skips_login(machine):
    state, calls, tmp_path = machine
    state.update(git=True, gh=True)
    report = tooling.initialize(Answers({}, interactive=False))
    assert calls["interactive"] == [] and any("ブラウザでの操作" in s for s in report.skipped)
    assert [i.name for i in report.remaining if i.required] == ["gh の認証"]


def test_set_home_back_to_default_removes_the_variable(machine):
    state, calls, tmp_path = machine
    tooling.set_home(tmp_path / "default")
    assert calls["environment"] == [("ECOBUILD_HOME", None)] and settings.home() == tmp_path / "default"
    assert (tmp_path / "default" / "config.toml").is_file()
