"""依存先が GitHub で名前を変えた（moved）：依存元の deps update・deps sync（タスクブランチ）が、記録の URL・場所の名前
（deps/<新しい名前>）・references・手元の clone（origin も）を新しい名前に直す。"""

import json

import pytest

from helpers import git, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecobuild_bundle import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def _solution(root):
    return json.loads((root / ".ecobuild/.cppbuild/solution.json").read_text(encoding="utf-8"))["data"]


def test_moved_dependency_is_followed(short_tmp, monkeypatch):
    engine_github = FakeGitHub(short_tmp / "gh1")
    engine = Module.create("Engine", directory=short_tmp, kind="library", github=engine_github)
    # GitHub の URL（https://github.com/tester/…）を手元の bare へ向ける（GitHub の代わり）
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{(short_tmp / 'gh1').as_uri()}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/tester/")
    github = FakeGitHub(short_tmp / "gh2")
    github.github_urls = True
    github.others["Engine"] = engine_github.bare
    game = Module.create("Game", directory=short_tmp, kind="app", github=github)
    game.repository.create_task("Engine を使う").start()
    game.link("Engine")
    recorded = _solution(game.root)
    assert recorded["git_sources"]["Engine"]["url"] == "https://github.com/tester/Engine.git"

    github.rename_repository("tester/Engine", "Motor")   # 依存先の側で module rename した（bare も Motor.git に）

    # タスクブランチでなければ、直さずに知らせるだけ
    with monkeypatch.context() as patched:
        patched.setattr(game.repository, "current_task_branch", lambda: None)
        assert not any(c.action == "moved" for c in game.sync_dependencies())
    assert any("Motor" in n for n in game.repository.notices)
    assert "Engine" in _solution(game.root)["git_sources"]

    changes = game.sync_dependencies()
    moved = next(c for c in changes if c.action == "moved")
    assert moved.name == "Motor" and "Engine.git" in moved.reason
    data = _solution(game.root)
    assert set(data["git_sources"]) == {"Motor"}
    assert data["git_sources"]["Motor"] == {**recorded["git_sources"]["Engine"], "url": "https://github.com/tester/Motor.git"}
    assert all("deps/Motor" in r["solution_directory"] for r in data["references"].values())
    assert not (game.root / "deps" / "Engine").exists() and (game.root / "deps" / "Motor" / ".git").exists()
    assert git(game.root / "deps" / "Motor", "config", "--get", "remote.origin.url") == "https://github.com/tester/Motor.git"
    assert git(game.root, "log", "-1", "--format=%s") == "依存先の名前の変更に合わせる"
    assert git(game.root, "status", "--porcelain") == ""
    assert {d.name: d.state for d in game.dependencies()} == {"Motor": "aligned"}
    assert game.build().configuration == "Debug"   # 新しい場所でビルドできる

    # もう一度：直すものはない。deps update も新しい名前で
    assert not any(c.action == "moved" for c in game.update_dependencies())
    assert [c.name for c in game.update_dependencies("Motor")] == ["Motor"]


def test_dependency_of_dependency_with_the_old_url(short_tmp, monkeypatch):
    """依存先 Lib も前の URL で Engine を記録していれば直さない（同じリポジトリが2つになる）。Lib が先に直して取り込まれたら、
    deps update の1回で Lib を進め、Lib が取った deps/Motor を使って Engine も直す（前の clone は消す）。"""
    place = short_tmp / "gh"
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{place.as_uri()}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/tester/")
    engine_github = FakeGitHub(place)
    Module.create("Engine", directory=short_tmp, kind="library", github=engine_github)
    lib_github = FakeGitHub(place)
    lib_github.github_urls = True
    lib_github.others["Engine"] = engine_github.bare
    lib = Module.create("Lib", directory=short_tmp, kind="library", github=lib_github)
    lib.repository.create_task("Engine を使う").start()
    lib.link("Engine", project="Lib")
    git(lib.root, "push", "--quiet", "origin", "HEAD:main")
    github = FakeGitHub(place)
    github.github_urls = True
    github.others.update({"Engine": engine_github.bare, "Lib": lib_github.bare})
    game = Module.create("Game", directory=short_tmp, kind="app", github=github)
    game.repository.create_task("使う").start()
    game.link("Engine")
    game.link("Lib")

    for fake in (engine_github, lib_github, github):   # Engine を Motor に（どの偽の GitHub からも同じに見える）
        fake.moved["Engine"] = "Motor"
    engine_github.bare = engine_github.bare.rename(engine_github.bare.with_name("Motor.git"))
    for fake in (lib_github, github):
        fake.others["Motor"] = fake.others.pop("Engine").with_name("Motor.git")
    # GitHub と同じく、前の URL も新しいリポジトリへ転送する（長い方の insteadOf が勝つ）
    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    monkeypatch.setenv("GIT_CONFIG_KEY_1", f"url.{(place / 'Motor.git').as_uri()}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_1", "https://github.com/tester/Engine.git")
    skipped = next(c for c in game.sync_dependencies() if c.name == "Engine")
    assert skipped.action == "skipped" and "Lib" in skipped.reason
    assert "Engine" in _solution(game.root)["git_sources"]

    moved = next(c for c in Module.find(lib.root, github=lib_github).sync_dependencies() if c.action == "moved")
    assert moved.name == "Motor"
    git(lib.root, "push", "--quiet", "origin", "HEAD:main")   # Lib の直しが取り込まれた
    changes = Module.find(game.root, github=github).update_dependencies()
    assert any(c.name == "Motor" and c.action == "moved" for c in changes)
    assert set(_solution(game.root)["git_sources"]) == {"Motor", "Lib"}
    assert not (game.root / "deps" / "Engine").exists() and (game.root / "deps" / "Motor" / ".git").exists()
    assert git(game.root, "status", "--porcelain") == ""
    states = {d.name: d for d in Module.find(game.root, github=github).dependencies()}
    assert states["Lib"].state == "aligned" and states["Lib"].recorded == git(lib.root, "rev-parse", "HEAD")
    assert states["Motor"].state == "aligned"
    assert Module.find(game.root, github=github).build().configuration == "Debug"
