"""Project・ファイル・名前付きビルド設定（範囲外の機能）。本物のCppBuildでビルドまで確かめる。"""

import pytest

from helpers import git, remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecobuild.config import Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import Module
from ecobuild_cpp import cpp

pytestmark = pytest.mark.cppbuild


@pytest.fixture(scope="module")
def module():
    base = short_temporary_directory()
    module = Module.create("Geo", directory=base, github=FakeGitHub(base / "gh"), kind="library")
    module.repository.create_task("Project・ファイルの試験").start()  # ファイルを変える操作はタスクブランチでだけ
    assert module.add_project("GeoApp", "app").paths == ("GeoApp/src/main.cpp",)   # ライブラリ Geo をリンクする
    yield module
    remove_tree(base)


def code_of(action):
    with pytest.raises(EcoBuildError) as error:
        action()
    return error.value.code


def test_file_add_mirrors_test_and_builds(module, monkeypatch):
    root = module.root
    write(root / "Geo/include/Geo/shape/Circle.h",
          "#pragma once\nnamespace geo { inline double area(double r) { return 3.0 * r * r; } }\n")
    monkeypatch.chdir(root / "Geo")
    changed = module.add_file("src/shape/Circle.cpp")
    assert changed.paths == ("Geo/src/shape/Circle.cpp", "GeoTest/src/shape/CircleTest.cpp")
    assert '#include "Geo/shape/Circle.h"' in (root / "GeoTest/src/shape/CircleTest.cpp").read_text(encoding="utf-8")
    assert "TEST(Circle, Works)" in (root / "GeoTest/src/shape/CircleTest.cpp").read_text(encoding="utf-8")
    result = module.test()
    assert result.failed == 0 and "Circle.Works" in [c.name for c in result.cases]

    assert module.add_file("include/Geo/shape/Square.h").paths == ("Geo/include/Geo/shape/Square.h",)
    assert code_of(lambda: module.add_file("src/shape/Circle.cpp")) == ErrorCode.ALREADY_EXISTS
    monkeypatch.chdir(root)
    assert code_of(lambda: module.add_file("README.md")) == ErrorCode.NOT_IN_PROJECT
    # ソースフォルダー（src・include）の外はビルドに入らないので、作らない・移さない
    assert code_of(lambda: module.add_file("Geo/notes/Memo.cpp")) == ErrorCode.NOT_IN_SOURCE_DIRECTORY
    assert code_of(lambda: module.add_file("Geo/Loose.cpp")) == ErrorCode.NOT_IN_SOURCE_DIRECTORY
    assert not (root / "Geo/notes").exists() and not (root / "Geo/Loose.cpp").exists()
    assert code_of(lambda: module.move_file("Geo/src/shape/Circle.cpp", "Geo/notes/Circle.cpp")) == ErrorCode.NOT_IN_SOURCE_DIRECTORY
    assert (root / "Geo/src/shape/Circle.cpp").is_file()

    moved = module.move_file("Geo/src/shape/Circle.cpp", "Geo/src/shape/Disk.cpp")
    assert moved.paths == ("Geo/src/shape/Circle.cpp", "Geo/src/shape/Disk.cpp",
                           "GeoTest/src/shape/CircleTest.cpp", "GeoTest/src/shape/DiskTest.cpp")
    removed = module.remove_file("Geo/src/shape/Disk.cpp")
    assert removed.paths == ("Geo/src/shape/Disk.cpp", "GeoTest/src/shape/DiskTest.cpp")
    assert not (root / "GeoTest/src/shape/DiskTest.cpp").exists()
    assert module.test().failed == 0


