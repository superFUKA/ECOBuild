"""依存先の版にコミットを選ぶ（deps update --at・deps add --at・deps libraries --at・deps versions --branch）：
GitHub に push 済みなら短いハッシュでも取れる。push していないなら、このPCのどこにあるかを添えて断る。"""

import pytest

from helpers import git, remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecobuild import workspaces as _workspaces
from ecobuild_bundle import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def _commit(root, branch, text):
    git(root, "switch", "--quiet", "-c", branch)
    write(root / "Engine" / "include" / "Engine" / "Engine.h", text)
    git(root, "commit", "--quiet", "-am", text)
    sha = git(root, "rev-parse", "HEAD")
    git(root, "switch", "--quiet", "main")
    return sha


def _game_with_engine(base):
    engine_github = FakeGitHub(base / "gh1")
    engine = Module.create("Engine", directory=base, kind="library", github=engine_github)
    _workspaces.record(engine.root)   # このPCのモジュールの一覧に（ecobuild workspace list）
    github = FakeGitHub(base / "gh2")
    github.others["Engine"] = engine_github.bare
    game = Module.create("Game", directory=base, kind="app", github=github)
    game.repository.create_task("Engine を使う").start()
    game.link("Engine")
    return engine, game


def test_pushed_commit_is_found_by_its_short_hash(short_tmp):
    engine, game = _game_with_engine(short_tmp)
    # 手元の clone（deps/Engine）を作った後に push したタスクブランチのコミット：取り込み直して解く
    pushed = _commit(engine.root, "task/5-pushed", "#pragma once\n// pushed\n")
    git(engine.root, "push", "--quiet", "origin", "task/5-pushed")
    game.update_dependencies("Engine", pushed[:8])
    state = next(d for d in game.dependencies() if d.name == "Engine")
    assert state.recorded == pushed and state.local == pushed


def test_unpushed_commit_says_where_it_is(short_tmp):
    engine, game = _game_with_engine(short_tmp)
    local = _commit(engine.root, "task/6-local", "#pragma once\n// local\n")
    for revision in (local[:8], local):
        with pytest.raises(Exception) as error:
            game.update_dependencies("Engine", revision)
        assert error.value.code == "dependency_revision_not_found"
        assert "task/6-local" in error.value.message and str(engine.root) in error.value.message
        assert "push" in error.value.hint
    with pytest.raises(Exception) as error:   # deps libraries --at も同じ
        game.dependency_libraries("Engine", revision=local[:8])
    assert error.value.code == "dependency_revision_not_found"

    # deps versions --branch：GitHub にないブランチが、このPCのどこにあるか
    with pytest.raises(Exception) as error:
        game.dependency_versions("Engine", branch="task/6-local")
    assert "push" in error.value.hint and str(engine.root) in error.value.hint


def test_unknown_commit_is_refused_and_the_record_is_kept(short_tmp):
    _, game = _game_with_engine(short_tmp)
    before = next(d for d in game.dependencies() if d.name == "Engine").recorded
    for revision in ("abcdef12", "1" * 40):   # 依存先の clone を取り込み直しても、ない
        with pytest.raises(Exception) as error:
            game.update_dependencies("Engine", revision)
        assert error.value.code == "dependency_revision_not_found" and "deps versions" in error.value.hint
    assert next(d for d in game.dependencies() if d.name == "Engine").recorded == before


def test_hex_like_branch_name_is_a_branch(short_tmp):
    """16進に見えるブランチ名（cafe1234 等）は、ハッシュではなくブランチとして選ぶ。"""
    engine, game = _game_with_engine(short_tmp)
    name = git(engine.root, "rev-parse", "HEAD")[:8]   # 今のコミットの短いハッシュと同じ名前
    tip = _commit(engine.root, name, "#pragma once\n// branch\n")
    git(engine.root, "push", "--quiet", "origin", name)
    git(engine.root, "branch", "-D", name)
    game.update_dependencies("Engine", name)
    assert next(d for d in game.dependencies() if d.name == "Engine").recorded == tip
