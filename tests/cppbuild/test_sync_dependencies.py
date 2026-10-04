import shutil
import tempfile
from pathlib import Path

import pytest
from cppbuild import ProjectType

from helpers import git, write
from fakes import FakeGitHub
from ecobuild import _cppbuild
from ecobuild.module import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = Path(tempfile.mkdtemp(prefix="eb"))
    yield base
    shutil.rmtree(base, ignore_errors=True)


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
    shutil.rmtree(clone, onerror=lambda f, p, e: (Path(p).chmod(0o700), f(p)))
    result = ecs.sync()
    assert [(d.name, d.action) for d in result.dependencies] == [("STL", "cloned")]
