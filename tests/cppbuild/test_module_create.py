import subprocess

import pytest

from helpers import git, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecowork import WorkError
from ecobuild import config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


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
    git(short_tmp, "clone", "--quiet", "--config", "core.autocrlf=true", str(github.bare), str(clone))
    # 改行を変換する設定でcloneしても、生成し直した生成ファイルが「変更あり」にならない
    from ecobuild import _cppbuild
    _cppbuild.update(clone)
    assert git(clone, "status", "--porcelain") == ""
    for args in (["cmake", "-S", ".", "-B", "b"], ["cmake", "--build", "b", "--config", "Debug"],
                 ["ctest", "--test-dir", "b", "-C", "Debug"]):
        completed = subprocess.run(args, cwd=clone, capture_output=True, text=True, errors="replace")
        assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]


def test_existing_directory_is_rejected(short_tmp):
    (short_tmp / "Calc").mkdir()
    with pytest.raises(WorkError) as error:  # 作業の進め方（ecowork）のエラー
        Module.create("Calc", directory=short_tmp, github=FakeGitHub(short_tmp / "gh"))
    assert error.value.code == ErrorCode.ALREADY_EXISTS


def test_invalid_name(short_tmp):
    with pytest.raises(EcoBuildError) as error:
        Module.create("1bad-name", directory=short_tmp, github=FakeGitHub(short_tmp / "gh"))
    assert error.value.code == ErrorCode.INVALID_CONFIG


def test_submit_requires_generated_files(short_tmp):
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, github=github)
    workspace = module.create_task("ファイル追加").start()
    extra = module.root / "Calc" / "src" / "Extra.cpp"
    extra.write_text("int extra() { return 1; }\n", encoding="utf-8")
    workspace.stage("Calc/src/Extra.cpp")
    workspace.commit("ソースを追加")
    with pytest.raises(EcoBuildError) as error:
        workspace.submit()
    assert error.value.code == ErrorCode.GENERATED_FILES_OUTDATED
    assert "Calc/CMakeLists.txt" in error.value.details
    workspace.stage(all=True)
    workspace.commit("生成ファイルを更新")
    pr = workspace.submit()
    assert pr.head == "task/1"
