"""型 python が外部のプロセス（venv・pip・pytest）を呼ぶ部分。外部を呼ぶのはこのファイルだけ。

環境はモジュール直下の .venv（.gitignore 済み）。pyproject.toml と使う Python が前回と同じなら、pip を呼ばない
（記録は .venv の中なので、.venv を消せば一緒に消える）。
"""

from __future__ import annotations

import codecs
import contextlib
import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass
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


def execute(args: list[str], root: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """env：足す環境変数。"""
    try:
        return subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**_environment(), **(env or {})}, stdin=subprocess.DEVNULL)
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

@dataclass(frozen=True)
class PythonTestCase(TestCaseResult):
    """テスト1件（name は pytest の nodeid：tests/test_x.py::TestA::test_b[1]。そのまま ecobuild test に渡せる）。"""
    message: str = ""        # 失敗：何が起きたか（assert の行・例外）。スキップ：理由
    duration: float = 0.0    # 秒（準備・後片付けを含む）


REPORT_PLUGIN = "ecobuild_pytest_report"   # .venv の pytest に -p で読み込ませる名前（_pytest_report.py の写し）


def run_tests(root: Path, python: Path, tests: tuple[str, ...] = (), *, filter: str | None = None,
              last_failed: bool = False) -> list[PythonTestCase]:
    """pytest を実行して、テストごとの結果を返す。失敗があれば TEST_FAILED。0件なら空。

    tests：流すものを絞る（空なら全部）。filter：pytest の -k の式。last_failed：前回失敗したものだけ（--lf）。
    pytest のキャッシュ（--lf の記録）は .venv の中に置く（コンテナの 9p の /work には .pytest_cache を作れない）。
    """
    with tempfile.TemporaryDirectory(prefix="eb") as directory:
        report = Path(directory) / "report.jsonl"
        shutil.copyfile(Path(__file__).with_name("_pytest_report.py"), Path(directory) / f"{REPORT_PLUGIN}.py")
        # 全部を流すときは、pytest-xdist があれば並べる（順に流すと数十分かかる。絞ったときは起動の手間のほうが大きい）
        selected = bool(tests or filter or last_failed)
        spread = ["-n", "auto"] if not selected and parallel_tests(root) else []
        args = [str(python), "-m", "pytest", "-p", REPORT_PLUGIN, "-o", f"cache_dir={(root / VENV / '.pytest_cache')}",
                *spread, *(["-k", filter] if filter else []), *(["--last-failed"] if last_failed else []), *tests]
        paths = os.pathsep.join(p for p in (directory, os.environ.get("PYTHONPATH", "")) if p)
        completed = execute(args, root, env={"PYTHONPATH": paths, "ECOBUILD_PYTEST_REPORT": str(report)})
        cases = read_report(report) if report.is_file() else []
    if completed.returncode not in (0, NO_TESTS):
        failed = [c.name for c in cases if c.status == "failed"]
        # どのテストかを1行目に出す（check の一覧には message だけが出る）。集める前の誤りなら件数は出ない
        summary = (f"：失敗 {len(failed)}・成功 {sum(c.status == 'passed' for c in cases)}（{'、'.join(failed[:3])}"
                   + ("…" if len(failed) > 3 else "") + "）") if failed else "（テストを集められませんでした）"
        error = failure(ErrorCode.TEST_FAILED, f"テストに失敗しました{summary}", args, completed)
        # 成功のときの result と同じ件数・テストごとの結果（失敗のときは result がないので details に）
        error.details.update(failed=failed, counts={s: sum(c.status == s for c in cases)
                                                    for s in ("passed", "failed", "skipped")}, cases=cases)
        raise error
    return cases


_RANK = {"passed": 0, "skipped": 1, "failed": 2}


def read_report(path: Path) -> list[PythonTestCase]:
    """プラグインが書いた結果（1行1件・段階〔準備・本体・後片付け〕ごと）を、テストごとにまとめる。
    状態は一番悪い段階のもの（本体が通っても後片付けで失敗したら失敗）、時間は足したもの。"""
    found: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        case = found.setdefault(record.get("nodeid") or ".", {"status": "passed", "message": "", "duration": 0.0})
        case["duration"] += float(record.get("duration") or 0.0)
        status = record.get("status", "passed")
        if _RANK.get(status, 0) > _RANK[case["status"]] or (status == case["status"] and not case["message"]):
            case.update(status=status, message=record.get("message") or case["message"])
    return [PythonTestCase(name, c["status"], c["message"], round(c["duration"], 3)) for name, c in found.items()]


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


def script_path(root: Path, name: str) -> Path:
    """[project.scripts] のコマンドの、.venv の中の実行ファイル。"""
    return scripts_directory(root) / (name + (".exe" if os.name == "nt" else ""))


