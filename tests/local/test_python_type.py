"""型 python：本物のgitと偽のGitHubで、作成・ファイル追加・コミットの流れ（venv・pip は使わない）。"""

import pytest

from fakes import FakeGitHub
from ecobuild.errors import ErrorCode
from ecowork import WorkError
from ecobuild_bundle import Module

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_python_module(tmp_path):
    module = Module.create("Calc", directory=tmp_path, type="python", github=FakeGitHub(tmp_path / "gh"))
    root = module.root
    assert module.config.type == "python" and module.config.projects is None
    names = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert {".ecobuild/ecobuild.toml", ".ecobuild/.gitignore", "pyproject.toml", "src/calc/__main__.py", "tests/test_calc.py", ".gitignore"} <= names
    assert ".venv/" in (root / ".gitignore").read_text(encoding="utf-8")

    # Project・依存先は持たない。ビルド等は型が受け持つ
    assert code_of(module.projects) == ErrorCode.NOT_SUPPORTED
    assert code_of(lambda: module.link("STL")) == ErrorCode.NOT_IN_WORKSPACE
    workspace = module.repository.create_task("ファイルを足す").start()
    assert code_of(lambda: module.link("STL")) == ErrorCode.NOT_SUPPORTED

    # file add で作ったファイルと、管理するファイルの既定（*.py）が commit に含まれる
    changed = module.add_file(root / "src/calc/ops.py")
    assert set(changed.paths) == {"src/calc/ops.py", "tests/test_ops.py"}
    (root / "src/calc/extra.py").write_text("X = 1\n", encoding="utf-8")   # file add を通さない新しい .py
    (root / "notes.bin").write_text("x", encoding="utf-8")                  # 管理するファイルの対象外
    committed = module.commit("ops を足す")
    assert {"src/calc/ops.py", "tests/test_ops.py", "src/calc/extra.py"} <= set(committed.files)
    assert "notes.bin" not in committed.files and "notes.bin" in committed.skipped
    assert module.repository.current_workspace().number == workspace.number
