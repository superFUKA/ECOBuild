"""eco_gui.shell：窓の開け方（Electron があればアプリの窓、なければ既定）。Electron は起こさない。"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("guiframework")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eco_gui import shell  # noqa: E402


def test_opens_in_electron_when_it_is_installed(tmp_path, monkeypatch):
    exe = tmp_path / "electron.exe"
    exe.write_text("", encoding="utf-8")
    started = []
    monkeypatch.delenv("GUIFRAMEWORK_NO_WINDOW", raising=False)
    monkeypatch.setenv("ECOBUILD_GUI_ELECTRON", str(exe))
    monkeypatch.setenv("ELECTRON_RUN_AS_NODE", "1")
    monkeypatch.setattr(shell.subprocess, "Popen", lambda command, **options: started.append((command, options)))
    shell.open_window("http://127.0.0.1:5000/w/w1#t.s", "ハブ", [900, 720])
    command, options = started[0]
    assert command == [str(exe), str(shell.APP), "--url=http://127.0.0.1:5000/w/w1#t.s", "--title=ハブ", "--size=900x720"]
    assert "ELECTRON_RUN_AS_NODE" not in options["env"]
    assert (shell.APP / "main.js").is_file() and (shell.APP / "package.json").is_file()


def test_falls_back_to_the_default_window_without_electron(tmp_path, monkeypatch):
    opened = []
    monkeypatch.delenv("GUIFRAMEWORK_NO_WINDOW", raising=False)
    monkeypatch.setenv("ECOBUILD_GUI_ELECTRON", str(tmp_path / "ない.exe"))
    monkeypatch.setattr(shell, "open_in_browser", lambda *args: opened.append(args))
    shell.open_window("http://127.0.0.1:5000/w/w1", "ハブ", [900, 720])
    assert opened == [("http://127.0.0.1:5000/w/w1", "ハブ", [900, 720])]


def test_opens_nothing_in_tests(monkeypatch):
    monkeypatch.setenv("GUIFRAMEWORK_NO_WINDOW", "1")
    monkeypatch.setattr(shell.subprocess, "Popen", lambda *a, **k: pytest.fail("開いた"))
    monkeypatch.setattr(shell, "open_in_browser", lambda *a: pytest.fail("開いた"))
    shell.open_window("http://127.0.0.1:5000/w/w1", "ハブ", [900, 720])
