"""型 generic：[commands] に書いたコマンドでビルド・テスト・実行する。本体と型の境目を確かめる2つ目の型。"""

import sys

import pytest

from fakes import FakeGitHub
from ecobuild import config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecowork import WorkError
from ecobuild.module import Module

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_generic_module(tmp_path):
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    root = module.root
    assert sorted(p.name for p in root.iterdir() if p.name != ".git") == [
        ".gitignore", "AGENTS.md", "README.md", "ecobuild.toml"]
    assert module.config.projects is None and module.project_names == ()
    assert code_of(lambda: Module.create("X", directory=tmp_path, type="generic", app=True,
                                         github=FakeGitHub(tmp_path / "gh2"))) == ErrorCode.INVALID_ARGUMENT

    # コマンドを書くまでは対応しない
    assert code_of(module.build) == ErrorCode.NOT_SUPPORTED
    assert code_of(module.projects) == ErrorCode.NOT_SUPPORTED
    assert code_of(lambda: module.link("STL")) == ErrorCode.NOT_IN_WORKSPACE

    workspace = module.create_task("コマンドを書く").start()
    commands = {"build": python("print('built {configuration}')"), "test": python("print('tested')"),
                "run": python("import sys; print('run {arguments}')"), "clean": ""}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    reloaded = Module.find(root, github=module.repository.github)
    assert reloaded.config.extra["commands"]["test"] == commands["test"]  # ecobuild.toml に書き戻せる

    assert reloaded.build(configuration="Release").configuration == "Release"
    assert reloaded.test().passed == 1
    assert reloaded.run(arguments="a b").output.strip() == "run a b"
    assert code_of(lambda: reloaded.build(action="clean")) == ErrorCode.NOT_SUPPORTED  # clean は空
    assert reloaded.build(action="rebuild").action == "rebuild"  # clean がなければビルドだけ
    assert [(i.name, i.ok) for i in reloaded.check().items] == [
        ("generated", True), ("conflict_markers", True), ("build", True), ("test", True)]

    failing = {**commands, "test": python("import sys; sys.exit(3)")}
    reloaded._save_config(config.ModuleConfig(**{**reloaded.config.__dict__, "extra": {"commands": failing}}))
    with pytest.raises(EcoBuildError) as error:
        reloaded.test()
    assert error.value.code == ErrorCode.TEST_FAILED and error.value.details["returncode"] == 3

    ci = reloaded.write_ci()
    workflow = (root / ci.path).read_text(encoding="utf-8")
    assert "ubuntu-latest" in workflow and "Build" in workflow and "workflow_dispatch" in workflow
    assert code_of(lambda: reloaded.add_file("a.txt")) == ErrorCode.NOT_SUPPORTED
    workspace.stage(all=True)
    workspace.commit("コマンドとCI")
    assert workspace.submit().number


def test_check_is_reused_while_unchanged(tmp_path):
    """ビルド・テストを含む check を通った版は、task submit --check で繰り返さない。変更・コミットで無効になる。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    workspace = module.create_task("確認の使い回し").start()
    commands = {"build": python("print('built')"), "test": python("print('tested')")}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    module.check()
    assert not module.checked()  # 変更が残っている（コミット前）
    workspace.stage(all=True)
    workspace.commit("コマンド")
    assert not module.checked()  # コミットした版はまだ確かめていない
    module.check()
    assert module.checked()
    module.check(build=False)
    assert not module.checked()  # ビルド・テストを省いた確認は記録しない

    module.check()
    (module.root / "note.txt").write_text("作業中\n", encoding="utf-8")
    assert not module.checked()
    (module.root / "note.txt").unlink()
    assert module.checked()
    failing = {**commands, "test": python("import sys; sys.exit(3)")}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": failing}}))
    workspace.stage(all=True)
    workspace.commit("失敗するテスト")
    with pytest.raises(EcoBuildError):
        module.check()
    assert not module.checked()
