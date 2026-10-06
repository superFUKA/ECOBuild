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

from ecowork import _process

from . import _gui
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


def home() -> Path:
    """ツールの管理ディレクトリ（OSの慣例。ECOBUILD_HOME で変更）。"""
    if os.environ.get("ECOBUILD_HOME"):
        return Path(os.environ["ECOBUILD_HOME"])
    import platformdirs
    return Path(platformdirs.user_config_dir("ecobuild", appauthor=False))


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
    fix: str = ""          # setup が直せるもの：install／setup-git／identity


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
                               "gh auth login を実行してください（ブラウザでログインします）。"))
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
    items += _toolchain()
    tortoise = _gui.find()
    if os.name == "nt":
        items.append(CheckItem("TortoiseGit", tortoise is not None, False, tortoise or "見つかりません（任意）",
                               "log・diff・blame の --gui に使います。"))
    return DoctorReport(tuple(items))


def _toolchain() -> list[CheckItem]:
    try:
        from cppbuild import Environment, EnvironmentOptions
        report = Environment.check(EnvironmentOptions(require_ctest=True))
    except Exception as error:  # CppBuildの診断そのものが失敗した
        return [CheckItem("CMake・コンパイラ", False, True, f"{type(error).__name__}: {error}",
                          "CMake と C++ コンパイラをインストールしてください。", "install")]
    result = []
    for item in report.items:
        label = {"cmake": "cmake", "ctest": "ctest"}.get(item.name, item.name)
        detail = " ".join(part for part in (item.version or "", item.path or "") if part) or item.detail
        result.append(CheckItem(label, item.success, True, detail if item.success else (item.detail or detail),
                                item.action or "CMake と C++ コンパイラ（Windows：Visual Studio のC++、Linux：g++）が必要です。",
                                "install"))
    return result


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
    missing = [i for i in report.items if not i.ok and i.fix == "install"]
    commands = []
    platform = INSTALL["nt" if os.name == "nt" else "posix"]
    for item in missing:
        key = item.name if item.name in platform else "compiler" if item.name not in ("cmake", "ctest") else "cmake"
        command = platform.get(key)
        if command is None or " ".join(command) in commands:
            continue
        if install:
            completed = _run(command)
            done.append(f"{item.name} を導入しました" if completed.ok else f"{item.name} の導入に失敗しました")
        else:
            commands.append(" ".join(command))
    if any(i.fix == "setup-git" and not i.ok for i in report.items):
        if _run(["gh", "auth", "setup-git"]).ok:
            done.append("gitが gh の認証を使うようにしました（gh auth setup-git）")
    if name:
        _run(["git", "config", "--global", "user.name", name])
        done.append(f"gitの名前を {name} にしました")
    if email:
        _run(["git", "config", "--global", "user.email", email])
        done.append(f"gitのメールを {email} にしました")
    after = doctor() if done else report
    return SetupReport(tuple(done), tuple(i for i in after.items if not i.ok), tuple(commands))


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
