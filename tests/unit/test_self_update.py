"""installer update：入れたときの記録から入れ元と版を知り、GitHub のその版の最新と比べる。"""

import pytest

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_cli import _self_update

OLD, NEW = "a" * 40, "b" * 40


def test_compares_with_the_latest_of_the_installed_branch(monkeypatch):
    monkeypatch.setattr(_self_update, "installed", lambda: _self_update.Installed("https://example.invalid/E", "main", OLD))
    asked = []
    monkeypatch.setattr(_self_update, "_remote_commit", lambda url, ref: asked.append(ref) or NEW)
    result = _self_update.check()
    assert (result.ref, result.current, result.latest, result.up_to_date) == ("main", OLD, NEW, False)
    assert _self_update.check("other").ref == "other" and asked == ["main", "other"]
    assert _self_update.check(OLD).up_to_date            # コミットを指定すれば問い合わせない
    assert asked == ["main", "other"]
    assert _self_update.update(OLD).up_to_date and not _self_update.update(OLD).started   # 最新なら何もしない


def test_update_starts_the_installer_in_another_window(monkeypatch, tmp_path):
    """Windows：別の窓で、この ecobuild が終わってから。その窓のプロセスを返す（GUI はそれが終わってから起動し直す）。
    うまくいけば窓は閉じ、失敗なら Enter を待つ。"""
    monkeypatch.setattr(_self_update.os, "name", "nt")
    monkeypatch.setattr(_self_update, "installed", lambda: _self_update.Installed("https://example.invalid/E", "main", OLD))
    monkeypatch.setattr(_self_update, "_remote_commit", lambda url, ref: NEW)
    monkeypatch.setattr(_self_update, "_installer", lambda url, commit, name: tmp_path / name)
    started = []

    class Process:
        pid = 1234

    monkeypatch.setattr(_self_update.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)
    monkeypatch.setattr(_self_update.subprocess, "Popen", lambda command, **kwargs: started.append(command) or Process())
    result = _self_update.update()
    assert result.started and result.process == 1234
    script = started[0][-1]
    assert "Wait-Process" in script and "-Ref 'main'" in script and "if ($LASTEXITCODE -ne 0)" in script


def test_source_installs_are_not_updated(monkeypatch):
    monkeypatch.setattr(_self_update, "installed", lambda: _self_update.Installed("file:///C:/src", None, None, editable=True))
    with pytest.raises(EcoBuildError) as error:
        _self_update.check()
    assert error.value.code == ErrorCode.NOT_UPDATABLE and "git pull" in error.value.hint
