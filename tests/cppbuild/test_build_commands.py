
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


def test_select_tests(module):
    """流すテストを <テスト用Project>[.<Suite>.<Test>]（* ?）で選ぶ。結果の名前はそのまま流し直せる形。"""
    path = module.root / "CalcTest/src/CalcTest.cpp"
    original = path.read_text(encoding="utf-8")
    write(path, original + "\nTEST(Calc, Second) { SUCCEED(); }\n")
    try:
        names = lambda result: sorted(c.name for c in result.cases)  # noqa: E731
        assert names(module.test()) == ["CalcTest.Calc.Builds", "CalcTest.Calc.Second"]
        assert names(module.test(tests=("CalcTest.Calc.Builds",))) == ["CalcTest.Calc.Builds"]
        assert names(module.test(tests=("CalcTest.*.Sec*",))) == ["CalcTest.Calc.Second"]
        assert names(module.test(project="CalcTest", tests=("Calc.B?ilds",))) == ["CalcTest.Calc.Builds"]
        assert len(module.test(tests=("CalcTest", "CalcTest.Calc.Builds")).cases) == 2   # Project の全部が勝つ
        with pytest.raises(EcoBuildError) as error:
            module.test(tests=("CalcTest.Nothing.*",))
        assert error.value.code == ErrorCode.TEST_FAILED and "当てはまるテストがありません" in error.value.message
        for project, tests in ((None, ("Calc.Builds",)), ("Calc", ("Calc.Builds",))):   # Project が分からない・テスト用でない
            with pytest.raises(EcoBuildError) as error:
                module.test(project=project, tests=tests)
            assert error.value.code == ErrorCode.PROJECT_NOT_FOUND and "CalcTest" in error.value.hint
    finally:
        write(path, original)


def test_list_tests(module):
    """流せるテストを、ビルドせずにソースの TEST(…) 等から（値・型でふやすものはパターン）。名前はそのまま流せる。"""
    path = module.root / "CalcTest/src/more/MoreTest.cpp"
    write(path, '#include <gtest/gtest.h>\n\nstruct Fix : ::testing::Test {};\nTEST_F(Fix, Works) { SUCCEED(); }\n'
                '  TEST_P(Param, Each) {}\n// TEST(Comment, Ignored) は行の頭でないので数えない\n')
    try:
        listed = [(t.name, t.file, t.line) for t in module.list_tests().tests]
        assert any(n == "CalcTest.Calc.Builds" and f == "CalcTest/src/CalcTest.cpp" for n, f, _ in listed)
        assert ("CalcTest.Fix.Works", "CalcTest/src/more/MoreTest.cpp", 4) in listed
        assert ("CalcTest.*/Param.Each/*", "CalcTest/src/more/MoreTest.cpp", 5) in listed
        assert not any("Comment" in n for n, _, _ in listed)
        assert module.list_tests(project="CalcTest").tests == module.list_tests().tests
        with pytest.raises(EcoBuildError) as error:
            module.list_tests(project="Calc")
        assert error.value.code == ErrorCode.PROJECT_NOT_FOUND
    finally:
        path.unlink()
    assert [c.name for c in module.test(tests=("CalcTest.Calc.Builds",)).cases] == ["CalcTest.Calc.Builds"]


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
