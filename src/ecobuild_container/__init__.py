"""拡張：作業空間をコンテナにする（このPCで、作業空間ごとに選ぶ）。Docker（Windows は WSL の中の Docker Engine）を使う。

選択はその作業空間の ecobuild.local.toml（コミットしない）の container に持つ。フォルダを動かしても選択はついてくる。
ファイルは今までどおりこのPC（Windows 等）に置き、コンテナにはその作業空間のフォルダだけを見せる（layout）：
前からの clone は /work、元の clone の worktree（.ecobuild/w/<名前>）は元の .git と自分の作業空間だけを、このPCと同じ
並びで /repo の下に（相対パスの記録が中でもたどれる。元の clone の作業ツリー・兄弟の作業空間は見せない）。
コンテナは作業空間ごとに1つ（名前は作業空間の場所から決まる）。root ではなく一般ユーザー（uid 1000）で動かす。

コンテナの元（イメージ）はモジュールごとに2段で作る：
1. モジュールの環境：作業空間の .ecobuild/container/（Dockerfile。モジュールのリポジトリにコミットし、ほかの端末と共有する。
   モジュールを作るときに型のひな型 dockerfile を置く：ContainerModule.environment_files）。なければ型のひな型。
2. ECOBuild の層：1 の上に git・gh・uv・ECOBuild（このPCと同じ版）と、ほかの拡張が足すもの（Feature）を重ねる
   （ECOBuild の版で変わるので、リポジトリには書かない）。
名前に材料のハッシュを入れる（環境：.ecobuild/container/ の中身。ECOBuild の層：環境の名前＋層の作り方）ので、材料が
同じなら作り直さない。リポジトリの更新で環境が変わる・ECOBuild を更新すると名前が変わり、コンテナは古い（outdated）と分かり、
次の start で作り直す。ecobuild.local.toml の container_image で、別のイメージを使うこともできる。

中で動かす（run_inside・exec_command）ときは、このPCの GitHub の鍵（gh auth token）と git の名前・メールを環境変数で渡す
（docker exec のたび。コンテナの設定には残らず、コマンドラインにも値を書かない）。中の git は gh を認証に使う。
コンテナはほかの拡張を知らない：中に足すもの（イメージに入れるもの・コンテナに付けるもの）は Feature として受け取る
（dev container の feature と同じ考え。使う型の一覧と一緒に、本体＋拡張が use で渡す）。
コンテナの形（ボリューム等）を変えたら VERSION を上げる：古い形のコンテナは start で作り直す（ファイルは作業空間にある）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from collections.abc import Sequence
from typing import TYPE_CHECKING, Callable
from pathlib import Path, PureWindowsPath

from ecobuild import config as _config
from ecobuild import locks
from ecobuild import settings as _settings
from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, WorkError, operation
from ecobuild.errors import ErrorCode as _ErrorCode
from ecobuild.results import CheckItem, CheckReport
from ecowork.git import MINIMUM_VERSION
from ecowork.repository import ACCOUNT_KEY

from . import docker

if TYPE_CHECKING:
    from ecobuild.module_type import ModuleType, Registry


class ErrorCode(_ErrorCode):
    CONTAINER_ERROR = "container_error"   # 作業空間のコンテナ：コンテナにしていない・Docker が使えない・docker が失敗した


KEY = "container"
IMAGE_KEY = "container_image"   # ecobuild.local.toml：使うイメージ（なければモジュールの環境から作る）
DIRECTORY = f"{_config.DIRECTORY}/container"   # モジュールの環境の作り方（Dockerfile。コミット。中のファイルすべてが材料）
DOCKERFILE = f"{DIRECTORY}/Dockerfile"
IMAGE_PREFIX = "ecobuild-"      # ECOBuild が作るイメージの名前の頭（ecobuild-<モジュール>：ECOBuild の層まで）
ENVIRONMENT_PREFIX = "ecobuild-env-"   # モジュールの環境のイメージ（ecobuild-env-<モジュール>）
SOURCE = ("https://github.com/superFUKA/ECOBuild", "feature/mvp")   # 中に入れる ECOBuild（使う側が版を渡さなければ）
WORKDIR = "/work"               # 中の作業空間の場所（前からの clone。worktree の作業空間は workdir(root)）
REPOSITORY = "/repo"            # worktree の作業空間：元の clone に当たる中の場所（.git と作業空間をこの下に同じ並びで付ける）
USER = "1000:1000"
LABEL = "ecobuild.workspace"    # コンテナに付けるラベル：作業空間の場所
VERSION_LABEL = "ecobuild.container"
VERSION = "7"                   # コンテナの形の版（2：エージェントのボリューム。3：エージェントの状態の置き場所。4：マイク。5：型のキャッシュ。
                                # 6：エージェントの設定をコンテナごとに・作業空間を一般ユーザーの持ち物として付ける。
                                # 7：worktree：元の .git と作業空間を同じ並びで付ける）
HOME = "/home/ubuntu"
INSIDE = "ECOBUILD_IN_CONTAINER"  # 中で 1（中の ecobuild がもう一度コンテナへ渡さないように）
# 端末の色：docker exec -t は TERM=xterm（16色）にするので、色が寄ってしまう
COLORS = {"TERM": "xterm-256color", "COLORTERM": "truecolor"}
# 端末で動かすもの（エージェント等）の印。docker exec は、こちらの docker（端末のタブ）が終わっても中のプロセスを止めない
# （閉じたタブ・起動し直した会話の Claude Code が中に残り、同じ会話を2つが書き換えることもある）。そこで docker を
# sh で包み、終わる・切られる（HUP・TERM・INT）と、この印を持つ中のプロセスを止める（STOP_INSIDE）
EXEC_TAG = "ECOBUILD_EXEC"
STOP_INSIDE = ("found() { for f in /proc/[0-9]*/environ; do tr \"\\0\" \"\\n\" <\"$f\" 2>/dev/null | grep -qx \"%s=$1\" "
               "&& { p=${f#/proc/}; echo ${p%%/environ}; }; done; }; "
               "pids=$(found \"$1\"); [ -n \"$pids\" ] || exit 0; kill $pids 2>/dev/null; sleep 1; "
               "pids=$(found \"$1\"); [ -z \"$pids\" ] || kill -9 $pids 2>/dev/null; exit 0") % EXEC_TAG
# 包む sh（引数：印・コンテナ・docker exec …）。docker は裏で動かして待つ（前で待つと、切られても docker が終わるまで
# trap が動かない）。裏で動かすと入力は /dev/null になるので、端末の入力を 3 に取っておいて渡す
STOP_WRAPPER = f"""unset IFS; set +f
tag=$1; box=$2; shift 2
stop() {{ docker exec "$box" sh -c '{STOP_INSIDE}' sh "$tag" >/dev/null 2>&1; }}
quit() {{ kill $child 2>/dev/null; stop; exit $1; }}
trap 'quit 129' HUP; trap 'quit 130' INT; trap 'quit 143' TERM
exec 3<&0
"$@" 0<&3 3<&- &
child=$!
wait $child; code=$?
stop
exit $code
"""


@dataclass(frozen=True)
class Feature:
    """ほかの拡張が作業空間のコンテナに足すもの（コンテナは中身を知らない）。
    packages：イメージに入れる apt のパッケージ。environment：イメージの環境変数 (名前, 値)。install：イメージを作るときに
    一般ユーザーで動かす sh の文（1つの RUN に && でつなぐ）。volumes(root)：コンテナに付けるもの (このPCの場所〔Path〕か
    名前付きボリューム〔str〕, 中の場所)。arguments(prefix)：docker run に足す引数（prefix：docker の呼び方）。
    中身を変えたら、イメージの名前（ハッシュ）が変わって作り直す。付け方を変えたら VERSION を上げる。"""
    name: str
    packages: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    install: tuple[str, ...] = ()
    volumes: Callable[[Path], tuple[tuple[Path | str, str], ...]] = lambda root: ()
    arguments: Callable[[tuple[str, ...]], tuple[str, ...]] = lambda prefix: ()


_registry: "Registry | None" = None   # 型の一覧（型のひな型・ビルドの出力の場所を読む）
_features: dict[str, Feature] = {}


def use(registry: "Registry", features: tuple[Feature, ...] = ()) -> None:
    """使う型の一覧と、ほかの拡張が足すもの（本体＋拡張が、つなぐときに1回渡す）。"""
    global _registry
    _registry = registry
    for feature in features:
        _features[feature.name] = feature


def features() -> tuple[Feature, ...]:
    return tuple(_features.values())


def _type_of(root: Path) -> "type[ModuleType]":
    if _registry is None:
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, "コンテナの拡張に、型の一覧が渡されていません。",
                            hint="ecobuild_container.use(registry) でつないでください（ECOBuild の不具合です）。")
    return _registry.load(_config.load(Path(root) / _config.FILE_NAME).type)


def dockerfile(type_class: "type[ModuleType]") -> str:
    """モジュールのコンテナの環境のひな型（DOCKERFILE。モジュールを作るときに置き、その後はモジュールのもの：解析ツール等を
    足してよい）。ここにはモジュールで要るものだけを書く。ECOBuild 自身（ecobuild・ほかの拡張が足すもの）は、イメージを
    作るときに上に重ねる。Ubuntu に型が使うツール（ModuleType.apt_packages）を入れる。"""
    lines = ["# このモジュールの作業空間のコンテナの環境（ECOBuild がこれを元にイメージを作る）。",
             "# モジュールで要るツールをここに足す。ECOBuild 自身（エージェント・ecobuild 等）は ECOBuild が上に重ねるので書かない。",
             "# apt の使える Ubuntu・Debian を元にする（ECOBuild の層が apt と uid 1000 の利用者を使う）。",
             "FROM ubuntu:24.04"]
    if packages := type_class.apt_packages():
        lines += ["RUN apt-get update \\",
                  f" && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends {' '.join(packages)} \\",
                  " && rm -rf /var/lib/apt/lists/*"]
    return "\n".join(lines) + "\n"


class ContainerModule:
    """Module に重ねる（本体＋拡張が class Module(ContainerModule, ecobuild.Module) とする）：モジュールを作る・最新にする
    ときに環境のひな型を置き、作業空間を閉じたらコンテナも消す。コンテナにした作業空間では、確認（check。task submit の
    中のものも）を中の ecobuild で行う（ビルド・テストに中のツールを使う）。"""

    def container_source(self) -> tuple[str, str] | None:
        """コンテナのイメージに入れる ECOBuild（git のリポジトリ, 版。start の source）。使う側が今の ECOBuild の入れ元を
        返す（CLI）。None なら今のコンテナをそのまま使う。"""
        return None

    def check(self, *, build: bool = True, allow_dependency_mismatch: bool = False,
              only: tuple[str, ...] | None = None, tests: tuple[str, ...] = ()) -> CheckReport:
        if os.environ.get(INSIDE) or not enabled(self.root):
            return super().check(build=build, allow_dependency_mismatch=allow_dependency_mismatch, only=only, tests=tests)
        args = ["ecobuild", "check", "--json", *([] if build else ["--no-build"]),
                *(["--allow-dependency-mismatch"] if allow_dependency_mismatch else []),
                *(["--only", ",".join(only) if only else "none"] if only is not None else []),
                *(["--tests", ",".join(tests)] if tests else [])]
        _, out = run_inside(self.root, args, cwd=self.root, command=self.command, source=self.container_source(),
                            capture=True)
        try:
            doc = outside(json.loads([line for line in out.splitlines() if line.strip()][-1]), self.root)
        except (IndexError, ValueError):
            raise EcoBuildError(ErrorCode.CONTAINER_ERROR, "コンテナの中の確認の結果を読めませんでした。",
                                hint=f"{operation(self.command, 'check')} を実行して、様子を確かめてください。") from None
        if doc.get("ok"):
            return CheckReport(tuple(CheckItem(**item) for item in (doc.get("result") or {}).get("items", ())))
        error = doc.get("error") or {}
        raise EcoBuildError(error.get("code") or ErrorCode.CONTAINER_ERROR,
                            error.get("message") or "コンテナの中の確認が失敗しました。",
                            hint=error.get("hint"), details=error.get("details"))

    @classmethod
    def environment_files(cls, type_class) -> dict[str, str]:
        return {**super().environment_files(type_class), DOCKERFILE: dockerfile(type_class)}

    def save_container_dockerfile(self, text: str, source: tuple[str, str] | None = None,
                                  runner: docker.Runner | None = None) -> "EnvironmentDockerfile":
        """モジュールの環境（DOCKERFILE）を書く（イメージのエディター）。リポジトリのファイルを変えるのでタスクブランチでだけ。
        書くだけで、コミットは今までどおり（task commit）。"""
        self.require_task_branch("コンテナの環境（Dockerfile）の変更")
        return save_environment_dockerfile(self.root, text, source or self.container_source() or SOURCE, runner)

    @classmethod
    def close_workspace(cls, path, **options):
        """閉じたら、その作業空間のコンテナも消す（Docker が使えなければそのまま。中のものは作業空間にない）。
        前からの clone なら、中の作業空間（前の版の作業役 等。一緒に消える）のコンテナも（worktree の作業空間は直下に並び、
        子は中にいない）。"""
        try:   # 閉じると ecobuild.local.toml も消えるので、先に読む
            root = _workspaces.module_root(Path(path))
            nested = () if _linked(root) else _workspaces.inside(root)
            chosen = [place for place in (root, *nested) if enabled(place)]
        except WorkError:
            chosen = []
        closed = super().close_workspace(path, **options)
        if closed.done:
            for place in chosen:
                discard(place)
        return closed


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
    custom_image: str = ""  # この作業空間だけの設定：使うイメージ（空ならモジュールの環境から作るイメージ）
    wanted_image: str = ""  # 今の作り方（.ecobuild/container・ECOBuild の版）のイメージ。分からなければ空
    outdated: bool = False  # コンテナが今の作り方のイメージでない（次の start で作り直す）
    recipe: str = ""        # 環境の作り方：.ecobuild/container/Dockerfile。なければ空（型のひな型を使う）


@dataclass(frozen=True)
class Recipe:
    """作業空間のコンテナのイメージの作り方（モジュールの環境 → ECOBuild の層）。"""
    module: str              # イメージの名前に使うモジュールの名前（小文字）
    environment: str         # モジュールの環境のイメージ：ecobuild-env-<モジュール>:<材料のハッシュ>
    dockerfile: str          # 環境の Dockerfile
    context: Path | None     # 環境の材料のフォルダ（.ecobuild/container/）。なければ None（型のひな型）
    image: str               # ECOBuild の層まで重ねたイメージ：ecobuild-<モジュール>:<ハッシュ>
    layer: str               # ECOBuild の層の Dockerfile


@dataclass(frozen=True)
class EnvironmentDockerfile:
    """作業空間のモジュールの環境（DOCKERFILE）の今の中身と、それから作るイメージ（イメージのエディターが読む）。"""
    path: Path               # 作業空間の .ecobuild/container/Dockerfile
    exists: bool             # 作業空間にある（なければ text は型のひな型）
    text: str                # 中身
    hash: str                # 環境の材料（.ecobuild/container/ の中身）のハッシュ（環境のイメージの名前のタグ）
    environment: str         # 環境のイメージの名前
    image: str               # 環境に ECOBuild を重ねたイメージの名前
    image_ready: bool        # このPCにそのイメージがある（作ってある）
    outdated: bool           # この作業空間のコンテナが、今の作り方のイメージでない（次に動かすときに作り直す）
    container: bool          # この作業空間をコンテナにしている
    container_image: str     # この作業空間のコンテナのイメージ（コンテナがなければ空）
    docker_ready: bool
    docker_detail: str
    changed: bool = False    # 今回書いて中身が変わった


@dataclass(frozen=True)
class ContainerImage:
    """ECOBuild が作ったイメージ。current：今の作業空間が使う作り方のもの。used_by：使っているコンテナの作業空間。
    environment：モジュールの環境（ECOBuild の層の元）。"""
    name: str
    module: str
    size: str
    created: str
    current: bool
    used_by: tuple[str, ...] = ()
    environment: bool = False


@dataclass(frozen=True)
class ImageList:
    images: tuple[ContainerImage, ...]
    docker_ready: bool
    docker_detail: str
    missing: tuple[str, ...] = ()   # 今の作り方のイメージがまだない作業空間（コンテナにしたもの）
    removed: tuple[str, ...] = ()   # 今回消したイメージ（prune）
    built: tuple[str, ...] = ()     # 今回作ったイメージ（build）


def enabled(root: Path) -> bool:
    return _config.load_local(root).get(KEY) is True


def name(root: Path) -> str:
    """作業空間のコンテナの名前：ecobuild-<フォルダ名>-<場所のハッシュ>（同じ名前のフォルダが別の場所にあっても重ならない）。
    元の clone の .ecobuild/w/<名前> なら、フォルダ名は <元のフォルダ名>-<名前>（番号だけでは何のものか分からない）。"""
    root = Path(root)
    shown = f"{root.parents[2].name}-{root.name}" if _in_workspaces(root) else root.name
    folder = re.sub(r"[^a-z0-9_.-]+", "-", shown.lower()).strip("-.") or "workspace"
    return f"ecobuild-{folder[:40]}-{hashlib.sha1(_workspaces.key(root).encode()).hexdigest()[:8]}"


def _in_workspaces(root: Path) -> bool:
    """元の clone の作業空間の置き場所（.ecobuild/w/<名前>）にあるか。"""
    return len(root.parents) > 2 and root.parent.name == "w" and root.parent.parent.name == _config.DIRECTORY


@dataclass(frozen=True)
class Layout:
    """作業空間のコンテナの付け方。workdir：中の作業空間の場所。mounts：(このPCの場所, 中の場所) の並び。"""
    workdir: str
    mounts: tuple[tuple[Path, str], ...]


def layout(root: Path) -> Layout:
    """作業空間 root をコンテナにどう付けるか。元の clone の worktree（linked worktree）なら、元の共通の .git を
    /repo/.git に、作業空間を /repo/<元からの相対> に付け、中でもこのPCと同じ並びにする（git 2.48 の相対パスの記録が
    どちら向きにもたどれる）。元の clone の作業ツリーと兄弟の作業空間は付けない。それ以外（前からの clone）は
    今までどおり root を /work に。"""
    root = Path(root)
    common = _common_directory(root)
    if common is not None:
        try:
            relative = root.resolve().relative_to(common.parent.resolve())
        except ValueError:   # 元の clone の外の worktree：並びを保てないので今までどおり
            relative = None
        if relative is not None and relative.parts:
            inner = "/".join([REPOSITORY, *relative.parts])
            return Layout(inner, ((common, f"{REPOSITORY}/.git"), (root, inner)))
    return Layout(WORKDIR, ((root, WORKDIR),))


def workdir(root: Path) -> str:
    """作業空間 root のコンテナの中の場所（中で動かすものの既定の場所。WORKDIR の代わりに使う）。"""
    return layout(root).workdir


def _linked(root: Path) -> bool:
    return _common_directory(Path(root)) is not None


def _common_directory(root: Path) -> Path | None:
    """root が元の clone の linked worktree なら、共通の .git（このPCの絶対パス）。そうでなければ None。
    .git がフォルダ（前からの clone）なら git を呼ばない。"""
    if not (root / ".git").is_file():
        return None
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-dir",
                               "--git-common-dir"], capture_output=True, text=True, encoding="utf-8",
                              stdin=subprocess.DEVNULL)
    except OSError:
        return None
    lines = done.stdout.strip().splitlines() if done.returncode == 0 else []
    if len(lines) != 2 or Path(lines[0]) == Path(lines[1]):   # submodule 等（共通の .git が自分）
        return None
    return Path(lines[1])


def layer(base: str, source: tuple[str, str] = SOURCE) -> str:
    """ECOBuild の層の作り方：モジュールの環境のイメージ base の上に ECOBuild 自身と、ほかの拡張が足すもの（Feature）を重ねる。
    source：中に入れる ECOBuild（git のリポジトリ, 版）。"""
    url, ref = source
    added = features()
    packages = " ".join(("ca-certificates", "curl", "git", "gh", "python3", "python3-venv",   # venv：型 python・doctor
                         *(package for feature in added for package in feature.packages)))
    environment = " ".join((f"PATH={HOME}/.local/bin:$PATH",
                            *(f"{key}={value}" for feature in added for key, value in feature.environment), f"{INSIDE}=1"))
    install = [("RUN " if index == 0 else " && ") + step + (" \\" if index + 1 < len(feature.install) else "")
               for feature in added for index, step in enumerate(feature.install)]
    return "\n".join([
        f"# ECOBuild が作る、作業空間のコンテナのイメージ（モジュールの環境 {base} の上に ECOBuild を重ねる）",
        f"FROM {base}",
        "USER root",
        GIT_SOURCE,
        "RUN apt-get update \\",
        f" && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends {packages} \\",
        " && rm -rf /var/lib/apt/lists/* \\",
        f" && {GIT_VERSION_CHECK} \\",
        " && (id -u ubuntu >/dev/null 2>&1 || useradd --create-home --uid 1000 --shell /bin/bash ubuntu)",   # Ubuntu 以外の元
        "USER ubuntu",
        f"ENV {environment}",
        "RUN git config --global --add safe.directory '*' \\",   # このPCのファイルは別の持ち主に見える（場所は作業空間ごと）
        " && git config --global credential.https://github.com.helper '!gh auth git-credential'",   # GH_TOKEN で push
        *install,
        "RUN curl -LsSf https://astral.sh/uv/install.sh | sh \\",
        f' && uv tool install --python python3 "git+{url}@{ref}"',
        f"WORKDIR {WORKDIR}",
        "",
    ])


# イメージの git は 2.48 以上（作業空間の worktree を相対パスで記録する。古い git は元の clone ごと開けない）。Ubuntu の
# 標準の git は足りない（24.04 は 2.43）ので、Ubuntu なら git-core の PPA から入れる。鍵は Launchpad が示す PPA の署名の
# 鍵（指紋 F911AB18…6217。PPA の InRelease がこの鍵で署名されているのを確かめた）。Ubuntu 以外の元は、版の確認で
# 止まる（分かる誤り）
GIT_CORE_KEY = "F911AB184317630C59970973E363C90F8F1B6217"
GIT_SOURCE = "\n".join([
    'RUN . /etc/os-release && if [ "$ID" = ubuntu ]; then apt-get update \\',
    " && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends ca-certificates curl \\",
    " && install -d /etc/apt/keyrings \\",
    f" && curl -fsSL 'https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x{GIT_CORE_KEY}'"
    " -o /etc/apt/keyrings/git-core.asc \\",
    ' && echo "deb [signed-by=/etc/apt/keyrings/git-core.asc] https://ppa.launchpadcontent.net/git-core/ppa/ubuntu'
    ' $VERSION_CODENAME main" > /etc/apt/sources.list.d/git-core.list; fi',
])
GIT_VERSION_CHECK = ("git version | awk '{split($3, v, \".\"); if (!(v[1] > %d || (v[1] == %d && v[2] >= %d))) "
                     "{print \"git %d.%d 以上が要ります（\" $3 \"）\" > \"/dev/stderr\"; exit 1}}'"
                     % (MINIMUM_VERSION[0], MINIMUM_VERSION[0], MINIMUM_VERSION[1], MINIMUM_VERSION[0], MINIMUM_VERSION[1]))


def recipe(root: Path, source: tuple[str, str] = SOURCE) -> Recipe:
    """作業空間 root のコンテナのイメージの作り方と名前。名前は材料のハッシュで決まる（作り方が同じなら同じ名前＝作り直さない）：
    環境は .ecobuild/container/ の中のファイルすべて（改行は LF にそろえる。端末によらず同じ名前）、なければ型のひな型。"""
    module_config = _config.load(Path(root) / _config.FILE_NAME)
    module = re.sub(r"[^a-z0-9_.-]+", "-", module_config.name.lower()).strip("-.") or "module"
    folder = Path(root) / DIRECTORY
    digest = hashlib.sha1()
    if (folder / "Dockerfile").is_file():
        text, context = (folder / "Dockerfile").read_text(encoding="utf-8"), folder
        files = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    else:   # ひな型を置いた（module upgrade）だけなら同じ名前（作り直さない）
        text, context = dockerfile(_type_of(root)), None
        files = {"Dockerfile": text.encode()}
    for relative in sorted(files):
        digest.update(relative.encode() + b"\0" + files[relative].replace(b"\r\n", b"\n") + b"\0")
    environment = f"{ENVIRONMENT_PREFIX}{module}:{digest.hexdigest()[:12]}"
    top = layer(environment, source)
    return Recipe(module, environment, text, context, f"{IMAGE_PREFIX}{module}:{hashlib.sha1(top.encode()).hexdigest()[:12]}", top)


def _recipe_or_none(root: Path, source: tuple[str, str]) -> Recipe | None:
    try:
        return recipe(root, source)
    except (WorkError, OSError):
        return None


def environment_dockerfile(root: Path, source: tuple[str, str] = SOURCE, runner: docker.Runner | None = None, *,
                           changed: bool = False) -> EnvironmentDockerfile:
    """作業空間 root のモジュールの環境（DOCKERFILE。なければ型のひな型）と、それから作るイメージの名前・このPCにあるか・
    この作業空間のコンテナが古いか。Docker が使えなくても中身と名前は返す。"""
    made = recipe(root, source)
    found = docker.status(runner or docker.run)   # 調べるのは1回（Windows では WSL を何度も呼ぶ）
    shown = _result(root, enabled(root), False, runner, source=source, found=found)
    ready = found.ready and (runner or docker.run)([*found.command, "image", "inspect", made.image]).ok
    return EnvironmentDockerfile(Path(root) / DOCKERFILE, made.context is not None, made.dockerfile,
                                 made.environment.rpartition(":")[2], made.environment, made.image, ready, shown.outdated,
                                 shown.container, shown.image, shown.docker_ready, shown.docker_detail, changed)


def save_environment_dockerfile(root: Path, text: str, source: tuple[str, str] = SOURCE,
                                runner: docker.Runner | None = None) -> EnvironmentDockerfile:
    """モジュールの環境（DOCKERFILE）を text にする（改行は LF。最後に改行を付ける）。タスクブランチかは使う側が確かめる
    （ContainerModule.save_container_dockerfile）。書いても、イメージは次に作る・動かすときに作る。"""
    body = text.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"
    if not body.strip():
        raise EcoBuildError(_ErrorCode.INVALID_ARGUMENT, "Dockerfile が空です。",
                            hint="FROM から始まる中身を渡してください（空にはできません）。")
    path = Path(root) / DOCKERFILE
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    if before != body:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8", newline="\n")
    return environment_dockerfile(root, source, runner, changed=before != body)


def mount_path(root: Path, command: tuple[str, ...], *, owned: bool = False) -> str:
    """docker に渡すこのPCの場所。WSL の中の docker には /mnt/<ドライブ>/... で渡す。owned：中の一般ユーザーの持ち物として
    付けたドライブ（OWNED_MOUNTS。prepare_owned_mount が付ける）の場所。"""
    if command[:1] != ("wsl",):
        return str(root)
    path = PureWindowsPath(root)
    drive = path.drive.rstrip(":").lower()
    return f"{OWNED_MOUNTS if owned else '/mnt'}/{drive}/" + "/".join(path.parts[1:])


# WSL が付ける Windows のドライブ（/mnt/c 等）は root の持ち物で、中の一般ユーザー（USER）は chmod できない（pip install
# --editable が egg-info で Operation not permitted になり、build・test・check が通らなかった）。作業空間は、ドライブを
# USER の持ち物として付け直した所（OWNED_MOUNTS）から付ける。WSL の設定（wsl.conf）は変えない（変えると WSL を起動し直す
# 必要があり、動いているコンテナが止まる）。WSL を起動し直すと消えるので、コンテナを作るたびに確かめる。
OWNED_MOUNTS = "/mnt/ecobuild"
USER_ID = "1000"   # USER（ubuntu）の uid・gid（ubuntu のイメージの一般ユーザー）


LINE_ENDING_KEYS = ("core.autocrlf", "core.eol")


def align_line_endings(root: Path) -> list[str]:
    """このPCの git で効いている改行コードの設定（Git for Windows の既定の core.autocrlf=true 等。system・global の設定）を、
    作業空間の clone の設定（--local）に写す。中の git は clone の設定しか読まないので、写さないと同じファイルを違って見る
    （このPCが CRLF で書き出したファイルが、中では触っていないのに変更ありになり、提出が止まった）。clone に設定があれば
    変えない。写した設定の名前を返す。"""
    copied = []
    for key in LINE_ENDING_KEYS:
        def get(*scope: str) -> str:
            try:
                done = subprocess.run(["git", "-C", str(root), "config", *scope, "--get", key], capture_output=True,
                                      text=True, stdin=subprocess.DEVNULL)
            except OSError:
                return ""
            return done.stdout.strip() if done.returncode == 0 else ""
        value = get()
        if value and not get("--local"):
            subprocess.run(["git", "-C", str(root), "config", "--local", key, value], capture_output=True,
                           stdin=subprocess.DEVNULL)
            copied.append(key)
    return copied


def prepare_owned_mount(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...]) -> str:
    """作業空間 root のドライブを USER の持ち物として付け（付いていなければ）、docker に渡す場所を返す。付けられなければ
    WSL のいつもの場所（chmod はできない）。WSL でなければそのまま。"""
    return mount_path(root, prefix, owned=own_drive(root, runner, prefix))


def own_drive(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...]) -> bool:
    """root のドライブを USER の持ち物として付ける（付いていなければ）。付いたら True（mount_path の owned）。
    WSL でなければ何もしない（False）。付け直す単位はドライブなので、同じドライブの場所（元の .git と作業空間）は1回で済む。"""
    if prefix[:1] != ("wsl",):
        return False
    drive = PureWindowsPath(root).drive.rstrip(":")
    place = f"{OWNED_MOUNTS}/{drive.lower()}"
    script = (f"mountpoint -q {place} || {{ mkdir -p {place} && "
              f"mount -t drvfs {drive.upper()}: {place} -o uid={USER_ID},gid={USER_ID}; }}")
    return (runner or docker.run)([*prefix[:-1], "sh", "-c", script]).ok


def show(root: Path, runner: docker.Runner | None = None, *, source: tuple[str, str] | None = None) -> WorkspaceContainer:
    """状態。source（今の ECOBuild の入れ元）を渡すと、コンテナが今の作り方のイメージか（outdated）も調べる。"""
    return _result(root, enabled(root), False, runner, source=source)


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


def start(root: Path, runner: docker.Runner | None = None, *, command: str = "",
          source: tuple[str, str] | None = None,
          progress: Callable[[str], None] = lambda message: None) -> WorkspaceContainer:
    """コンテナを動かす（なければ作る。イメージもなければ作る：最初の1回は数分かかる）。
    source：イメージに入れる ECOBuild（git のリポジトリ, 版）。使う側が今の ECOBuild の入れ元を渡す。渡したときは、
    コンテナのイメージが今の作り方のものと違えば（ECOBuild を更新した・.ecobuild/container が変わった）作り直す。
    古い形（VERSION）のコンテナも作り直す。"""
    if not enabled(root):
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{root} はコンテナにしていません。",
                            hint=f"{operation(command, 'container on')} でコンテナにできます。")
    prefix = docker_command(runner, command)
    state, current, version = _inspect(root, runner, prefix)
    image = _config.load_local(root).get(IMAGE_KEY)
    built, environment = False, ""
    if state != "none":
        if not image and source is not None:
            image, built, environment = _image(root, runner, prefix, source, progress)
        if version != VERSION or (image and image != current):
            progress("コンテナを作り直します（ECOBuild の更新・コンテナの環境の変更に合わせる。作業空間のファイルはそのまま）")
            run_docker(runner, [*prefix, "rm", "--force", name(root)], "古いコンテナを消せませんでした")
            state = "none"
    if state == "running":
        return _result(root, True, False, runner)
    if state == "none":
        if not image:
            image, built, environment = _image(root, runner, prefix, source or SOURCE, progress)
        progress("コンテナを作ります")
        added = features()
        volumes = [(source_, place) for feature in added for source_, place in feature.volumes(Path(root))]
        place = layout(root)
        owned = own_drive(root, runner, prefix)
        align_line_endings(root)
        run_docker(runner, [*prefix, "run", "--detach", "--init", "--name", name(root), "--label", f"{LABEL}={root}",
                            "--label", f"{VERSION_LABEL}={VERSION}",
                            *(item for outer, inner in place.mounts
                              for item in ("--volume", f"{mount_path(outer, prefix, owned=owned)}:{inner}")),
                            *(item for source_, place in volumes for item in ("--volume", f"{_volume(source_, prefix)}:{place}")),
                            *(item for feature in added for item in feature.arguments(prefix)),
                            *(item for volume, place in caches(root) for item in ("--volume", f"{volume}:{place}")),
                            "--workdir", place.workdir, "--user", USER, image, "sleep", "infinity"], "コンテナを作れませんでした")
        if caches(root):   # 新しいボリュームは root のものになるので、中の一般ユーザーが書けるように
            run_docker(runner, [*prefix, "exec", "--user", "0", name(root), "chown", USER, *(place for _, place in caches(root))],
                 "キャッシュの置き場所を用意できませんでした")
        tidy(image, runner, prefix)   # 作り直した：前の版のイメージは、もうどのコンテナも使っていなければ消す
        if environment:
            tidy(environment, runner, prefix)   # 前の環境（ほかのイメージの元になっていれば消えない）
    else:
        run_docker(runner, [*prefix, "start", name(root)], "コンテナを動かせませんでした")
    return _result(root, True, True, runner, built=built)


def _volume(source: Path | str, prefix: tuple[str, ...]) -> str:
    """付けるもの：このPCの場所（なければ作る）か、名前付きボリューム。"""
    if isinstance(source, Path):
        source.mkdir(parents=True, exist_ok=True)
        return mount_path(source, prefix)
    return source


def tidy(keep: str, runner: docker.Runner | None, prefix: tuple[str, ...]) -> tuple[str, ...]:
    """keep と同じモジュール（同じリポジトリの名前）の、ECOBuild が作った前の版のイメージのうち、どのコンテナも使っていない
    ものを消す（ECOBuild の更新・環境の変更でイメージの名前が変わるので、放っておくと増える）。消せなくても止めない。
    消したものを返す。"""
    repository = keep.rsplit(":", 1)[0]
    if not repository.startswith(IMAGE_PREFIX):
        return ()     # 作業空間で指定したイメージ（ECOBuild が作ったものでない）は触らない
    run = runner or docker.run
    listed = run([*prefix, "image", "ls", repository, "--format", "{{.Repository}}:{{.Tag}}"])
    used = run([*prefix, "ps", "--all", "--format", "{{.Image}}"])
    if not listed.ok or not used.ok:
        return ()
    first = lambda output: [line.split()[0] for line in output.splitlines() if line.strip()]
    in_use = set(first(used.output))
    removed = []
    for image in first(listed.output):
        if image != keep and image not in in_use and run([*prefix, "image", "rm", image]).ok:
            removed.append(image)
            shutil.rmtree(_settings.home() / "containers" / image.replace(":", "-"), ignore_errors=True)
    return tuple(removed)


def _image(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...], source: tuple[str, str],
           progress: Callable[[str], None]) -> tuple[str, bool, str]:
    """作業空間のイメージ（なければ作る）。(イメージ, 作ったか, 環境のイメージ)。"""
    found = recipe(root, source)
    return found.image, _build(found, runner, prefix, progress), found.environment


def _build(found: Recipe, runner: docker.Runner | None, prefix: tuple[str, ...],
           progress: Callable[[str], None]) -> bool:
    """イメージを作る（あれば作らない）。作ったら True。環境の材料は .ecobuild/container/（なければ型のひな型を
    ECOBUILD_HOME/containers/<名前>/ に置く）、ECOBuild の層の作り方も ECOBUILD_HOME/containers/<名前>/ に置く。"""
    run = runner or docker.run
    if run([*prefix, "image", "inspect", found.image]).ok:
        return False
    if not run([*prefix, "image", "inspect", found.environment]).ok:
        context = found.context or _write_dockerfile(found.environment, found.dockerfile)
        progress(f"モジュールの環境のイメージ {found.environment} を作ります（"
                 f"{DOCKERFILE if found.context else '型のひな型'}から。数分かかることがあります）")
        run_docker(runner, [*prefix, "build", "--tag", found.environment, mount_path(context, prefix)],
             "モジュールの環境のイメージを作れませんでした")
    progress(f"コンテナのイメージ {found.image} を作ります（環境に ECOBuild を重ねる。数分かかります）")
    run_docker(runner, [*prefix, "build", "--tag", found.image, mount_path(_write_dockerfile(found.image, found.layer), prefix)],
         "コンテナのイメージを作れませんでした")
    return True


def _write_dockerfile(image: str, text: str) -> Path:
    directory = _settings.home() / "containers" / image.replace(":", "-")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "Dockerfile").write_text(text, encoding="utf-8", newline="\n")
    return directory


def stop(root: Path, runner: docker.Runner | None = None, *, command: str = "") -> WorkspaceContainer:
    """コンテナを止める（消さない。start でまた動かせる）。"""
    prefix = docker_command(runner, command)
    changed = container_state(root, runner, prefix) == "running"
    if changed:
        run_docker(runner, [*prefix, "stop", "--time", "1", name(root)], "コンテナを止められませんでした")
    return _result(root, enabled(root), changed, runner)


def remove(root: Path, runner: docker.Runner | None = None, *, command: str = "") -> WorkspaceContainer:
    """コンテナを消す（作業空間のファイルは残る。コンテナの中で入れたものは消える）。"""
    prefix = docker_command(runner, command)
    changed = container_state(root, runner, prefix) != "none"
    if changed:
        run_docker(runner, [*prefix, "rm", "--force", name(root)], "コンテナを消せませんでした")
        for volume in own_volumes(root):   # 型のキャッシュ（ビルドの出力など）・ほかの拡張のこのコンテナだけのものも消す
            (runner or docker.run)([*prefix, "volume", "rm", "--force", volume])
    return _result(root, enabled(root), changed, runner)


def own_volumes(root: Path) -> list[str]:
    """このコンテナだけのボリューム：型のキャッシュと、ほかの拡張が足したもののうち名前がコンテナの名前で始まるもの
    （共有のものは残す）。"""
    owned = [volume for volume, _ in caches(root)]
    for feature in features():
        owned += [source for source, _ in feature.volumes(Path(root))
                  if isinstance(source, str) and source.startswith(name(root) + "-") and source not in owned]
    return owned


def caches(root: Path) -> list[tuple[str, str]]:
    """型のビルドの出力（ModuleType.build_outputs）の [(ボリュームの名前, 中の場所)]。作業空間（このPCのフォルダ）の代わりに
    コンテナの側に置く（中から権限を変えられ、速く、このPCのビルドの出力と混ざらない）。"""
    try:
        type_class = _type_of(root)
    except WorkError:
        return []
    inner = workdir(root)
    return [(f"{name(root)}-{re.sub(r'[^a-z0-9_.-]+', '-', place.lower()).strip('-.') or 'cache'}", f"{inner}/{place}")
            for place in type_class.build_outputs()]


def discard(root: Path, runner: docker.Runner | None = None) -> bool:
    """作業空間を閉じたときに、コンテナがあれば消す（失敗しても閉じる操作は止めない）。消したら True。"""
    try:
        return _exists(root, runner) and remove(root, runner).changed
    except EcoBuildError:
        return False


def docker_command(runner: docker.Runner | None, command: str) -> tuple[str, ...]:
    """このPCの docker の呼び方（WSL の中なら wsl を前に）。Docker が使えなければ止める。"""
    found = docker.status(runner or docker.run)
    if not found.ready:
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"Docker が使えません（{found.detail}）。",
                            hint=f"{operation(command, 'setup')} --docker で導入できます。")
    return found.command


def container_state(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...]) -> str:
    """作業空間のコンテナの状態（none：まだない・running・exited 等）。"""
    return _inspect(root, runner, prefix)[0]


def _inspect(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...]) -> tuple[str, str, str]:
    """コンテナの状態・イメージ・形の版（なければ none と空）。"""
    labels = '{{index .Config.Labels "' + VERSION_LABEL + '"}}'
    found = (runner or docker.run)([*prefix, "inspect", "--format", "{{.State.Status}} {{.Config.Image}} " + labels,
                                    name(root)])
    if not found.ok:
        return "none", "", ""
    state, image, version = (found.output.strip().split() + ["", ""])[:3]
    return state, image, version


def _exists(root: Path, runner: docker.Runner | None) -> bool:
    found = docker.status(runner or docker.run)
    return found.ready and container_state(root, runner, found.command) != "none"


def lock_source(roots: "Sequence[Path]") -> "list[list[locks.Detected]]":
    """作業空間のロックの理由（ecobuild.locks.add_source）：その作業空間のコンテナが動いている間。
    コンテナにしている作業空間があるときだけ、docker を呼ぶ（1回の ps でまとめて調べる。docker が使えなければ、ロックなし）。"""
    found: list[list] = [[] for _ in roots]
    boxed = [i for i, root in enumerate(roots) if enabled(root)]
    if not boxed:
        return found
    status = docker.status(docker.run)
    if not status.ready:
        return found
    listed = docker.run([*status.command, "ps", "--filter", "status=running", "--format", "{{.Names}} {{.ID}}"])
    if not listed.ok:
        return found
    running = {parts[0]: (parts[1] if len(parts) > 1 else "") for line in listed.output.splitlines()
               if (parts := line.split())}
    for i in boxed:
        container_name = name(roots[i])
        if container_name in running:
            found[i].append((locks.Reason(locks.CONTAINER, f"この作業空間のコンテナ {container_name} が動いています"),
                             f"container:{container_name}:{running[container_name]}"))
    return found


def run_docker(runner: docker.Runner | None, args: list[str], message: str) -> None:
    """docker を動かす。失敗したら message に docker の出力を付けて止める。"""
    found = (runner or docker.run)(args)
    if not found.ok:
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{message}：{found.output.strip() or f'終了コード {found.returncode}'}")


def _result(root: Path, container: bool, changed: bool, runner: docker.Runner | None, *,
            built: bool = False, source: tuple[str, str] | None = None,
            found: docker.DockerStatus | None = None) -> WorkspaceContainer:
    found = found or docker.status(runner or docker.run)
    state, image, _ = _inspect(root, runner, found.command) if found.ready else ("unknown", "", "")
    local = _config.load_local(root)
    custom = local.get(IMAGE_KEY) or ""
    wanted = custom or (made.image if source is not None and (made := _recipe_or_none(root, source)) else "")
    has_recipe = (Path(root) / DOCKERFILE).is_file()
    return WorkspaceContainer(Path(root), container, changed, found.ready, found.detail, name(root), state, image, built,
                              custom, wanted, bool(wanted and image and image != wanted),
                              DOCKERFILE if has_recipe else "")


def configure(root: Path, *, image: str | None = None, runner: docker.Runner | None = None) -> WorkspaceContainer:
    """この作業空間のコンテナだけの設定（ecobuild.local.toml）。image：使うイメージ（"" で型のイメージに戻す）。
    イメージを変えると、次の start でコンテナを作り直す。"""
    local = _config.load_local(root)
    before = local.get(IMAGE_KEY)
    if image is not None:
        local[IMAGE_KEY] = image.strip() or None
    changed = local.get(IMAGE_KEY) != before
    if changed:
        _config.save_local(root, local)
    return _result(root, enabled(root), changed, runner)


# 中で動かす -------------------------------------------------------------------------------------

def credentials(root: Path | None = None) -> dict[str, str]:
    """中へ渡す環境変数：このPCの GitHub の鍵（gh auth token）と git の名前・メール（なければ渡さない）。
    作業空間 root にアカウントを結び付けていれば（ecowork.account。AI 用のアカウント等）、そのアカウントの鍵と、
    その clone の名前・メール。--local に限らずに読む（worktree の作業空間ごとの値は --worktree の設定にある）。"""
    values = {}
    account = _output(["git", "-C", str(root), "config", "--get", ACCOUNT_KEY]) if root is not None else ""
    token = _output(["gh", "auth", "token", "--user", account]) if account else \
        os.environ.get("GH_TOKEN") or _output(["gh", "auth", "token"])
    if token:
        values["GH_TOKEN"] = token
    for key, names in (("user.name", ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")),
                       ("user.email", ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"))):
        value = _output(["git", "-C", str(root), "config", "--get", key] if account else ["git", "config", "--global", "--get", key])
        if value:
            values.update(dict.fromkeys(names, value))
    return values


def exec_command(root: Path, prefix: tuple[str, ...], args: list[str] | tuple[str, ...], names: tuple[str, ...] = (),
                 *, directory: str | None = None, tty: bool = False, stdin: bool = False, tag: str = "") -> list[str]:
    """コンテナの中で args を実行するコマンド。names：このPCの環境変数から渡すもの（値はコマンドラインに書かない）。
    directory：中の場所（省略すると作業空間：workdir(root)）。
    tty（端末で動かす）なら、終わる・切られると中のプロセスも止める（EXEC_TAG）。stdin：端末なしで標準入力を渡し続ける
    （閉じると中のプロセスに入力の終わりが届く）。tag：中のプロセスに印を付ける（stop_tagged で止められる）。"""
    flags = ["--interactive", "--tty", *(item for k, v in COLORS.items() for item in ("--env", f"{k}={v}"))] if tty         else ["--interactive"] if stdin else []
    passed = [item for each in names for item in ("--env", each)]
    command = [*prefix, "exec", *flags, *(("--env", f"{EXEC_TAG}={tag}") if tag and not tty else ()), *passed,
               "--workdir", directory or workdir(root), name(root), *args]
    if not tty:
        return command
    tag = uuid.uuid4().hex[:16]
    command[len(prefix) + 1:len(prefix) + 1] = ["--env", f"{EXEC_TAG}={tag}"]
    wrapper = _stop_wrapper(prefix)
    return [*wrapper, tag, name(root), *command[len(prefix) - 1:]] if wrapper else command


def _stop_wrapper(prefix: tuple[str, ...]) -> list[str]:
    """docker を包む sh（STOP_WRAPPER）。WSL の中の docker なら WSL の sh、Linux・macOS ならこの PC の sh。
    Windows で docker を直に使う（Docker Desktop 等）なら sh がないので包まない（空）。
    中身は base64 で渡す（WSL を通すと引数の " が崩れる）。IFS を空にして、展開した文を分けずに eval する。"""
    if prefix[-1:] != ("docker",):
        return []
    if prefix[:1] != ("wsl",) and os.name == "nt":
        return []
    encoded = base64.b64encode(STOP_WRAPPER.encode("utf-8")).decode("ascii")
    return [*prefix[:-1], "sh", "-c", f"set -f; IFS=; eval $(echo {encoded} | base64 -d)", "sh"]


