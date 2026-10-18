"""作業空間をコンテナにする（このPCで、作業空間ごとに選ぶ）。

選択はその作業空間の ecobuild.local.toml（コミットしない）の container に持つ。フォルダを動かしても選択はついてくる。
ファイルは今までどおりこのPC（Windows 等）に置き、コンテナにはその作業空間のフォルダだけを /work として見せる。
コンテナは作業空間ごとに1つ（名前は作業空間の場所から決まる）。root ではなく一般ユーザー（uid 1000）で動かす。

コンテナの元（イメージ）は ECOBuild が型ごとに作る：Ubuntu に git・gh・uv・ECOBuild（このPCと同じ版）と、
型が使うツール（ModuleType.container_packages）を入れる。中身（Dockerfile）が同じなら作り直さない（名前に中身の
ハッシュ）ので、作るのは最初の1回（と ECOBuild・型のツールが変わったとき）だけ。ecobuild.local.toml の
container_image で、別のイメージを使うこともできる。

中で動かす（run_inside・start_agent）ときは、このPCの GitHub の鍵（gh auth token）と git の名前・メールを環境変数で渡す
（docker exec のたび。コンテナの設定には残らず、コマンドラインにも値を書かない）。中の git は gh を認証に使う。
エージェント（Claude Code）はイメージに入れてあり、ログインはすべてのコンテナで共有するボリューム（AGENT_VOLUME）に残る
（中の CLAUDE_CONFIG_DIR。このPCの ~/.claude は見せない）。中は隔離されているので確認なしで動かし、使わせない道具・
コマンドだけを managed-settings の deny に書く（ダメなものだけを列挙する）。
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
DENY_KEY = "agent_deny"         # ecobuild.local.toml：このコンテナのエージェントに使わせないもの（; 区切り。このPCの設定に足す）
IMAGE_PREFIX = "ecobuild-"      # ECOBuild が作るイメージの名前の頭
BASE = "ubuntu:24.04"           # 作るイメージの元
SOURCE = ("https://github.com/superFUKA/ECOBuild", "feature/mvp")   # 中に入れる ECOBuild（使う側が版を渡さなければ）
WORKDIR = "/work"
USER = "1000:1000"
LABEL = "ecobuild.workspace"    # コンテナに付けるラベル：作業空間の場所
VERSION_LABEL = "ecobuild.container"
VERSION = "2"                   # コンテナの形の版（2：エージェントのボリューム）
HOME = "/home/ubuntu"
AGENT_HOME = f"{HOME}/.claude"  # 中のエージェントの設定・ログイン（CLAUDE_CONFIG_DIR）
AGENT_VOLUME = "ecobuild-agent" # AGENT_HOME に付けるボリューム（すべてのコンテナで共有：ログインは1回）
MANAGED_SETTINGS = "/etc/claude-code/managed-settings.json"
INSIDE = "ECOBUILD_IN_CONTAINER"  # 中で 1（中の ecobuild がもう一度コンテナへ渡さないように）
AGENT_FLAGS = {"claude": ("--dangerously-skip-permissions",)}   # 中で確認なしに動かすときに足すもの
TOKEN_FILE = Path("agents") / "container-token"   # ECOBUILD_HOME の下：中のエージェントのログイン（claude setup-token）
TOKEN_VARIABLE = "CLAUDE_CODE_OAUTH_TOKEN"
# 中のエージェントの初めての質問に先に答えておく（足りないものだけ足す）。.claude.json：初めての案内・/work の信頼。
# settings.json：テーマ・確認なしのモードの注意（コンテナなので出さない）
FIRST_RUN = {
    ".claude.json": {"hasCompletedOnboarding": True, "projects": {WORKDIR: {"hasTrustDialogAccepted": True}}},
    "settings.json": {"theme": "dark", "skipDangerousModePermissionPrompt": True},
}
# 端末の色：docker exec -t は TERM=xterm（16色）にするので、Claude Code のオレンジが赤に寄ってしまう
COLORS = {"TERM": "xterm-256color", "COLORTERM": "truecolor"}


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
    custom_image: str = ""  # この作業空間だけの設定：使うイメージ（空なら型のイメージ）
    deny: tuple[str, ...] = ()   # この作業空間だけの設定：エージェントに使わせないもの（このPCの agent_deny に足す）


@dataclass(frozen=True)
class ContainerImage:
    """ECOBuild が作ったイメージ。current：今の ECOBuild の型のイメージ。used_by：使っているコンテナの作業空間。"""
    name: str
    type: str
    size: str
    created: str
    current: bool
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImageList:
    images: tuple[ContainerImage, ...]
    docker_ready: bool
    docker_detail: str
    missing: tuple[str, ...] = ()   # 今の版のイメージがまだない型
    removed: tuple[str, ...] = ()   # 今回消したイメージ（prune）
    built: tuple[str, ...] = ()     # 今回作ったイメージ（build）


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
        f"ENV PATH={HOME}/.local/bin:$PATH CLAUDE_CONFIG_DIR={AGENT_HOME} {INSIDE}=1",
        f"RUN git config --global --add safe.directory {WORKDIR} \\",   # このPCのファイルは別の持ち主に見える
        " && git config --global credential.https://github.com.helper '!gh auth git-credential'",   # GH_TOKEN で push
        f"RUN mkdir -p {AGENT_HOME} \\",     # ボリュームの持ち主を ubuntu に（初めて付けたときに写る）
        " && curl -fsSL https://claude.ai/install.sh | bash",
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


def start(root: Path, runner: docker.Runner | None = None, *, command: str = "",
          source: tuple[str, str] | None = None,
          progress: Callable[[str], None] = lambda message: None) -> WorkspaceContainer:
    """コンテナを動かす（なければ作る。イメージもなければ作る：最初の1回は数分かかる）。
    source：イメージに入れる ECOBuild（git のリポジトリ, 版）。使う側が今の ECOBuild の入れ元を渡す。渡したときは、
    コンテナのイメージがそれと違えば（ECOBuild を更新した）作り直す。古い形（VERSION）のコンテナも作り直す。"""
    if not enabled(root):
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{root} はコンテナにしていません。",
                            hint=f"{operation(command, 'container on')} でコンテナにできます。")
    prefix = _docker(runner, command)
    state, current, version = _inspect(root, runner, prefix)
    image = _config.load_local(root).get(IMAGE_KEY)
    built = False
    if state != "none":
        if not image and source is not None:
            image, built = _image(root, runner, prefix, source, progress)
        if version != VERSION or (image and image != current):
            progress("コンテナを作り直します（ECOBuild の更新に合わせる。作業空間のファイルはそのまま）")
            _run(runner, [*prefix, "rm", "--force", name(root)], "古いコンテナを消せませんでした")
            state = "none"
    if state == "running":
        return _result(root, True, False, runner)
    if state == "none":
        if not image:
            image, built = _image(root, runner, prefix, source or SOURCE, progress)
        progress("コンテナを作ります")
        _run(runner, [*prefix, "run", "--detach", "--init", "--name", name(root), "--label", f"{LABEL}={root}",
                      "--label", f"{VERSION_LABEL}={VERSION}",
                      "--volume", f"{mount_path(root, prefix)}:{WORKDIR}", "--volume", f"{AGENT_VOLUME}:{AGENT_HOME}",
                      "--workdir", WORKDIR, "--user", USER, image, "sleep", "infinity"], "コンテナを作れませんでした")
    else:
        _run(runner, [*prefix, "start", name(root)], "コンテナを動かせませんでした")
    return _result(root, True, True, runner, built=built)


def _image(root: Path, runner: docker.Runner | None, prefix: tuple[str, ...], source: tuple[str, str],
           progress: Callable[[str], None]) -> tuple[str, bool]:
    """型のイメージ（なければ作る）。作ったら True。作り方は ECOBUILD_HOME/containers/<名前>/Dockerfile に置く。"""
    from . import REGISTRY
    return _type_image(REGISTRY.load(_config.load(root / _config.FILE_NAME).type), runner, prefix, source, progress)


def _type_image(type_class, runner: docker.Runner | None, prefix: tuple[str, ...], source: tuple[str, str],
                progress: Callable[[str], None]) -> tuple[str, bool]:
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
    return found.ready and _state(root, runner, found.command) != "none"


def _run(runner: docker.Runner | None, args: list[str], message: str) -> None:
    found = (runner or docker.run)(args)
    if not found.ok:
        raise EcoBuildError(ErrorCode.CONTAINER_ERROR, f"{message}：{found.output.strip() or f'終了コード {found.returncode}'}")


def _result(root: Path, container: bool, changed: bool, runner: docker.Runner | None, *,
            built: bool = False) -> WorkspaceContainer:
    found = docker.status(runner or docker.run)
    state, image, _ = _inspect(root, runner, found.command) if found.ready else ("unknown", "", "")
    local = _config.load_local(root)
    return WorkspaceContainer(Path(root), container, changed, found.ready, found.detail, name(root), state, image, built,
                              local.get(IMAGE_KEY) or "", split_rules(local.get(DENY_KEY) or ""))


def split_rules(text: str) -> tuple[str, ...]:
    """「;」で区切った許可の規則。"""
    return tuple(rule.strip() for rule in text.split(";") if rule.strip())


def configure(root: Path, *, image: str | None = None, deny: tuple[str, ...] | None = None,
              runner: docker.Runner | None = None) -> WorkspaceContainer:
    """この作業空間のコンテナだけの設定（ecobuild.local.toml）。image：使うイメージ（"" で型のイメージに戻す）。
    deny：エージェントに使わせないもの（() で消す）。イメージを変えると、次の start でコンテナを作り直す。"""
    local = _config.load_local(root)
    before = (local.get(IMAGE_KEY), local.get(DENY_KEY))
    if image is not None:
        local[IMAGE_KEY] = image.strip() or None
    if deny is not None:
        local[DENY_KEY] = ";".join(deny) or None
    changed = (local.get(IMAGE_KEY), local.get(DENY_KEY)) != before
    if changed:
        _config.save_local(root, local)
    return _result(root, enabled(root), changed, runner)


# 中で動かす -------------------------------------------------------------------------------------

def credentials() -> dict[str, str]:
    """中へ渡す環境変数：このPCの GitHub の鍵（gh auth token）と git の名前・メール（なければ渡さない）。"""
    values = {}
    token = os.environ.get("GH_TOKEN") or _output(["gh", "auth", "token"])
    if token:
        values["GH_TOKEN"] = token
    for key, names in (("user.name", ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")),
                       ("user.email", ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"))):
        value = _output(["git", "config", "--global", "--get", key])
        if value:
            values.update(dict.fromkeys(names, value))
    return values


def exec_command(root: Path, prefix: tuple[str, ...], args: list[str] | tuple[str, ...], names: tuple[str, ...] = (),
                 *, directory: str = WORKDIR, tty: bool = False) -> list[str]:
    """コンテナの中で args を実行するコマンド。names：このPCの環境変数から渡すもの（値はコマンドラインに書かない）。"""
    flags = ["--interactive", "--tty", *(item for k, v in COLORS.items() for item in ("--env", f"{k}={v}"))] if tty else []
    passed = [item for each in names for item in ("--env", each)]
    return [*prefix, "exec", *flags, *passed, "--workdir", directory, name(root), *args]


def environment(prefix: tuple[str, ...], values: dict[str, str]) -> dict[str, str]:
    """exec_command に渡す環境。WSL の中の docker には WSLENV で名前を通す。"""
    env = {**os.environ, **values}
    if prefix[:1] == ("wsl",) and values:
        env["WSLENV"] = ":".join(filter(None, [os.environ.get("WSLENV", ""), *values]))
    return env


def inside_path(root: Path, cwd: Path) -> str:
    """このPCの場所 cwd（作業空間の中）に当たる、コンテナの中の場所。"""
    try:
        relative = Path(cwd).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return WORKDIR
    return "/".join([WORKDIR, *relative.parts])


def run_inside(root: Path, args: list[str], *, cwd: Path, command: str = "", source: tuple[str, str] | None = None,
               progress: Callable[[str], None] = lambda message: None, capture: bool = False) -> tuple[int, str]:
    """コンテナの中で args（ecobuild 等）を実行する。(終了コード, 標準出力)。標準出力は capture のときだけ取り込み、
    ほかは流す（標準エラーはいつも流す）。コンテナは動かしてから。"""
    start(root, command=command, source=source, progress=progress)
    prefix = _docker(None, command)
    values = credentials()
    tty = not capture and sys.stdin.isatty() and sys.stdout.isatty()
    argv = exec_command(root, prefix, args, tuple(values), directory=inside_path(root, cwd), tty=tty)
    done = subprocess.run(argv, env=environment(prefix, values), stdout=subprocess.PIPE if capture else None,
                          encoding="utf-8" if capture else None, errors="replace" if capture else None)
    return done.returncode, done.stdout or ""


def outside(value, root: Path):
    """中の場所（/work…）の文字を、このPCの場所に読み替える（結果の JSON の中身）。"""
    if isinstance(value, str) and (value == WORKDIR or value.startswith(WORKDIR + "/")):
        return Path(root).as_posix() + value[len(WORKDIR):]
    if isinstance(value, list):
        return [outside(v, root) for v in value]
    if isinstance(value, dict):
        return {k: outside(v, root) for k, v in value.items()}
    return value


def agent_settings(deny: tuple[str, ...]) -> str:
    """中のエージェントの managed-settings（使わせないものだけ）。"""
    return json.dumps({"permissions": {"deny": list(deny)}}, ensure_ascii=False)


def write_settings(deny: tuple[str, ...]) -> str:
    """managed-settings を書く sh のスクリプト。中身は base64 で渡す（WSL を通すと引数の " が崩れる）。"""
    encoded = base64.b64encode(agent_settings(deny).encode("utf-8")).decode("ascii")
    folder = MANAGED_SETTINGS.rsplit("/", 1)[0]
    return f"mkdir -p {folder} && echo {encoded} | base64 -d > {MANAGED_SETTINGS}"


