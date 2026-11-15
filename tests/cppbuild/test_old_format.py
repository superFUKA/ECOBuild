"""CppBuild の管理ファイルの古い形式（schema 5。Project の名前の頃）を、今の形式（schema 6・Subproject）にする。

材料（old_format/）は実物のモジュール（ECOSTL・ECOJob）の .ecobuild/.cppbuild の写し（output・operations を除く）。
"""

import json
import shutil
from pathlib import Path

import pytest

from cppbuild import Solution, SubprojectType

from helpers import git, remove_tree, short_temporary_directory, write
from fakes import FakeGitHub
from ecobuild import config
from ecobuild.errors import EcoBuildError
from ecobuild_bundle import Module
from ecobuild_cpp import _cppbuild, _migrate
from ecobuild_cpp.errors import ErrorCode

MATERIAL = Path(__file__).parent / "old_format"
CONFIG = _cppbuild.CONFIG_DIRECTORY


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def _place(root: Path, name: str) -> Path:
    """材料の .cppbuild を root/.ecobuild/.cppbuild に置き、Projectのディレクトリにソースを1つずつ置く。"""
    config_directory = root / CONFIG
    shutil.copytree(MATERIAL / name, config_directory)
    projects = json.loads((config_directory / "project.json").read_text(encoding="utf-8"))["data"]["projects"]
    for project in projects:
        write(root / project / "include" / project / f"{project}.h", "#pragma once\n")
        write(root / project / "src" / f"{project}.cpp", "int main() { return 0; }\n" if "Test" in project or "Bench" in project
              else f'#include "{project}/{project}.h"\n')
    return config_directory


def _old(config_directory: Path) -> dict:
    """古い形式の中身（Project名 → (data, 型 → 型の data)）と Solution の data。"""
    solution = json.loads((config_directory / "project.json").read_text(encoding="utf-8"))["data"]
    projects = {}
    for name in solution["projects"]:
        directory = config_directory / "projects" / name
        data = json.loads((directory / "project.json").read_text(encoding="utf-8"))["data"]
        types = {kind: json.loads((directory / "types" / file).read_text(encoding="utf-8"))["data"]
                 for kind, file in data["types"].items()}
        projects[name] = (data, types)
    return {"solution": solution, "projects": projects}


def test_convert_keeps_contents(tmp_path):
    root = tmp_path / "ECOJob"
    config_directory = _place(root, "ECOJob")
    old = _old(config_directory)
    templates = {p.name: p.read_bytes() for p in (config_directory / "templates").iterdir()}
    assert _migrate.is_old(config_directory)
    with pytest.raises(EcoBuildError) as raised:   # 古い形式のままでは開かず、module upgrade を案内する
        _cppbuild.open_solution(root)
    assert raised.value.code == ErrorCode.OLD_FORMAT and "module upgrade" in raised.value.hint

    moves = dict(_migrate.convert(config_directory))
    assert moves["project.json"] == "solution.json"
    assert moves["projects/ECOJob/project.json"] == "subprojects/ECOJob/subproject.json"
    assert moves["projects/ECOJob/CMakeLists.txt"] == ""          # 生成ファイルは update で作り直す
    assert not _migrate.is_old(config_directory) and not (config_directory / "projects").exists()
    assert {p.name: p.read_bytes() for p in (config_directory / "templates").iterdir()} == templates

    solution = Solution.open(config_directory)
    data = solution.settings.get()
    assert data.name == "ECOJob" and data.main_subproject == "ECOJob"
    assert set(data.subprojects) == set(old["solution"]["projects"])
    assert data.dependency_directories == ["deps"]
    assert {k: (v.url, v.revision, v.path) for k, v in data.git_sources.items()} == {
        k: (v["url"], v["revision"], v["path"]) for k, v in old["solution"]["git_sources"].items()}
    assert {k: v.subproject_guid for k, v in data.references.items()} == {
        k: v["project_guid"] for k, v in old["solution"]["references"].items()}
    assert data.file_templates == old["solution"]["file_templates"]
    folders = data.solution_folders   # CppBuild の古い既定のままだったので、新しい既定に
    assert (folders.subprojects, folders.linked_subprojects, folders.subproject_folders) == ("Subprojects", "LinkedSubprojects", {})

    for name, (before, types) in old["projects"].items():
        values = solution.get_subproject(name).settings.get()
        assert (values.guid, values.initial_type.value, values.source_directories, values.subproject_headers,
                values.system_headers) == (before["guid"], before["initial_type"], before["source_directories"],
                                           before["project_headers"], before["system_headers"])
        assert values.windows_export_all_symbols == before.get("windows_export_all_symbols", False)
        assert {k: (d.subproject_guid, d.subproject_type.value) for k, d in values.dependencies.items()} == {
            k: (d["values"]["project_guid"], d["values"]["project_type"]) for k, d in before["dependencies"].items()}
        assert {k.value: (t.include_directories, t.compile_definitions, t.public_definitions)
                for k, t in values.types.items()} == {
            k: (t["include_directories"], t["compile_definitions"], t["public_definitions"]) for k, t in types.items()}
    assert SubprojectType.STATIC_LIBRARY in solution.get_subproject("ECOJob").settings.get().types


