"""Visual Studio のプロパティに当たる設定（オプション・警告・ビルドイベント・出力ファイル・MSVCのランタイム）と、
CppBuild のログが ECOBuild のログに流れること。本物のCppBuildでビルドまで確かめる。"""

import json
import logging
from pathlib import Path

import pytest

from helpers import remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecobuild.config import Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import Module
from ecobuild_cpp import _cppbuild, cpp

pytestmark = pytest.mark.cppbuild


@pytest.fixture(scope="module")
def module():
    """ライブラリ Shape（と ShapeTest）と、実行ファイル Viewer（Shape をリンク）。"""
    base = short_temporary_directory()
    module = Module.create("Draw", directory=base, github=FakeGitHub(base / "gh"), kind="library", project="Shape")
    module.repository.create_task("プロパティの試験").start()
    module.add_project("Viewer", "app")
    yield module
    remove_tree(base)


def code_of(action):
    with pytest.raises(EcoBuildError) as error:
        action()
    return error.value.code


MAIN = """\
#ifndef ALWAYS_ON
#error the conditional definition for every compiler and configuration is missing
#endif
#ifdef RELEASE_ONLY
#error the configuration condition was ignored
#endif
#if defined(_MSC_VER) && !defined(__clang__)
#ifndef MSVC_ONLY
#error the MSVC option is missing
#endif
#ifdef GNU_ONLY
#error the compiler condition was ignored
#endif
#endif
int main() { return 0; }
"""