def stop_tagged(root: Path, tag: str, runner: docker.Runner | None = None, *, command: str = "") -> None:
    """exec_command の tag の印を持つ中のプロセスを止める（コンテナが動いていなければ何もしない）。"""
    found = docker.status(runner or docker.run)
    if found.ready and tag:
        (runner or docker.run)([*found.command, "exec", name(root), "sh", "-c", STOP_INSIDE, "sh", tag])


def environment(prefix: tuple[str, ...], values: dict[str, str]) -> dict[str, str]:
    """exec_command に渡す環境。WSL の中の docker には WSLENV で名前を通す。"""
    env = {**os.environ, **values}
    if prefix[:1] == ("wsl",) and values:
        env["WSLENV"] = ":".join(filter(None, [os.environ.get("WSLENV", ""), *values]))
    return env


def inside_path(root: Path, cwd: Path) -> str:
    """このPCの場所 cwd（作業空間の中）に当たる、コンテナの中の場所。"""
    inner = workdir(root)
    try:
        relative = Path(cwd).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return inner
    return "/".join([inner, *relative.parts])


def run_inside(root: Path, args: list[str], *, cwd: Path, command: str = "", source: tuple[str, str] | None = None,
               progress: Callable[[str], None] = lambda message: None, capture: bool = False) -> tuple[int, str]:
    """コンテナの中で args（ecobuild 等）を実行する。(終了コード, 標準出力)。標準出力は capture のときだけ取り込み、
    ほかは流す（標準エラーはいつも流す）。コンテナは動かしてから。"""
    start(root, command=command, source=source, progress=progress)
    prefix = docker_command(None, command)
    values = credentials(root)
    tty = not capture and sys.stdin.isatty() and sys.stdout.isatty()
    argv = exec_command(root, prefix, args, tuple(values), directory=inside_path(root, cwd), tty=tty)
    done = subprocess.run(argv, env=environment(prefix, values), stdout=subprocess.PIPE if capture else None,
                          encoding="utf-8" if capture else None, errors="replace" if capture else None)
    return done.returncode, done.stdout or ""


