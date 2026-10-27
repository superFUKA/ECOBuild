"""installer update：入れたときの記録から入れ元と版を知り、GitHub のその版の最新と比べる。"""

import pytest

from ecobuild.errors import EcoBuildError
from ecobuild_cli._self_update import ErrorCode
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


def test_versions_lists_branches_tags_and_recent_commits(monkeypatch):
    """installer versions：入れたときのブランチが先頭、次に既定のブランチ。タグは新しい版が先。今の版・最新に印。"""
    monkeypatch.setattr(_self_update, "installed", lambda: _self_update.Installed("https://example.invalid/E", "dev", OLD))
    remote = {"--heads": f"{NEW}\trefs/heads/zz\n{NEW}\trefs/heads/main\n{OLD}\trefs/heads/dev\n"
                         f"{OLD}\trefs/tags/v1.9\n{NEW}\trefs/tags/v1.10\n{NEW}\trefs/tags/v1.10^{{}}\n",
              "--symref": f"ref: refs/heads/main\tHEAD\n{NEW}\tHEAD\n"}
    monkeypatch.setattr(_self_update, "_git", lambda *args: remote[args[1]])
    asked = []
    monkeypatch.setattr(_self_update, "_recent_commits",
                        lambda url, ref, count: asked.append((ref, count)) or [(NEW, "2026-10-02T00:00:00+09:00", "新しい"),
                                                                               (OLD, "2026-10-01T00:00:00+09:00", "古い")])
    result = _self_update.versions()
    assert (result.ref, result.default_branch, result.branches, result.tags) == ("dev", "main", ("dev", "main", "zz"), ("v1.10", "v1.9"))
    assert [(c.sha, c.current, c.latest) for c in result.commits] == [(NEW, False, True), (OLD, True, False)]
    assert _self_update.versions("zz", 5).branches == ("zz", "dev", "main") and asked[-1] == ("zz", 5)
    assert _self_update.versions("v1.9").ref == "v1.9"
    with pytest.raises(EcoBuildError) as error:
        _self_update.versions("nothing")
    assert error.value.code == ErrorCode.REVISION_NOT_FOUND


def test_versions_of_a_pinned_commit_start_from_the_default_branch(monkeypatch):
    monkeypatch.setattr(_self_update, "installed", lambda: _self_update.Installed("https://example.invalid/E", OLD, OLD))
    monkeypatch.setattr(_self_update, "_git", lambda *args: f"{NEW}\trefs/heads/main\n" if args[1] == "--heads" else "ref: refs/heads/main\tHEAD\n")
    monkeypatch.setattr(_self_update, "_recent_commits", lambda url, ref, count: [])
    assert _self_update.versions().ref == "main"


def test_recent_commits_are_read_from_the_repository(tmp_path):
    """sha・日時・件名を新しい順に、count まで（偽の GitHub：手元の git のリポジトリ）。"""
    import subprocess
    source = tmp_path / "source"
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(source)], check=True)
    for subject in ("一つ目", "二つ目", "三つ目"):
        subprocess.run(["git", "-C", str(source), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "--quiet", "--allow-empty", "-m", subject], check=True)
    commits = _self_update._recent_commits(source.as_uri(), "main", 2)
    assert [subject for _, _, subject in commits] == ["三つ目", "二つ目"]
    assert all(len(sha) == 40 and "T" in date for sha, date, _ in commits)


def test_source_installs_have_no_versions(monkeypatch):
    monkeypatch.setattr(_self_update, "installed", lambda: _self_update.Installed("file:///C:/src", None, None, editable=True))
    with pytest.raises(EcoBuildError) as error:
        _self_update.versions()
    assert error.value.code == ErrorCode.NOT_UPDATABLE
