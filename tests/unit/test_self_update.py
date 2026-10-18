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


def test_source_installs_are_not_updated(monkeypatch):
    monkeypatch.setattr(_self_update, "installed", lambda: _self_update.Installed("file:///C:/src", None, None, editable=True))
    with pytest.raises(EcoBuildError) as error:
        _self_update.check()
    assert error.value.code == ErrorCode.NOT_UPDATABLE and "git pull" in error.value.hint
