"""open：ファイル・フォルダーを、この PC の道具（既定のアプリ・エクスプローラー・Visual Studio）で開く。

道具は起こさない：起こす口（subprocess.Popen・os.startfile）と、Visual Studio を探す口を偽物にして、何を頼んだかを確かめる。"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from helpers import write
from ecowork import github as _github
from ecobuild_cli import _open, build_cli

pytestmark = pytest.mark.local


@pytest.fixture
def cli(module, monkeypatch):
    monkeypatch.setattr(_github, "default", lambda: module.repository.github)
    monkeypatch.chdir(module.root)
    runner = CliRunner()

    def invoke(*args):
        return runner.invoke(build_cli(), list(args), catch_exceptions=False)

    return invoke


@pytest.fixture
def started(monkeypatch):
    """起こした道具の記録（コマンドライン。既定のアプリは ["startfile", 場所]）。"""
    calls = []
    monkeypatch.setattr(_open, "_start", lambda line, cwd=None: calls.append([str(word) for word in line]))
    monkeypatch.setattr(_open, "_start_default", lambda place: calls.append(["startfile", str(place)]))
    monkeypatch.setattr(_open, "_windows", lambda: True)
    return calls


@pytest.fixture
def studio(monkeypatch, tmp_path):
    """Visual Studio 2026 だけが入っている PC（2022 はない）。開いている窓はない。"""
    devenv = tmp_path / "devenv.exe"
    devenv.write_text("")
    monkeypatch.setattr(_open, "visual_studio", lambda version: str(devenv) if version == "2026" else None)
    monkeypatch.setattr(_open, "_processes", lambda opened: [])
    return str(devenv)


def result(done):
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_open_opens_the_module_folder_with_the_default_app(cli, module, started):
    done = result(cli("open", "--json"))
    assert done["ok"] and done["result"]["opened"] == "folder"
    assert started == [["startfile", str(Path(module.root).resolve())]]


def test_open_shows_a_file_selected_in_the_explorer(cli, module, started):
    done = result(cli("open", "README.md", "--app", "explorer", "--json"))
    assert done["result"]["opened"] == "reveal"
    assert started == [["explorer", "/select,", str((Path(module.root) / "README.md").resolve())]]
    started.clear()
    assert result(cli("open", "README.md", "--json"))["result"]["opened"] == "file"   # 既定のアプリ
    assert started == [["startfile", str((Path(module.root) / "README.md").resolve())]]


def test_open_tells_a_missing_path(cli, started):
    done = cli("open", "ない.txt", "--json")
    assert done.exit_code == 1 and result(done)["error"]["code"] == "file_not_found" and started == []
    assert result(cli("open", "ない.txt", "--can", "--json"))["result"]["can"] is False


def test_open_with_visual_studio_opens_the_solution_or_the_folder(cli, module, started, studio):
    root = Path(module.root).resolve()
    done = result(cli("open", "--app", "vs", "--json"))["result"]   # ソリューションがまだない：フォルダーとして
    assert done["opened"] == "folder" and done["version"] == "2026" and started == [[studio, str(root)]]
    started.clear()
    write(root / "build" / "x64" / "Calc.sln", "")
    done = result(cli("open", "--app", "vs", "--json"))["result"]
    assert done["opened"] == "solution" and started == [[studio, str(root / "build" / "x64" / "Calc.sln")]]


def test_open_with_the_solution_refuses_until_a_build_made_one(cli, module, started, studio):
    # C++（ソリューションを作る型）：まだなければ開かずに no_solution（画面は「ビルドしてから開きますか？」を出す）
    root = Path(module.root).resolve()
    done = cli("open", "--app", "vs", "--solution", "--json")
    assert done.exit_code == 1 and result(done)["error"]["code"] == "no_solution" and started == []
    write(root / "build" / "x64" / "Calc.slnx", "")
    done = result(cli("open", "--app", "vs", "--solution", "--json"))["result"]
    assert done["opened"] == "solution" and done["name"] == "Calc.slnx" and started == [[studio, str(root / "build" / "x64" / "Calc.slnx")]]
    assert cli("open", "--app", "explorer", "--solution", "--json").exit_code == 2   # vs のときだけ


def test_open_a_file_with_visual_studio_goes_to_the_line(cli, module, started, studio):
    target = str((Path(module.root) / "README.md").resolve())
    done = result(cli("open", "README.md", "--app", "vs", "--line", "12", "--json"))["result"]
    assert done["opened"] == "file" and done["line"] == 12
    assert started == [[studio, "/edit", target, "/command", "Edit.GoTo 12"]]


def test_open_tells_why_a_version_of_visual_studio_cannot_be_used(cli, started, studio):
    can = result(cli("open", "--app", "vs", "--vs-version", "2022", "--can", "--json"))["result"]
    assert can["can"] is False and "2022" in can["reason"] and "2026" in can["reason"]   # あるのは 2026
    assert result(cli("open", "--app", "vs", "--vs-version", "2026", "--can", "--json"))["result"] == {"can": True, "reason": ""}
    done = cli("open", "--app", "vs", "--vs-version", "2022", "--json")
    assert done.exit_code == 1 and result(done)["error"]["code"] == "tool_missing" and started == []


def test_open_refuses_unknown_tools_and_versions(cli, started):
    assert cli("open", "--app", "notepad", "--json").exit_code == 2
    assert cli("open", "--app", "vs", "--vs-version", "2019", "--json").exit_code == 2
    assert cli("open", "--line", "3", "--json").exit_code == 2   # --line は Visual Studio だけ
    assert started == []


def test_visual_studio_is_only_on_windows(cli, started, studio, monkeypatch):
    monkeypatch.setattr(_open, "_windows", lambda: False)
    can = result(cli("open", "--app", "vs", "--can", "--json"))["result"]
    assert can["can"] is False and "Windows" in can["reason"]


def test_the_editor_is_visual_studio_or_else_the_default_app(cli, module, started, studio, monkeypatch):
    target = str((Path(module.root) / "README.md").resolve())
    done = result(cli("open", "README.md", "--app", "editor", "--line", "3", "--json"))["result"]
    assert done["app"] == "vs" and started == [[studio, "/edit", target, "/command", "Edit.GoTo 3"]]
    started.clear()
    monkeypatch.setattr(_open, "visual_studio", lambda version: None)   # Visual Studio がない PC：既定のアプリで
    done = result(cli("open", "README.md", "--app", "editor", "--line", "3", "--json"))["result"]
    assert done["app"] == "default" and started == [["startfile", target]]
    assert result(cli("open", "README.md", "--app", "editor", "--can", "--json"))["result"]["can"] is True
