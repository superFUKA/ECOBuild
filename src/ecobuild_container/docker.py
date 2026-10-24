"""このPCの準備：Docker（作業空間をコンテナで隔離するため。今は導入と診断だけ）。

- Windows：WSL2 の中の ECOBuild 専用のディストリビューション（DISTRO）に Docker Engine を入れ、
  `wsl -d ECOBuild -u root -- docker …` で使う。Docker Desktop 等で docker が既に使えるなら、それを使う。
  WSL2 の有効化だけは管理者の承認（UAC）と再起動が要る。再起動の後にもう一度導入すると続きから進む。
- Linux：docker がなければ apt-get で docker.io を入れ、ユーザーを docker グループに入れる（ログインし直すと効く）。

何度実行してもよい（できている段階は飛ばす）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from ecobuild.errors import operation
from ecobuild.fsutil import kill_tree
from ecobuild.results import DoctorItem

DISTRO = "ECOBuild"          # Windows：Docker Engine を入れる WSL のディストリビューションの名前
IMAGE = "Ubuntu-24.04"       # その元（wsl --install の名前）
NAME = "docker（作業空間の隔離）"
WSL_PACKAGE = ["winget", "install", "--id", "Microsoft.WSL", "--exact", "--silent",
               "--accept-package-agreements", "--accept-source-agreements"]
FIX = "docker"              # DoctorItem.fix：setup --docker・init が導入する（setup --install では入れない）

_APT = "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --yes docker.io"
_START = "systemctl enable --now docker 2>/dev/null || service docker start"
_NO_VIRTUALIZATION = "aka.ms/enablevirtualization"   # wsl --status の案内の URL（文は言語で変わるので URL で見分ける）

Runner = Callable[[list[str]], "Completed"]


@dataclass(frozen=True)
class Completed:
    args: tuple[str, ...]
    returncode: int
    output: str
    timed_out: bool = False      # 時間内に終わらなかった（probe。止めて失敗とみなした）

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class DockerStatus:
    ready: bool
    stage: str              # ready・no_wsl・no_distro・no_engine・not_running（Windows）／no_docker・no_permission・not_running（Linux）
    detail: str
    command: tuple[str, ...] = ()   # docker の呼び方（使えるときだけ）


@dataclass(frozen=True)
class DockerSetup:
    done: tuple[str, ...]   # 行ったこと
    ready: bool             # docker が使える
    restart: str            # 続けるのに要ること（再起動・ログインし直す。なければ空）
    detail: str             # 今の状態
    command: tuple[str, ...] = ()


def run(args: list[str], timeout: float | None = None) -> Completed:
    """実行して出力を取り込む。wsl.exe は UTF-16 で出すことがあるので、NUL を含めば UTF-16 として読む。
    timeout（秒）を過ぎたら子ごと止めて、失敗（timed_out）とする（wsl.exe は中にもう1つ wsl.exe を起こし、外側だけ
    止めると残って WSL を止まらなくする）。"""
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   env={**os.environ, "WSL_UTF8": "1"})
    except OSError as error:
        return Completed(tuple(args), 1, str(error))
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process.pid)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return Completed(tuple(args), 1, f"{timeout:g} 秒たっても応答がありません", True)
    return Completed(tuple(args), process.returncode, _decode(output))


_RUN = run                   # 本物の run（status が時間制限付きの probe に置き換えるもの）
PROBE_SECONDS = 15           # 状態を調べるだけの呼び出しの時間制限（WSL・Docker が固まっていても、一覧等を止めない）


def probe(args: list[str]) -> Completed:
    """状態を調べるだけの呼び出し（状態の表示・ほかの確認）。PROBE_SECONDS で打ち切る。"""
    return _RUN(args, PROBE_SECONDS)


def _decode(data: bytes) -> str:
    if b"\x00" in data:
        return data.decode("utf-16-le", errors="replace").replace("\x00", "")
    return data.decode("utf-8", errors="replace")


def elevated(args: list[str]) -> list[str]:
    """Windows：管理者として実行するコマンド（UAC の画面が出る。断ると失敗）。終了コードは元のコマンドのもの。
    出力は別の窓に出るので取り込めない。"""
    quoted = ",".join("'" + arg.replace("'", "''") + "'" for arg in args[1:])
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
            f"$p = Start-Process -FilePath '{args[0]}' -ArgumentList {quoted} -Verb RunAs -Wait -PassThru; "
            "exit $p.ExitCode"]


def wsl(*args: str) -> list[str]:
    """DISTRO の中で root として実行するコマンド。--exec：シェルを通さない（-- だと bash を通り、引数の ' や $ が崩れる）。"""
    return ["wsl", "-d", DISTRO, "-u", "root", "--exec", *args]