def split_arguments(text: str) -> list[str]:
    """--arguments の1つの文字列を引数に分ける（shlex）。空白で区切り、"…"・'…' でまとめる。Windows では \\ を
    そのまま残す（パスに使えるように）。まとめた引用符は外す。引用符が閉じていなければ INVALID_ARGUMENT。"""
    try:
        if os.name != "nt":
            return shlex.split(text)
        parts = shlex.split(text, posix=False)
    except ValueError as error:     # No closing quotation 等
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"--arguments の引数を分けられません（{error}）：{text}",
                            hint="引用符（\"…\"・'…'）を閉じてください。引用符そのものを渡すなら、"
                                 "ecobuild run -- <引数…> のように -- の後ろに並べます。") from error
    return [part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'" else part for part in parts]


STOP_WAIT = 10.0    # 止めたあと、プログラムが終わるのを待つ秒数（過ぎたら強制終了する）


def run_script(root: Path, name: str, arguments: list[str], *, stream: bool = False, stdin: str | None = None,
               echo=False, on_start=None) -> subprocess.CompletedProcess:
    """[project.scripts] のコマンドを .venv で実行する。終了コードが 0 でなければ RUN_FAILED（details に returncode・
    stdout・stderr）。止められたら（SIGINT・SIGTERM）プログラムも止めて RUN_INTERRUPTED（途中までの出力つき）。

    stream：出力を受け継いでそのまま流す（人向け。ためない。結果の stdout・stderr は空）。偽なら stdout・stderr を
    分けてためる（echo なら、ためながら標準エラーにも流す：--json で標準出力は JSON だけにする。呼べるもの〔文字列を
    受ける〕なら、標準エラーの代わりにそれに渡す）。
    stdin：None は渡さない（空）・"inherit" は受け継ぐ（対話型のプログラム）・ほかはそのファイルを渡す。
    on_start：起こした直後に (コマンドの表示, PID) で呼ぶ。
    """
    args = [str(script_path(root, name)), *arguments]
    # 端末で対話するときだけ同じプロセスグループ（端末の Ctrl+C がプログラムに届き、端末を読める）。ほかは別にして、
    # 止めるときはグループごと（プログラムが起こした子も）止める
    own_group = not (stdin == "inherit" and sys.stdin is not None and sys.stdin.isatty())
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"process_group": 0}) \
        if own_group else {}
    pipe = None if stream else subprocess.PIPE
    with _input(stdin) as source:
        try:
            process = subprocess.Popen(args, cwd=root, env=_environment(), stdin=source, stdout=pipe, stderr=pipe,
                                       **group)
        except OSError as error:
            raise EcoBuildError(ErrorCode.RUN_FAILED, f"{name} を実行できません：{error}",
                                hint="ecobuild build で .venv を作り直してください。") from error
        if on_start is not None:
            on_start(command_text(args), process.pid)
        readers = [] if stream else [_Reader(process.stdout, echo), _Reader(process.stderr, echo)]
        stopped = _wait(process, own_group)
        for reader in readers:
            reader.join()
    out, err = (readers[0].text, readers[1].text) if readers else ("", "")
    completed = subprocess.CompletedProcess(args, process.returncode, out, err)
    error = None
    if stopped is not None:
        error = failure(ErrorCode.RUN_INTERRUPTED, f"止めました（{signal.Signals(stopped).name}）。プログラムも止めました",
                        args, completed)
        error.details["signal"] = signal.Signals(stopped).name
    elif completed.returncode != 0:
        error = failure(ErrorCode.RUN_FAILED, "実行に失敗しました。", args, completed)
    if error is not None:
        if stream:   # 出力は流したので、人向けの詳細にはコマンドだけ出す
            error.details["output"] = f"コマンド：{error.details['command']}（出力は上に流しました）"
        raise error
    return completed


@contextlib.contextmanager
def _input(stdin: str | None):
    if stdin is None:
        yield subprocess.DEVNULL
    elif stdin == "inherit":
        yield None
    else:
        try:
            file = open(stdin, "rb")
        except OSError as error:
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"入力のファイル {stdin} を開けません：{error}") from error
        with file:
            yield file


def _wait(process: subprocess.Popen, own_group: bool) -> int | None:
    """プログラムが終わるのを待つ。その間に ecobuild が SIGINT・SIGTERM を受けたら、プログラム（別のグループなら
    グループごと）に渡し、終わるのを待つ（STOP_WAIT 秒で強制終了）。受けたシグナルを返す（なければ None）。"""
    received: list[int] = []

    def forward(number, _frame):
        received.append(number)
        _signal_program(process, own_group, number)

    numbers = [signal.SIGINT, signal.SIGTERM]
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for number in numbers:
            previous[number] = signal.signal(number, forward)
    try:
        # 少しずつ待つ（Windows では待っている間はシグナルの処理が動かない）
        until = None
        while process.poll() is None:
            if received and until is None:
                until = time.monotonic() + STOP_WAIT
            if until is not None and time.monotonic() > until:
                _signal_program(process, own_group, None)   # 止まらない：強制終了
                until = time.monotonic() + STOP_WAIT
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    return received[0] if received else None


def _signal_program(process: subprocess.Popen, own_group: bool, number: int | None) -> None:
    """プログラムにシグナルを渡す（number が None なら強制終了）。端末と同じグループの Ctrl+C は端末が渡している。"""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            if number is None or number == signal.SIGTERM:   # プログラムが起こした子も一緒に（/T）
                done = subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
                if done.returncode != 0:
                    process.kill()
            elif own_group:
                process.send_signal(signal.CTRL_BREAK_EVENT)
        elif own_group:
            os.killpg(process.pid, signal.SIGKILL if number is None else number)
        elif number is None or number == signal.SIGTERM:
            process.send_signal(signal.SIGKILL if number is None else number)
    except OSError:
        pass   # もう終わっていた


class _Reader(threading.Thread):
    """プログラムの出力を読みながらためる（echo なら標準エラーにも流す。呼べるものなら、それに渡す）。部分的な行
    （入力の催促）もすぐ流す。"""

    def __init__(self, stream, echo):
        super().__init__(daemon=True)
        self.stream, self.echo, self.parts = stream, echo, []
        self.start()

    def run(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while chunk := self.stream.read1(65536) if hasattr(self.stream, "read1") else self.stream.read(65536):
            text = decoder.decode(chunk)
            self.parts.append(text)
            if callable(self.echo) and text:
                self.echo(text)
            elif self.echo and text:
                sys.stderr.write(text)
                sys.stderr.flush()
        self.parts.append(decoder.decode(b"", final=True))
        self.stream.close()

    @property
    def text(self) -> str:
        return "".join(self.parts).replace("\r\n", "\n")
