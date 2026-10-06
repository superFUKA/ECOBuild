"""Project・ファイル・名前付きビルド設定（範囲外の機能）。本物のCppBuildでビルドまで確かめる。"""

import os

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


@pytest.mark.skipif(os.name != "nt", reason="共有ライブラリの書き出しの確認はWindowsのみ")
def test_shared_profile(module):
    module.add_profile("dll", Profile("Debug", True, 1))
    try:
        assert module.test(profile="dll").failed == 0
    finally:
        module.remove_profile("dll")


def test_docs_ci_and_check(module):
    root = module.root
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "前の試験の変更")  # 生成ファイルをコミット済みにする
    assert "ecobuild task new" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "cmake -S . -B build" in (root / "README.md").read_text(encoding="utf-8")
    (root / "AGENTS.md").unlink()
    assert module.write_agents().paths == ("AGENTS.md",) and (root / "AGENTS.md").exists()
    assert module.write_ci().paths == (".github/workflows/ecobuild.yml",)
    assert "windows-latest" in (root / ".github/workflows/ecobuild.yml").read_text(encoding="utf-8")

    report = module.check()
    assert [(i.name, i.ok) for i in report.items] == [("generated", True), ("conflict_markers", True),
                                                      ("build", True), ("test", True)]
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
