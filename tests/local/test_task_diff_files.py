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


def test_top_level_diff_and_show_list_files(cli, module):
    """#9-34：ecobuild diff・show にも --stat・--name-only（task diff と同じ形）。"""
    root = module.root
    write(root / "README.md", "変えた\n")
    write(root / "c.txt", "c\n")
    git(root, "add", "c.txt")
    unstaged = json.loads(cli("diff", "--stat", "--json").stdout)["result"]["files"]
    assert [(f["path"], f["status"]) for f in unstaged] == [("README.md", "M")]
    assert cli("diff", "--staged", "--name-only").output.split() == ["c.txt"]
    assert cli("diff", "--name-only", "c.txt").output.strip() == "差分はありません"
    assert "1 ファイル" in cli("diff", "--stat").output
    git(root, "commit", "--quiet", "-am", "変える")
    shown = json.loads(cli("show", "--stat", "--json").stdout)["result"]["files"]
    assert sorted(f["path"] for f in shown) == ["README.md", "c.txt"] and all("eol_only" in f for f in shown)
    assert cli("show", "HEAD", "--name-only").output.split() == ["README.md", "c.txt"]
    assert cli("show", "--gui", "--stat").exit_code == 2


def test_status_warns_about_eol_only_changes(cli, module):
    """#9-1：文字の status にも、改行コードだけの差（JSON の eol_only）を出す。"""
    import subprocess
    root = module.root
    git(root, "config", "core.autocrlf", "false")
    recorded = subprocess.run(["git", "show", "HEAD:README.md"], cwd=root, capture_output=True, check=True).stdout
    (root / "README.md").write_bytes(recorded.replace(b"\r\n", b"\n") if b"\r\n" in recorded else recorded.replace(b"\n", b"\r\n"))
    assert json.loads(cli("status", "--json").stdout)["result"]["eol_only"] == ["README.md"]
    assert "改行コード（CRLF／LF）だけが変わったファイルがあります" in cli("status").output