def test_projects_bench_pch_and_remove(module):
    added = module.add_project("GeoBench", "bench")
    assert added.paths == ("GeoBench/src/bench.cpp",)
    kinds = {p.name: (p.kind, p.links) for p in module.projects()}
    assert kinds["GeoBench"] == ("executable", ("Geo",))
    assert {p.name: p.source_directories for p in module.projects()}["Geo"] == ("src", "include")   # GUIが置き場所を選ぶ
    run = module.run(project="GeoBench", configuration="Release")
    assert "example:" in run.output
    assert module.executable_at(module.root / "GeoBench" / "src") == "GeoBench"
    assert module.executable_at(module.root / "Geo") is None

    assert module.add_project("GeoExtra", "library").paths == (     # 組のテスト用Projectも作る
        "GeoExtra/include/GeoExtra/GeoExtra.h", "GeoExtra/src/GeoExtra.cpp", "GeoExtraTest/src/GeoExtraTest.cpp")
    assert code_of(lambda: module.add_project("GeoExtra", "library")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: module.add_project("X", "plugin")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.add_project("X", "app")) == ErrorCode.INVALID_ARGUMENT     # ライブラリが2つ
    assert code_of(lambda: module.add_project("X", "app", link="GeoApp")) == ErrorCode.INVALID_ARGUMENT
    assert module.add_project("GeoExtraBench", "bench", link="GeoExtra").paths == ("GeoExtraBench/src/bench.cpp",)
    assert {p.name: p.links for p in module.projects()}["GeoExtraBench"] == ("GeoExtra",)
    assert module.add_project("GeoAlone", "library", test=False).paths == (
        "GeoAlone/include/GeoAlone/GeoAlone.h", "GeoAlone/src/GeoAlone.cpp")

    pch = cpp(module).set_pch("Geo")
    assert pch.paths == ("Geo/include/Geo/pch.h",)
    assert "target_precompile_headers" in (module.root / ".ecobuild/.cppbuild/projects/Geo/CMakeLists.txt").read_text(encoding="utf-8")
    module.build(project="Geo")
    cpp(module).set_pch("Geo", enable=False)
    assert "target_precompile_headers" not in (module.root / ".ecobuild/.cppbuild/projects/Geo/CMakeLists.txt").read_text(encoding="utf-8")

    for name in ("GeoBench", "GeoExtraBench", "GeoExtraTest", "GeoExtra", "GeoAlone"):
        module.remove_project(name)
    assert not (module.root / "GeoBench").exists()
    assert {p.name for p in module.projects()} == {"Geo", "GeoTest", "GeoApp"}


def test_profiles_clean_and_rebuild(module):
    assert module.profiles().profiles == {} and module.profiles().selected is None
    module.add_profile("fast", Profile("Release", False, 4))
    assert code_of(lambda: module.add_profile("bad name", Profile())) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.add_profile("x", Profile("Fast"))) == ErrorCode.INVALID_CONFIGURATION
    assert code_of(lambda: module.use_profile("nosuch")) == ErrorCode.PROFILE_NOT_FOUND
    assert module.use_profile("fast").selected == "fast"
    assert "fast" in (module.root / ".ecobuild/ecobuild.local.toml").read_text(encoding="utf-8")
    assert "[profiles.\"fast\"]" in (module.root / ".ecobuild/ecobuild.toml").read_text(encoding="utf-8")
    result = module.build()
    assert (result.configuration, result.profile) == ("Release", "fast")
    assert module.build(configuration="Debug").configuration == "Debug"  # 指定した構成が優先
    assert module.build(action="clean").action == "clean"
    assert module.build(action="rebuild").artifacts
    module.remove_profile("fast")
    assert module.profiles().selected is None and module.build_options()[0].configuration == "Debug"


def test_shared_profile_builds_library_as_shared(module):
    """共有ライブラリにする設定は、ライブラリを共有ライブラリとしてビルドし、使う側もリンクできる。

    Windowsでは __declspec(dllexport) のない関数は書き出されず、インポートライブラリができずに使う側のリンクが
    失敗していた（仮運用3回目）。ライブラリにCppBuildの windows_export_all_symbols を設定し、ソースのまま使える。
    """
    header = module.root / "Geo/include/Geo/Geo.h"
    source = module.root / "Geo/src/Geo.cpp"
    originals = {path: path.read_text(encoding="utf-8") for path in (header, source)}
    assert "dllexport" not in originals[header]
    write(header, originals[header] + "int geo_value();\n")
    write(source, originals[source] + "int geo_value() { return 42; }\n")
    module.add_profile("dll", Profile("Debug", True, 1))
    try:
        artifacts = module.build(profile="dll").artifacts  # 使う側（GeoTest・GeoApp）のリンクまで
        assert any(a.endswith((".dll", ".so")) for a in artifacts)
        assert module.test(profile="dll").failed == 0
        assert module.build().artifacts  # 静的ライブラリのままでもビルドできる
    finally:
        module.remove_profile("dll")
        for path, text in originals.items():
            write(path, text)


