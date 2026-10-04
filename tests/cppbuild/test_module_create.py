import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from helpers import git
from fakes import FakeGitHub
from ecobuild import config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = Path(tempfile.mkdtemp(prefix="eb"))
    yield base
    shutil.rmtree(base, ignore_errors=True)


def test_create_module(short_tmp):
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, app=True, description="電卓", github=github)
    root = short_tmp / "Calc"
    assert module.root == root
    assert config.load(root / config.FILE_NAME).projects.app == "CalcApp"
    assert "/deps/" in (root / ".gitignore").read_text(encoding="utf-8")
    assert github.private is True
    # 初回コミットがGitHub（bare）のmainにある
    assert git(github.bare, "log", "--format=%s", "main") == "ECOBuildでモジュールを作成"
    files = git(github.bare, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert "CMakeLists.txt" in files and "Calc/CMakeLists.txt" in files
    assert not any(f.startswith(".cppbuild/output") for f in files)
    assert git(root, "status", "--porcelain") == ""
    assert Module.find(root / "Calc" / "src").name == "Calc"
    assert module.summary().projects == ("Calc", "CalcTest", "CalcApp")

    # cloneしただけの人が、CMakeだけでビルド・テストできる
    clone = short_tmp / "c"
    git(short_tmp, "clone", "--quiet", str(github.bare), str(clone))
    for args in (["cmake", "-S", ".", "-B", "b"], ["cmake", "--build", "b", "--config", "Debug"],
                 ["ctest", "--test-dir", "b", "-C", "Debug"]):
        completed = subprocess.run(args, cwd=clone, capture_output=True, text=True, errors="replace")
        assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]


def test_existing_directory_is_rejected(short_tmp):
    (short_tmp / "Calc").mkdir()
    with pytest.raises(EcoBuildError) as error:
        Module.create("Calc", directory=short_tmp, github=FakeGitHub(short_tmp / "gh"))
    assert error.value.code == ErrorCode.ALREADY_EXISTS


def test_invalid_name(short_tmp):
    with pytest.raises(EcoBuildError) as error:
        Module.create("1bad-name", directory=short_tmp, github=FakeGitHub(short_tmp / "gh"))
    assert error.value.code == ErrorCode.INVALID_CONFIG
