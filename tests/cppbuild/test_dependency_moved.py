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
