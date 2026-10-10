"""ツールの準備：前提ツールの診断（doctor）・設定（setup）と、ツールの設定（config）。

モジュールの外で使う（どのモジュールにも属さない）。I-012・I-030・I-035。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ecotask import _process

from . import _gui
from . import module_type as _module_type
from .errors import EcoBuildError, ErrorCode

# config で扱う項目 → 説明
CONFIG_KEYS = {
    "owner": "new・clone・link で、所有者を省略したリポジトリの所有者（組織名など。既定はログイン中のユーザー）",
}

# 足りないツールの導入コマンド（setup --install で実行する）
INSTALL = {
    "nt": {
        "git": ["winget", "install", "--id", "Git.Git", "--exact", "--silent"],
        "gh": ["winget", "install", "--id", "GitHub.cli", "--exact", "--silent"],
        "cmake": ["winget", "install", "--id", "Kitware.CMake", "--exact", "--silent"],
        "compiler": ["winget", "install", "--id", "Microsoft.VisualStudio.2022.BuildTools", "--exact", "--silent",
                     "--override", "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools "
                                   "--includeRecommended"],
    },
    "posix": {
        "git": ["sudo", "apt-get", "install", "--yes", "git"],
        "gh": ["sudo", "apt-get", "install", "--yes", "gh"],
        "cmake": ["sudo", "apt-get", "install", "--yes", "cmake", "ninja-build"],
        "compiler": ["sudo", "apt-get", "install", "--yes", "g++"],
    },
}


HOME_VARIABLE = "ECOBUILD_HOME"


def home() -> Path:
    """ツールの設定を置くディレクトリ（ECOBUILD_HOME、なければOSの慣例の場所）。"""
    if os.environ.get(HOME_VARIABLE):
        return Path(os.environ[HOME_VARIABLE])
    return default_home()


def default_home() -> Path:
    """ツールの設定を置く既定のディレクトリ（OSの慣例。Windows：%LOCALAPPDATA%\\ecobuild）。"""
    import platformdirs
    return Path(platformdirs.user_config_dir("ecobuild", appauthor=False))


def set_home(path: Path) -> list[str]:
    """ツールの設定を置くディレクトリを変える：作り、今の設定ファイルを写し、ECOBUILD_HOME をユーザーの環境変数に
    保存する（既定の場所なら消す）。行ったことを返す。保存できないOS（Linux 等）では、設定の仕方を返す。"""
    path = Path(path).expanduser().resolve()
    old = home()
    done = []
    path.mkdir(parents=True, exist_ok=True)
    source, target = old / "config.toml", path / "config.toml"
    if source.is_file() and not target.exists() and source.resolve() != target.resolve():
        target.write_bytes(source.read_bytes())
        done.append(f"設定ファイルを {target} に写しました（前の {source} は残しています）")
    value = None if path == default_home().resolve() else str(path)
    if persist_environment(HOME_VARIABLE, value):
        done.append(f"設定を置くディレクトリを {path} にしました"
                    + ("" if value else f"（既定の場所。環境変数 {HOME_VARIABLE} を消しました）"))
    else:
        done.append(f"設定を置くディレクトリを {path} にするには、シェルの起動ファイル（~/.profile 等）に "
                    f"export {HOME_VARIABLE}={path} を書いてください" if value else
                    f"既定の場所を使うには、シェルの起動ファイルから {HOME_VARIABLE} を消してください")
    if value is None:
        os.environ.pop(HOME_VARIABLE, None)
    else:
        os.environ[HOME_VARIABLE] = value
    return done


def persist_environment(name: str, value: str | None) -> bool:
    """ユーザーの環境変数を保存する（None なら消す）。Windows だけ（新しく開く端末から効く）。できたら True。"""
    if os.name != "nt":
        return False
    import ctypes
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        if value is None:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    # 開いているエクスプローラー等に知らせる（ここから開く端末が新しい値を読む）
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
    return True


# ツールの設定 ------------------------------------------------------------------

def load_config() -> dict[str, str]:
    path = home() / "config.toml"
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{path} を読み込めません：{error}") from error
    return {key: value for key, value in data.items() if key in CONFIG_KEYS and isinstance(value, str)}


def set_config(key: str, value: str | None) -> dict[str, str]:
    if key not in CONFIG_KEYS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"設定 {key} はありません。",
                            hint="設定できる項目：" + "、".join(CONFIG_KEYS))
    values = load_config()
    if value is None:
        values.pop(key, None)
    else:
        values[key] = value
    path = home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# ECOBuildのツールの設定（ecobuild config）。"]
    lines += [f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return values


def qualify(repository: str) -> str:
    """所有者のないリポジトリ名に、設定の owner を付ける。"""
    owner = load_config().get("owner")
    return f"{owner}/{repository}" if owner and "/" not in repository else repository


# 診断 -------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckItem:
    name: str
    ok: bool
    required: bool         # Falseなら、なくても使える（警告だけ）
    detail: str
    hint: str = ""
    fix: str = ""          # 直し方：install／setup-git／identity（setup が直す）、login／scope（init が聞いて直す）


@dataclass(frozen=True)
class DoctorReport:
    items: tuple[CheckItem, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok or not item.required for item in self.items)


def doctor() -> DoctorReport:
    """前提ツール・認証・gitの設定・コンパイラを、読み取りだけで調べる。"""
    items = [CheckItem("python", sys.version_info >= (3, 11), True, sys.version.split()[0],
                       "Python 3.11 以上が必要です。")]
    git = _version("git", "--version")
    items.append(CheckItem("git", git is not None, True, git or "見つかりません", "git をインストールしてください。",
                           "install"))
    gh = _version("gh", "--version")
    items.append(CheckItem("gh", gh is not None, True, (gh or "見つかりません").splitlines()[0],
                           "GitHub CLI（gh）をインストールしてください。", "install"))
    if gh is not None:
        status = _run(["gh", "auth", "status"])
        account = next((line.split("account", 1)[1].split()[0] for line in status.output.splitlines()
                        if "Logged in to github.com account" in line), "")
        items.append(CheckItem("gh の認証", status.ok, True, f"ログイン中：{account}" if status.ok else "ログインしていません",
                               "gh auth login を実行してください（ブラウザでログインします）。", "login"))
        if status.ok:
            scopes = next((line.split(":", 1)[1] for line in status.output.splitlines() if "Token scopes" in line), "")
            board = "'project'" in scopes
            items.append(CheckItem("ボードの権限（GitHub Projects）", board, False,
                                   "あります" if board else "ありません（ボードを使うときだけ必要）",
                                   "gh auth refresh -s project を実行してください（ブラウザで承認します）。", "scope"))
        if git is not None:
            helpers = _run(["git", "config", "--get-urlmatch", "credential.helper", "https://github.com"]).stdout
            uses_gh = "auth git-credential" in helpers  # gh auth setup-git が設定するヘルパー
            items.append(CheckItem(
                "git の認証（gh）", uses_gh, False,
                "gh の認証を使います" if uses_gh else "gh の認証を使っていません（push・fetch でアカウントの選択画面が出ることがあります）",
                "ecobuild setup（または gh auth setup-git）で、gitが gh の認証を使うようにできます。", "setup-git"))
    if git is not None:
        name = _run(["git", "config", "--global", "user.name"]).stdout.strip()
        email = _run(["git", "config", "--global", "user.email"]).stdout.strip()
        items.append(CheckItem("git の名前・メール", bool(name and email), True,
                               f"{name} <{email}>" if name and email else "設定されていません",
                               "ecobuild setup --name <名前> --email <メール> で設定できます。", "identity"))
    for module_type in _module_type.available():  # 型が使うツール（cpp：CMake・コンパイラ）
        items += module_type.doctor_items()
    tortoise = _gui.find()
    if os.name == "nt":
        items.append(CheckItem("TortoiseGit", tortoise is not None, False, tortoise or "見つかりません（任意）",
                               "log・diff・blame の --gui に使います。"))
    return DoctorReport(tuple(items))


# 設定 -------------------------------------------------------------------------

@dataclass(frozen=True)
class SetupReport:
    done: tuple[str, ...]          # 行ったこと
    remaining: tuple[CheckItem, ...]  # まだ足りないもの
    commands: tuple[str, ...]      # 足りないツールの導入コマンド（--install なしのとき）


def setup(*, name: str = "", email: str = "", install: bool = False) -> SetupReport:
    """doctor の結果から直せるものを直す。ツールの導入は install のときだけ行う。"""
    done = []
    report = doctor()
    commands = []
    for label, command in install_commands(report):
        if install:
            completed = _run(command)
            done.append(f"{label} を導入しました" if completed.ok else f"{label} の導入に失敗しました")
        else:
            commands.append(" ".join(command))
    if any(i.fix == "setup-git" and not i.ok for i in report.items) and setup_git():
        done.append("gitが gh の認証を使うようにしました（gh auth setup-git）")
    done += set_identity(name, email)
    after = doctor() if done else report
    return SetupReport(tuple(done), tuple(i for i in after.items if not i.ok), tuple(commands))


def install_commands(report: DoctorReport) -> list[tuple[str, list[str]]]:
    """足りないツールの (名前, 導入コマンド)。同じコマンドで入るものは1つにまとめる。"""
    platform = INSTALL["nt" if os.name == "nt" else "posix"]
    result = []
    for item in report.items:
        if item.ok or item.fix != "install":
            continue
        key = item.name if item.name in platform else "compiler" if item.name not in ("cmake", "ctest") else "cmake"
        command = platform.get(key)
        if command is not None and all(command != c for _, c in result):
            result.append((item.name, command))
    return result


def setup_git() -> bool:
    """gitが gh の認証を使うようにする（push・fetch でアカウントの選択画面を出さない）。"""
    return _run(["gh", "auth", "setup-git"]).ok


def set_identity(name: str = "", email: str = "") -> list[str]:
    """gitの名前・メール（--global）を設定する。空なら変えない。行ったことを返す。"""
    done = []
    if name:
        _run(["git", "config", "--global", "user.name", name])
        done.append(f"gitの名前を {name} にしました")
    if email:
        _run(["git", "config", "--global", "user.email", email])
        done.append(f"gitのメールを {email} にしました")
    return done


def github_identity() -> tuple[str, str]:
    """ログイン中のGitHubのアカウントから、gitの名前・メールの候補（名前、なければログイン名／公開のメール、
    なければGitHubの noreply のメール）。取れなければ空。"""
    completed = _run(["gh", "api", "user"])
    if not completed.ok:
        return "", ""
    try:
        user = json.loads(completed.stdout)
    except ValueError:
        return "", ""
    login = user.get("login") or ""
    email = user.get("email") or (f"{user['id']}+{login}@users.noreply.github.com" if login and user.get("id") else "")
    return user.get("name") or login, email


def run_interactive(args: list[str]) -> bool:
    """端末の入出力をそのまま渡して実行する（gh auth login 等、利用者の操作が要るもの）。成功なら True。"""
    import subprocess
    try:
        return subprocess.run(args, check=False).returncode == 0
    except OSError:
        return False


def refresh_path() -> None:
    """導入したツールを、この実行の中でも見つけられるようにする（Windows：レジストリの PATH を読み直す）。"""
    if os.name != "nt":
        return
    import winreg
    parts = []
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(root, key) as handle:
                parts.append(os.path.expandvars(winreg.QueryValueEx(handle, "Path")[0]))
        except OSError:
            continue
    if parts:
        os.environ["PATH"] = os.pathsep.join([*parts, os.environ.get("PATH", "")])


# 初期化（ecobuild init。質問しながら準備する） ------------------------------------------

class Questions:
    """初期化で利用者に聞く方法（CLIは端末で聞く。試験では答えを決めておく）。

    interactive：利用者が操作できる（ブラウザでのログイン等を行う）。False なら、それらは行わずに知らせる。
    """

    interactive = True

    def confirm(self, prompt: str, default: bool = True) -> bool:
        raise NotImplementedError

    def ask(self, prompt: str, default: str = "") -> str:
        raise NotImplementedError

    def info(self, message: str) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class InitReport:
    home: Path                         # ツールの設定を置くディレクトリ
    done: tuple[str, ...]              # 行ったこと
    skipped: tuple[str, ...]           # 聞いて、行わなかったこと
    remaining: tuple[CheckItem, ...]   # まだ足りないもの（必須でないものも含む）


def initialize(questions: Questions) -> InitReport:
    """使い始める準備を、質問しながら行う：ツールの設定を置くディレクトリ、足りないツールの導入、GitHubへの
    ログイン（ボードの権限も）、gitが gh の認証を使う設定、gitの名前・メール、既定の所有者。
    直っているものは聞かない（置き場所と所有者は、今の値を既定にして毎回聞く）。"""
    done, skipped = [], []
    current = home()
    answer = questions.ask("ECOBuild の設定を置くディレクトリ", str(current)).strip()
    if answer and Path(answer).expanduser().resolve() != current.resolve():
        done += set_home(Path(answer))
    else:
        current.mkdir(parents=True, exist_ok=True)

    report = doctor()
    for item in report.items:
        questions.info(("OK " if item.ok else "NG " if item.required else "-- ") + f"{item.name}：{item.detail}")

    for label, command in install_commands(report):
        if questions.confirm(f"{label} がありません。導入しますか？（{' '.join(command)}）"):
            ok = run_interactive(command)
            refresh_path()
            (done if ok else skipped).append(f"{label} を導入しました" if ok else f"{label} の導入に失敗しました")
        else:
            skipped.append(f"{label} の導入")
    report = doctor() if done else report

    def failed(fix: str) -> bool:
        return any(i.fix == fix and not i.ok for i in report.items)

    if not questions.interactive and (failed("login") or failed("scope")):
        skipped.append("GitHub へのログイン・ボードの権限（ブラウザでの操作が要るので、端末で ecobuild init）")
    elif failed("login"):
        if questions.confirm("GitHub にログインしますか？（ブラウザが開きます。ボードの権限も一緒に承認します）"):
            ok = run_interactive(["gh", "auth", "login", "--web", "--git-protocol", "https", "--scopes", "project"])
            (done if ok else skipped).append("GitHub にログインしました" if ok else "GitHub へのログインに失敗しました")
        else:
            skipped.append("GitHub へのログイン")
        report = doctor()
    elif failed("scope"):
        if questions.confirm("タスクのボード（GitHub Projects）の権限がありません。追加しますか？（ブラウザで承認します）"):
            ok = run_interactive(["gh", "auth", "refresh", "--scopes", "project"])
            (done if ok else skipped).append("ボードの権限を追加しました" if ok else "ボードの権限の追加に失敗しました")
        else:
            skipped.append("ボードの権限の追加")
    if failed("setup-git") and setup_git():
        done.append("gitが gh の認証を使うようにしました（gh auth setup-git）")

    if failed("identity"):
        name, email = github_identity()
        current_name = _run(["git", "config", "--global", "user.name"]).stdout.strip()
        current_email = _run(["git", "config", "--global", "user.email"]).stdout.strip()
        name = current_name or questions.ask("gitに設定する名前（コミットの作者）", name)
        email = current_email or questions.ask("gitに設定するメール", email)
        done += set_identity("" if current_name else name, "" if current_email else email)

    owner = load_config().get("owner", "")
    answer = questions.ask("new・clone で使う既定の所有者（組織名など。空ならログイン中のユーザー）", owner).strip()
    if answer != owner:
        set_config("owner", answer or None)
        done.append(f"既定の所有者を {answer} にしました" if answer else "既定の所有者の設定を消しました")

    after = doctor()
    return InitReport(home(), tuple(done), tuple(skipped), tuple(i for i in after.items if not i.ok))


def _version(tool: str, *args: str) -> str | None:
    if shutil.which(tool) is None:
        return None
    completed = _run([tool, *args])
    return completed.stdout.strip() if completed.ok else None


def _run(args: list[str]) -> _process.Completed:
    try:
        return _process.run(args, check=False)
    except Exception as error:  # ツールがない等
        return _process.Completed(tuple(args), 1, "", str(error))
