"""module rename の型 cpp の分：Solution 名だけを変える（Project 名・include/<名前>/ は依存元が使うので変えない）。"""

import json

import pytest

from helpers import git, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecobuild import workspaces
from ecobuild_bundle import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local, pytest.mark.needs_git_2_48]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def test_rename_changes_only_the_solution_name(short_tmp):
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Engine", directory=short_tmp, kind="library", github=github)
    root = module.root
    workspaces.record(root)
    module.type.refresh()
    assert (root / "build").is_dir()   # 前の場所で構成したビルドツリー

    planned = module.rename("Motor", dry_run=True)
    assert ".ecobuild/.cppbuild/solution.json" in planned.paths
    done = module.rename("Motor")
    new_root = short_tmp / "Motor"
    assert done.moved and done.commit
    solution = json.loads((new_root / ".ecobuild/.cppbuild/solution.json").read_text(encoding="utf-8"))
    assert solution["data"]["name"] == "Motor"
    changed = git(new_root, "show", "--name-only", "--format=", done.commit).splitlines()
    assert ".ecobuild/.cppbuild/solution.json" in changed
    assert ".ecobuild/.cppbuild/CMakeLists.txt" in changed   # 生成ファイルも同じコミットに
    assert "Motor" in (new_root / ".ecobuild/.cppbuild/CMakeLists.txt").read_text(encoding="utf-8")
    assert {p.name for p in Module.find(new_root, github=github).projects()} == {"Engine", "EngineTest"}
    assert (new_root / "Engine" / "include" / "Engine").is_dir()
    assert not (new_root / "build").exists()   # CMakeCache に前の場所が入っているので消した（次のビルドで作り直す）
    assert any("build" in line for line in done.cleaned)
    assert git(new_root, "status", "--porcelain").strip() == ""
