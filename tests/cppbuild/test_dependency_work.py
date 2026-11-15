"""依存先の作業版（deps work）：依存先の手元の clone を、依存先のタスクブランチの最新にする（記録は変えない）。

このPCに依存先のモジュールとそのタスクの作業空間があればそこから（push していないコミットも）、なければ GitHub から。
"""

import pytest
from click.testing import CliRunner

from helpers import git, remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecowork.git import Git
from ecobuild import workspaces as _workspaces
from ecobuild_bundle import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]

HEADER = ("Engine", "include", "Engine", "Engine.h")


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def _game_with_engine(base, *, recorded=True):
    engine_github = FakeGitHub(base / "gh1")
    engine = Module.create("Engine", directory=base, kind="library", github=engine_github)
    if recorded:
        _workspaces.record(engine.root)   # このPCのモジュールの一覧に（ecobuild workspace list）
    github = FakeGitHub(base / "gh2")
    github.others["Engine"] = engine_github.bare
    game = Module.create("Game", directory=base, kind="app", github=github)
    game.repository.create_task("Engine を使う").start()
    game.link("Engine")
    return engine, game


def _change(root, text):
    write(root.joinpath(*HEADER), text)
    git(root, "commit", "--quiet", "-am", text.strip())
    return git(root, "rev-parse", "HEAD")


def _state(game):
    return next(d for d in game.dependencies() if d.name == "Engine")


