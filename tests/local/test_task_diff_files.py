"""task diff --stat・--name-only・--outside：ファイルの一覧（JSON の files）。"""

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


def test_diff_lists_files_with_counts(cli, module):
    root = module.root
    assert cli("task", "new", "差分", "--start", "--name", "差分").exit_code == 0
    write(root / "src" / "a.txt", "1\n2\n")
    write(root / "docs" / "b.md", "b\n")
    git(root, "rm", "--quiet", "README.md")
    git(root, "add", "src/a.txt", "docs/b.md")
    git(root, "commit", "--quiet", "-m", "変える")

    files = json.loads(cli("task", "diff", "--stat", "--json").stdout)["result"]["files"]
    assert {f["path"]: (f["status"], f["added"], f["eol_only"]) for f in files} == {
        "README.md": ("D", 0, False), "docs/b.md": ("A", 1, False), "src/a.txt": ("A", 2, False)}
    assert "3 ファイル" in cli("task", "diff", "--stat").output
    assert cli("task", "diff", "--name-only").output.split() == ["README.md", "docs/b.md", "src/a.txt"]
    assert cli("task", "diff", "--outside", "src/*,README.md").output.split() == ["docs/b.md"]
    assert "diff --git" in cli("task", "diff").output    # 既定は今までどおり全文
    assert cli("task", "diff", "--gui", "--stat").exit_code == 2
