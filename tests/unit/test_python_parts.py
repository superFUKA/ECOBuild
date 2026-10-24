"""型 python：雛形・ファイル・CIのワークフロー・構成の確認（venv・pip を使わない部分）。"""

import errno
import json
import os
import signal
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

import pytest

from ecobuild import HasDependencies, HasFiles, HasProjects
from ecobuild.config import CiSettings, ModuleConfig, Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module_type import Builds
from ecobuild_python import PythonType
from ecobuild_python import _python


class Fake:
    """型の __init__ が受け取る Module の代わり（root と、ヒントの操作名だけ使う）。"""
    def __init__(self, root):
        self.root = root

    def op(self, name: str) -> str:
        return f"ecobuild {name}"


def make(tmp_path, kind="app", name="Calc", project=None) -> PythonType:
    PythonType.populate(tmp_path, ModuleConfig.for_new_module(name, "python"), kind, project)
    return PythonType(Fake(tmp_path))


def code_of(action):
    with pytest.raises(EcoBuildError) as error:
        action()
    return error.value.code


def test_capabilities():
    assert issubclass(PythonType, Builds) and issubclass(PythonType, HasFiles)
    assert not issubclass(PythonType, HasProjects) and not issubclass(PythonType, HasDependencies)


@pytest.mark.parametrize("kind,files", [
    ("app", {"pyproject.toml", "src/calc/__init__.py", "src/calc/__main__.py", "tests/test_calc.py"}),
    ("library", {"pyproject.toml", "src/calc/__init__.py", "tests/test_calc.py"}),
    ("none", {"pyproject.toml", "src/.gitkeep", "tests/.gitkeep"}),
])
def test_populate(tmp_path, kind, files):
    make(tmp_path, kind)
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()} == files
    data = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "Calc" and ("scripts" in data["project"]) == (kind == "app")
    assert _python.script_name(tmp_path) == ("Calc" if kind == "app" else None)
    assert data["build-system"]["build-backend"] == "hatchling.build" and not _python.needs_init(tmp_path)
    assert any(d.startswith("pytest-xdist") for d in data["project"]["optional-dependencies"]["dev"])   # テストを並べて流す


def test_library_without_tests(tmp_path):
    PythonType.populate(tmp_path, ModuleConfig.for_new_module("Calc", "python"), "library", None, test=False)
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()} == {
        "pyproject.toml", "src/calc/__init__.py", "tests/.gitkeep"}


def test_project_names_the_package(tmp_path):
    make(tmp_path, "library", project="Engine")
    assert (tmp_path / "src/engine/__init__.py").is_file() and (tmp_path / "tests/test_engine.py").is_file()


def test_module_defaults():
    assert PythonType.new_kinds == ("app", "library", "none") and PythonType.default_new_kind == "app"
    assert ".venv/" in PythonType.gitignore() and "*.py" in PythonType.tracked_patterns()
    assert {"Dockerfile", "*.html", "*.js", "*.css", "*.json"} <= set(PythonType.tracked_patterns())
    assert PythonType.gitattributes().startswith("* text=auto eol=lf")   # 本体が置く（upgrade・adopt でも足す）
    assert PythonType.generated_note == "" and "python" in PythonType.tool_settings()


