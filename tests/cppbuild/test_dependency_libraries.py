"""依存先のどのライブラリにリンクするかを選ぶ（deps add --library・deps libraries・deps remove --library）。"""

import pytest

from helpers import git, remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecobuild_cpp import _cppbuild
from ecobuild_bundle import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def _engine(base):
    """ライブラリ Engine（main）・Physics と、実行ファイル Tool を持つモジュール（GitHub の main に push 済み）。"""
    github = FakeGitHub(base / "gh1")
    engine = Module.create("Engine", directory=base, kind="library", github=github)
    _cppbuild.add_project(engine.root, "Physics", "library")
    _cppbuild.add_project(engine.root, "Tool", "app", link="Physics")
    write(engine.root / "Physics/include/Physics/Physics.h", "#pragma once\ninline int gravity() { return 10; }\n")
    _cppbuild.update(engine.root)
    git(engine.root, "add", "-A")
    git(engine.root, "commit", "--quiet", "-m", "Physics・Tool")
    git(engine.root, "push", "--quiet", "origin", "main")
    return github


def test_choose_libraries_of_a_dependency(short_tmp):
    engine_github = _engine(short_tmp)
    github = FakeGitHub(short_tmp / "gh2")
    github.others["Engine"] = engine_github.bare
    game = Module.create("Game", directory=short_tmp, kind="app", github=github)
    game.repository.create_task("Engine を使う").start()

    # まだ依存先でないリポジトリ：一時的に取って読む
    found = game.dependency_libraries("Engine")
    assert found.name is None and len(found.revision) == 40
    assert [(l.name, l.kind, l.main, l.linkable) for l in found.libraries] == [
        ("Engine", "static_library", True, True), ("Physics", "static_library", False, True),
        ("EngineTest", "test", False, False), ("PhysicsTest", "test", False, False), ("Tool", "executable", False, False)]

    # main 以外へのリンク
    linked = game.link("Engine", library="Physics")
    assert (linked.name, linked.projects, linked.libraries) == ("Engine", ("Game",), ("Physics",))
    # 同じ依存先の別のライブラリ（記録の版のまま）。省けば main
    second = game.link("Engine")
    assert (second.libraries, second.revision) == (("Engine",), linked.revision)
    with pytest.raises(Exception) as error:   # 同じライブラリの2回目
        game.link("Engine", library="Physics")
    assert error.value.code == "already_exists"
    with pytest.raises(Exception) as error:   # ない名前：選べるライブラリを案内
        game.link("Engine", library="Nope")
    assert error.value.code == "project_not_found" and "Physics" in error.value.hint and "Engine（main）" in error.value.hint
    with pytest.raises(Exception) as error:   # 実行ファイル
        game.link("Engine", library="Tool")
    assert error.value.code == "not_linkable" and "実行ファイル" in error.value.message
    with pytest.raises(Exception) as error:   # テスト用
        game.link("Engine", library="EngineTest")
    assert error.value.code == "not_linkable" and "テスト用" in error.value.message

    # 見せる：deps list・deps tree・project show・deps libraries（依存先）
    [state] = game.dependencies()
    assert sorted((l.project, l.library) for l in state.links) == [("Game", "Engine"), ("Game", "Physics")]
    tree = game.dependency_tree()
    assert [(n.name, n.libraries) for n in tree.nodes] == [("Engine", ("Engine", "Physics"))]
    links = [(l["dependency"], l["library"]) for l in game.project_details("Game")["links"] if l["kind"] == "module"]
    assert sorted(links) == [("Engine", "Engine"), ("Engine", "Physics")]
    listed = game.dependency_libraries("Engine")
    assert {l.name: l.linked for l in listed.libraries}["Physics"] == ("Game",) and listed.name == "Engine"

    # ビルドまで（Physics の関数を使う）
    write(game.root / "Game/src/main.cpp", '#include "Physics/Physics.h"\nint main() { return gravity() == 10 ? 0 : 1; }\n')
    game.build()   # 失敗なら例外
    assert game.run(project="Game").returncode == 0

    # 1つだけ外す：記録と clone は残る
    removed = game.unlink("Engine", "Physics")
    assert (removed.projects, removed.libraries) == (("Game",), ("Physics",))
    [state] = game.dependencies()
    assert [(l.project, l.library) for l in state.links] == [("Game", "Engine")] and (game.root / "deps/Engine").is_dir()
    with pytest.raises(Exception) as error:
        game.unlink("Engine", "Physics")
    assert error.value.code == "project_not_found" and "Engine" in error.value.hint
    assert game.unlink("Engine").projects == ("Game",) and game.dependencies() == ()