def start_agent(root: Path, agent: tuple[str, ...], *, deny: tuple[str, ...] = (), command: str = "",
                source: tuple[str, str] | None = None, progress: Callable[[str], None] = lambda message: None):
    """コンテナの中でエージェントを新しい画面で起動する（確認なし。deny に書いたものだけ使わせない）。"""
    import ecoagent
    start(root, command=command, source=source, progress=progress)
    prefix = _docker(None, command)
    _run(None, [*prefix, "exec", "--user", "0", name(root), "sh", "-c", write_settings(deny)],
         "エージェントの設定を書けませんでした")
    _run(None, [*prefix, "exec", name(root), "python3", "-c", first_run_script()], "エージェントの初めての設定を書けませんでした")
    if agent:
        agent = (*agent, *(flag for flag in AGENT_FLAGS.get(agent[0], ()) if flag not in agent))
    values = credentials()
    if token := load_token():
        values[TOKEN_VARIABLE] = token
    argv = exec_command(root, prefix, agent, tuple(values), tty=True)
    try:
        return ecoagent.start(root, argv, env=environment(prefix, values))
    except ecoagent.AgentError as error:
        raise EcoBuildError(ErrorCode.AGENT_ERROR, error.message, hint=error.hint, details=error.code) from error


def _output(args: list[str]) -> str:
    if shutil.which(args[0]) is None:
        return ""
    try:
        done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