def test_add_move_remove_file(tmp_path):
    python = make(tmp_path, "library")
    added = python.add_file(tmp_path / "src/calc/core/ops.py", test=True)
    assert set(added.paths) == {"src/calc/core/ops.py", "tests/core/test_ops.py"}     # hatchling：__init__.py は要らない
    assert "from calc.core import ops" in (tmp_path / "tests/core/test_ops.py").read_text(encoding="utf-8")
    assert code_of(lambda: python.add_file(tmp_path / "src/calc/core/ops.py", test=True)) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: python.add_file(tmp_path / "docs/x.py", test=True)) == ErrorCode.NOT_IN_SOURCE_DIRECTORY
    assert code_of(lambda: python.add_file(tmp_path / "src/x.py", test=True)) == ErrorCode.NOT_IN_SOURCE_DIRECTORY
    assert code_of(lambda: python.add_file(tmp_path / "src/calc/y.py", test=True, template="t")) == ErrorCode.NOT_SUPPORTED
    assert python.add_file(tmp_path / "src/calc/z.py", test=False).paths == ("src/calc/z.py",)
    assert python.add_file(tmp_path / "tests/test_extra.py", test=True).paths == ("tests/test_extra.py",)

    moved = python.move_file(tmp_path / "src/calc/core/ops.py", tmp_path / "src/calc/math/ops.py", test=True)
    assert moved.paths == ("src/calc/core/ops.py", "src/calc/math/ops.py", "tests/core/test_ops.py",
                           "tests/math/test_ops.py")                         # 移動元・移動先の組
    assert not (tmp_path / "tests/core/test_ops.py").exists()
    assert "from calc.math import ops\n" in (tmp_path / "tests/math/test_ops.py").read_text(encoding="utf-8")
    python.move_file(tmp_path / "src/calc/math/ops.py", tmp_path / "src/calc/math/calc.py", test=True)
    assert "from calc.math import calc as ops\n" in (tmp_path / "tests/math/test_calc.py").read_text(encoding="utf-8")
    python.move_file(tmp_path / "src/calc/math/calc.py", tmp_path / "src/calc/math/ops.py", test=True)
    removed = python.remove_file(tmp_path / "src/calc/math/ops.py", test=True)
    assert set(removed.paths) == {"src/calc/math/ops.py", "tests/math/test_ops.py"}
    assert not (tmp_path / "src/calc/math").exists() and not (tmp_path / "tests/math").exists()   # 空のフォルダーも片付ける
    assert code_of(lambda: python.remove_file(tmp_path / "src/calc/math/ops.py", test=True)) == ErrorCode.FILE_NOT_FOUND


def test_setuptools_needs_init(tmp_path):
    """setuptools（packages.find）のモジュールでは、新しいフォルダーに空の __init__.py を作り、消すときに片付ける。"""
    python = make(tmp_path, "library")
    (tmp_path / "pyproject.toml").write_text('[build-system]\nbuild-backend = "setuptools.build_meta"\n', encoding="utf-8")
    assert _python.needs_init(tmp_path)
    added = python.add_file(tmp_path / "src/calc/core/deep/ops.py", test=True)
    assert set(added.paths) == {"src/calc/core/__init__.py", "src/calc/core/deep/__init__.py", "src/calc/core/deep/ops.py",
                                "tests/core/deep/test_ops.py"}
    (tmp_path / "src/calc/core/deep/__pycache__").mkdir()
    python.add_file(tmp_path / "src/calc/core/keep.py", test=False)
    removed = python.remove_file(tmp_path / "src/calc/core/deep/ops.py", test=True)
    assert set(removed.paths) == {"src/calc/core/deep/ops.py", "tests/core/deep/test_ops.py", "src/calc/core/deep/__init__.py"}
    assert not (tmp_path / "src/calc/core/deep").exists() and not (tmp_path / "tests/core").exists()
    assert (tmp_path / "src/calc/core/__init__.py").is_file()           # ほかのファイルがあるフォルダーは残す
    python.remove_file(tmp_path / "src/calc/core/keep.py", test=True)
    assert not (tmp_path / "src/calc/core").exists() and (tmp_path / "src/calc/__init__.py").is_file()
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")    # [build-system] なし＝setuptools
    assert _python.needs_init(tmp_path)


def test_profile_and_options(tmp_path):
    python = make(tmp_path)
    python.validate_profile(Profile(configuration="Release"))
    for bad in (Profile(configuration="Fast"), Profile(shared=True), Profile(options={"x": 1})):
        assert code_of(lambda: python.validate_profile(bad)) in (ErrorCode.INVALID_CONFIGURATION, ErrorCode.INVALID_ARGUMENT)
    assert python.build_options(None, "").configuration == "Debug"
    assert python.build_options(Profile(configuration="Release"), "").configuration == "Release"
    assert code_of(lambda: python.build_options(None, "Fast")) == ErrorCode.INVALID_CONFIGURATION


