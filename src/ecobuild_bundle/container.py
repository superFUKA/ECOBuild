"""作業空間をコンテナにする（このPCで、作業空間ごとに選ぶ）。

選択はその作業空間の ecobuild.local.toml（コミットしない）の container に持つ。フォルダを動かしても選択はついてくる。
ファイルは今までどおりこのPC（Windows 等）に置き、コンテナにはその作業空間のフォルダだけを /work として見せる。
コンテナは作業空間ごとに1つ（名前は作業空間の場所から決まる）。root ではなく一般ユーザー（uid 1000）で動かす。
ビルド・テスト・エージェントをコンテナの中で動かすのはこれから（今はこのPCで動く）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from ecobuild import config as _config
from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, ErrorCode, operation

from . import docker

KEY = "container"
IMAGE_KEY = "container_image"   # ecobuild.local.toml：使うイメージ（なければ IMAGE）
IMAGE = "ubuntu:24.04"
WORKDIR = "/work"
USER = "1000:1000"
LABEL = "ecobuild.workspace"    # コンテナに付けるラベル：作業空間の場所


@dataclass(frozen=True)
class WorkspaceContainer:
    path: Path
    container: bool         # この作業空間をコンテナにする
    changed: bool           # 今回の操作で選択・コンテナを変えた
    docker_ready: bool      # このPCで Docker が使える
    docker_detail: str      # Docker の今の状態
    name: str = ""          # コンテナの名前
    state: str = "none"     # コンテナ：none（まだない）・running・exited 等（docker の State.Status）。Docker が使えなければ unknown
    image: str = ""


def enabled(root: Path) -> bool:
    return _config.load_local(root).get(KEY) is True


def name(root: Path) -> str:
    """作業空間のコンテナの名前：ecobuild-<フォルダ名>-<場所のハッシュ>（同じ名前のフォルダが別の場所にあっても重ならない）。"""
    folder = re.sub(r"[^a-z0-9_.-]+", "-", Path(root).name.lower()).strip("-.") or "workspace"
    return f"ecobuild-{folder[:40]}-{hashlib.sha1(_workspaces.key(root).encode()).hexdigest()[:8]}"


def image(root: Path) -> str:
    return _config.load_local(root).get(IMAGE_KEY) or IMAGE


def mount_path(root: Path, command: tuple[str, ...]) -> str:
    """docker に渡す作業空間の場所。WSL の中の docker には /mnt/<ドライブ>/... で渡す。"""
    if command[:1] != ("wsl",):
        return str(root)
    path = PureWindowsPath(root)
    drive = path.drive.rstrip(":").lower()
    return f"/mnt/{drive}/" + "/".join(path.parts[1:])


def show(root: Path, runner: docker.Runner | None = None) -> WorkspaceContainer:
    return _result(root, enabled(root), False, runner)


def choose(root: Path, container: bool, runner: docker.Runner | None = None, *,
           command: str = "") -> WorkspaceContainer:
    """コンテナにするかを選ぶ（Docker がなくても選べる。使うときに Docker が要る）。
    コンテナにしないなら、作ったコンテナも消す（ファイルは作業空間にあるので失わない）。"""
    local = _config.load_local(root)
    changed = (local.get(KEY) is True) != container
    if not container and _exists(root, runner):
        remove(root, runner, command=command)
        changed = True
    if (local.get(KEY) is True) != container:   # changed は、コンテナを消しただけのときも True
        local[KEY] = True if container else None   # 選ばないときは書かない（既定はコンテナにしない）
        _config.save_local(root, local)
    return _result(root, container, changed, runner)


def start(root: Path, runner: docker.Runner | None = None, *, command: str = "") -> WorkspaceContainer:
    """コンテナを動かす（なければ作る）。"""
    if not enabled(root):
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{root} はコンテナにしていません。",
                            hint=f"{operation(command, 'container on')} でコンテナにできます。")
    prefix = _docker(runner, command)
    state = _state(root, runner, prefix)
    if state == "running":
        return _result(root, True, False, runner)
    if state == "none":
        _run(runner, [*prefix, "run", "--detach", "--init", "--name", name(root), "--label", f"{LABEL}={root}",
                      "--volume", f"{mount_path(root, prefix)}:{WORKDIR}", "--workdir", WORKDIR, "--user", USER,
                      image(root), "sleep", "infinity"], "コンテナを作れませんでした")
    else:
        _run(runner, [*prefix, "start", name(root)], "コンテナを動かせませんでした")
    return _result(root, True, True, runner)


def stop(root: Path, runner: docker.Runner | None = None, *, command: str = "") -> WorkspaceContainer:
    """コンテナを止める（消さない。start でまた動かせる）。"""
    prefix = _docker(runner, command)
    changed = _state(root, runner, prefix) == "running"
    if changed:
        _run(runner, [*prefix, "stop", "--time", "1", name(root)], "コンテナを止められませんでした")
    return _result(root, enabled(root), changed, runner)


def remove(root: Path, runner: docker.Runner | None = None, *, command: str = "") -> WorkspaceContainer:
    """コンテナを消す（作業空間のファイルは残る。コンテナの中で入れたものは消える）。"""
    prefix = _docker(runner, command)
    changed = _state(root, runner, prefix) != "none"
    if changed:
        _run(runner, [*prefix, "rm", "--force", name(root)], "コンテナを消せませんでした")
    return _result(root, enabled(root), changed, runner)


def discard(root: Path, runner: docker.Runner | None = None) -> bool:
    """作業空間を閉じたときに、コンテナがあれば消す（失敗しても閉じる操作は止めない）。消したら True。"""
    try:
        return _exists(root, runner) and remove(root, runner).changed
    except EcoBuildError:
        return False


def _docker(runner: docker.Runner | None, command: str) -> tuple[str, ...]:
    found = docker.status(runner or docker.run)
    if not found.ready:
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"Docker が使えません（{found.detail}）。",
                            hint=f"{operation(command, 'setup')} --docker で導入できます。")
    return found.command


def _state(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...]) -> str:
    found = (runner or docker.run)([*prefix, "inspect", "--format", "{{.State.Status}}", name(root)])
    return found.output.strip() if found.ok else "none"


def _exists(root: Path, runner: docker.Runner | None) -> bool:
    found = docker.status(runner or docker.run)
    return found.ready and _state(root, runner, found.command) != "none"


def _run(runner: docker.Runner | None, args: list[str], message: str) -> None:
    found = (runner or docker.run)(args)
    if not found.ok:
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{message}：{found.output.strip() or f'終了コード {found.returncode}'}")


def _result(root: Path, container: bool, changed: bool, runner: docker.Runner | None) -> WorkspaceContainer:
    found = docker.status(runner or docker.run)
    state = _state(root, runner, found.command) if found.ready else "unknown"
    return WorkspaceContainer(Path(root), container, changed, found.ready, found.detail, name(root), state, image(root))
