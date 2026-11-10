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