def status(runner: Runner | None = None, *, windows: bool | None = None, wake: bool = True) -> DockerStatus:
    """docker が使えるか（デーモンに繋がるか）を調べる。Windows で WSL の中を調べるときは、その中を起動する。
    wake=False（状態を見せるだけ。GUI が窓のたびに読む等）：WSL の DISTRO が止まっていれば起こさず、使えるもの（stage
    sleeping。中のコンテナも止まっている）として答える。起こすと 15 秒ほどは動き続け、何度も読むと WSL が止まらない。"""
    # 本物の呼び出しは時間制限付きで（WSL の中が固まると wsl -d … は返らず、workspace list 等が終わらなくなる）
    runner = probe if runner is None or runner is _RUN else runner
    windows = os.name == "nt" if windows is None else windows
    if not wake and windows and shutil.which("docker") is None and shutil.which("wsl") is not None:
        sleeping = _sleeping(runner)
        if sleeping is not None:
            return sleeping
    timed_out: list[list[str]] = []

    def watched(args: list[str]) -> Completed:
        done = runner(args)
        if getattr(done, "timed_out", False):
            timed_out.append(args)
        return done

    found = _status(watched, windows)
    if timed_out and not found.ready:   # 「ありません」ではなく、応答しないこととして知らせる
        inside = timed_out[0][:2] == ["wsl", "-d"]
        return DockerStatus(False, "not_running",
                            f"WSL の {DISTRO} が応答しません（wsl --shutdown で止めると直ることがあります）" if inside
                            else f"{' '.join(timed_out[0][:2])} が {PROBE_SECONDS} 秒たっても応答しません")
    return found


def _names(runner: Runner, *options: str) -> set[str]:
    return {line.strip().casefold() for line in runner(["wsl", "--list", *options, "--quiet"]).output.splitlines()
            if line.strip()}


def _sleeping(runner: Runner) -> DockerStatus | None:
    """WSL の DISTRO があって止まっていれば、その状態（wsl --list は Windows 側だけで答え、ディストリを起こさない）。"""
    if DISTRO.casefold() not in _names(runner) or DISTRO.casefold() in _names(runner, "--running"):
        return None
    return DockerStatus(True, "sleeping", f"WSL の {DISTRO} は止まっています（使うときに起動します）", tuple(wsl("docker")))


def _status(runner: Runner, windows: bool) -> DockerStatus:
    if shutil.which("docker") is not None:
        version = runner(["docker", "version", "--format", "{{.Server.Version}}"])
        if version.ok:
            return DockerStatus(True, "ready", f"Docker {version.output.strip()}", ("docker",))
        if not windows:
            denied = "permission denied" in version.output.lower()
            return DockerStatus(False, "no_permission" if denied else "not_running",
                                "docker を使う権限がありません（docker グループ）" if denied else "Docker のデーモンに繋がりません")
    if not windows:
        return DockerStatus(False, "no_docker", "見つかりません")
    if shutil.which("wsl") is None or not (found := runner(["wsl", "--status"])).ok:
        return DockerStatus(False, "no_wsl", "WSL2 がありません")
    if _NO_VIRTUALIZATION in found.output:   # WSL 本体はあるが、仮想マシン プラットフォームが無効（終了コードは 0）
        return DockerStatus(False, "no_wsl", "WSL2 が有効になっていません（仮想マシン プラットフォーム）")
    names = runner(["wsl", "--list", "--quiet"])
    if DISTRO.casefold() not in (line.strip().casefold() for line in names.output.splitlines()):
        return DockerStatus(False, "no_distro", f"WSL に {DISTRO} がありません")
    if not runner(wsl("sh", "-c", "command -v docker")).ok:
        return DockerStatus(False, "no_engine", f"WSL の {DISTRO} に Docker がありません")
    version = runner(wsl("docker", "version", "--format", "{{.Server.Version}}"))
    if not version.ok:
        return DockerStatus(False, "not_running", f"WSL の {DISTRO} の Docker が動いていません")
    return DockerStatus(True, "ready", f"Docker {version.output.strip()}（WSL の {DISTRO}）", tuple(wsl("docker")))


