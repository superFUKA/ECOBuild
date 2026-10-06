from pathlib import Path

import pytest
from cppbuild import ProjectType

from helpers import git, write, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecobuild import _cppbuild
from ecobuild.module import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def url(path: Path) -> str:
    return "file:///" + path.as_posix()


def new_stl_commit(stl_root: Path, text: str) -> str:
    write(stl_root / "STL" / "include" / "STL" / "STL.h", text)
    git(stl_root, "commit", "--quiet", "-am", "STLを更新")
    git(stl_root, "push", "--quiet", "origin", "main")
    return git(stl_root, "rev-parse", "HEAD")


def test_sync_aligns_dependencies(short_tmp):
    stl_github = FakeGitHub(short_tmp / "gh1")
    stl = Module.create("STL", directory=short_tmp, github=stl_github)
    ecs = Module.create("ECS", directory=short_tmp, github=FakeGitHub(short_tmp / "gh2"))
    solution = _cppbuild.open_solution(ecs.root)
    solution.get_project("ECS").settings.link_git(url(stl_github.bare), link_type=ProjectType.STATIC_LIBRARY)
    clone = ecs.root / "deps" / "STL"
    first = git(clone, "rev-parse", "HEAD")

    # STLが進み、ECSの記録を新しい版へ更新した（手元のcloneは古いまま）
    second = new_stl_commit(stl.root, "#pragma once\n// v2\n")
    solution.set_git_source(url(stl_github.bare))
    assert git(clone, "rev-parse", "HEAD") == first
    result = ecs.sync()
    assert [(d.name, d.action) for d in result.dependencies] == [("STL", "aligned")]
    assert git(clone, "rev-parse", "HEAD") == second and result.regenerated

    # 手元で編集中の依存先は触らない
    new_stl_commit(stl.root, "#pragma once\n// v3\n")
    solution.set_git_source(url(stl_github.bare))
    write(clone / "STL" / "src" / "STL.cpp", "// 編集中\n")
    result = ecs.sync()
    assert [(d.name, d.action) for d in result.dependencies] == [("STL", "skipped")]
    assert git(clone, "rev-parse", "HEAD") == second

    # 消した依存先は取り直す
    git(clone, "checkout", "--quiet", "--", ".")
    remove_tree(clone)
    result = ecs.sync()
    assert [(d.name, d.action) for d in result.dependencies] == [("STL", "cloned")]


def test_sync_regenerates_conflicted_generated_files(short_tmp):
    """生成ファイルだけが衝突したら、管理ファイルから作り直して取り込みを完了する。"""
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, github=github)
    top = "CppBuildTopLevel.cmake"
    expected = (module.root / top).read_text(encoding="utf-8")
    workspace = module.create_task("t").start()
    write(module.root / top, expected + "# 手元\n")
    workspace.commit("手元で生成ファイルを変えた", all=True)
    other = short_tmp / "other"
    git(short_tmp, "clone", "--quiet", str(github.bare), str(other))
    write(other / top, expected + "# GitHub\n")
    git(other, "commit", "--quiet", "-am", "GitHubで生成ファイルを変えた")
    git(other, "push", "--quiet", "origin", "main")
    result = module.sync()
    assert result.merged == ("merge",) and result.regenerated
    assert (module.root / top).read_text(encoding="utf-8") == expected
    assert not module.status().merging