def test_folder_names_chosen_by_hand_stay(tmp_path):
    config_directory = _place(tmp_path / "ECOSTL", "ECOSTL")
    path = config_directory / "project.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["data"]["solution_folders"] = {"projects": "Code", "linked_projects": "LinkedProjects",
                                            "project_folders": {"ECOSTLTest": "Tests"}}
    path.write_text(json.dumps(document), encoding="utf-8")
    _migrate.convert(config_directory)
    folders = Solution.open(config_directory).settings.get().solution_folders
    assert (folders.subprojects, folders.linked_subprojects, folders.subproject_folders) == (
        "Code", "LinkedSubprojects", {"ECOSTLTest": "Tests"})


def test_broken_file_changes_nothing(tmp_path):
    config_directory = _place(tmp_path / "ECOJob", "ECOJob")
    (config_directory / "projects/ECOJobTest/project.json").write_text("{", encoding="utf-8")
    before = sorted(p.relative_to(config_directory).as_posix() for p in config_directory.rglob("*"))
    with pytest.raises(EcoBuildError) as raised:
        _migrate.convert(config_directory)
    assert "ECOJobTest" in raised.value.message
    assert sorted(p.relative_to(config_directory).as_posix() for p in config_directory.rglob("*")) == before


@pytest.mark.cppbuild
def test_old_dependency_clone_is_named(short_tmp):
    """依存先の clone（deps/<名前>）が古い形式なら、変換せずに名前と案内で止める。"""
    root = short_tmp / "ECOJob"
    _migrate.convert(_place(root, "ECOJob"))
    _place(root / "deps" / "ECOSTL", "ECOSTL")
    with pytest.raises(EcoBuildError) as raised:
        _cppbuild.update(root)
    error = raised.value
    assert error.code == ErrorCode.DEPENDENCY_OLD_FORMAT and "ECOSTL" in error.message
    assert "module upgrade" in error.hint and "deps update ECOSTL" in error.hint and error.details == ["deps/ECOSTL"]
    assert _migrate.is_old(root / "deps/ECOSTL" / CONFIG)   # clone は書き換えない
    # deps sync・deps update が clone を記録の版へ切り替えられるよう、依存先の一覧には入る（clone はしない）
    fetched, sources = _cppbuild.fetch_dependencies(root)
    assert fetched == () and [s.name for s in sources] == ["ECOSTL"]


@pytest.mark.cppbuild
def test_converted_module_updates_with_converted_dependency(short_tmp):
    root = short_tmp / "ECOJob"
    _migrate.convert(_place(root, "ECOJob"))
    _migrate.convert(_place(root / "deps" / "ECOSTL", "ECOSTL"))
    assert _cppbuild.update(root).success
    generated = root / CONFIG / "subprojects/ECOJob/CMakeLists.txt"
    assert generated.read_text(encoding="utf-8").startswith("# Generated by CppBuild")
    assert "ECOSTL" in (root / CONFIG / "CppBuildTopLevel.cmake").read_text(encoding="utf-8")
    assert [p.name for p in _cppbuild.list_projects(root)] == ["ECOJob", "ECOJobBench", "ECOJobTest"]


