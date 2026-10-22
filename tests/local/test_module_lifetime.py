"""同じ Module を使い続けるときの、設定の読み直しと準備の対象（CODE_REVIEW.md の R2・R3）。"""

import dataclasses
import sys

import pytest

from fakes import FakeGitHub
from ecobuild import config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import Module
from ecobuild_cpp.type import CppType
from ecobuild.results import PrepareResult

pytestmark = pytest.mark.local


def python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_config_is_reloaded_after_switching(tmp_path):
    """main で取得した Module のまま、コマンドを書いたタスクブランチへ切り替えてもビルドできる。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    first = module.repository.create_task("コマンドを書く").start()
    commands = {"build": python("print('built')"), "test": "", "run": "", "clean": ""}
    module._save_config(dataclasses.replace(module.config, default_base="develop",
                                            extra={**module.config.extra, "commands": commands}))
    first.stage(config.FILE_NAME)
    first.commit("コマンド")

    module.repository.create_task("別の作業").start(base="main")   # main から：コマンドなし
    assert module.config.extra["commands"]["build"] == ""
    assert module.repository.default_base == "main"
    with pytest.raises(EcoBuildError) as error:
        module.build()
    assert error.value.code == ErrorCode.NOT_SUPPORTED

    module.repository.task(first.number).start()                   # 戻ると、そのタスクブランチの設定を読み直す
    assert module.build().configuration == "Debug"
    assert module.repository.default_base == "develop"


def test_workspace_prepares_only_itself(module, tmp_path, monkeypatch):
    """タスクを作業空間（元の clone の中の .ecobuild/w/<番号>）で始めるとき、型の準備（依存先・生成ファイル）は作業空間
    だけで行う。元の clone のブランチは変えない。このPC用の設定（ecobuild.local.toml）は元の clone のものを写す。"""
    prepared = []

    def prepare(self):
        prepared.append(self.module.root)
        return PrepareResult((), False)

    monkeypatch.setattr(CppType, "prepare", prepare)
    config.save_local(module.root, {"profile": "Release"})
    task = module.repository.create_task("並行作業")
    other = module.start_task(task.number)
    assert other.root == module.root / ".ecobuild" / "w" / str(task.number)
    assert other.repository.current_task_branch().number == task.number and other.workspace_root == module.root
    assert prepared and set(prepared) == {other.root}
    assert module.repository.current_task_branch() is None and module.repository.git.current_branch() == "main"
    assert config.load_local(other.root) == {"profile": "Release"}
    assert module.start_task(task.number).root == other.root      # 既にあれば、その作業空間を返す
