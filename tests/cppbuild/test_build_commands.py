
import pytest

from helpers import write, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture(scope="module")
def module():
    base = short_temporary_directory()
    module = Module.create("Calc", directory=base, app=True, github=FakeGitHub(base / "gh"))
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
    assert not (module.root / ".cppbuild" / "output" / "intermediate").exists()


def test_test(module):
    result = module.test()
    assert (result.passed, result.failed) == (1, 0)
    assert result.cases[0].name.endswith("Builds")


def test_run_captures_output(module):
    result = module.run(arguments="a 'b c'")
    assert result.returncode == 0
    assert "args=2" in result.output


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
