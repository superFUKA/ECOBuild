"""モジュール（Solution）・Projectの保存する設定と、ビルド設定のすべての項目。本物のCppBuildでビルドまで確かめる。"""

import json

import pytest

from helpers import remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecobuild.config import Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import Module
from ecobuild_cpp import cpp

pytestmark = pytest.mark.cppbuild


@pytest.fixture(scope="module")
def module():
    """ライブラリ Shape（と ShapeTest）と、実行ファイル Viewer（Shape をリンク）。"""
    base = short_temporary_directory()
    module = Module.create("Draw", directory=base, github=FakeGitHub(base / "gh"), kind="library", project="Shape")
    module.repository.create_task("設定の試験").start()
    module.add_project("Viewer", "app")
    yield module
    remove_tree(base)


def code_of(action):
    with pytest.raises(EcoBuildError) as error:
        action()
    return error.value.code


def entry(module, project):
    return (module.root / project / "CMakeLists.txt").read_text(encoding="utf-8")


def test_project_settings_reach_the_build(module):
    """定義・公開する定義・インクルード・ソースディレクトリ・関数の書き出し・フォルダーは管理ファイルに残り、ビルドに効く。"""
    details = module.project_details("Shape")
    assert (details["kind"], details["main"], details["folder"]) == ("static_library", True, "Projects")
    assert set(details["types"]) == {"static", "shared", "interface"}
    assert details["source_directories"] == ["src", "include"]

    write(module.root / "Shape/extra/Extra.cpp", "int shape_extra() { return SHAPE_LEVEL; }\n")
    write(module.root / "Shape/third/Third.h", "#pragma once\n#define THIRD_VALUE 3\n")
    write(module.root / "Viewer/src/main.cpp",
          '#include "Third.h"\nint shape_extra();\n'
          "#ifndef SHAPE_PUBLIC\n#error public define is not propagated\n#endif\n"
          "#ifdef SHAPE_LEVEL\n#error private define leaked\n#endif\n"
          "int main() { return shape_extra() == 2 && THIRD_VALUE == 3 ? 0 : 1; }\n")
    changed = module.set_project("Shape", add_defines=("SHAPE_LEVEL=2",), add_public_defines=("SHAPE_PUBLIC",),
                                 add_include_directories=("third",), add_source_directories=("extra",),
                                 export_all_symbols=True, folder="Libraries/Shape")
    assert changed["types"]["static"]["defines"] == ["SHAPE_LEVEL=2"]
    assert changed["types"]["static"]["public_defines"] == ["SHAPE_PUBLIC"]
    assert changed["types"]["shared"]["include_directories"] == ["include", "third"]
    assert changed["source_directories"] == ["src", "include", "extra"]
    assert (changed["export_all_symbols"], changed["folder"]) == (True, "Libraries/Shape")
    assert "SHAPE_LEVEL=2" in entry(module, "Shape")
    assert module.run(project="Viewer").returncode == 0      # 公開する定義・インクルードは使う側にも伝わる

    # 形式を選んで変える・外す。ないものを外す・同じものを足すのは誤り
    only = module.set_project("Shape", types=("shared",), add_defines=("ONLY_SHARED",))
    assert only["types"]["shared"]["defines"] == ["SHAPE_LEVEL=2", "ONLY_SHARED"]
    assert only["types"]["static"]["defines"] == ["SHAPE_LEVEL=2"]
    module.set_project("Shape", types=("shared",), remove_defines=("ONLY_SHARED",))
    assert code_of(lambda: module.set_project("Shape", remove_defines=("NOPE",))) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Shape", add_defines=("SHAPE_LEVEL=2",))) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: module.set_project("Viewer", types=("static",))) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Viewer", export_all_symbols=True)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.set_project("Nope")) == ErrorCode.PROJECT_NOT_FOUND
    assert module.set_project("Shape", clear_folder=True)["folder"] == "Projects"


