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


def test_clone_module_prepares_dependencies(short_tmp):
    """clone はモジュールをcloneし、依存先と生成ファイルを sync と同じく用意する。"""
    stl_github = FakeGitHub(short_tmp / "gh1")
    Module.create("STL", directory=short_tmp, github=stl_github)
    ecs_github = FakeGitHub(short_tmp / "gh2")
    ecs = Module.create("ECS", directory=short_tmp, github=ecs_github)
    workspace = ecs.create_task("STLを使う").start()
    _cppbuild.open_solution(ecs.root).get_project("ECS").settings.link_git(
        url(stl_github.bare), link_type=ProjectType.STATIC_LIBRARY)
    _cppbuild.update(ecs.root)
    workspace.stage(all=True)
    workspace.commit("STLを依存先にする")
    workspace.submit()
    ecs.pull_request().merge()

    second = short_tmp / "second"
    second.mkdir()
    module, dependencies = Module.clone("ECS", directory=second, github=ecs_github)
    assert module.root == (second / "ECS").resolve() and module.name == "ECS"
    assert [(d.name, d.action) for d in dependencies] == [("STL", "cloned")]
    assert (module.root / "deps" / "STL" / "ecobuild.toml").exists()
    assert module.status().branch == "main" and not module.status().unstaged


def test_clone_refuses_non_module(short_tmp):
    github = FakeGitHub(short_tmp / "gh")
    bare = short_tmp / "Plain.git"
    git(short_tmp, "init", "--quiet", "--bare", "--initial-branch=main", str(bare))
    seed = short_tmp / "seed"
    git(short_tmp, "clone", "--quiet", str(bare), str(seed))
    write(seed / "README.md", "plain\n")
    git(seed, "add", "--all")
    git(seed, "commit", "--quiet", "-m", "init")
    git(seed, "push", "--quiet", "origin", "main")
    github.use_bare(bare)
    target = short_tmp / "target"
    target.mkdir()
    with pytest.raises(Exception) as error:
        Module.clone("Plain", directory=target, github=github)
    assert error.value.code == "not_in_module" and not (target / "Plain").exists()


def test_link_deps_and_work_version(short_tmp):
    """link → deps list → 依存先が進む → deps update → 作業版は触らない → unlink。"""
    stl_github = FakeGitHub(short_tmp / "gh1")
    stl = Module.create("STL", directory=short_tmp, github=stl_github)
    github = FakeGitHub(short_tmp / "gh2")
    github.others["STL"] = stl_github.bare
    ecs = Module.create("ECS", directory=short_tmp, github=github)
    with pytest.raises(Exception) as error:
        ecs.link("NoSuch")
    assert error.value.code == "repository_not_found"

    linked = ecs.link("STL")
    assert (linked.name, linked.projects) == ("STL", ("ECS",))
    assert (ecs.root / "deps/STL/ecobuild.toml").exists()
    assert [(d.name, d.state) for d in ecs.dependencies()] == [("STL", "aligned")]
    with pytest.raises(Exception) as error:
        ecs.link("STL")
    assert error.value.code == "already_exists"
    assert ecs.test().failed == 0

    second = new_stl_commit(stl.root, "#pragma once\n// v2\n")
    assert [d.state for d in ecs.dependencies()] == ["aligned"]  # 記録はまだ古い
    changes = ecs.update_dependencies()
    assert [(c.name, c.action) for c in changes] == [("STL", "aligned")] and "→" in changes[0].reason
    assert ecs.dependencies()[0].recorded == second and ecs.dependencies()[0].state == "aligned"

    # 依存先の中で作業する（作業版）：sync・deps sync・deps update は触らない
    clone = ecs.root / "deps" / "STL"
    git(clone, "switch", "--quiet", "-c", "task/9")
    write(clone / "STL/include/STL/STL.h", "#pragma once\n// 作業中\n")
    git(clone, "commit", "--quiet", "-am", "作業中")
    state = ecs.dependencies()[0]
    assert (state.state, state.branch) == ("working", "task/9")
    assert [(c.action, c.reason) for c in ecs.sync_dependencies()] == [("skipped", "作業版です（task/9）")]
    assert git(clone, "branch", "--show-current") == "task/9"

    removed = ecs.unlink("STL")
    assert removed.projects == ("ECS",) and not removed.clone_removed and clone.exists()  # 作業版は残す
    assert ecs.dependencies() == ()
    with pytest.raises(Exception) as error:
        ecs.unlink("STL")
    assert error.value.code == "dependency_not_found"
