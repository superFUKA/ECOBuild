"""依存先の作業版（deps work）：依存先の手元の clone を、依存先のタスクブランチの最新にする（記録は変えない）。

このPCに依存先のモジュールとそのタスクの作業空間があればそこから（push していないコミットも）、なければ GitHub から。
"""

import json

import pytest
from click.testing import CliRunner

from helpers import git, remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecowork.git import Git
from ecobuild import workspaces as _workspaces
from ecobuild_bundle import Module
from ecobuild_cpp import _cppbuild

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


def _cli(game, monkeypatch, *args):
    from ecobuild_cli import build_cli
    with monkeypatch.context() as patch:   # 終われば元の場所へ（片付けで Game を消せるように）
        patch.chdir(game.root)
        result = CliRunner().invoke(build_cli("cpp"), list(args))
    assert result.exit_code == 0, result.output
    return result.stdout


def _deps_list(game, monkeypatch, *args):
    return _cli(game, monkeypatch, "deps", *args)


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
    # ブランチを作らず切り離す（deps/ の中の ecobuild が依存先のタスクブランチと見なさない）
    assert git(clone, "branch", "--show-current") == "" and not git(clone, "branch", "--list", "task/*")
    state = _state(game)
    assert (state.state, state.recorded, state.local, state.work.task) == ("working", recorded, first, task.number)
    assert git(game.root, "rev-parse", "HEAD") == managed and not git(game.root, "status", "--porcelain")   # 記録は変えない
    assert not git(clone, "remote").replace("origin", "").strip()   # remote を足さない
    shown = _deps_list(game, monkeypatch, "list")
    assert f"作業版（Engine #{task.number}・このPCの作業空間、task/{task.number}-fast）" in shown
    assert f"作業版：Engine #{task.number}・このPCの作業空間" in _deps_list(game, monkeypatch, "tree")
    assert [d.name for d in game.status().dependencies] == ["Engine"]   # 記録と違うと知らせる

    # 作業版のままビルドできる（止めず、記録と違うことを知らせる）
    built = json.loads(_cli(game, monkeypatch, "build", "--json"))
    assert built["ok"] and any("手元の依存先が記録の版と違います" in n and "Engine" in n for n in built["notices"])
    # check の中の build では知らせない（依存先の項目と二重にしない）
    game.repository.notices.clear()
    game.build(note_dependencies=False)
    assert not any("手元の依存先" in n for n in game.repository.notices)

    # 作業版の clone の未コミットの変更も見える
    write(clone / "note.txt", "x")
    assert _state(game).work.modified and "未コミットの変更あり" in _deps_list(game, monkeypatch, "list")
    (clone / "note.txt").unlink()

    # sync は作業版に触らない
    assert [(c.name, c.action) for c in game.sync_dependencies()] == [("Engine", "skipped")]
    assert git(clone, "rev-parse", "HEAD") == first

    # 取り直し：依存先の側が進んだら、省いて同じタスクの最新に
    second = _change(workspace.root, "#pragma once\n// work 2\n")
    again = game.work_dependency("Engine")
    assert (again.action, again.previous, again.work.commit) == ("refreshed", first, second)
    assert game.work_dependency("Engine").action == "unchanged"

    # 別のタスクに切り替える（12→13 等）
    other = engine.repository.create_task("別の作業")
    other_workspace = engine.start_task(other.number, name="other")
    third = _change(other_workspace.root, "#pragma once\n// other\n")
    moved = game.work_dependency("Engine", task=other.number)
    assert (moved.action, moved.work.task, moved.work.commit) == ("switched", other.number, third)
    assert not git(clone, "branch", "--list", "task/*")   # 前の作業版のブランチも残らない

    # --done：記録の版に戻し、覚えたものを消す
    done = game.work_dependency("Engine", done=True)
    assert done.action == "done" and done.work is None
    assert git(clone, "rev-parse", "HEAD") == recorded
    assert _state(game).state == "aligned" and _state(game).work is None
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


