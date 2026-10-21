"""型 python が外部のプロセス（venv・pip・pytest）を呼ぶ部分。外部を呼ぶのはこのファイルだけ。

環境はモジュール直下の .venv（.gitignore 済み）。pyproject.toml と使う Python が前回と同じなら、pip を呼ばない
（記録は .venv の中なので、.venv を消せば一緒に消える）。
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from ecobuild.errors import EcoBuildError
from ecobuild.fsutil import remove_tree
from ecobuild.results import TestCaseResult

from .errors import ErrorCode

VENV = ".venv"
STAMP = ".ecobuild-stamp"
PYPROJECT = "pyproject.toml"
DIST = "dist"
CONFIGURATIONS = ("Debug", "Release")
NO_TESTS = 5            # pytest の終了コード：テストが1件も集まらなかった


def _environment() -> dict[str, str]:
    # 出力はUTF-8（Windows の既定 cp932 での文字化けを避ける）。pip の更新の案内は出さない
    return {**os.environ, "PYTHONUTF8": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}


def run(args: list[str], root: Path, code: str, message: str) -> subprocess.CompletedProcess:
    """実行して、失敗なら EcoBuildError（details に command・returncode・output。よくある原因なら hint）。"""
    completed = execute(args, root)
    if completed.returncode != 0:
        raise failure(code, message, args, completed, hint=cause_hint(root, completed.stdout + completed.stderr))
    return completed


def execute(args: list[str], root: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=_environment(), stdin=subprocess.DEVNULL)
    except OSError as error:
        raise EcoBuildError(ErrorCode.BUILD_FAILED, f"{args[0]} を実行できません：{error}",
                            hint="ecobuild doctor で Python の状態を確認できます。") from error


def failure(code: str, message: str, args: list[str], completed: subprocess.CompletedProcess, *,
            hint: str | None = None) -> EcoBuildError:
    """details：command（そのまま貼って使える形）・arguments（分けた引数）・returncode・stdout・stderr・output（両方）。"""
    stdout, stderr = completed.stdout or "", completed.stderr or ""
    output = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
    return EcoBuildError(code, f"{message}（終了コード {completed.returncode}）", hint=hint,
                         details={"command": command_text(args), "arguments": list(args),
                                  "returncode": completed.returncode, "stdout": stdout, "stderr": stderr,
                                  "output": output})


def command_text(args: list[str]) -> str:
    """表示するコマンド：引用を付けて、そのまま端末に貼って使える形（Windows は cmd.exe、ほかは sh の書き方）。"""
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


# 失敗の出力から見分ける、よくある原因（pip・venv・build）
_CHMOD = re.compile(r"Operation not permitted|EPERM|\[Errno 1\]|chmod", re.IGNORECASE)
_DENIED = re.compile(r"Permission denied|EACCES|\[Errno 13\]|Access is denied|アクセスが拒否", re.IGNORECASE)
_NETWORK = re.compile(r"Failed to establish a new connection|Temporary failure in name resolution|Name or service not known"
                      r"|getaddrinfo failed|Could not fetch URL|Network is unreachable|Read timed out|ConnectTimeout"
                      r"|No matching distribution found|Could not find a version that satisfies", re.IGNORECASE)


def cause_hint(root: Path, output: str) -> str | None:
    """失敗の出力から、よくある原因（権限・ネットワーク）を見分けて、次の一手を返す（分からなければ None）。"""
    owners = owner_note(root)
    if owners or _DENIED.search(output):
        return (f"書き込めない場所があります{owners}。コンテナでは、マウントした .venv・build・dist の所有者を作業する人に"
                "してください（例：sudo chown -R \"$(id -u):$(id -g)\" .venv build dist）。")
    if _CHMOD.search(output):
        return ("ファイルの権限を変えられませんでした（コンテナの共有フォルダー〔9p 等〕の上では chmod が失敗します。"
                "setuptools の egg-info 等）。pyproject.toml のビルドを hatchling にする（今のひな形と同じ）か、"
                "ホストでビルドしてください。")
    if _NETWORK.search(output):
        return ("パッケージの置き場所（PyPI 等）につながりません。ネットワーク・プロキシ（HTTPS_PROXY）・"
                "pip の設定（PIP_INDEX_URL）を確かめてください。")
    return None


def owner_note(root: Path) -> str:
    """ビルドが書く場所（.venv・build・dist）のうち、書き込めないものとその所有者（「（.venv：所有者 root・755）」）。"""
    notes = []
    for name in (VENV, "build", DIST):
        path = root / name
        if path.exists() and not os.access(path, os.W_OK):
            try:
                owner = path.owner()
            except (NotImplementedError, KeyError, OSError):
                owner = str(getattr(path.stat(), "st_uid", "?"))
            notes.append(f"{name}：所有者 {owner}・{stat.S_IMODE(path.stat().st_mode):o}")
    return f"（{'、'.join(notes)}）" if notes else ""


# 環境 ---------------------------------------------------------------------------

def venv_python(root: Path) -> Path:
    return root / VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def scripts_directory(root: Path) -> Path:
    return root / VENV / ("Scripts" if os.name == "nt" else "bin")


def installed(root: Path, name: str) -> bool:
    """.venv の site-packages に name（フォルダー・dist-info の glob）があるか（Python を起こさずに確かめる）。"""
    site = "Lib/site-packages" if os.name == "nt" else "lib/python*/site-packages"
    return any(True for _ in (root / VENV).glob(f"{site}/{name}"))


def parallel_tests(root: Path) -> bool:
    """.venv に pytest-xdist が入っているか（入っていれば、テストを CPU の数だけ並べて流す）。"""
    return installed(root, "xdist")


def base_python(configured: str | None) -> str:
    """.venv を作る Python（ecobuild config set python で設定したものか、ECOBuild と同じ Python）。"""
    return configured or sys.executable


def fingerprint(root: Path, base: str) -> str:
    pyproject = root / PYPROJECT
    if not pyproject.is_file():
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{PYPROJECT} がありません。",
                            hint="モジュールのルート（.ecobuild のある場所）に pyproject.toml を置いてください（module new で作れます）。")
    return hashlib.sha256(pyproject.read_bytes() + b"\0" + base.encode("utf-8")).hexdigest()


def ensure_environment(root: Path, base: str, *, force: bool = False) -> Path:
    """.venv を用意し、プロジェクトと dev の依存を入れる（指紋が同じなら何もしない）。.venv の Python を返す。"""
    key = fingerprint(root, base)
    python = venv_python(root)
    stamp = root / VENV / STAMP
    try:
        if not python.is_file():
            run([base, "-m", "venv", str(root / VENV)], root, ErrorCode.BUILD_FAILED, ".venv を作れませんでした。")
            stamp.unlink(missing_ok=True)
        if force or not stamp.is_file() or stamp.read_text(encoding="utf-8").strip() != key:
            run([str(python), "-m", "pip", "install", "--editable", ".[dev]"], root, ErrorCode.BUILD_FAILED,
                "依存のインストールに失敗しました。")
            stamp.write_text(key + "\n", encoding="utf-8")
    except OSError as error:   # .venv に書き込めない（コンテナで root が持つマウント点 等）
        raise EcoBuildError(ErrorCode.BUILD_FAILED, f".venv を用意できませんでした：{error}",
                            hint=cause_hint(root, str(error))) from error
    return python


# ビルド・クリーン ---------------------------------------------------------------

def build_distribution(root: Path, python: Path) -> tuple[str, ...]:
    """wheel と sdist を dist/ に作る。作ったファイル（モジュールからの相対）を返す。
    build（パッケージを作る道具）は .venv に入っていなければ入れる（毎回 pip でネットワークに出ない）。"""
    if not installed(root, "build-*.dist-info"):
        run([str(python), "-m", "pip", "install", "build"], root, ErrorCode.BUILD_FAILED,
            "build のインストールに失敗しました。")
    run([str(python), "-m", "build", "--outdir", DIST], root, ErrorCode.BUILD_FAILED, "パッケージの作成に失敗しました。")
    try:
        return tuple(sorted(p.relative_to(root).as_posix() for p in (root / DIST).iterdir() if p.is_file()))
    except OSError as error:
        raise EcoBuildError(ErrorCode.BUILD_FAILED, f"{DIST}/ を読めません：{error}",
                            hint=cause_hint(root, str(error))) from error


def clean(root: Path) -> None:
    """dist/・build/・*.egg-info（setuptools のモジュール）を消す（.venv は残す。作り直しは遅いため）。

    マウント点（コンテナで dist・build だけを別に置くとき）はフォルダーごとは消せないので、中身だけ消す。
    フォルダーの権限は変えない（消せなかったときに書き込めないフォルダーを残さない）。"""
    targets = [root / DIST, root / "build", *root.glob("*.egg-info"), *root.glob("src/*.egg-info")]
    for target in targets:
        if not target.is_dir():
            continue
        try:
            for child in target.iterdir():
                _remove(child)
            if not os.path.ismount(target):
                target.rmdir()
        except OSError as error:
            if error.errno == errno.EBUSY and not any(target.iterdir()):
                continue   # 中身は消せた。マウント点（ismount で見分けられないバインドマウント等）なので残す
            raise EcoBuildError(ErrorCode.CLEAN_FAILED,
                                f"{target.relative_to(root).as_posix()} を消せませんでした：{error}",
                                hint=cause_hint(root, str(error))
                                or "ほかのプログラム（エディター・エクスプローラー・実行中のプログラム）が使っていないか"
                                   "確かめてから、もう一度実行してください。") from error


def _remove(path: Path) -> None:
    """ファイル・フォルダーを消す。Windows は読み取り専用のファイルも消す（remove_tree）。ほかの OS では権限を変えない
    （中のファイルの消せる・消せないはフォルダーの権限で決まるので、変えても消せず、権限だけが変わって残る）。"""
    if path.is_dir() and not path.is_symlink():
        remove_tree(path) if os.name == "nt" else shutil.rmtree(path)
    elif os.name == "nt":
        try:
            path.unlink()
        except PermissionError:
            os.chmod(path, stat.S_IWRITE)
            path.unlink()
    else:
        path.unlink()


# テスト・実行 -------------------------------------------------------------------

def run_tests(root: Path, python: Path, tests: tuple[str, ...] = ()) -> list[TestCaseResult]:
    """pytest を実行して、テストごとの結果を返す（tests：流すものを絞る。空なら全部）。失敗があれば TEST_FAILED。0件なら空。"""
    with tempfile.TemporaryDirectory(prefix="eb") as directory:
        report = Path(directory) / "junit.xml"
        # 全部を流すときは、pytest-xdist があれば並べる（順に流すと数十分かかる。絞ったときは起動の手間のほうが大きい）
        spread = ["-n", "auto"] if not tests and parallel_tests(root) else []
        args = [str(python), "-m", "pytest", f"--junitxml={report}", *spread, *tests]
        completed = execute(args, root)
        cases = read_junit(report) if report.is_file() else []
    if completed.returncode not in (0, NO_TESTS):
        failed = [c.name for c in cases if c.status == "failed"]
        # どのテストかを1行目に出す（check の一覧には message だけが出る）。集める前の誤りなら件数は出ない
        summary = (f"：失敗 {len(failed)}・成功 {sum(c.status == 'passed' for c in cases)}（{'、'.join(failed[:3])}"
                   + ("…" if len(failed) > 3 else "") + "）") if failed else "（テストを集められませんでした）"
        error = failure(ErrorCode.TEST_FAILED, f"テストに失敗しました{summary}", args, completed)
        error.details["failed"] = failed
        raise error
    return cases


def read_junit(path: Path) -> list[TestCaseResult]:
    cases = []
    for case in ElementTree.parse(path).getroot().iter("testcase"):
        status = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        elif case.find("skipped") is not None:
            status = "skipped"
        name = "::".join(part for part in (case.get("classname"), case.get("name")) if part)
        cases.append(TestCaseResult(name, status))
    return cases


def _pyproject(root: Path) -> dict:
    try:
        return tomllib.loads((root / PYPROJECT).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{PYPROJECT} を読み込めません：{error}") from error


def script_name(root: Path) -> str | None:
    """[project.scripts] の最初の名前（なければNone）。"""
    scripts = _pyproject(root).get("project", {}).get("scripts", {})
    return next(iter(scripts), None)


def needs_init(root: Path) -> bool:
    """パッケージのフォルダーに __init__.py が要るか：setuptools（[build-system] を書かない既定も setuptools）は
    packages.find で __init__.py のあるフォルダーだけを入れる。hatchling 等（ひな形）はフォルダーごと入れるので要らない。"""
    try:
        backend = _pyproject(root).get("build-system", {}).get("build-backend", "setuptools.build_meta")
    except EcoBuildError:
        return True
    return str(backend).startswith("setuptools")


def run_script(root: Path, name: str, arguments: str) -> subprocess.CompletedProcess:
    executable = scripts_directory(root) / (name + (".exe" if os.name == "nt" else ""))
    args = [str(executable), *shlex.split(arguments, posix=os.name != "nt")]
    completed = execute(args, root)
    if completed.returncode != 0:
        raise failure(ErrorCode.RUN_FAILED, "実行に失敗しました。", args, completed)
    return completed