def doctor_item(runner: Runner | None = None, *, command: str = "") -> DoctorItem:
    runner = runner or run
    found = status(runner)
    return DoctorItem(NAME, found.ready, False, found.detail if found.ready else f"{found.detail}（なくても使えます）",
                      f"{operation(command, 'setup')} --docker で導入できます（作業空間をコンテナで隔離するときに使います）。", FIX)


def install(runner: Runner | None = None, *, windows: bool | None = None,
            progress: Callable[[str], None] = lambda message: None, command: str = "") -> DockerSetup:
    """docker が使えるまで、足りない段階を順に行う。再起動・ログインし直すことが要れば、そこで止まる。
    command：ヒントに書くプログラム名（errors.operation）。"""
    runner = runner or run
    windows = os.name == "nt" if windows is None else windows
    done: list[str] = []
    again = f"もう一度 {operation(command, 'setup')} --docker を実行してください"


    def step(message: str, args: list[str]) -> bool:
        progress(message)
        completed = runner(args)
        if not completed.ok:
            done.append(f"{message}：失敗しました（終了コード {completed.returncode}）"
                        + (f"\n{completed.output.strip()}" if completed.output.strip() else ""))
        return completed.ok

    def result(restart: str = "") -> DockerSetup:
        found = status(runner, windows=windows)
        return DockerSetup(tuple(done), found.ready, "" if found.ready else restart, found.detail, found.command)

    found = status(runner, windows=windows)
    if not windows:
        if found.stage == "no_docker":
            if not step("Docker（docker.io）を導入します", ["sudo", "sh", "-c", _APT]):
                return result()
            done.append("Docker（docker.io）を導入しました")
            found = status(runner, windows=windows)
        if found.stage == "not_running" and step("Docker を起動します", ["sudo", "sh", "-c", _START]):
            found = status(runner, windows=windows)
        if found.stage == "no_permission":
            user = os.environ.get("USER", "")
            if user and step(f"{user} を docker グループに入れます", ["sudo", "usermod", "--append", "--groups", "docker", user]):
                done.append(f"{user} を docker グループに入れました")
            return result(f"ログインし直してから（グループが効くように）、{again}。")
        return result()

    if found.stage == "no_wsl":
        # Windows に最初からある wsl.exe は案内だけで、--install 以外を受け付けない。先に WSL 本体を入れる
        if not runner(["wsl", "--version"]).ok:
            if not step("WSL 本体を導入します（winget。管理者の承認の画面が出ます）", elevated(WSL_PACKAGE)):
                return result()
            done.append("WSL 本体を導入しました")
        if not step("WSL2 を有効にします（管理者の承認の画面が出ます）",
                    elevated(["wsl", "--install", "--no-distribution"])):
            return result()
        done.append("WSL2 を有効にしました")
        found = status(runner, windows=windows)
        if found.stage == "no_wsl":
            return result(f"PC を再起動してから（WSL2 の有効化を終えるため）、{again}。")
    if found.stage == "no_distro":
        if not step(f"WSL に {DISTRO}（{IMAGE}）を作ります",
                    ["wsl", "--install", IMAGE, "--name", DISTRO, "--no-launch"]):
            return result()
        done.append(f"WSL に {DISTRO}（{IMAGE}）を作りました")
        found = status(runner, windows=windows)
    if found.stage == "no_engine":
        if not step(f"WSL の {DISTRO} に Docker（docker.io）を導入します", wsl("sh", "-c", _APT)):
            return result()
        done.append(f"WSL の {DISTRO} に Docker（docker.io）を導入しました")
        found = status(runner, windows=windows)
    if found.stage == "not_running" and step(f"WSL の {DISTRO} の Docker を起動します", wsl("sh", "-c", _START)):
        done.append(f"WSL の {DISTRO} の Docker を起動しました")
    return result()
