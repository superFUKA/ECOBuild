"""入口（-C・--json の用法エラー）とツールの設定・診断（範囲外の機能）。"""

import json

import pytest

from ecobuild import tooling
from ecobuild.cli import main


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
    assert tooling.home() == tmp_path / "home" and tooling.load_config() == {}
    assert tooling.qualify("Calc") == "Calc"
    assert tooling.set_config("owner", "my-org") == {"owner": "my-org"}
    assert tooling.qualify("Calc") == "my-org/Calc" and tooling.qualify("other/Calc") == "other/Calc"
    assert tooling.set_config("owner", None) == {}
    with pytest.raises(Exception) as error:
        tooling.set_config("nosuch", "x")
    assert error.value.code == "invalid_argument"


def test_doctor_reports_missing_tools(monkeypatch):
    """ツールが見つからなければ必須の項目がNGになり、setup が導入コマンドを示す。"""
    monkeypatch.setattr(tooling.shutil, "which", lambda name: None)
    monkeypatch.setattr(tooling._module_type, "available", lambda: [])
    report = tooling.doctor()
    names = {i.name: i.ok for i in report.items}
    assert names["git"] is False and names["gh"] is False and not report.ok
    setup = tooling.setup()
    assert setup.done == () and any("Git.Git" in c or "git" in c for c in setup.commands)


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

    def doctor():
        items = [tooling.CheckItem("git", state["git"], True, "", "", "install"),
                 tooling.CheckItem("gh", state["gh"], True, "", "", "install")]
        if state["gh"]:
            items.append(tooling.CheckItem("gh の認証", state["login"], True, "", "", "login"))
            if state["login"]:
                items.append(tooling.CheckItem("ボードの権限（GitHub Projects）", state["scope"], False, "", "", "scope"))
                items.append(tooling.CheckItem("git の認証（gh）", state["setup-git"], False, "", "", "setup-git"))
        if state["git"]:
            items.append(tooling.CheckItem("git の名前・メール", state["identity"], True, "", "", "identity"))
        return tooling.DoctorReport(tuple(items))

    def run_interactive(args):
        calls["interactive"].append(args)
        if "Git.Git" in args:
            state["git"] = True
        elif "GitHub.cli" in args:
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
    assert [c[3] for c in calls["interactive"][:2]] == ["Git.Git", "GitHub.cli"]
    assert calls["interactive"][2][:3] == ["gh", "auth", "login"] and "project" in calls["interactive"][2]
    assert state["setup-git"] and calls["identity"] == [("fuka", "7+fuka@users.noreply.github.com")]
    assert tooling.load_config() == {}                                      # 所有者は空にした
    assert any("既定の所有者の設定を消しました" in d for d in report.done)


def test_initialize_keeps_what_is_declined(machine):
    state, calls, tmp_path = machine
    answers = Answers({"GitHub.cli": False, "既定の所有者": "my-org"})
    report = tooling.initialize(answers)
    assert report.home == tmp_path / "old" and calls["environment"] == []   # 置き場所は今のまま
    assert "gh の導入" in report.skipped and not any(a.startswith("GitHub にログイン") for a in answers.asked)
    assert [i.name for i in report.remaining if i.required] == ["gh"]
    assert tooling.load_config() == {"owner": "my-org"}


def test_initialize_without_terminal_skips_login(machine):
    state, calls, tmp_path = machine
    state.update(git=True, gh=True)
    report = tooling.initialize(Answers({}, interactive=False))
    assert calls["interactive"] == [] and any("ブラウザでの操作" in s for s in report.skipped)
    assert [i.name for i in report.remaining if i.required] == ["gh の認証"]


def test_set_home_back_to_default_removes_the_variable(machine):
    state, calls, tmp_path = machine
    tooling.set_home(tmp_path / "default")
    assert calls["environment"] == [("ECOBUILD_HOME", None)] and tooling.home() == tmp_path / "default"
    assert (tmp_path / "default" / "config.toml").is_file()
