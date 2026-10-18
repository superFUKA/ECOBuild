"""作業空間をコンテナにするか（このPCで、作業空間ごとに選ぶ。今は選ぶだけ）。

選択はその作業空間の ecobuild.local.toml（コミットしない）の container に持つ。フォルダを動かしても選択はついてくる。
ファイルは今までどおりこのPC（Windows 等）に置き、コンテナにはその作業空間のフォルダだけを見せる想定。
ビルド・テスト・エージェントをコンテナの中で動かすのはこれから（今はこのPCで動く）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ecobuild import config as _config

from . import docker

KEY = "container"


@dataclass(frozen=True)
class WorkspaceContainer:
    path: Path
    container: bool         # この作業空間をコンテナにする
    changed: bool           # 今回の操作で選択を変えた
    docker_ready: bool      # このPCで Docker が使える
    docker_detail: str      # Docker の今の状態


def enabled(root: Path) -> bool:
    return _config.load_local(root).get(KEY) is True


def show(root: Path, runner: docker.Runner | None = None) -> WorkspaceContainer:
    return _result(root, enabled(root), False, runner)


def choose(root: Path, container: bool, runner: docker.Runner | None = None) -> WorkspaceContainer:
    """コンテナにするかを選ぶ（Docker がなくても選べる。使うときに Docker が要る）。"""
    local = _config.load_local(root)
    changed = (local.get(KEY) is True) != container
    if changed:
        local[KEY] = True if container else None   # 選ばないときは書かない（既定はコンテナにしない）
        _config.save_local(root, local)
    return _result(root, container, changed, runner)


def _result(root: Path, container: bool, changed: bool, runner: docker.Runner) -> WorkspaceContainer:
    found = docker.status(runner or docker.run) if container else None
    return WorkspaceContainer(Path(root), container, changed, bool(found and found.ready), found.detail if found else "")
