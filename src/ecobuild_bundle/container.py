"""作業空間をコンテナにする（このPCで、作業空間ごとに選ぶ）。

選択はその作業空間の ecobuild.local.toml（コミットしない）の container に持つ。フォルダを動かしても選択はついてくる。
ファイルは今までどおりこのPC（Windows 等）に置き、コンテナにはその作業空間のフォルダだけを /work として見せる。
コンテナは作業空間ごとに1つ（名前は作業空間の場所から決まる）。root ではなく一般ユーザー（uid 1000）で動かす。

コンテナの元（イメージ）は ECOBuild が型ごとに作る：Ubuntu に git・gh・uv・ECOBuild（このPCと同じ版）と、
型が使うツール（ModuleType.container_packages）を入れる。中身（Dockerfile）が同じなら作り直さない（名前に中身の
ハッシュ）ので、作るのは最初の1回（と ECOBuild・型のツールが変わったとき）だけ。ecobuild.local.toml の
container_image で、別のイメージを使うこともできる。
ビルド・テスト・エージェントをコンテナの中で動かすのはこれから（今はこのPCで動く）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable
from pathlib import Path, PureWindowsPath

from ecobuild import config as _config
from ecobuild import settings as _settings
from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, ErrorCode, operation

from . import docker

KEY = "container"
IMAGE_KEY = "container_image"   # ecobuild.local.toml：使うイメージ（なければ型ごとに作る）
BASE = "ubuntu:24.04"           # 作るイメージの元
SOURCE = ("https://github.com/superFUKA/ECOBuild", "feature/mvp")   # 中に入れる ECOBuild（使う側が版を渡さなければ）
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
    image: str = ""         # コンテナのイメージ（コンテナがなければ空）
    built: bool = False     # 今回イメージを作った


def enabled(root: Path) -> bool:
    return _config.load_local(root).get(KEY) is True


def name(root: Path) -> str:
    """作業空間のコンテナの名前：ecobuild-<フォルダ名>-<場所のハッシュ>（同じ名前のフォルダが別の場所にあっても重ならない）。"""
    folder = re.sub(r"[^a-z0-9_.-]+", "-", Path(root).name.lower()).strip("-.") or "workspace"
    return f"ecobuild-{folder[:40]}-{hashlib.sha1(_workspaces.key(root).encode()).hexdigest()[:8]}"


def dockerfile(type_class, source: tuple[str, str] = SOURCE) -> str:
    """作業空間のコンテナのイメージの作り方。source：中に入れる ECOBuild（git のリポジトリ, 版）。"""
    url, ref = source
    packages = " ".join(("ca-certificates", "curl", "git", "gh", "python3", "python3-venv",   # venv：型 python・doctor
                         *type_class.container_packages()))
    return "\n".join([
        f"# ECOBuild が作る、作業空間のコンテナのイメージ（型 {type_class.name}）",
        f"FROM {BASE}",
        "RUN apt-get update \\",
        f" && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends {packages} \\",
        " && rm -rf /var/lib/apt/lists/*",
        "USER ubuntu",
        "ENV PATH=/home/ubuntu/.local/bin:$PATH",
        f"RUN git config --global --add safe.directory {WORKDIR}",   # このPCのファイルは別の持ち主に見える
        "RUN curl -LsSf https://astral.sh/uv/install.sh | sh \\",
        f' && uv tool install --python python3 "git+{url}@{ref}"',
        f"WORKDIR {WORKDIR}",
        "",
    ])


def image_name(type_class, text: str) -> str:
    """イメージの名前：ecobuild-<型>:<作り方のハッシュ>（作り方が同じなら同じ名前＝作り直さない）。"""
    return f"ecobuild-{type_class.name}:{hashlib.sha1(text.encode()).hexdigest()[:12]}"


def mount_path(root: Path, command: tuple[str, ...]) -> str:
    """docker に渡すこのPCの場所。WSL の中の docker には /mnt/<ドライブ>/... で渡す。"""
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


def start(root: Path, runner: docker.Runner | None = None, *, command: str = "", source: tuple[str, str] = SOURCE,
          progress: Callable[[str], None] = lambda message: None) -> WorkspaceContainer:
    """コンテナを動かす（なければ作る。イメージもなければ作る：最初の1回は数分かかる）。
    source：イメージに入れる ECOBuild（git のリポジトリ, 版）。使う側が今の ECOBuild の入れ元を渡す。"""
    if not enabled(root):
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{root} はコンテナにしていません。",
                            hint=f"{operation(command, 'container on')} でコンテナにできます。")
    prefix = _docker(runner, command)
    state = _state(root, runner, prefix)
    if state == "running":
        return _result(root, True, False, runner)
    built = False
    if state == "none":
        image = _config.load_local(root).get(IMAGE_KEY)
        if not image:
            image, built = _image(root, runner, prefix, source, progress)
        progress("コンテナを作ります")
        _run(runner, [*prefix, "run", "--detach", "--init", "--name", name(root), "--label", f"{LABEL}={root}",
                      "--volume", f"{mount_path(root, prefix)}:{WORKDIR}", "--workdir", WORKDIR, "--user", USER,
                      image, "sleep", "infinity"], "コンテナを作れませんでした")
    else:
        _run(runner, [*prefix, "start", name(root)], "コンテナを動かせませんでした")
    return _result(root, True, True, runner, built=built)


def _image(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...], source: tuple[str, str],
           progress: Callable[[str], None]) -> tuple[str, bool]:
    """型のイメージ（なければ作る）。作ったら True。作り方は ECOBUILD_HOME/containers/<名前>/Dockerfile に置く。"""
    from . import REGISTRY
    type_class = REGISTRY.load(_config.load(root / _config.FILE_NAME).type)
    text = dockerfile(type_class, source)
    image = image_name(type_class, text)
    if (runner or docker.run)([*prefix, "image", "inspect", image]).ok:
        return image, False
    directory = _settings.home() / "containers" / image.replace(":", "-")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "Dockerfile").write_text(text, encoding="utf-8", newline="\n")
    progress(f"コンテナのイメージ {image} を作ります（最初の1回だけ。数分かかります）")
    _run(runner, [*prefix, "build", "--tag", image, mount_path(directory, prefix)], "コンテナのイメージを作れませんでした")
    return image, True


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
    return _inspect(root, runner, prefix)[0]


def _inspect(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...]) -> tuple[str, str]:
    """コンテナの状態とイメージ（なければ none と空）。"""
    found = (runner or docker.run)([*prefix, "inspect", "--format", "{{.State.Status}} {{.Config.Image}}", name(root)])
    if not found.ok:
        return "none", ""
    state, _, image = found.output.strip().partition(" ")
    return state, image


def _exists(root: Path, runner: docker.Runner | None) -> bool:
    found = docker.status(runner or docker.run)
    return found.ready and _state(root, runner, found.command) != "none"


def _run(runner: docker.Runner | None, args: list[str], message: str) -> None:
    found = (runner or docker.run)(args)
    if not found.ok:
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{message}：{found.output.strip() or f'終了コード {found.returncode}'}")


def _result(root: Path, container: bool, changed: bool, runner: docker.Runner | None, *,
            built: bool = False) -> WorkspaceContainer:
    found = docker.status(runner or docker.run)
    state, image = _inspect(root, runner, found.command) if found.ready else ("unknown", "")
    return WorkspaceContainer(Path(root), container, changed, found.ready, found.detail, name(root), state, image, built)