# イメージ（ECOBuild の版 × 型ごと。モジュールごとではない） ---------------------------------------

def images(source: tuple[str, str] = SOURCE, runner: docker.Runner | None = None, *, command: str = "") -> ImageList:
    """ECOBuild が作ったイメージの一覧（今の版か・使っているコンテナ）。Docker が使えなければ空。"""
    found = docker.status(runner or docker.run)
    if not found.ready:
        return ImageList((), False, found.detail)
    run = runner or docker.run
    current = _current_images(source)
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
        type_name = image[len(IMAGE_PREFIX):].split(":", 1)[0]
        result.append(ContainerImage(image, type_name, size, created, image in current.values(),
                                     tuple(used.get(image, ()))))
    have = {i.name for i in result}
    missing = tuple(t for t, image in current.items() if image not in have)
    return ImageList(tuple(result), True, found.detail, missing)


def build_images(types: tuple[str, ...] = (), source: tuple[str, str] = SOURCE, runner: docker.Runner | None = None,
                 *, command: str = "", progress: Callable[[str], None] = lambda message: None) -> ImageList:
    """今の ECOBuild の型のイメージを作る（types を省略するとすべての型。あるものは作り直さない）。"""
    from . import REGISTRY
    prefix = _docker(runner, command)
    built = []
    for type_class in REGISTRY.available():
        if types and type_class.name not in types:
            continue
        image, made = _type_image(type_class, runner, prefix, source, progress)
        if made:
            built.append(image)
    listed = images(source, runner, command=command)
    return ImageList(listed.images, listed.docker_ready, listed.docker_detail, listed.missing, (), tuple(built))


