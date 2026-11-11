"""files：モジュールのファイルの一覧（管理しているものと、新しいファイル。.gitignore の対象は除く）。"""

import json

import pytest
from click.testing import CliRunner

from helpers import git, write
from ecowork import github as _github
from ecobuild_cli import build_cli

pytestmark = pytest.mark.local


@pytest.fixture
def cli(module, monkeypatch):
    monkeypatch.setattr(_github, "default", lambda: module.repository.github)
    monkeypatch.chdir(module.root)
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(build_cli(), list(args), catch_exceptions=False)

    return invoke


def test_files_shows_tracked_and_new_files_but_not_ignored_ones(cli, module):
    root = module.root
    before = json.loads(cli("files", "--json").stdout)["result"]["files"]
    assert "README.md" in before and before == sorted(before)
    write(root / "docs" / "新しい.md", "x\n")           # まだ管理していない新しいファイル
    write(root / ".gitignore", "*.log\n")
    write(root / "build.log", "x\n")                    # .gitignore の対象
    git(root, "rm", "--quiet", "--cached", "README.md")  # 管理から外しただけ（ファイルは残る）
    files = json.loads(cli("files", "--json").stdout)["result"]["files"]
    assert "docs/新しい.md" in files and "README.md" in files and "build.log" not in files
    assert "docs/新しい.md" in cli("files").output.split()


def test_files_tells_the_files_that_are_gone_from_the_folder(cli, module):
    root = module.root
    assert json.loads(cli("files", "--json").stdout)["result"]["missing"] == []
    (root / "README.md").unlink()                      # 消しただけ（まだコミットしていない）
    result = json.loads(cli("files", "--json").stdout)["result"]
    assert "README.md" in result["files"] and result["missing"] == ["README.md"]
    assert "README.md（削除）" in cli("files").output.split()