def test_shared_library_project_builds_as_dll(module):
    """種類 shared は共有ライブラリとして作り、組のテスト用Projectも共有ライブラリとしてリンクして通る。"""
    assert module.add_project("GeoDll", "shared").paths == (
        "GeoDll/include/GeoDll/GeoDll.h", "GeoDll/src/GeoDll.cpp", "GeoDllTest/src/GeoDllTest.cpp")
    try:
        kinds = {p.name: p for p in module.projects()}
        assert kinds["GeoDll"].kind == "shared_library"
        assert code_of(lambda: module.add_project("X", "shared", link="Geo")) == ErrorCode.INVALID_ARGUMENT
        assert any(a.endswith((".dll", ".so")) for a in module.build(project="GeoDll").artifacts)
        assert module.build(project="GeoDllTest").artifacts  # 使う側のリンクまで（Windows では .lib が要る）
        assert module.test(project="GeoDllTest").failed == 0
    finally:
        module.remove_project("GeoDllTest")
        module.remove_project("GeoDll")


def test_docs_ci_and_check(module):
    root = module.root
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "前の試験の変更")  # 生成ファイルをコミット済みにする
    assert not (root / "AGENTS.md").exists()          # module new では作らない
    assert "ecobuild task new" in module.agent_guide().text
    assert "cmake -S .ecobuild/.cppbuild -B build" in (root / "README.md").read_text(encoding="utf-8")
    assert module.write_agents().paths == ("AGENTS.md",)
    assert "ecobuild agent guide" in (root / "AGENTS.md").read_text(encoding="utf-8")
    ci = module.write_ci()
    assert (ci.path, ci.private_dependencies) == (".github/workflows/ecobuild.yml", ())
    assert "windows-latest" in (root / ".github/workflows/ecobuild.yml").read_text(encoding="utf-8")

    report = module.check()
    assert [(i.name, i.ok) for i in report.items] == [("generated", True), ("conflict_markers", True),
                                                      ("build", True), ("test", True)]
    module.add_project("GeoTool", "app")  # 生成ファイルが未コミットでも、コミット前の確認は通る（知らせるだけ）
    report = module.check(build=False)
    assert report.ok and "未コミット" in report.items[0].detail
    module.remove_project("GeoTool")
    source = root / "Geo/src/Geo.cpp"
    original = source.read_text(encoding="utf-8")
    source.write_text(original + "<<<<<<< HEAD\n=======\n>>>>>>> origin/main\n", encoding="utf-8")
    try:
        with pytest.raises(EcoBuildError) as error:
            module.check(build=False)
        assert error.value.code == ErrorCode.CHECK_FAILED
        assert [d["name"] for d in error.value.details if not d["ok"]] == ["conflict_markers"]
    finally:
        source.write_text(original, encoding="utf-8")


def test_update_is_skipped_when_nothing_changed(module, monkeypatch):
    """生成ファイルの作り直し（CppBuildの update）は、入力が変わったときだけ行う。"""
    from ecobuild_cpp import _cppbuild
    calls = []
    original = _cppbuild.update
    monkeypatch.setattr(_cppbuild, "update", lambda root, options=None: (calls.append(root), original(root, options))[1])
    module.type.refresh()
    module.type.refresh()
    assert len(calls) <= 1  # 2回目は変化なしで飛ばす
    calls.clear()
    # ソースの追加は作り直さない（生成ファイルに一覧はなく、CMakeがビルドのたびに集める）
    (module.root / "Geo/src/Skip.cpp").write_text('#include "Geo/Geo.h"\n', encoding="utf-8")
    module.type.refresh()
    assert calls == [] and "Skip.cpp" not in (module.root / ".ecobuild/.cppbuild/projects/Geo/CMakeLists.txt").read_text(encoding="utf-8")
    (module.root / "Geo/src/Skip.cpp").unlink()
    # 生成ファイルが書き換えられていれば作り直す
    generated = module.root / ".ecobuild/.cppbuild/projects/Geo/CMakeLists.txt"
    original_text = generated.read_text(encoding="utf-8")
    generated.write_text(original_text + "# edited\n", encoding="utf-8")
    module.type.refresh()
    assert len(calls) == 1 and generated.read_text(encoding="utf-8") == original_text