def test_links_inside_the_module_and_to_external_libraries(module):
    """同じモジュールのライブラリを後からリンク・解除できる。CMakeのソース・パッケージ・ビルド済みのファイルもリンクできる。"""
    module.add_project("Color", "library", test=False)
    write(module.root / "Color/src/Color.cpp", '#include "Color/Color.h"\nint color_value() { return 7; }\n')
    write(module.root / "Viewer/src/main.cpp", "int color_value();\nint main() { return color_value() == 7 ? 0 : 1; }\n")
    linked = module.link_project("Viewer", "Color")
    assert {(l["kind"], l["name"], l["as"]) for l in linked["links"]} == {("project", "Shape", "static"),
                                                                        ("project", "Color", "static")}
    assert module.run(project="Viewer").returncode == 0
    assert code_of(lambda: module.link_project("Viewer", "Color")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: module.link_project("Color", "Viewer")) == ErrorCode.NOT_LINKABLE

    # CMakeのソース（add_subdirectory）：本物のビルドで使う側までリンクできる
    write(module.root / "Viewer/vendor/tiny/CMakeLists.txt", "add_library(tiny STATIC tiny.cpp)\n")
    write(module.root / "Viewer/vendor/tiny/tiny.cpp", "int tiny_value() { return 5; }\n")
    write(module.root / "Viewer/src/main.cpp",
          "int color_value();\nint tiny_value();\nint main() { return color_value() + tiny_value() == 12 ? 0 : 1; }\n")
    cmake = cpp(module).link_cmake("Viewer", "vendor/tiny", target="tiny")
    assert ("cmake", "tiny", "vendor/tiny") in [(l["kind"], l["name"], l.get("directory")) for l in cmake["links"]]
    assert module.run(project="Viewer").returncode == 0

    # パッケージ（find_package の CONFIG）とビルド済みのファイル（構成の時点で、ファイルがあること）
    write(module.root / "Viewer/vendor/fmt/lib/cmake/fmt/fmtConfig.cmake",
          "if(NOT TARGET fmt::fmt)\n  add_library(fmt::fmt INTERFACE IMPORTED)\nendif()\n")
    for name in ("old_d.lib", "old.lib", "include/old.h"):
        write(module.root / "Viewer/vendor/old" / name, "")
    before = (module.root / "Viewer/.cppbuild/project.json").read_text(encoding="utf-8")
    error = code_of(lambda: cpp(module).link_cmake("Viewer", "vendor/none", target="none"))   # 構成に失敗したら元に戻す
    assert error == ErrorCode.CPPBUILD_ERROR
    assert (module.root / "Viewer/.cppbuild/project.json").read_text(encoding="utf-8") == before
    package = cpp(module).link_package("Viewer", "fmt", target="fmt::fmt", directory="vendor/fmt/lib/cmake/fmt")
    assert any(l["kind"] == "package" and l["target"] == "fmt::fmt" for l in package["links"])
    library = cpp(module).link_library_file("Viewer", kind="static", locations={"Debug": "vendor/old/old_d.lib",
                                                                           "Release": "vendor/old/old.lib"},
                                       include_directories=("vendor/old/include",))
    file_link = next(l for l in library["links"] if l["kind"] == "file")
    assert file_link["files"] == {"Debug": "vendor/old/old_d.lib", "Release": "vendor/old/old.lib"}
    text = (module.root / "CMakeLists.txt").read_text(encoding="utf-8") + entry(module, "Viewer")
    assert "find_package(fmt" in text and "IMPORTED" in text
    assert code_of(lambda: cpp(module).link_library_file("Viewer", kind="static", locations={"Fast": "a.lib"})) \
        == ErrorCode.INVALID_CONFIGURATION

    # 外す：名前か id で。外部のものを外すとビルドできる状態に戻る
    module.unlink_project("Viewer", "fmt")
    module.unlink_project("Viewer", file_link["id"])
    module.unlink_project("Viewer", "tiny")
    after = module.unlink_project("Viewer", "Color")
    assert [l["name"] for l in after["links"]] == ["Shape"]
    assert code_of(lambda: module.unlink_project("Viewer", "Color")) == ErrorCode.INVALID_ARGUMENT
    write(module.root / "Viewer/src/main.cpp", "int main() { return 0; }\n")
    assert module.run(project="Viewer").returncode == 0


