"""型 python：雛形・ファイル・CIのワークフロー・構成の確認（venv・pip を使わない部分）。"""

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


def test_project_names_the_package(tmp_path):
    make(tmp_path, "library", project="Engine")
    assert (tmp_path / "src/engine/__init__.py").is_file() and (tmp_path / "tests/test_engine.py").is_file()


def test_module_defaults():
    assert PythonType.new_kinds == ("app", "library", "none") and PythonType.default_new_kind == "app"
    assert ".venv/" in PythonType.gitignore() and "*.py" in PythonType.tracked_patterns()
    assert PythonType.generated_note == "" and "python" in PythonType.tool_settings()


def test_add_move_remove_file(tmp_path):
    python = make(tmp_path, "library")
    added = python.add_file(tmp_path / "src/calc/core/ops.py", test=True)
    assert set(added.paths) == {"src/calc/core/__init__.py", "src/calc/core/ops.py", "tests/core/test_ops.py"}
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
    assert (tmp_path / "src/calc/math/__init__.py").is_file() and not (tmp_path / "tests/core/test_ops.py").exists()
    assert "from calc.math import ops\n" in (tmp_path / "tests/math/test_ops.py").read_text(encoding="utf-8")
    python.move_file(tmp_path / "src/calc/math/ops.py", tmp_path / "src/calc/math/calc.py", test=True)
    assert "from calc.math import calc as ops\n" in (tmp_path / "tests/math/test_calc.py").read_text(encoding="utf-8")
    python.move_file(tmp_path / "src/calc/math/calc.py", tmp_path / "src/calc/math/ops.py", test=True)
    removed = python.remove_file(tmp_path / "src/calc/math/ops.py", test=True)
    assert set(removed.paths) == {"src/calc/math/ops.py", "tests/math/test_ops.py"}
    assert code_of(lambda: python.remove_file(tmp_path / "src/calc/math/ops.py", test=True)) == ErrorCode.FILE_NOT_FOUND


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
    assert "os: [ubuntu-latest]" in default and 'python: ["3.12"]' in default and "python -m pytest" in default
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


def test_read_junit(tmp_path):
    report = tmp_path / "r.xml"
    report.write_text('<testsuites><testsuite>'
                      '<testcase classname="t.a" name="ok"/><testcase classname="t.a" name="bad"><failure/></testcase>'
                      '<testcase name="skip"><skipped/></testcase></testsuite></testsuites>', encoding="utf-8")
    assert [(c.name, c.status) for c in _python.read_junit(report)] == [
        ("t.a::ok", "passed"), ("t.a::bad", "failed"), ("skip", "skipped")]


def test_clean_keeps_the_venv(tmp_path):
    make(tmp_path)
    for name in ("dist", "build", "src/calc.egg-info", ".venv"):
        (tmp_path / name).mkdir(parents=True)
    _python.clean(tmp_path)
    assert [n for n in ("dist", "build", "src/calc.egg-info", ".venv") if (tmp_path / n).exists()] == [".venv"]