def test_project_is_rejected(tmp_path):
    python = make(tmp_path)
    options = python.build_options(None, "")
    for action in (lambda: python.build("Foo", options, "build"), lambda: python.test("Foo", options),
                   lambda: python.run("sample.txt", options, "")):
        assert code_of(action) == ErrorCode.NOT_SUPPORTED


def test_run_needs_a_script(tmp_path):
    python = make(tmp_path, "library")
    assert code_of(lambda: python.run(None, python.build_options(None, ""), "")) == ErrorCode.NOT_SUPPORTED


def test_ci_workflow():
    base = ModuleConfig.for_new_module("Calc", "python")
    default = PythonType.ci_workflow(base)
    assert "os: [ubuntu-latest]" in default and 'python: ["3.12"]' in default and "python -m pytest -n auto" in default
    assert "name: Package" not in default and "run: ecobuild" not in default
    custom = PythonType.ci_workflow(
        ModuleConfig("Calc", None, "python", extra={"python": {"versions": ["3.11", "3.13"]}})
        .with_ci(CiSettings(os=("linux", "windows"), configurations=("Debug", "Release"))))
    assert 'python: ["3.11", "3.13"]' in custom and "configuration: [Debug, Release]" in custom and "name: Package" in custom
    assert code_of(lambda: PythonType.ci_workflow(base.with_ci(CiSettings(shared=True)))) == ErrorCode.NOT_SUPPORTED
    bad = ModuleConfig("Calc", None, "python", extra={"python": {"versions": "3.12"}})
    assert code_of(lambda: PythonType.ci_workflow(bad)) == ErrorCode.INVALID_CONFIG


def test_environment_is_rebuilt_only_when_changed(tmp_path, monkeypatch):
    make(tmp_path)
    calls = []

    def fake_run(args, root, code, message):
        calls.append(args[1:3])
        if args[1:3] == ["-m", "venv"]:
            _python.venv_python(root).parent.mkdir(parents=True)
            _python.venv_python(root).write_text("", encoding="utf-8")

    monkeypatch.setattr(_python, "run", fake_run)
    _python.ensure_environment(tmp_path, "python")
    _python.ensure_environment(tmp_path, "python")
    assert calls == [["-m", "venv"], ["-m", "pip"]]            # 2回目は何もしない
    (tmp_path / "pyproject.toml").write_text("# 変更\n" + (tmp_path / "pyproject.toml").read_text(encoding="utf-8"),
                                             encoding="utf-8")
    _python.ensure_environment(tmp_path, "python")
    assert calls[2:] == [["-m", "pip"]]                         # pyproject が変わったら入れ直す
    _python.ensure_environment(tmp_path, "python", force=True)
    assert len(calls) == 4


def test_read_report(tmp_path):
    """段階（準備・本体・後片付け）ごとの記録を、テストごとにまとめる：一番悪い状態と、足した時間。"""
    records = [("t.py::ok", "setup", "passed", "", 0.1), ("t.py::ok", "call", "passed", "", 0.2),
               ("t.py::ok", "teardown", "failed", "RuntimeError: x", 0.1), ("t.py::skip", "setup", "skipped", "まだ", 0),
               ("t.py::bad", "call", "failed", "assert 1 == 2", 0.5), ("t.py::bad", "teardown", "passed", "", 0)]
    report = tmp_path / "r.jsonl"
    report.write_text("".join(json.dumps(dict(zip(("nodeid", "when", "status", "message", "duration"), r))) + "\n"
                              for r in records) + "壊れた行\n", encoding="utf-8")
    assert [(c.name, c.status, c.message, c.duration) for c in _python.read_report(report)] == [
        ("t.py::ok", "failed", "RuntimeError: x", 0.4), ("t.py::skip", "skipped", "まだ", 0.0),
        ("t.py::bad", "failed", "assert 1 == 2", 0.5)]


