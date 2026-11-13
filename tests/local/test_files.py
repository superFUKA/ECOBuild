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
    first = json.loads(cli("files", "--json").stdout)["result"]
    assert first["missing"] == [] and first["generated"] == []   # この型には、道具が作り直すファイルがない
    (root / "README.md").unlink()                      # 消しただけ（まだコミットしていない）
    result = json.loads(cli("files", "--json").stdout)["result"]
    assert "README.md" in result["files"] and result["missing"] == ["README.md"]
    assert "README.md（削除）" in cli("files").output.split()


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


def test_files_tells_the_files_the_tool_makes_again(cli, module, monkeypatch):
    """生成ファイル（道具が作り直すもの）は、型が決める。"""
    monkeypatch.setattr(type(module.type), "is_generated", lambda self, path: path.endswith(".md"))
    result = json.loads(cli("files", "--json").stdout)["result"]
    assert result["generated"] == ["README.md"] and "README.md（生成）" in cli("files").output.split()


def test_module_show_lists_the_kinds_of_the_projects(cli, module):
    result = json.loads(cli("module", "show", "--json").stdout)["result"]
    assert result["projects"] == [p["name"] for p in result["project_list"]]   # 名前の並びと、1件ずつの種類・場所


def test_file_add_folder_makes_an_empty_folder_and_files_lists_it(cli, module):
    """file add --folder：空のフォルダーを作る（git は記録しない）。files は、中にファイルのないフォルダーを folders に出す。"""
    root = module.root
    module.repository.create_task("フォルダー").start()
    result = json.loads(cli("file", "add", "--folder", "docs/memo", "notes", "--json").stdout)["result"]
    assert result["paths"] == ["docs/memo", "notes"] and (root / "docs" / "memo").is_dir()
    assert json.loads(cli("files", "--json").stdout)["result"]["folders"] == ["docs/memo", "notes"]
    assert "notes/（空のフォルダー）" in cli("files").output.split()
    again = json.loads(cli("file", "add", "--folder", "notes", "--json").stdout)
    assert again["ok"] is False and again["error"]["code"] == "already_exists"
    write(root / "notes" / "a.md", "x\n")  # 中にファイルを足すと、空のフォルダーではなくなる
    assert json.loads(cli("files", "--json").stdout)["result"]["folders"] == ["docs/memo"]


def test_status_tells_the_module_name(cli, module):
    assert json.loads(cli("status", "--json").stdout)["result"]["module"] == module.name
