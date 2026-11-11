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


def test_module_readme_shows_the_readme_at_the_top(cli, module):
    root = module.root
    write(root / "README.md", "# 題\n\n本文\n")
    write(root / "docs" / "README.md", "別の README\n")  # 下のフォルダーのものは見ない
    result = json.loads(cli("module", "readme", "--json").stdout)["result"]
    assert result == {"path": "README.md", "text": "# 題\n\n本文\n", "truncated": False}
    assert "本文" in cli("module", "readme").output
    (root / "README.md").unlink()
    write(root / "README.txt", "文字だけ\n")           # README.md がなければ、ほかの README
    assert json.loads(cli("module", "readme", "--json").stdout)["result"]["path"] == "README.txt"
    (root / "README.txt").unlink()
    assert json.loads(cli("module", "readme", "--json").stdout)["result"] is None
    assert "README はありません" in cli("module", "readme").output