def test_run_tests_with_real_pytest(tmp_path):
    """ECOBuild の pytest で、プラグインの結果（nodeid・理由）・-k・--last-failed・キャッシュの置き場所を確かめる（pip は使わない）。"""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a.py").write_text(
        "import pytest\n\n\ndef test_ok():\n    pass\n\n\ndef test_bad():\n    assert 1 == 2\n\n\n"
        "@pytest.mark.skip(reason='まだ')\ndef test_skip():\n    pass\n\n\nclass TestK:\n"
        "    @pytest.mark.parametrize('x', [1])\n    def test_p(self, x):\n        pass\n", encoding="utf-8")
    (tmp_path / "tests/test_broken.py").write_text("import nosuchmodule\n", encoding="utf-8")
    python = Path(sys.executable)
    with pytest.raises(EcoBuildError) as error:                                 # 集める途中の誤り（pytest は流さない）
        _python.run_tests(tmp_path, python)
    [broken] = error.value.details["cases"]
    assert (broken.name, broken.status) == ("tests/test_broken.py", "failed") and "nosuchmodule" in broken.message
    assert "tests/test_broken.py" in error.value.message

    (tmp_path / "tests/test_broken.py").unlink()
    with pytest.raises(EcoBuildError) as error:
        _python.run_tests(tmp_path, python)
    details = error.value.details
    cases = {c.name: c for c in details["cases"]}
    assert set(cases) == {"tests/test_a.py::test_ok", "tests/test_a.py::test_bad", "tests/test_a.py::test_skip",
                          "tests/test_a.py::TestK::test_p[1]"}
    assert "assert 1 == 2" in cases["tests/test_a.py::test_bad"].message and cases["tests/test_a.py::test_skip"].message == "まだ"
    assert details["counts"] == {"passed": 2, "failed": 1, "skipped": 1} and details["failed"] == ["tests/test_a.py::test_bad"]
    assert (tmp_path / ".venv/.pytest_cache").is_dir() and not (tmp_path / ".pytest_cache").exists()

    with pytest.raises(EcoBuildError) as error:
        _python.run_tests(tmp_path, python, last_failed=True)                   # 前回失敗したものだけ
    assert [c.name for c in error.value.details["cases"]] == ["tests/test_a.py::test_bad"]
    picked = _python.run_tests(tmp_path, python, ("tests/test_a.py",), filter="ok or test_p")
    assert sorted((c.name, c.status) for c in picked) == [("tests/test_a.py::TestK::test_p[1]", "passed"),
                                                          ("tests/test_a.py::test_ok", "passed")]
    assert _python.run_tests(tmp_path, python, filter="nothing_matches") == []


def test_run_tests_in_parallel_reports_once(tmp_path, monkeypatch):
    """pytest-xdist で並べても、結果は1件ずつ（ワーカーは書かず、親だけが書く）。"""
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "2")   # -n auto の数（CPU の数だけ起こすと遅い）
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a.py").write_text("def test_1():\n    pass\n\n\ndef test_2():\n    pass\n", encoding="utf-8")
    site = tmp_path / ".venv" / ("Lib/site-packages" if os.name == "nt" else "lib/python3.12/site-packages")
    (site / "xdist").mkdir(parents=True)                        # 並べる（ECOBuild の pytest には xdist がある）
    cases = _python.run_tests(tmp_path, Path(sys.executable))
    assert sorted(c.name for c in cases) == ["tests/test_a.py::test_1", "tests/test_a.py::test_2"]


def test_clean_keeps_the_venv(tmp_path):
    make(tmp_path)
    for name in ("dist", "build", "src/calc.egg-info", ".venv"):
        (tmp_path / name).mkdir(parents=True)
    _python.clean(tmp_path)
    assert [n for n in ("dist", "build", "src/calc.egg-info", ".venv") if (tmp_path / n).exists()] == [".venv"]


