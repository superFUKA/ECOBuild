"""同じ Module を使い続けるときの、設定の読み直しと準備の対象（CODE_REVIEW.md の R2・R3）。"""

import dataclasses
import sys

import pytest

from fakes import FakeGitHub
from ecobuild import config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module import Module
from ecobuild_cpp.type import CppType
from ecobuild.results import PrepareResult

pytestmark = pytest.mark.local


def python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_config_is_reloaded_after_switching(tmp_path):
    """main で取得した Module のまま、コマンドを書いた作業空間へ切り替えてもビルドできる。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    first = module.create_task("コマンドを書く").start()
    commands = {"build": python("print('built')"), "test": "", "run": "", "clean": ""}
    module._save_config(dataclasses.replace(module.config, default_base="develop",
                                            extra={**module.config.extra, "commands": commands}))
    first.stage(config.FILE_NAME)
    first.commit("コマンド")

    module.create_task("別の作業").start(base="main")   # main から：コマンドなし
    assert module.config.extra["commands"]["build"] == ""
    assert module.repository.default_base == "main"
    with pytest.raises(EcoBuildError) as error:
        module.build()
    assert error.value.code == ErrorCode.NOT_SUPPORTED

    module.task(first.number).start()                   # 戻ると、その作業空間の設定を読み直す
    assert module.build().configuration == "Debug"
    assert module.repository.default_base == "develop"


def test_dedicated_clone_prepares_only_the_clone(module, tmp_path, monkeypatch):
    """専用のcloneで作業空間を作るとき、型の準備（依存先・生成ファイル）は clone 先だけで行う。"""
    prepared = []

    def prepare(self):
        prepared.append(self.module.root)
        return PrepareResult((), False)

    monkeypatch.setattr(CppType, "prepare", prepare)
    task = module.create_task("並行作業")
    other = module.start_task_in(task.number, tmp_path / "Calc-1")
    assert other.root != module.root and other.current_workspace().number == task.number
    assert prepared and set(prepared) == {other.root}
    assert module.current_workspace() is None