def test_options_with_conditions_reach_the_build(module):
    """定義・コンパイルオプション・リンクオプションは、コンパイラ・構成の条件つきでビルドに効き、外せる。"""
    write(module.root / "Viewer/src/main.cpp", MAIN)
    module.set_project("Viewer", add_conditional_defines=("ALWAYS_ON",))
    module.set_project("Viewer", add_conditional_defines=("RELEASE_ONLY",), configuration="Release")
    module.set_project("Viewer", add_compile_options=("/DMSVC_ONLY",), compiler="MSVC")
    module.set_project("Viewer", add_compile_options=("-DGNU_ONLY",), compiler="GNU")
    changed = module.set_project("Viewer", add_link_options=("/STACK:4194304",), compiler="MSVC", configuration="Debug")
    assert changed["conditional_definitions"] == [
        {"value": "ALWAYS_ON", "compiler": None, "configuration": None},
        {"value": "RELEASE_ONLY", "compiler": None, "configuration": "Release"}]
    assert changed["compile_options"] == [{"value": "/DMSVC_ONLY", "compiler": "MSVC", "configuration": None},
                                          {"value": "-DGNU_ONLY", "compiler": "GNU", "configuration": None}]
    assert changed["link_options"] == [{"value": "/STACK:4194304", "compiler": "MSVC", "configuration": "Debug"}]
    assert module.build(project="Viewer").artifacts and module.run(project="Viewer").returncode == 0

    # 外すときは、足したときと同じ条件で。違えば別のもの
    assert code_of(lambda: module.set_project("Viewer", remove_compile_options=("/DMSVC_ONLY",))) \
        == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Viewer", add_conditional_defines=("ALWAYS_ON",))) \
        == ErrorCode.ALREADY_EXISTS
    module.set_project("Viewer", add_conditional_defines=("ALWAYS_ON",), configuration="Debug")   # 条件が違えば足せる
    module.set_project("Viewer", remove_conditional_defines=("ALWAYS_ON",), configuration="Debug")
    module.set_project("Viewer", remove_compile_options=("/DMSVC_ONLY",), compiler="MSVC")
    module.set_project("Viewer", remove_compile_options=("-DGNU_ONLY",), compiler="GNU")
    module.set_project("Viewer", remove_link_options=("/STACK:4194304",), compiler="MSVC", configuration="Debug")
    changed = module.set_project("Viewer", remove_conditional_defines=("RELEASE_ONLY",), configuration="Release")
    assert changed["compile_options"] == [] and changed["link_options"] == []
    assert changed["conditional_definitions"] == [{"value": "ALWAYS_ON", "compiler": None, "configuration": None}]
    module.set_project("Viewer", remove_conditional_defines=("ALWAYS_ON",))

    # 誤り：条件だけ・ない構成・コンパイラの種類の誤り
    assert code_of(lambda: module.set_project("Viewer", compiler="MSVC")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Viewer", add_compile_options=("/W4",), configuration="Fast")) \
        == ErrorCode.INVALID_CONFIGURATION
    assert code_of(lambda: module.set_project("Viewer", add_compile_options=("/W4",), compiler="m s")) \
        == ErrorCode.INVALID_ARGUMENT


def test_warnings_events_and_output_files(module):
    """警告のレベルとエラー化・ビルドイベント・出力ファイルの横へのコピー。"""
    write(module.root / "Viewer/src/main.cpp", "int main() { return 0; }\n")
    write(module.root / "Viewer/src/Warn.cpp", "int unused_parameter(int x) { return 0; }\n")
    assert module.project_details("Viewer")["warning_level"] is None
    module.set_project("Viewer", warning_level=4, warnings_as_errors=True)     # 未使用の引数は警告 → エラー
    assert code_of(lambda: module.build(project="Viewer")) == ErrorCode.BUILD_FAILED
    changed = module.set_project("Viewer", warnings_as_errors=False)
    assert (changed["warning_level"], changed["warnings_as_errors"]) == (4, False)
    assert module.build(project="Viewer").artifacts
    changed = module.set_project("Viewer", default_warning_level=True)
    assert changed["warning_level"] is None
    assert code_of(lambda: module.set_project("Viewer", warning_level=5)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Viewer", warning_level=1, default_warning_level=True)) \
        == ErrorCode.INVALID_ARGUMENT

    write(module.root / "Viewer/data/hello.txt", "hello\n")
    changed = module.set_project("Viewer", add_output_files=("data/hello.txt",), event="post_build",
                                 add_build_events=("cmake -E touch post_build_ran.txt",))
    assert changed["output_files"] == ["data/hello.txt"]
    assert changed["build_events"] == {"pre_build": [], "pre_link": [],
                                       "post_build": [["cmake", "-E", "touch", "post_build_ran.txt"]]}
    artifacts = module.build(project="Viewer").artifacts
    executable = next(Path(a) for a in artifacts if Path(a).suffix in (".exe", ""))
    assert (executable.parent / "data/hello.txt").read_text(encoding="utf-8") == "hello\n"   # 出力の横へ、Projectでの場所のまま
    assert (module.root / "Viewer/post_build_ran.txt").is_file()                         # Projectのディレクトリで実行

    assert code_of(lambda: module.set_project("Viewer", add_build_events=("cmake -E true",))) \
        == ErrorCode.INVALID_ARGUMENT                                    # 段階を選ぶ
    assert code_of(lambda: module.set_project("Viewer", event="nowhere", add_build_events=("cmake -E true",))) \
        == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Viewer", event="post_build")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Viewer", event="pre_link", remove_build_events=("cmake -E true",))) \
        == ErrorCode.INVALID_ARGUMENT
    changed = module.set_project("Viewer", remove_output_files=("data/hello.txt",), event="post_build",
                                 remove_build_events=("cmake -E touch post_build_ran.txt",))
    assert changed["output_files"] == [] and changed["build_events"]["post_build"] == []


def test_msvc_runtime_and_windows_sdk(module):
    """MSVCのCランタイム（モジュール全体の設定）と、Windows SDKの版（ビルド設定）。"""
    assert module.module_settings()["msvc_runtime"] == "dll"
    assert module.set_module_settings(msvc_runtime="static")["msvc_runtime"] == "static"
    try:
        assert module.build(project="Viewer").artifacts
        assert code_of(lambda: module.set_module_settings(msvc_runtime="both")) == ErrorCode.INVALID_ARGUMENT
    finally:
        assert module.set_module_settings(msvc_runtime="dll")["msvc_runtime"] == "dll"

    module.add_profile("sdk", Profile("Debug", False, 1, {"windows_sdk": "10.0.22621.0"}))
    try:
        options = cpp(module).build_options(module.profiles().profiles["sdk"], "Debug")
        assert options.windows_sdk == "10.0.22621.0"
        assert code_of(lambda: module.add_profile("bad", Profile(options={"windows_sdk": 10}))) \
            == ErrorCode.INVALID_ARGUMENT
    finally:
        module.remove_profile("sdk")