def prune_images(source: tuple[str, str] = SOURCE, runner: docker.Runner | None = None, *,
                 command: str = "") -> ImageList:
    """古いイメージ（今の版でなく、どのコンテナも使っていないもの）を消す。"""
    prefix = _docker(runner, command)
    listed = images(source, runner, command=command)
    removed = []
    for image in listed.images:
        if not image.current and not image.used_by:
            _run(runner, [*prefix, "image", "rm", image.name], f"イメージ {image.name} を消せませんでした")
            removed.append(image.name)
    after = images(source, runner, command=command)
    return ImageList(after.images, after.docker_ready, after.docker_detail, after.missing, tuple(removed))


def _current_images(source: tuple[str, str]) -> dict[str, str]:
    from . import REGISTRY
    return {t.name: image_name(t, dockerfile(t, source)) for t in REGISTRY.available()}


def first_run_script() -> str:
    """中のエージェントの設定（AGENT_HOME）に FIRST_RUN を足す python3 のスクリプト（ある値は変えない）。
    中身は base64 で渡す（WSL を通しても崩れないように）。"""
    encoded = base64.b64encode(json.dumps(FIRST_RUN).encode()).decode("ascii")
    return ("import base64,json,os\n"
            f"want=json.loads(base64.b64decode('{encoded}'))\n"
            "def merge(have,add):\n"
            " for k,v in add.items():\n"
            "  if isinstance(v,dict) and isinstance(have.get(k),dict): merge(have[k],v)\n"
            "  elif k not in have: have[k]=v\n"
            "home=os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')\n"
            "for name,add in want.items():\n"
            " path=os.path.join(home,name)\n"
            " try: have=json.load(open(path))\n"
            " except Exception: have={}\n"
            " merge(have,add)\n"
            " tmp=path+'.ecobuild'\n"
            " json.dump(have,open(tmp,'w'),indent=2)\n"
            " os.chmod(tmp,0o600); os.replace(tmp,path)\n")


