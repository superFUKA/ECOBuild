
import pytest

from helpers import write, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecobuild.errors import EcoBuildError
from ecobuild_cpp.errors import ErrorCode
from ecobuild_bundle import Module
from ecobuild_cpp import _cppbuild

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture(scope="module")
def module():
    base = short_temporary_directory()
    module = Module.create("Calc", directory=base, kind="library", github=FakeGitHub(base / "gh"))
    _cppbuild.add_project(module.root, "CalcApp", "app")
    write(module.root / "CalcApp/src/main.cpp",
          '#include <iostream>\n#include "Calc/Calc.h"\n\n'
          'int main(int argc, char** argv) {\n    std::cout << "args=" << argc - 1 << std::endl;\n    return 0;\n}\n')
    yield module
    remove_tree(base)


def test_project_at(module):
    assert module.project_at(module.root / "CalcTest" / "src") == "CalcTest"
    assert module.project_at(module.root) is None


def test_build_whole_and_one_project(module):
    assert module.build().project is None
    assert module.build(project="Calc", configuration="Release").configuration == "Release"
    # 中間ファイルはモジュール直下の build/ に置く（Windowsのパス長の対策）
    assert any((module.root / "build").iterdir())
    assert not (module.root / ".ecobuild/.cppbuild" / "output" / "intermediate").exists()


def test_test(module):
    result = module.test()
    assert (result.passed, result.failed) == (1, 0)
    assert result.cases[0].name.endswith("Builds")


def test_run_captures_output(module):
    result = module.run(arguments="a 'b c'")
    assert result.returncode == 0
    assert "args=2" in result.output


def test_run_streams_output(module):
    """program_output の中では、実行するプログラムの出力を終わる前から1行ずつ (行, stream, source) で渡す（tools=False
    ならビルドの行は渡さない）。結果の output は今までどおり全部。"""
    lines = []
    with module.type.program_output(lambda *line: lines.append(line), tools=False):
        result = module.run(arguments="x")
    assert lines == [("args=1", "stdout", "program")] and "args=1" in result.output


def test_build_error_output_is_readable(module):
    """コンパイラ・MSBuildの出力（日本語環境ではメッセージも日本語）が文字化けしない（CppBuild 2bbbfb5）。"""
    path = module.root / "Calc/src/Calc.cpp"
    original = path.read_text(encoding="utf-8")
    write(path, original + "\nint broken() { return undefined_name; }\n")
    try:
        with pytest.raises(EcoBuildError) as error:
            module.build(project="Calc")
        assert error.value.code == ErrorCode.BUILD_FAILED
        assert "undefined_name" in error.value.details and "�" not in error.value.details
    finally:
        write(path, original)


def test_failing_test_is_reported(module):
    path = module.root / "CalcTest/src/CalcTest.cpp"
    original = path.read_text(encoding="utf-8")
    write(path, original + "\nTEST(Calc, Fails) { FAIL(); }\n")
    try:
        with pytest.raises(EcoBuildError) as error:
            module.test(project="CalcTest")
        assert error.value.code == ErrorCode.TEST_FAILED
        assert "Fails" in error.value.message
    finally:
        write(path, original)