def test_work_aligns_what_the_working_version_records(short_tmp):
    """依存先のタスクが、依存先の依存先（Core）の記録を上げていれば、作業版にするとき deps/Core もその版に。"""
    core_github = FakeGitHub(short_tmp / "gh0")
    core = Module.create("Core", directory=short_tmp, kind="library", github=core_github)
    engine_github = FakeGitHub(short_tmp / "gh1")
    engine_github.others["Core"] = core_github.bare
    engine = Module.create("Engine", directory=short_tmp, kind="library", github=engine_github)
    _workspaces.record(engine.root)
    engine.repository.create_task("Core を使う").start()
    engine.link("Core")
    git(engine.root, "push", "--quiet", "origin", "HEAD:main")
    tool_github = FakeGitHub(short_tmp / "gh3")
    tool = Module.create("Tool", directory=short_tmp, kind="library", github=tool_github)
    github = FakeGitHub(short_tmp / "gh2")
    github.others["Engine"] = engine_github.bare
    github.others["Tool"] = tool_github.bare
    game = Module.create("Game", directory=short_tmp, kind="app", github=github)
    game.repository.create_task("Engine を使う").start()
    game.link("Engine")
    game.link("Tool")
    # 利用者が手で別の版にした、ほかの依存先（Tool）：deps work Engine では触らない
    write(tool.root / "Tool" / "include" / "Tool" / "Tool.h", "#pragma once\n// tool 2\n")
    git(tool.root, "commit", "--quiet", "-am", "Tool 2")
    git(tool.root, "push", "--quiet", "origin", "main")
    tool_clone = game.root / "deps" / "Tool"
    git(tool_clone, "fetch", "--quiet", "origin")
    git(tool_clone, "switch", "--quiet", "--detach", "origin/main")
    tool_head = git(tool_clone, "rev-parse", "HEAD")
    assert next(d for d in game.dependencies() if d.name == "Tool").state == "differs"
    core_clone = next(s for s, _ in _cppbuild.all_git_sources(game.root) if s.name == "Core").directory
    old_core = git(core_clone, "rev-parse", "HEAD")

    write(core.root / "Core" / "include" / "Core" / "Core.h", "#pragma once\n// core 2\n")
    git(core.root, "commit", "--quiet", "-am", "Core 2")
    git(core.root, "push", "--quiet", "origin", "main")
    new_core = git(core.root, "rev-parse", "HEAD")
    task = engine.repository.create_task("Core を上げる")
    workspace = engine.start_task(task.number, name="core")
    workspace.update_dependencies("Core")   # 依存先のタスクで Core の記録を上げる（コミットだけ。push しない）

    result = game.work_dependency("Engine", task=task.number)
    assert git(core_clone, "rev-parse", "HEAD") == new_core != old_core
    assert ("Core", "aligned") in [(c.name, c.action) for c in result.changes]
    assert git(tool_clone, "rev-parse", "HEAD") == tool_head and "Tool" not in [c.name for c in result.changes]


def test_work_chooses_the_exact_task_and_one_way(short_tmp):
    """--task 12 は task/12-… だけ（task/120-… は別）。--task と --branch は一緒に使えない。"""
    engine, game = _game_with_engine(short_tmp, recorded=False)
    tips = {}
    for branch in ("task/12-a", "task/120-b"):
        git(engine.root, "switch", "--quiet", "-c", branch, "main")
        tips[branch] = _change(engine.root, f"#pragma once\n// {branch}\n")
        git(engine.root, "push", "--quiet", "origin", branch)
    git(engine.root, "switch", "--quiet", "main")
    assert game.work_dependency("Engine", task=12).work.commit == tips["task/12-a"]
    assert game.work_dependency("Engine", task=120).work.commit == tips["task/120-b"]
    with pytest.raises(Exception) as error:
        game.work_dependency("Engine", task=12, branch="task/12-a")
    assert error.value.code == "invalid_argument"


