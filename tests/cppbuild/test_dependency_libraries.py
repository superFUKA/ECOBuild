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
    git(engine.root, "tag", "v1")
    git(engine.root, "push", "--quiet", "origin", "v1")
    return github


def test_choose_libraries_of_a_dependency(short_tmp):
    engine_github = _engine(short_tmp)
    github = FakeGitHub(short_tmp / "gh2")
    github.others["Engine"] = engine_github.bare
    game = Module.create("Game", directory=short_tmp, kind="app", github=github)
    game.repository.create_task("Engine を使う").start()

    # まだ依存先でないリポジトリ：一時的に取って読む
    found = game.dependency_libraries("Engine")
    assert game.dependency_libraries("Engine", revision="v1").revision == found.revision   # タグの版（まだ依存先でない）
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
    # 外した後の図：依存先の中のリンク（EngineTest → Engine 等）は数えない
    assert [(n.name, n.libraries) for n in game.dependency_tree().nodes] == [("Engine", ("Engine",))]
    # 依存先の名前と版：記録の url のその版を読み、リンクしているものを添える
    at = game.dependency_libraries("Engine", revision="main")
    assert at.name == "Engine" and {l.name: l.linked for l in at.libraries}["Engine"] == ("Game",)
    tagged = game.dependency_libraries("Engine", revision="v1")   # タグの版も読める
    assert tagged.name == "Engine" and "Physics" in [l.name for l in tagged.libraries]
    assert [l.name for l in game.dependency_libraries("Engine", linked_only=True).libraries] == ["Engine"]
    assert game.dependency_libraries("Nope", linked_only=True).libraries == ()   # 依存先でなければ GitHub へ行かない

    # 最後の1つ：リンクのない記録と clone を残さず、依存先ごと外す
    last = game.unlink("Engine", "Engine")
    assert (last.dependency_removed, last.libraries) == (True, ("Engine",)) and game.dependencies() == ()
    assert git(game.root, "log", "-1", "--format=%s") == "Engine のリンクを外す"

    # clone がなくても外せる（名前が分からないものは識別子の頭で）
    game.link("Engine", library="Physics")
    game.link("Engine")
    remove_tree(game.root / "deps/Engine")
    [state] = game.dependencies()
    assert sorted(l.library for l in state.links) == ["", ""] and all(len(l.id) == 36 for l in state.links)
    physics = _cppbuild.open_solution(short_tmp / "Engine").get_subproject("Physics").settings.get().guid
    listed = game.dependency_libraries("Engine", linked_only=True)   # 外す窓の候補：clone がなくても記録から
    assert sorted(l.name for l in listed.libraries) == sorted(f"{l.id[:8]}（clone なし）" for l in state.links)
    assert physics in {l.id for l in state.links}
    assert game.unlink("Engine", physics[:8]).libraries == (physics[:8],)
    [state] = game.dependencies()
    assert len(state.links) == 1



def _module_with_dependency(base, name, dependency_bare, github):
    """dependency（bare）のライブラリにリンクした、ライブラリ name のモジュール（GitHub の main に push 済み）。"""
    module = Module.create(name, directory=base, kind="library", github=github)
    _cppbuild.link(module.root, name, "file:///" + dependency_bare.as_posix(), shared=False)
    git(module.root, "add", "-A")
    git(module.root, "commit", "--quiet", "-m", "依存先")
    git(module.root, "push", "--quiet", "origin", "main")
    return module


def test_libraries_of_a_dependency_of_a_dependency_and_an_old_one(short_tmp):
    """依存先の依存先のライブラリも読める。依存先の依存先が古い形式の版なら、リンクしようとしたものではなく、その名前で案内する。"""
    import json
    base_github = FakeGitHub(short_tmp / "gh1")
    Module.create("Base", directory=short_tmp, kind="library", github=base_github)
    engine_github = FakeGitHub(short_tmp / "gh2")
    _module_with_dependency(short_tmp, "Engine", base_github.bare, engine_github)
    github = FakeGitHub(short_tmp / "gh3")
    github.others["Engine"] = engine_github.bare
    game = Module.create("Game", directory=short_tmp, kind="app", github=github)
    game.repository.create_task("Engine を使う").start()
    game.link("Engine")
    nested = game.dependency_libraries("Base")
    assert nested.name == "Base" and [(l.name, l.main) for l in nested.libraries if l.linkable] == [("Base", True)]
    assert {n.name: n.libraries for n in game.dependency_tree().nodes} == {"Engine": ("Engine",), "Base": ("Base",)}

    # Legacy：記録の版が古い形式（solution.json のない版）を、Old が記録している
    legacy_github = FakeGitHub(short_tmp / "gh4")
    legacy = Module.create("Legacy", directory=short_tmp, kind="library", github=legacy_github)
    old_github = FakeGitHub(short_tmp / "gh5")
    old = _module_with_dependency(short_tmp, "Old", legacy_github.bare, old_github)
    git(legacy.root, "rm", "--quiet", ".ecobuild/.cppbuild/solution.json")
    git(legacy.root, "commit", "--quiet", "-m", "古い形式の代わり")
    git(legacy.root, "push", "--quiet", "origin", "main")
    sha = git(legacy.root, "rev-parse", "HEAD")
    path = old.root / ".ecobuild/.cppbuild/solution.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["data"]["git_sources"]["Legacy"]["revision"] = sha
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    git(old.root, "commit", "--quiet", "-am", "古い版を記録")
    git(old.root, "push", "--quiet", "origin", "main")
    github.others["Old"] = old_github.bare
    with pytest.raises(Exception) as error:
        game.link("Old")
    assert error.value.code == "dependency_old_format" and "Legacy" in error.value.message
    assert "deps update Legacy" in error.value.hint and [d.name for d in game.dependencies()] == ["Engine"]