def outside(value, root: Path):
    """中の場所（作業空間：workdir(root)。/work 等）の文字を、このPCの場所に読み替える（結果の JSON の中身）。"""
    return _outside(value, workdir(root), Path(root).as_posix())


def _outside(value, inner: str, outer: str):
    if isinstance(value, str) and (value == inner or value.startswith(inner + "/")):
        return outer + value[len(inner):]
    if isinstance(value, list):
        return [_outside(v, inner, outer) for v in value]
    if isinstance(value, dict):
        return {k: _outside(v, inner, outer) for k, v in value.items()}
    return value


def _output(args: list[str]) -> str:
    if shutil.which(args[0]) is None:
        return ""
    try:
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


# イメージ（モジュールごと：環境 × ECOBuild の版） --------------------------------------------------

def images(source: tuple[str, str] = SOURCE, runner: docker.Runner | None = None, *, command: str = "") -> ImageList:
    """ECOBuild が作ったイメージの一覧（今の作業空間が使う作り方のものか・使っているコンテナ）。Docker が使えなければ空。
    「今の」は、このPCのコンテナにした作業空間（workspaces.json）の今の作り方（.ecobuild/container・ECOBuild の版）。"""
    found = docker.status(runner or docker.run)
    if not found.ready:
        return ImageList((), False, found.detail)
    run = runner or docker.run
    wanted = _current_recipes(source)
    current = {name for made in wanted.values() for name in (made.image, made.environment)}
    listed = run([*found.command, "image", "ls", "--filter", f"reference={IMAGE_PREFIX}*", "--format",
                  "{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"])
    used: dict[str, list[str]] = {}
    containers = run([*found.command, "ps", "--all", "--filter", f"label={LABEL}", "--format",
                      "{{.Image}}\t{{.Label \"" + LABEL + "\"}}"])
    for line in containers.output.splitlines() if containers.ok else ():
        image, _, place = line.partition("\t")
        used.setdefault(image.strip(), []).append(place.strip())
    result = []
    for line in listed.output.splitlines() if listed.ok else ():
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].startswith(IMAGE_PREFIX):
            continue
        image, size, created = parts[0].strip(), parts[1].strip(), parts[2].strip()
        environment = image.startswith(ENVIRONMENT_PREFIX)
        module = image[len(ENVIRONMENT_PREFIX if environment else IMAGE_PREFIX):].split(":", 1)[0]
        result.append(ContainerImage(image, module, size, created, image in current, tuple(used.get(image, ())),
                                     environment))
    have = {i.name for i in result}
    missing = tuple(str(root) for root, made in wanted.items() if made.image not in have)
    return ImageList(tuple(result), True, found.detail, missing)