def test_clean_empties_mount_points(tmp_path, monkeypatch):
    """マウント点（コンテナで別に置いた dist・build）は中身だけ消し、フォルダーと権限は残す。消せなければ clean_failed。"""
    make(tmp_path)
    for name in ("dist/sub", "build"):
        (tmp_path / name).mkdir(parents=True)
    (tmp_path / "dist/a.whl").write_text("x", encoding="utf-8")
    mode = (tmp_path / "dist").stat().st_mode
    monkeypatch.setattr(_python.os.path, "ismount", lambda path: Path(path).name == "dist")
    _python.clean(tmp_path)
    assert (tmp_path / "dist").is_dir() and not any((tmp_path / "dist").iterdir())
    assert (tmp_path / "dist").stat().st_mode == mode and not (tmp_path / "build").exists()

    (tmp_path / "build").mkdir()                          # ismount で見分けられないマウント点（rmdir が EBUSY）
    monkeypatch.setattr(_python.os.path, "ismount", lambda path: False)

    def busy(self):
        raise OSError(errno.EBUSY, "Device or resource busy")
    monkeypatch.setattr(Path, "rmdir", busy)
    _python.clean(tmp_path)
    assert (tmp_path / "build").is_dir()

    (tmp_path / "build/x.txt").write_text("x", encoding="utf-8")

    def denied(path):
        raise PermissionError(errno.EACCES, "Permission denied", str(path))
    monkeypatch.setattr(_python, "_remove", denied)
    with pytest.raises(EcoBuildError) as error:
        _python.clean(tmp_path)
    assert error.value.code == "clean_failed" and "build" in error.value.message and error.value.hint


@pytest.mark.parametrize("output,word", [
    ("PermissionError: [Errno 1] Operation not permitted: 'src/calc.egg-info'", "chmod"),
    ("ERROR: Could not find a version that satisfies the requirement hatchling", "ネットワーク"),
    ("OSError: [Errno 13] Permission denied: '.venv/bin'", "chown"),
    ("SyntaxError: invalid syntax", None),
])
def test_cause_hint(tmp_path, output, word):
    hint = _python.cause_hint(tmp_path, output)
    assert (hint is None) if word is None else word in hint


def test_cause_hint_names_the_owner(tmp_path, monkeypatch):
    """.venv 等に書き込めなければ、出力によらず所有者を示す（コンテナで root が持つマウント点）。"""
    (tmp_path / ".venv").mkdir()
    monkeypatch.setattr(_python.os, "access", lambda path, mode: Path(path).name != ".venv")
    monkeypatch.setattr(Path, "owner", lambda self: "root")
    hint = _python.cause_hint(tmp_path, "Error: [Errno 2] something")
    assert ".venv：所有者 root" in hint and "chown" in hint


def test_failure_details(tmp_path):
    """失敗の details：そのまま貼って使えるコマンド・分けた引数・stdout と stderr を分けた欄（output は両方）。"""
    completed = subprocess.CompletedProcess(["calc", "a b"], 3, "out\n", "err\n")
    details = _python.failure("run_failed", "失敗", ["calc", "a b"], completed).details
    assert details["arguments"] == ["calc", "a b"] and details["returncode"] == 3
    assert details["command"] == ('calc "a b"' if os.name == "nt" else "calc 'a b'")
    assert (details["stdout"], details["stderr"], details["output"]) == ("out\n", "err\n", "out\nerr")


def test_build_tool_is_installed_once(tmp_path, monkeypatch):
    """Release のパッケージを作る build は、.venv に入っていれば pip で入れ直さない（毎回ネットワークに出ない）。"""
    calls = []
    monkeypatch.setattr(_python, "run", lambda args, root, code, message: calls.append(args[1:4]))
    (tmp_path / "dist").mkdir()
    _python.build_distribution(tmp_path, Path("python"))
    site = tmp_path / ".venv" / ("Lib/site-packages" if os.name == "nt" else "lib/python3.12/site-packages")
    (site / "build-1.2.2.dist-info").mkdir(parents=True)
    _python.build_distribution(tmp_path, Path("python"))
    assert calls == [["-m", "pip", "install"], ["-m", "build", "--outdir"], ["-m", "build", "--outdir"]]


