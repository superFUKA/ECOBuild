"""eco_gui_setup：新しい GUI の venv の準備（pip は呼ばず、呼び方だけ確かめる）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import eco_gui_setup  # noqa: E402


def test_prepare_installs_once_per_requirements(tmp_path, monkeypatch):
    calls = []

    def run(command, **_):
        calls.append(command)
        if command[1:3] == ["-m", "venv"]:  # venv を作ったことにする
            python = eco_gui_setup.python_of(Path(command[3]))
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    monkeypatch.setattr(eco_gui_setup.subprocess, "run", run)
    venv = tmp_path / "venv"
    eco_gui_setup.prepare(venv)
    assert [c[1:3] for c in calls] == [["-m", "venv"], ["-m", "pip"]]
    assert "--force-reinstall" in calls[1]  # 版の番号が同じでも、コミットが違えば入れ直す
    assert "-r" not in calls[1] and any(word.startswith("GUIFrameWork @ git+") for word in calls[1])  # pip にファイルを読ませない
    eco_gui_setup.prepare(venv)
    assert len(calls) == 2  # requirements.txt が同じなら、入れ直さない
    (venv / "eco_gui-requirements.txt").write_text("古い版", encoding="utf-8")
    eco_gui_setup.prepare(venv)
    assert len(calls) == 3 and calls[2][1:3] == ["-m", "pip"]


def test_setup_reports_failure_without_raising(tmp_path, monkeypatch, capsys):
    def fail(venv):
        raise OSError("書けません")

    monkeypatch.setattr(eco_gui_setup, "prepare", fail)
    assert eco_gui_setup.main(["--venv", str(tmp_path / "venv"), "--no-shortcuts"]) == 1
    assert "準備できませんでした" in capsys.readouterr().err


def test_the_command_is_placed_without_fighting(tmp_path):
    """ecobuild gui の入口（ecobuild-gui）：なければ置く。動く入口がもうあれば（今までの GUI が置いたもの等）触らない。
    指す先がなくなっていれば、置き直す。ecobuild が見つからなければ何もしない。"""
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ecobuild = bin_dir / ("ecobuild.exe" if os.name == "nt" else "ecobuild")
    ecobuild.write_text("", encoding="utf-8")
    python = tmp_path / "venv" / "python.exe"
    python.parent.mkdir()
    python.write_text("", encoding="utf-8")
    assert eco_gui_setup.place_command(None, python) is None and eco_gui_setup.place_command(str(tmp_path / "none"), python) is None
    placed = eco_gui_setup.place_command(str(ecobuild), python)
    assert placed == bin_dir / ("ecobuild-gui.cmd" if os.name == "nt" else "ecobuild-gui")
    text = placed.read_text(encoding="utf-8")
    assert str(python) in text and str(eco_gui_setup.HERE / "ecobuild_gui.py") in text
    # 今までの GUI が、自分の Python で置いたもの：動くので、そのまま
    other = tmp_path / "other" / "python.exe"
    other.parent.mkdir()
    other.write_text("", encoding="utf-8")
    theirs = text.replace(str(python), str(other))
    placed.write_text(theirs, encoding="utf-8", newline="")
    assert eco_gui_setup.place_command(str(ecobuild), python) == placed and placed.read_text(encoding="utf-8") == theirs
    # 指す先（Python）がなくなった：置き直す
    other.unlink()
    assert eco_gui_setup.place_command(str(ecobuild), python) == placed and placed.read_text(encoding="utf-8") == text


def test_setup_places_the_command_next_to_ecobuild(tmp_path, monkeypatch, capsys):
    placed = []
    monkeypatch.setattr(eco_gui_setup, "prepare", lambda venv: None)
    monkeypatch.setattr(eco_gui_setup, "place_command", lambda ecobuild, python=None: placed.append((ecobuild, python)) or None)
    venv = tmp_path / "venv"
    assert eco_gui_setup.main(["--venv", str(venv), "--no-shortcuts", "--ecobuild", "C:/bin/ecobuild.exe"]) == 0
    assert placed == [("C:/bin/ecobuild.exe", eco_gui_setup.python_of(venv))] and "置けませんでした" in capsys.readouterr().out
    assert eco_gui_setup.main(["--venv", str(venv), "--no-shortcuts", "--no-command"]) == 0 and len(placed) == 1
