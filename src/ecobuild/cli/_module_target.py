"""archive・unarchive・delete の共通処理：対象のモジュール（GitHubのリポジトリ）と、その手元のcloneを決める。

new と同じく「名前」と --owner で指定する（「所有者/名前」も使える）。手元のcloneは、今いるモジュールか、
今いるディレクトリの <名前>（new が作る場所）が、そのモジュールのものなら見つける。
"""

from __future__ import annotations

from ecowork import WorkError

from ..module import Module


def full_name(name: str, owner: str) -> str:
    from .. import tooling
    if "/" in name:
        return name
    owner = owner or tooling.load_config().get("owner")
    return f"{owner}/{name}" if owner else name


def find_clone(inv, repository: str) -> Module | None:
    """repository の手元のclone。なければ None。所有者を省いた名前は、GitHubで 所有者/名前 にしてから探す。"""
    if "/" not in repository:
        from ecowork import github as _github
        repository = _github.default().get_repository(repository).full_name
    short = repository.split("/")[-1]
    for candidate in (inv.cwd, inv.cwd / short):
        try:
            module = Module.find(candidate) if candidate == inv.cwd else Module(candidate, _load(candidate))
        except (WorkError, OSError):
            continue
        if module.repository.github.repository_name(module.root).casefold() == repository.casefold():
            return module
    return None


def _load(root):
    from .. import config as _config
    return _config.load(root / _config.FILE_NAME)