def test_all_tests_run_in_parallel_with_xdist(tmp_path, monkeypatch):
    """テスト全部を流すときは、.venv に pytest-xdist があれば並べる（-n auto）。絞ったとき・ないときは並べない。"""
    ran = []
    monkeypatch.setattr(_python, "execute", lambda args, root, env: ran.append(args) or type("C", (), {"returncode": 5})())
    _python.run_tests(tmp_path, Path("python"))
    site = tmp_path / ".venv" / ("Lib/site-packages" if _python.os.name == "nt" else "lib/python3.12/site-packages")
    (site / "xdist").mkdir(parents=True)
    _python.run_tests(tmp_path, Path("python"))
    _python.run_tests(tmp_path, Path("python"), ("tests/test_a.py",))
    assert ["-n" in args for args in ran] == [False, True, False]


# run：[project.scripts] のコマンドの代わりに、ECOBuild の Python に -c で書いたプログラムを動かす

@pytest.fixture
def program(tmp_path, monkeypatch):
    monkeypatch.setattr(_python, "script_path", lambda root, name: Path(sys.executable))
    return lambda code, **options: _python.run_script(tmp_path, "calc", ["-c", code], **options)


def test_run_separates_stdout_and_stderr(program, capsys):
    """出力は stdout・stderr を分けてためる。echo なら、ためながら標準エラーにも流す（--json の標準出力を汚さない）。"""
    started = []
    done = program("import sys; print('out'); print('err', file=sys.stderr)", echo=True,
                   on_start=lambda shown, pid: started.append(pid))
    assert (done.stdout, done.stderr, done.returncode) == ("out\n", "err\n", 0) and started[0] > 0
    shown = capsys.readouterr()
    assert shown.out == "" and "out" in shown.err and "err" in shown.err


def test_run_echo_tells_the_stream(program):
    """echo が呼べるもの（--json の ProgramOutput）なら、出力と一緒に stdout・stderr のどちらかを渡す。"""
    seen = []
    program("import sys; print('out'); print('err', file=sys.stderr)", echo=lambda text, stream: seen.append((stream, text)))
    assert sorted(seen) == [("stderr", "err\n"), ("stdout", "out\n")] or sorted(seen) == [("stderr", "err\r\n"), ("stdout", "out\r\n")]


def test_run_failure_keeps_the_return_code(program):
    with pytest.raises(EcoBuildError) as error:
        program("import sys; print('so far'); sys.exit(3)")
    details = error.value.details
    assert error.value.code == ErrorCode.RUN_FAILED and details["returncode"] == 3 and details["stdout"] == "so far\n"
    assert details["arguments"][1:] == ["-c", "import sys; print('so far'); sys.exit(3)"]


def test_run_stdin(program, tmp_path):
    """stdin：既定は渡さない（すぐ EOF）。ファイルを渡せる。"""
    code = "import sys; print(repr(sys.stdin.read()))"
    assert program(code).stdout == "''\n"
    (tmp_path / "input.txt").write_text("1 2\n", encoding="utf-8")
    assert program(code, stdin=str(tmp_path / "input.txt")).stdout == "'1 2\\n'\n"
    with pytest.raises(EcoBuildError):
        program(code, stdin=str(tmp_path / "nothing.txt"))


def test_run_stops_the_program_on_a_signal(program):
    """ecobuild が SIGTERM を受けたら、プログラムも止めて RUN_INTERRUPTED（途中までの出力つき）。子を残さない。"""
    timer = threading.Timer(1.0, lambda: signal.raise_signal(signal.SIGTERM))
    timer.start()
    started = time.monotonic()
    with pytest.raises(EcoBuildError) as error:
        program("import time; print('ready', flush=True); time.sleep(60)")
    timer.join()
    assert error.value.code == "run_interrupted" and error.value.details["signal"] == "SIGTERM"
    assert error.value.details["stdout"] == "ready\n" and time.monotonic() - started < 30


