"""Project・ファイル・名前付きビルド設定（範囲外の機能）。本物のCppBuildでビルドまで確かめる。"""

import pytest

from helpers import git, remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecobuild.config import Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module import Module

pytestmark = pytest.mark.cppbuild


@pytest.fixture(scope="module")
def module():
    base = short_temporary_directory()
    module = Module.create("Geo", directory=base, github=FakeGitHub(base / "gh"), app=True)
    module.create_task("Project・ファイルの試験").start()  # ファイルを変える操作は作業空間でだけ
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
    assert "src/shape/Circle.cpp" in (root / "Geo/CMakeLists.txt").read_text(encoding="utf-8")
    result = module.test()
    assert result.failed == 0 and "Circle.Works" in [c.name for c in result.cases]

    assert module.add_file("include/Geo/shape/Square.h").paths == ("Geo/include/Geo/shape/Square.h",)
    assert code_of(lambda: module.add_file("src/shape/Circle.cpp")) == ErrorCode.ALREADY_EXISTS
    monkeypatch.chdir(root)
    assert code_of(lambda: module.add_file("README.md")) == ErrorCode.NOT_IN_PROJECT

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
    run = module.run(project="GeoBench", configuration="Release")
    assert "example:" in run.output
    assert module.executable_at(module.root / "GeoBench" / "src") == "GeoBench"
    assert module.executable_at(module.root / "Geo") is None

    assert module.add_project("GeoExtra", "library").paths == ("GeoExtra/include/GeoExtra/GeoExtra.h",
                                                               "GeoExtra/src/GeoExtra.cpp")
    assert code_of(lambda: module.add_project("GeoExtra", "library")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: module.add_project("X", "plugin")) == ErrorCode.INVALID_ARGUMENT

    pch = module.set_pch("Geo")
    assert pch.paths == ("Geo/include/Geo/pch.h",)
    assert "target_precompile_headers" in (module.root / "Geo/CMakeLists.txt").read_text(encoding="utf-8")
    module.build(project="Geo")
    module.set_pch("Geo", enable=False)
    assert "target_precompile_headers" not in (module.root / "Geo/CMakeLists.txt").read_text(encoding="utf-8")

    assert code_of(lambda: module.remove_project("Geo")) == ErrorCode.INVALID_ARGUMENT
    module.remove_project("GeoBench")
    module.remove_project("GeoExtra")
    assert not (module.root / "GeoBench").exists()
    assert {p.name for p in module.projects()} == {"Geo", "GeoTest", "GeoApp"}


def test_profiles_clean_and_rebuild(module):
    assert module.profiles().profiles == {} and module.profiles().selected is None
    module.add_profile("fast", Profile("Release", False, 4))
    assert code_of(lambda: module.add_profile("bad name", Profile())) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: module.add_profile("x", Profile("Fast"))) == ErrorCode.INVALID_CONFIGURATION
    assert code_of(lambda: module.use_profile("nosuch")) == ErrorCode.PROFILE_NOT_FOUND
    assert module.use_profile("fast").selected == "fast"
    assert "fast" in (module.root / "ecobuild.local.toml").read_text(encoding="utf-8")
    assert "[profiles.\"fast\"]" in (module.root / "ecobuild.toml").read_text(encoding="utf-8")
    result = module.build()
    assert (result.configuration, result.profile) == ("Release", "fast")
    assert module.build(configuration="Debug").configuration == "Debug"  # 指定した構成が優先
    assert module.build(action="clean").action == "clean"
    assert module.build(action="rebuild").artifacts
    module.remove_profile("fast")
    assert module.profiles().selected is None and module.build_options()[0].configuration == "Debug"


def test_shared_profile_builds_library_as_shared(module):
    """共有ライブラリにする設定は、ライブラリを共有ライブラリとしてビルドし、使う側もリンクできる。

    Windowsでは書き出しのマクロ（GEO_API）を付けた関数だけが書き出される（付けないとインポートライブラリが
    できず、使う側のリンクが失敗する。仮運用3回目で見つかった）。
    """
    header = module.root / "Geo/include/Geo/Geo.h"
    source = module.root / "Geo/src/Geo.cpp"
    originals = {path: path.read_text(encoding="utf-8") for path in (header, source)}
    assert "#define GEO_API __declspec(dllexport)" in originals[header]
    write(header, originals[header] + "GEO_API int geo_value();\n")
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


def test_docs_ci_and_check(module):
    root = module.root
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "前の試験の変更")  # 生成ファイルをコミット済みにする
    assert "ecobuild task new" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "cmake -S . -B build" in (root / "README.md").read_text(encoding="utf-8")
    (root / "AGENTS.md").unlink()
    assert module.write_agents().paths == ("AGENTS.md",) and (root / "AGENTS.md").exists()
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
    monkeypatch.setattr(_cppbuild, "update", lambda root: (calls.append(root), original(root))[1])
    module.type.refresh()
    module.type.refresh()
    assert len(calls) <= 1  # 2回目は変化なしで飛ばす
    calls.clear()
    (module.root / "Geo/src/Skip.cpp").write_text('#include "Geo/Geo.h"\n', encoding="utf-8")
    module.type.refresh()
    assert len(calls) == 1 and "src/Skip.cpp" in (module.root / "Geo/CMakeLists.txt").read_text(encoding="utf-8")
    (module.root / "Geo/src/Skip.cpp").unlink()
    module.type.refresh()
    assert len(calls) == 2 and "src/Skip.cpp" not in (module.root / "Geo/CMakeLists.txt").read_text(encoding="utf-8")