# 中のエージェントのログイン（トークン） --------------------------------------------------------------
# claude setup-token（このPCで1回、ブラウザーで許可する）が出す長く使えるトークンを覚え、中で起動するときに
# CLAUDE_CODE_OAUTH_TOKEN で渡す（中でログインしなくてよい）。なければ、中で一度ログインする（ボリュームに残る）。

def token_path() -> Path:
    return _settings.home() / TOKEN_FILE


def load_token() -> str:
    try:
        return token_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_token(token: str) -> Path:
    token = token.strip()
    if not token or any(c.isspace() for c in token):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "トークンが空か、空白を含んでいます。",
                            hint="claude setup-token が最後に出す sk-ant-oat… の1行をそのまま貼ってください。")
    path = token_path()
    repository = next((p for p in path.resolve().parents if (p / ".git").exists()), None)
    if repository is not None:     # コミットされてしまう場所には置かない（ECOBUILD_HOME をリポジトリの中にした等）
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"トークンの置き場所 {path} が git のリポジトリ（{repository}）の中です。",
                            hint="コミットされないよう、ECOBUILD_HOME をリポジトリの外にしてください。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def forget_token() -> bool:
    try:
        token_path().unlink()
        return True
    except FileNotFoundError:
        return False


def token_login(command: tuple[str, ...] = ("claude", "setup-token")):
    """このPCで、トークンを作る画面（claude setup-token）を新しい窓で開く。"""
    import ecoagent
    folder = token_path().parent
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return ecoagent.start(folder, command)
    except ecoagent.AgentError as error:
        raise EcoBuildError(ErrorCode.AGENT_ERROR, error.message, hint=error.hint, details=error.code) from error