def test_module_settings_templates_and_move(module):
    """main・ソリューションフォルダーの名前・ファイルテンプレート・Projectの移動。"""
    settings = module.module_settings()
    assert settings["main_project"] == "Shape" and settings["folders"]["projects"] == "Projects"
    assert settings["templates"]["source"]["builtin"]

    changed = module.set_module_settings(projects_folder="Code", external_folder="ThirdParty")
    assert (changed["folders"]["projects"], changed["folders"]["external"]) == ("Code", "ThirdParty")
    assert module.set_module_settings(clear_main=True)["main_project"] is None
    assert module.set_module_settings(main="Shape")["main_project"] == "Shape"
    assert code_of(lambda: module.set_module_settings(main="Nope")) == ErrorCode.PROJECT_NOT_FOUND
    assert code_of(lambda: module.set_module_settings(projects_folder="a/b")) == ErrorCode.INVALID_ARGUMENT
    module.set_module_settings(projects_folder="Projects", external_folder="External")

    material = module.root.parent / "class.h"
    write(material, "#pragma once\n// {{project}}: {{name}}\nclass {{name}} {};\n")
    templates = cpp(module).add_template("klass", material)
    assert not templates["klass"]["builtin"]
    added = module.add_file(module.root / "Shape/include/Shape/Circle.h", template="klass")
    assert added.paths == ("Shape/include/Shape/Circle.h",)
    assert "class Circle {};" in (module.root / added.paths[0]).read_text(encoding="utf-8")
    assert "// Shape: Circle" in (module.root / added.paths[0]).read_text(encoding="utf-8")
    write(material, "{{unknown}}\n")
    cpp(module).add_template("klass", material)                     # 同じ名前は差し替え
    assert code_of(lambda: module.add_file(module.root / "Shape/include/Shape/Box.h", template="klass")) \
        == ErrorCode.INVALID_ARGUMENT                           # 入れる値がない差し込み口
    cpp(module).remove_template("klass")
    assert "klass" not in module.module_settings()["templates"]
    assert code_of(lambda: cpp(module).remove_template("source")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.add_file(module.root / "Shape/src/X.cpp", template="nope")) == ErrorCode.INVALID_ARGUMENT

    moved = module.move_project("Viewer", "apps/Viewer")
    assert moved.paths == ("apps/Viewer",) or moved.paths[0].endswith("apps/Viewer")
    assert (module.root / "apps/Viewer/src/main.cpp").is_file() and not (module.root / "Viewer").exists()
    assert module.project_details("Viewer")["directory"].endswith("apps/Viewer")
    assert module.run(project="Viewer").returncode == 0
    assert code_of(lambda: module.move_project("Viewer", "apps/Viewer")) == ErrorCode.ALREADY_EXISTS
    module.move_project("Viewer", "Viewer")