def build_images(roots: tuple[Path, ...] = (), source: tuple[str, str] = SOURCE, runner: docker.Runner | None = None,
                 *, command: str = "", progress: Callable[[str], None] = lambda message: None) -> ImageList:
    """作業空間のイメージを今の作り方で作る（roots を省略すると、このPCのコンテナにした作業空間すべて。あるものは
    作り直さない）。作っておくと、コンテナを動かすときに待たずに済む。"""
    prefix = docker_command(runner, command)
    wanted = {Path(root): made for root in roots if (made := recipe(root, source))} if roots else _current_recipes(source)
    built = []
    for made in {made.image: made for made in wanted.values()}.values():   # 同じ作り方の作業空間は1回
        if _build(made, runner, prefix, progress):
            built.append(made.image)
            tidy(made.image, runner, prefix)
            tidy(made.environment, runner, prefix)
    listed = images(source, runner, command=command)
    return ImageList(listed.images, listed.docker_ready, listed.docker_detail, listed.missing, (), tuple(built))


def prune_images(source: tuple[str, str] = SOURCE, runner: docker.Runner | None = None, *,
                 command: str = "") -> ImageList:
    """古いイメージ（今の作り方でなく、どのコンテナも使っていないもの）を消す。環境は後で消す（ほかのイメージの元に
    なっていて消せなければ残す）。"""
    prefix = docker_command(runner, command)
    listed = images(source, runner, command=command)
    removed = []
    for image in sorted(listed.images, key=lambda i: i.environment):
        if not image.current and not image.used_by:
            if image.environment:
                if (runner or docker.run)([*prefix, "image", "rm", image.name]).ok:
                    removed.append(image.name)
                continue
            run_docker(runner, [*prefix, "image", "rm", image.name], f"イメージ {image.name} を消せませんでした")
            removed.append(image.name)
    after = images(source, runner, command=command)
    return ImageList(after.images, after.docker_ready, after.docker_detail, after.missing, tuple(removed))


def _current_recipes(source: tuple[str, str]) -> dict[Path, Recipe]:
    """このPCのコンテナにした作業空間（別のイメージを指定したものを除く）の、今の作り方。"""
    found = {}
    for path in _workspaces.places():
        try:
            mine = enabled(path) and not _config.load_local(path).get(IMAGE_KEY)
        except WorkError:
            continue
        if mine and (made := _recipe_or_none(path, source)):
            found[path] = made
    return found