def _deps_list(game, monkeypatch, *args):
    from ecobuild_cli import build_cli
    with monkeypatch.context() as patch:   # 終われば元の場所へ（片付けで Game を消せるように）
        patch.chdir(game.root)
        result = CliRunner().invoke(build_cli("cpp"), ["deps", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_work_takes_unpushed_commits_from_the_task_workspace(short_tmp, monkeypatch):
    engine, game = _game_with_engine(short_tmp)
    recorded = _state(game).recorded
    managed = git(game.root, "rev-parse", "HEAD")
    task = engine.repository.create_task("速くする")
    workspace = engine.start_task(task.number, name="fast")
    first = _change(workspace.root, "#pragma once\n// work 1\n")   # push していない

    result = game.work_dependency("Engine", task=task.number)
    assert (result.action, result.work.branch, result.work.task, result.work.origin, result.work.commit) == (
        "switched", f"task/{task.number}-fast", task.number, "local", first)
    clone = game.root / "deps" / "Engine"
    assert git(clone, "rev-parse", "HEAD") == first
    state = _state(game)
    assert (state.state, state.recorded, state.local, state.work.task) == ("working", recorded, first, task.number)
    assert git(game.root, "rev-parse", "HEAD") == managed and not git(game.root, "status", "--porcelain")   # 記録は変えない
    assert not git(clone, "remote").replace("origin", "").strip()   # remote を足さない
    shown = _deps_list(game, monkeypatch, "list")
    assert f"作業版（Engine #{task.number}・このPCの作業空間、task/{task.number}-fast）" in shown
    assert f"作業版：Engine #{task.number}・このPCの作業空間" in _deps_list(game, monkeypatch, "tree")
    assert [d.name for d in game.status().dependencies] == ["Engine"]   # 記録と違うと知らせる

    # 作業版のままビルドできる（止めず、記録と違うことを知らせる）
    game.repository.notices.clear()
    game.build()
    assert any("手元の依存先が記録の版と違います" in n and "Engine" in n for n in game.repository.notices)

    # sync は作業版に触らない
    assert [(c.name, c.action) for c in game.sync_dependencies()] == [("Engine", "skipped")]
    assert git(clone, "rev-parse", "HEAD") == first

    # 取り直し：依存先の側が進んだら、省いて同じタスクの最新に
    second = _change(workspace.root, "#pragma once\n// work 2\n")
    again = game.work_dependency("Engine")
    assert (again.action, again.previous, again.work.commit) == ("refreshed", first, second)
    assert game.work_dependency("Engine").action == "unchanged"

    # --done：記録の版に戻し、作業版のブランチと覚えたものを消す
    done = game.work_dependency("Engine", done=True)
    assert done.action == "done" and done.work is None
    assert git(clone, "rev-parse", "HEAD") == recorded
    assert _state(game).state == "aligned" and _state(game).work is None
    assert not git(clone, "branch", "--list", f"task/{task.number}-fast")
    assert Git(clone).get_config("ecobuild-work.branch") is None
    assert git(game.root, "rev-parse", "HEAD") == managed


def test_work_takes_the_pushed_task_branch_from_github(short_tmp):
    """このPCに依存先のモジュールがない（コンテナの中も同じ）：GitHub のタスクブランチから（push 済みのものだけ）。"""
    engine, game = _game_with_engine(short_tmp, recorded=False)
    git(engine.root, "switch", "--quiet", "-c", "task/7-net")
    pushed = _change(engine.root, "#pragma once\n// pushed\n")
    git(engine.root, "push", "--quiet", "origin", "task/7-net")
    _change(engine.root, "#pragma once\n// not pushed\n")
    git(engine.root, "switch", "--quiet", "main")

    result = game.work_dependency("Engine", task=7)
    assert (result.work.origin, result.work.branch, result.work.commit) == ("github", "task/7-net", pushed)
    assert _state(game).work.origin == "github"


def test_work_with_a_branch_that_is_not_a_task_branch(short_tmp):
    engine, game = _game_with_engine(short_tmp, recorded=False)
    git(engine.root, "switch", "--quiet", "-c", "feature")
    tip = _change(engine.root, "#pragma once\n// feature\n")
    git(engine.root, "push", "--quiet", "origin", "feature")
    git(engine.root, "switch", "--quiet", "main")

    result = game.work_dependency("Engine", branch="feature")
    assert (result.work.branch, result.work.task, result.work.commit) == ("feature", None, tip)
    state = _state(game)
    assert (state.state, state.branch) == ("working", "feature")   # タスクブランチでなくても作業版
    assert [(c.name, c.action) for c in game.sync_dependencies()] == [("Engine", "skipped")]
    assert git(game.root / "deps" / "Engine", "rev-parse", "HEAD") == tip


def test_work_refuses_what_it_would_lose_or_cannot_find(short_tmp):
    engine, game = _game_with_engine(short_tmp)
    clone = game.root / "deps" / "Engine"
    recorded = _state(game).recorded

    with pytest.raises(Exception) as error:   # 作業版でないのに取り直し
        game.work_dependency("Engine")
    assert error.value.code == "invalid_argument" and "--task" in error.value.hint
    with pytest.raises(Exception) as error:   # どこにもないタスク
        game.work_dependency("Engine", task=99)
    assert error.value.code == "branch_not_found" and "task push" in error.value.hint

    task = engine.repository.create_task("直す")
    workspace = engine.start_task(task.number, name="fix")
    _change(workspace.root, "#pragma once\n// fix\n")
    write(clone.joinpath(*HEADER), "// deps の中で直した\n")   # 未コミットの変更があれば止める
    with pytest.raises(Exception) as error:
        game.work_dependency("Engine", task=task.number)
    assert error.value.code == "dirty_working_tree"
    assert git(clone, "rev-parse", "HEAD") == recorded and _state(game).state == "modified"
    git(clone, "checkout", "--quiet", "--", ".")

    game.work_dependency("Engine", task=task.number)
    git(clone, "commit", "--quiet", "--allow-empty", "-m", "deps の中でコミット")   # 取ってきた先にないコミットは消さない
    mine = git(clone, "rev-parse", "HEAD")
    for attempt in (lambda: game.work_dependency("Engine"), lambda: game.work_dependency("Engine", done=True)):
        with pytest.raises(Exception) as error:
            attempt()
        assert error.value.code == "commits_would_be_lost"
        assert git(clone, "rev-parse", "HEAD") == mine
    assert _state(game).recorded == recorded   # 記録はずっと変わらない