@pytest.mark.cppbuild
@pytest.mark.local
def test_module_upgrade_converts(short_tmp):
    """module upgrade で新しい形式にし、生成ファイルを作り直して「ECOBuild の更新」としてコミットする（移動として追える）。"""
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("ECOSTL", directory=short_tmp, kind="library", github=github)
    root = module.root
    remove_tree(root / CONFIG)
    shutil.copytree(MATERIAL / "ECOSTL", root / CONFIG)
    path = root / config.FILE_NAME
    path.write_text(path.read_text(encoding="utf-8").replace(f"format = {config.FORMAT}", "format = 6"), encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "古い形式")
    git(root, "push", "-q", "origin", "HEAD")
    old = Module.find(root, github=github)
    with pytest.raises(EcoBuildError) as raised:
        old.projects()
    assert raised.value.code == ErrorCode.OLD_FORMAT

    done = old.upgrade()
    assert (done.format, done.commit is not None) == (6, True)
    assert not _migrate.is_old(root / CONFIG) and (root / CONFIG / "subprojects/ECOSTL/CMakeLists.txt").is_file()
    assert git(root, "status", "--porcelain") == ""
    renames = git(root, "show", "-M", "--name-status", "--format=", "HEAD").splitlines()
    # 中身の差が小さいファイルは移動として追える（小さい subproject.json は、キーの改名の割合が大きく追えないことがある）
    assert any(line.startswith("R") and line.endswith(f"{CONFIG}/solution.json") for line in renames)
    assert any(line.startswith("R") and f"{CONFIG}/subprojects/ECOSTL/types/static_library-" in line for line in renames)
    assert [p.name for p in Module.find(root, github=github).projects()] == ["ECOSTL", "ECOSTLTest"]


def test_interrupted_cleanup_finishes_later(tmp_path, monkeypatch):
    """古い置き場所を消せなくても（Visual Studio がつかんでいる等）移し終わり、後で片付けをやり直せる。"""
    config_directory = _place(tmp_path / "ECOJob", "ECOJob")
    (config_directory / "projects/ECOJob/.ecobuild-tmp").write_text("書きかけ", encoding="utf-8")   # 前に止まった一時ファイル

    def locked(*args, **kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(_migrate.shutil, "rmtree", locked)
    _migrate.convert(config_directory)
    assert not _migrate.is_old(config_directory) and _migrate.needs_cleanup(config_directory)
    Solution.open(config_directory)   # 移し終わっている
    monkeypatch.undo()
    assert _migrate.cleanup(config_directory) and not _migrate.needs_cleanup(config_directory)
    assert not list(config_directory.rglob(".ecobuild-tmp"))


@pytest.mark.cppbuild
def test_advice_depends_on_why_the_clone_is_old(short_tmp):
    """手元の clone だけが記録より古いなら deps sync を案内する。古い依存先は、ただ外せる。"""
    root = short_tmp / "ECOJob"
    _migrate.convert(_place(root, "ECOJob"))
    clone = root / "deps" / "ECOSTL"
    _place(clone, "ECOSTL")
    git(clone, "init", "-q")
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "古い形式")   # 記録の版（97ee66e…）とは違うコミット
    with pytest.raises(EcoBuildError) as raised:
        _cppbuild.update(root)
    assert raised.value.code == ErrorCode.DEPENDENCY_OLD_FORMAT and "deps sync" in raised.value.hint
    assert _cppbuild.unlink(root, "ECOSTL") == ("ECOJob",)   # 古い形式のままでも外せる
    assert _cppbuild.git_sources(root) == ()


@pytest.mark.cppbuild
@pytest.mark.local
def test_failed_upgrade_leaves_nothing_behind(short_tmp, monkeypatch):
    """作り直せなければ、タスクブランチでないとき（push まで行く）は止めて、書いたものを戻す。タスクブランチなら移した分を
    コミットして案内を残す。--dry-run には移すファイルが出る。"""
    from ecobuild_cpp.type import CppType

    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("ECOSTL", directory=short_tmp, kind="library", github=github)
    root = module.root
    remove_tree(root / CONFIG)
    shutil.copytree(MATERIAL / "ECOSTL", root / CONFIG)
    path = root / config.FILE_NAME
    path.write_text(path.read_text(encoding="utf-8").replace(f"format = {config.FORMAT}", "format = 6"), encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "古い形式")
    git(root, "push", "-q", "origin", "HEAD")
    old = Module.find(root, github=github)
    planned = old.upgrade(dry_run=True).paths
    assert f"{CONFIG}/project.json" in planned and f"{CONFIG}/solution.json" in planned

    def broken(self):
        raise EcoBuildError(ErrorCode.CPPBUILD_ERROR, "CMake の構成に失敗しました。")

    monkeypatch.setattr(CppType, "refresh", broken)
    with pytest.raises(EcoBuildError):
        old.upgrade()   # main：止めて戻す
    assert git(root, "status", "--porcelain") == "" and _migrate.is_old(root / CONFIG)
    assert "format = 6" in path.read_text(encoding="utf-8")

    old.repository.create_task("形式を新しく").start()
    task = Module.find(root, github=github)
    done = task.upgrade()   # タスクブランチ：移した分をコミットし、作り直せなかったことを案内する
    assert done.commit is not None and not _migrate.is_old(root / CONFIG)
    assert any("作り直せませんでした" in notice for notice in task.repository.notices)
