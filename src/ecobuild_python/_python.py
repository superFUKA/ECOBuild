"""型 python が外部のプロセス（venv・pip・pytest）を呼ぶ部分。外部を呼ぶのはこのファイルだけ。

環境はモジュール直下の .venv（.gitignore 済み）。pyproject.toml と使う Python が前回と同じなら、pip を呼ばない
（記録は .venv の中なので、.venv を消せば一緒に消える）。
"""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.fsutil import remove_tree
from ecobuild.results import TestCaseResult

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
    """実行して、失敗なら EcoBuildError（details に command・returncode・output）。"""
    completed = execute(args, root)
    if completed.returncode != 0:
        raise failure(code, message, args, completed)
    return completed


def execute(args: list[str], root: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=_environment(), stdin=subprocess.DEVNULL)
    except OSError as error:
        raise EcoBuildError(ErrorCode.BUILD_FAILED, f"{args[0]} を実行できません：{error}",
                            hint="ecobuild doctor で Python の状態を確認できます。") from error


def failure(code: str, message: str, args: list[str], completed: subprocess.CompletedProcess) -> EcoBuildError:
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    return EcoBuildError(code, f"{message}（終了コード {completed.returncode}）",
                         details={"command": " ".join(args), "returncode": completed.returncode, "output": output})


# 環境 ---------------------------------------------------------------------------

def venv_python(root: Path) -> Path:
    return root / VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def scripts_directory(root: Path) -> Path:
    return root / VENV / ("Scripts" if os.name == "nt" else "bin")


def base_python(configured: str | None) -> str:
    """.venv を作る Python（ecobuild config set python で設定したものか、ECOBuild と同じ Python）。"""
    return configured or sys.executable


def fingerprint(root: Path, base: str) -> str:
    pyproject = root / PYPROJECT
    if not pyproject.is_file():
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{PYPROJECT} がありません。",
                            hint="ecobuild.toml と同じ場所に pyproject.toml を置いてください（module new で作れます）。")
    return hashlib.sha256(pyproject.read_bytes() + b"\0" + base.encode("utf-8")).hexdigest()


def ensure_environment(root: Path, base: str, *, force: bool = False) -> Path:
    """.venv を用意し、プロジェクトと dev の依存を入れる（指紋が同じなら何もしない）。.venv の Python を返す。"""
    key = fingerprint(root, base)
    python = venv_python(root)
    stamp = root / VENV / STAMP
    if not python.is_file():
        run([base, "-m", "venv", str(root / VENV)], root, ErrorCode.BUILD_FAILED, ".venv を作れませんでした。")
        stamp.unlink(missing_ok=True)
    if force or not stamp.is_file() or stamp.read_text(encoding="utf-8").strip() != key:
        run([str(python), "-m", "pip", "install", "--editable", ".[dev]"], root, ErrorCode.BUILD_FAILED,
            "依存のインストールに失敗しました。")
        stamp.write_text(key + "\n", encoding="utf-8")
    return python


# ビルド・クリーン ---------------------------------------------------------------

def build_distribution(root: Path, python: Path) -> tuple[str, ...]:
    """wheel と sdist を dist/ に作る。作ったファイル（モジュールからの相対）を返す。"""
    run([str(python), "-m", "pip", "install", "build"], root, ErrorCode.BUILD_FAILED, "build のインストールに失敗しました。")
    run([str(python), "-m", "build", "--outdir", DIST], root, ErrorCode.BUILD_FAILED, "パッケージの作成に失敗しました。")
    return tuple(sorted(p.relative_to(root).as_posix() for p in (root / DIST).iterdir() if p.is_file()))


def clean(root: Path) -> None:
    """dist/・build/・*.egg-info を消す（.venv は残す。作り直しは遅いため）。"""
    targets = [root / DIST, root / "build", *root.glob("*.egg-info"), *root.glob("src/*.egg-info")]
    for target in targets:
        if target.is_dir():
            remove_tree(target)


# テスト・実行 -------------------------------------------------------------------

def run_tests(root: Path, python: Path) -> list[TestCaseResult]:
    """pytest を実行して、テストごとの結果を返す。失敗があれば TEST_FAILED。0件なら空。"""
    with tempfile.TemporaryDirectory(prefix="eb") as directory:
        report = Path(directory) / "junit.xml"
        args = [str(python), "-m", "pytest", f"--junitxml={report}"]
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


def script_name(root: Path) -> str | None:
    """[project.scripts] の最初の名前（なければNone）。"""
    try:
        data = tomllib.loads((root / PYPROJECT).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{PYPROJECT} を読み込めません：{error}") from error
    scripts = data.get("project", {}).get("scripts", {})
    return next(iter(scripts), None)


def run_script(root: Path, name: str, arguments: str) -> subprocess.CompletedProcess:
    executable = scripts_directory(root) / (name + (".exe" if os.name == "nt" else ""))
    args = [str(executable), *shlex.split(arguments, posix=os.name != "nt")]
    completed = execute(args, root)
    if completed.returncode != 0:
        raise failure(ErrorCode.RUN_FAILED, "実行に失敗しました。", args, completed)
    return completed