def test_profile_carries_every_build_setting(module):
    """ビルド設定の型ごとの項目（C++の規格等）と、Projectごとの上書き（形式・規格）がビルドに効く。"""
    # MSVC の C++23 は /std:c++latest（_MSVC_LANG は 202002 より大きい値）
    check = ("#if defined(_MSVC_LANG)\n#define CPP _MSVC_LANG\n#else\n#define CPP __cplusplus\n#endif\n"
             "static_assert({condition}, \"C++ standard\");\n")
    write(module.root / "Shape/src/Standard.cpp", check.format(condition="CPP / 100 == 2017"))
    write(module.root / "Viewer/src/Standard.cpp", check.format(condition="CPP > 202002L"))
    module.add_profile("modern", Profile("Debug", False, 2, {"cpp_standard": 17, "test_parallel": 2,
                                                              "test_continue_on_failure": False}))
    module.set_profile_project("modern", "Viewer", {"cpp_standard": 23})
    module.set_profile_project("modern", "Shape", {"type": "shared"})
    try:
        text = (module.root / "ecobuild.toml").read_text(encoding="utf-8")
        assert "cpp_standard = 17" in text and '[profiles."modern".projects."Viewer"]' in text
        assert module.profiles().profiles["modern"].projects == {"Shape": {"type": "shared"},
                                                                  "Viewer": {"cpp_standard": 23}}
        artifacts = module.build(profile="modern").artifacts     # 規格が違えば static_assert で失敗する
        assert any(a.endswith((".dll", ".so")) for a in artifacts)  # Shape だけ共有ライブラリ
        assert module.run(project="Viewer", profile="modern").returncode == 0

        # 誤り：知らない項目・使えない値・ライブラリでないProjectの形式・ないProject
        bad = [{"nope": 1}, {"cpp_standard": 14}, {"architecture": "x86"}, {"generator": "Make"},
               {"test_parallel": 0}, {"fetch_git": "no"}]
        for options in bad:
            assert code_of(lambda: module.add_profile("bad", Profile(options=options))) == ErrorCode.INVALID_ARGUMENT
        assert code_of(lambda: module.set_profile_project("modern", "Viewer", {"type": "shared"})) \
            == ErrorCode.INVALID_ARGUMENT
        assert code_of(lambda: module.set_profile_project("modern", "Nope", {"cpp_standard": 20})) \
            == ErrorCode.PROJECT_NOT_FOUND
        assert code_of(lambda: module.set_profile_project("none", "Viewer", {})) == ErrorCode.PROFILE_NOT_FOUND
        module.set_profile_project("modern", "Viewer", None)
        assert "Viewer" not in module.profiles().profiles["modern"].projects
    finally:
        module.remove_profile("modern")
        for path in ("Shape/src/Standard.cpp", "Viewer/src/Standard.cpp"):
            (module.root / path).unlink()


@pytest.mark.skipif(__import__("os").name != "nt", reason="WinMain・ws2_32 は Windows のもの")
def test_entry_point_and_system_libraries(module):
    """実行ファイルの入口の関数（GUIアプリ）と、OSのライブラリの名前でのリンク。"""
    main = module.root / "Viewer/src/main.cpp"
    original = main.read_text(encoding="utf-8")
    assert module.project_details("Viewer")["entry_point"] == "main"
    write(main, "#include <winsock2.h>\n#include <windows.h>\n"
                "int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {\n"
                "    WSADATA data; return WSAStartup(MAKEWORD(2, 2), &data) == 0 ? (WSACleanup(), 0) : 1;\n}\n")
    try:
        changed = module.set_project("Viewer", entry_point="wWinMain", add_system_libraries=("ws2_32",))
        assert (changed["entry_point"], changed["gui"], changed["system_libraries"]) == ("wWinMain", True, ["ws2_32"])
        assert module.build(project="Viewer").artifacts                 # wWinMain と ws2_32 がリンクできる
        assert code_of(lambda: module.set_project("Viewer", entry_point="main", gui=True)) == ErrorCode.INVALID_ARGUMENT
        assert code_of(lambda: module.set_project("Shape", entry_point="wWinMain")) == ErrorCode.INVALID_ARGUMENT
        assert code_of(lambda: module.set_project("Viewer", add_system_libraries=("-lws2_32",))) \
            == ErrorCode.INVALID_ARGUMENT
        custom = module.set_project("Viewer", entry_point="AppMain", gui=False)
        assert (custom["entry_point"], custom["gui"]) == ("AppMain", False)
    finally:
        restored = module.set_project("Viewer", entry_point="main", remove_system_libraries=("ws2_32",))
        assert (restored["entry_point"], restored["gui"], restored["system_libraries"]) == ("main", False, [])
        write(main, original)