def test_work_says_when_github_is_ahead_of_the_workspace(short_tmp):
    engine, game = _game_with_engine(short_tmp)
    task = engine.repository.create_task("速くする")
    workspace = engine.start_task(task.number, name="fast")
    first = _change(workspace.root, "#pragma once\n// 1\n")
    _change(workspace.root, "#pragma once\n// 2\n")
    git(workspace.root, "push", "--quiet", "origin", f"task/{task.number}-fast")
    git(workspace.root, "reset", "--quiet", "--hard", first)   # 作業空間の方が古い
    game.repository.notices.clear()
    assert game.work_dependency("Engine", task=task.number).work.commit == first
    assert any("GitHub の" in n and "にないコミット" in n for n in game.repository.notices)


def test_work_keeps_commits_made_in_a_detached_clone(short_tmp):
    """作業版でない（記録と別の版に切り離した）clone でコミットしたものも、切り替えで消さない。"""
    engine, game = _game_with_engine(short_tmp, recorded=False)
    git(engine.root, "switch", "--quiet", "-c", "task/3-x")
    _change(engine.root, "#pragma once\n// x\n")
    git(engine.root, "push", "--quiet", "origin", "task/3-x")
    clone = game.root / "deps" / "Engine"
    git(clone, "commit", "--quiet", "--allow-empty", "-m", "deps の中でコミット")
    mine = git(clone, "rev-parse", "HEAD")
    assert _state(game).state == "differs"
    with pytest.raises(Exception) as error:
        game.work_dependency("Engine", task=3)
    assert error.value.code == "commits_would_be_lost" and git(clone, "rev-parse", "HEAD") == mine


def test_a_stale_work_setting_does_not_keep_the_clone_working(short_tmp):
    """手で記録の版・ブランチへ切り替えたら、残った作業版の設定は効かない（sync で記録の版に合わせられる）。"""
    engine, game = _game_with_engine(short_tmp)
    recorded = _state(game).recorded
    task = engine.repository.create_task("x")
    workspace = engine.start_task(task.number, name="x")
    _change(workspace.root, "#pragma once\n// w\n")
    clone = game.root / "deps" / "Engine"

    game.work_dependency("Engine", task=task.number)
    git(clone, "switch", "--quiet", "--detach", recorded)   # 1. 手で記録の版に戻す
    assert _state(game).state == "aligned" and _state(game).work is None

    game.work_dependency("Engine", task=task.number)
    git(clone, "switch", "--quiet", "main")   # 2. 手でブランチへ → sync で記録の版に（古い設定は生き返らない）
    assert _state(game).work is None
    assert [(c.name, c.action) for c in game.sync_dependencies()] == [("Engine", "aligned")]
    state = _state(game)
    assert (state.state, state.work, git(clone, "rev-parse", "HEAD")) == ("aligned", None, recorded)
    assert Git(clone).get_config("ecobuild-work.branch") is None
    assert [(c.name, c.action) for c in game.sync_dependencies()] == [("Engine", "unchanged")]


def test_work_ends_when_the_task_is_merged_and_recorded(short_tmp):
    """依存先のタスクが取り込まれ、こちらで deps update したら、作業版は終わり（--done なしで記録の版に合わせる）。"""
    engine, game = _game_with_engine(short_tmp)
    task = engine.repository.create_task("速くする")
    workspace = engine.start_task(task.number, name="fast")
    work = _change(workspace.root, "#pragma once\n// merged\n")
    clone = game.root / "deps" / "Engine"
    game.work_dependency("Engine", task=task.number)
    assert _state(game).state == "working"

    git(engine.root, "merge", "--quiet", "--no-ff", "-m", "取り込み", f"task/{task.number}-fast")   # 依存先で取り込む
    git(engine.root, "push", "--quiet", "origin", "main")
    merged = git(engine.root, "rev-parse", "HEAD")
    assert [(c.name, c.action) for c in game.update_dependencies("Engine")] == [("Engine", "aligned")]
    state = _state(game)
    assert (state.state, state.recorded, state.local, state.work) == ("aligned", merged, merged, None)
    assert git(clone, "merge-base", "--is-ancestor", work, "HEAD") == ""
    assert Git(clone).get_config("ecobuild-work.branch") is None
