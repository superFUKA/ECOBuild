"""ファイル操作の共通処理：remove_tree は読み取り専用を外して消し直すのを Windows だけで行う。"""

import os

import pytest

from ecobuild import fsutil


def _fail_once(monkeypatch, name):
    """shutil.rmtree の代わり：1つ目のファイルで消せなかったことにして onerror を呼ぶ。"""
    chmods, removed = [], []
    monkeypatch.setattr(fsutil.os, "chmod", lambda target, mode: chmods.append((target, mode)))

    def rmtree(path, onerror):
        error = PermissionError(13, "消せません", str(path))
        onerror(removed.append, str(path), (PermissionError, error, None))
    monkeypatch.setattr(fsutil.shutil, "rmtree", rmtree)
    monkeypatch.setattr(fsutil.os, "name", name)
    return chmods, removed


def test_posix_keeps_permissions_when_it_cannot_remove(monkeypatch, tmp_path):
    chmods, removed = _fail_once(monkeypatch, "posix")
    with pytest.raises(PermissionError):
        fsutil.remove_tree(tmp_path / "dist")
    assert chmods == [] and removed == []   # 権限を変えずに、消せなかった誤りを出す


def test_windows_clears_read_only_and_retries(monkeypatch, tmp_path):
    chmods, removed = _fail_once(monkeypatch, "nt")
    fsutil.remove_tree(tmp_path / "dist")
    assert chmods == [(str(tmp_path / "dist"), fsutil.stat.S_IWRITE)] and removed == [str(tmp_path / "dist")]


def test_removes_a_tree(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "c.txt").write_text("c", encoding="utf-8")
    fsutil.remove_tree(tmp_path / "a")
    assert not (tmp_path / "a").exists() and os.listdir(tmp_path) == []