def test_source_includes_the_header_added_with_it(module, monkeypatch):
    """同じ名前のヘッダーとソースを一緒に足すと、ソースはそのヘッダーを相対パスで読み込む（順序は問わない）。"""
    monkeypatch.chdir(module.root)
    changed = module.add_files(["Viewer/src/ui/Panel.cpp", "Viewer/src/ui/Panel.h"])   # ソースが先でも
    assert [c.paths for c in changed] == [("Viewer/src/ui/Panel.h",), ("Viewer/src/ui/Panel.cpp",)]
    assert '#include "Panel.h"' in (module.root / "Viewer/src/ui/Panel.cpp").read_text(encoding="utf-8")

    module.add_files(["Shape/include/Shape/geo/Box.h", "Shape/src/geo/Box.cpp"])
    source = (module.root / "Shape/src/geo/Box.cpp").read_text(encoding="utf-8")
    assert '#include "../../include/Shape/geo/Box.h"' in source
    test = (module.root / "ShapeTest/src/geo/BoxTest.cpp").read_text(encoding="utf-8")
    assert '#include "Shape/geo/Box.h"' in test           # テストはライブラリの include/ から
    module.add_files(["Shape/src/geo/Cell.h", "Shape/src/geo/Cell.cpp"])   # include/ の外のヘッダー
    assert '#include "Cell.h"' in (module.root / "Shape/src/geo/Cell.cpp").read_text(encoding="utf-8")
    assert '#include "../../../Shape/src/geo/Cell.h"' in \
        (module.root / "ShapeTest/src/geo/CellTest.cpp").read_text(encoding="utf-8")
    assert module.test().failed == 0 and module.build(project="Viewer").artifacts


def test_settings_cli(module, monkeypatch, capsys):
    """CLI：project show・set・link・unlink、module settings、template、profile project。"""
    from ecobuild_cli import main

    def run(*args):
        capsys.readouterr()
        with pytest.raises(SystemExit) as exited:
            main(list(args) + ["--json"])
        return exited.value.code, json.loads(capsys.readouterr().out)

    monkeypatch.chdir(module.root / "Viewer")
    code, out = run("project", "show")
    assert code == 0 and out["result"]["name"] == "Viewer"
    code, out = run("project", "set", "--add-define", "A=1,B", "--folder", "Apps")
    assert code == 0 and out["result"]["types"]["executable"]["defines"] == ["A=1", "B"]
    code, out = run("project", "set", "--remove-define", "A=1,B", "--clear-folder")
    assert code == 0 and out["result"]["folder"] == "Projects"
    write(module.root / "Viewer/vendor/z/zlibConfig.cmake",
          "if(NOT TARGET ZLIB::ZLIB)\n  add_library(ZLIB::ZLIB INTERFACE IMPORTED)\nendif()\n")
    write(module.root / "Viewer/a.lib", "")
    write(module.root / "Viewer/inc/a.h", "")
    code, out = run("project", "link", "--package", "zlib", "--target", "ZLIB::ZLIB", "--directory", "vendor/z")
    assert code == 0 and any(l["name"] == "zlib" for l in out["result"]["links"])
    code, out = run("project", "link", "Shape", "--package", "x")
    assert code != 0 and out["error"]["code"] == "invalid_argument"
    code, out = run("project", "unlink", "zlib")
    assert code == 0
    code, out = run("project", "link", "--file", "Debug=a.lib", "--type", "static", "--include", "inc")
    assert code == 0
    link_id = next(l["id"] for l in out["result"]["links"] if l["kind"] == "file")
    assert run("project", "unlink", link_id)[0] == 0
    code, out = run("module", "settings")
    assert code == 0 and out["result"]["main_project"] == "Shape"
    code, out = run("template", "list")
    assert code == 0 and "unit_test" in out["result"]
    code, out = run("profile", "add", "p", "--cpp-standard", "23", "--generator", "Ninja Multi-Config",
                    "--stop-on-test-failure", "--no-fetch")
    assert code == 0
    assert out["result"]["profiles"]["p"]["options"] == {"cpp_standard": 23, "generator": "Ninja Multi-Config",
                                                         "test_continue_on_failure": False, "fetch_git": False}
    code, out = run("profile", "project", "p", "Shape", "--type", "interface")
    assert code == 0 and out["result"]["profiles"]["p"]["projects"] == {"Shape": {"type": "interface"}}
    code, out = run("profile", "add", "p", "--cpp-standard", "20")   # 上書きしても Project ごとの設定は残る
    assert out["result"]["profiles"]["p"]["projects"] == {"Shape": {"type": "interface"}}
    code, out = run("profile", "add", "q", "--cpp-standard", "14")
    assert code != 0 and out["error"]["code"] == "invalid_argument"
    run("profile", "remove", "p")