@pytest.mark.skipif(os.name == "nt", reason="プロセスグループ（killpg）は POSIX")
def test_run_stops_the_whole_group(program, tmp_path):
    """プログラムが起こした子（孫）も、グループごと止める。"""
    pid_file = tmp_path / "child.pid"
    timer = threading.Timer(1.5, lambda: signal.raise_signal(signal.SIGTERM))
    timer.start()
    with pytest.raises(EcoBuildError):
        program("import subprocess, sys, time; p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
                f"open({str(pid_file)!r}, 'w').write(str(p.pid)); time.sleep(60)")
    timer.join()
    child = int(pid_file.read_text())

    def alive(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        try:   # 終わって片付けを待つもの（ゾンビ。コンテナで init が片付けないとき）は止まっている
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return True
    until = time.monotonic() + 5
    while alive(child) and time.monotonic() < until:
        time.sleep(0.1)
    assert not alive(child)


def test_run_command_line(monkeypatch, tmp_path):
    """ecobuild run：引数は -- の後ろに並べる。--propagate-exit なら終了コードはプログラムのもの。--json なしでは
    出力を流し（ためない）、標準入力を渡す。"""
    from click.testing import CliRunner
    from ecobuild_cli import build_cli
    from ecobuild_python.cli import run as run_cli

    shown = CliRunner().invoke(build_cli("python"), ["run", "--arguments", "a", "--", "b"])
    assert shown.exit_code == 2 and "どちらか1つ" in shown.output
    assert CliRunner().invoke(build_cli("python"), ["run", "--stdin", "--input-file", "x", "--", "b"]).exit_code == 2

    calls = []

    class Type:
        def run_program(self, options, arguments, **kw):
            echo = kw["echo"] if isinstance(kw["echo"], bool) else type(kw["echo"]).__name__   # --json：ProgramOutput
            calls.append((arguments, kw["stream"], kw["stdin"], echo))
            if arguments == ["fail"]:
                raise EcoBuildError(ErrorCode.RUN_FAILED, "失敗", details={"returncode": 3})
            return type("R", (), {"returncode": 0, "output": ""})()

    class Inv:
        cwd = tmp_path
        module = type("M", (), {"type": Type(), "build_options": lambda self, c, p: (None, None)})()

        def info(self, text):
            pass

    def fake_run_command(name, action, render, json_output):
        try:
            render(action(Inv()))
            return 0
        except EcoBuildError:
            return 1
    monkeypatch.setattr(run_cli, "run_command", fake_run_command)
    assert run_cli.command("--port", "80") == 0 and calls[-1] == (["--port", "80"], True, "inherit", False)
    assert run_cli.command(arguments='x "y z"', json=True) == 0 and calls[-1] == (["x", "y z"], False, None, "ProgramOutput")
    run_cli.command("a", json=True, stdin=True)
    assert calls[-1][2] == "inherit"
    run_cli.command("a", input_file="in.txt")
    assert calls[-1][2] == str(tmp_path / "in.txt")
    assert run_cli.command("fail") == 1 and run_cli.command("fail", propagate_exit=True) == 3
    assert run_cli._exit_code(-15) == 143


@pytest.mark.parametrize("text,expected", [
    ('a "b c" d', ["a", "b c", "d"]),
    ("--name 'x y'", ["--name", "x y"]),
    ("", []),
])
def test_split_arguments(text, expected):
    assert _python.split_arguments(text) == expected


def test_split_arguments_tells_an_unclosed_quote():
    """#11-38：引用符が閉じていなければ ValueError のままではなく、引数の誤り（ヒント付き）。"""
    with pytest.raises(EcoBuildError) as error:
        _python.split_arguments("a 'b")
    assert error.value.code == ErrorCode.INVALID_ARGUMENT and "--" in error.value.hint


def test_split_arguments_keeps_windows_paths(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows の分け方")
    assert _python.split_arguments(r'C:\work\a.txt "C:\Program Files\x"') == [r"C:\work\a.txt", r"C:\Program Files\x"]