def test_properties_cli(module, monkeypatch, capsys):
    """CLI：project set のオプション・条件・ビルドイベントと、module settings の --msvc-runtime、表示。"""
    from ecobuild_cli import main

    def run(*args):
        capsys.readouterr()
        with pytest.raises(SystemExit) as exited:
            main(list(args) + ["--json"])
        return exited.value.code, json.loads(capsys.readouterr().out)

    monkeypatch.chdir(module.root / "Viewer")
    code, out = run("project", "set", "--add-compile-option", "/W4;-Wl,--no-undefined", "--compiler", "MSVC",
                    "--warning-level", "3", "--warnings-as-errors", "on",
                    "--event", "pre_build", "--add-build-event", "cmake -E true;cmake -E echo hi, there")
    assert code == 0
    result = out["result"]
    assert [o["value"] for o in result["compile_options"]] == ["/W4", "-Wl,--no-undefined"]   # カンマは値の一部
    assert (result["warning_level"], result["warnings_as_errors"]) == (3, True)
    assert result["build_events"]["pre_build"] == [["cmake", "-E", "true"], ["cmake", "-E", "echo", "hi,", "there"]]
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["project", "show"])
    shown = capsys.readouterr().out
    assert "[MSVC] /W4" in shown and "警告：レベル 3（エラーにする）" in shown and "ビルドイベント（コンパイルの前）" in shown
    code, out = run("project", "set", "--remove-compile-option", "/W4;-Wl,--no-undefined", "--compiler", "MSVC",
                    "--warning-level", "default", "--warnings-as-errors", "off",
                    "--event", "pre_build", "--remove-build-event", "cmake -E true;cmake -E echo hi, there")
    assert code == 0 and out["result"]["compile_options"] == [] and out["result"]["build_events"]["pre_build"] == []
    code, out = run("project", "set", "--warning-level", "high")
    assert code != 0 and out["error"]["code"] == "invalid_argument"
    code, out = run("module", "settings", "--msvc-runtime", "static")
    assert code == 0 and out["result"]["msvc_runtime"] == "static"
    code, out = run("module", "settings", "--msvc-runtime", "dll")
    assert code == 0 and out["result"]["msvc_runtime"] == "dll"
    code, out = run("profile", "add", "sdk", "--windows-sdk", "10.0.22621.0")
    assert code == 0 and out["result"]["profiles"]["sdk"]["options"] == {"windows_sdk": "10.0.22621.0"}
    run("profile", "remove", "sdk")


def test_cppbuild_logs_flow_into_the_ecobuild_log(module):
    """CppBuild の中の動き（API の呼び出し・実行したコマンドと出力・書いたファイル）は、ECOBuild のログの量
    （ルートのロガー）に従って、そのまま流れ込む。CppBuild 側の設定（configure_logging）は要らない。"""
    records = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    root, handler = logging.getLogger(), Collect(logging.DEBUG)
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        write(module.root / "Viewer/src/main.cpp", "int main() { return 0; }\n")
        write(module.root / "Viewer/src/Warn.cpp", "int ok() { return 0; }\n")
        module.set_project("Viewer", add_output_files=("src/Warn.cpp",))
        _cppbuild.update(module.root)
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        module.set_project("Viewer", remove_output_files=("src/Warn.cpp",))
    names = {r.name for r in records if r.name.startswith("cppbuild")}
    assert {"cppbuild.api", "cppbuild.files", "cppbuild.process"} <= names
    assert any(r.name == "cppbuild.process" and "cmake" in r.getMessage().lower() for r in records)
