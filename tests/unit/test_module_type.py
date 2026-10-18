"""モジュールの型：本体は型の中身を知らず、使う側が Registry に登録した型を使う。持たない能力は not_supported。"""

import pytest

import ecobuild_bundle
from ecobuild import Module, Registry
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module_type import Builds, ModuleType, TypeEntry


class PlainType(ModuleType):
    """何の能力も持たない型（試験用）。"""
    name = "plain"


def test_registry_loads_registered_types():
    registry = Registry([PlainType, TypeEntry("generic", "ecobuild_generic", "GenericType")], default="plain")
    assert registry.load() is PlainType and registry.load("generic").name == "generic"
    assert list(registry.entries()) == ["plain", "generic"]
    with pytest.raises(EcoBuildError) as error:
        registry.load("nosuch")
    assert error.value.code == ErrorCode.INVALID_CONFIG and "plain" in error.value.hint
    with pytest.raises(EcoBuildError) as error:
        Registry().load()                         # 本体には既定の型がない
    assert error.value.code == ErrorCode.INVALID_ARGUMENT


def test_registry_reports_broken_entries():
    registry = Registry([TypeEntry("broken", "no_such_module", "X"), TypeEntry("notype", __name__, "Registry")])
    for name in ("broken", "notype"):
        with pytest.raises(EcoBuildError) as error:
            registry.load(name)
        assert error.value.code == ErrorCode.INVALID_CONFIG
    assert registry.available() == []


def test_core_module_has_no_types(module):
    """本体の Module は型を知らない（空の Registry）。同梱の型は ecobuild_bundle が登録する。"""
    assert Module.registry.entries() == {}
    with pytest.raises(EcoBuildError) as error:
        Module(module.root, module.config)
    assert error.value.code == ErrorCode.INVALID_CONFIG
    assert ecobuild_bundle.REGISTRY.default == "cpp"
    assert set(ecobuild_bundle.REGISTRY.entries()) == {"cpp", "generic", "python"}
    assert type(module).registry is ecobuild_bundle.REGISTRY


def test_external_type_can_be_added(module):
    """外部の型も、Registry に渡せば使える（Module が開く別の Module も同じ Registry を使う）。"""
    registry = Registry([PlainType])
    plain = Module(module.root, module.config.__class__(**{**module.config.__dict__, "type": "plain"}),
                   github=module.repository.github, registry=registry)
    assert isinstance(plain.type, PlainType) and plain.registry is registry


def test_unsupported_operations_are_reported(module):
    """持たない能力の操作は not_supported で止まる。作業の流れ（ecowork）はそのまま使える。"""
    module.type = PlainType(module)
    for action in (lambda: module.build(), lambda: module.test(), lambda: module.projects(),
                   lambda: module.dependency_tree()):
        with pytest.raises(EcoBuildError) as error:
            action()
        assert error.value.code == ErrorCode.NOT_SUPPORTED and "plain" in error.value.message
    assert module.project_at(module.root) is None and module.project_names == ()
    task_branch = module.repository.create_task("型に関係なく使える").start()
    assert module.repository.current_task_branch().number == task_branch.number
    with pytest.raises(EcoBuildError) as error:
        module.add_file("x.txt")
    assert error.value.code == ErrorCode.NOT_SUPPORTED
    assert module.dependencies() == () and module.sync().merged == ()


def test_cpp_only_operations_need_cpp(module):
    """C++だけの操作は拡張の公開API（cpp(module)）。型が cpp でなければ not_supported。"""
    from ecobuild_cpp import CppType, cpp
    assert isinstance(cpp(module), CppType)
    module.type = PlainType(module)
    with pytest.raises(EcoBuildError) as error:
        cpp(module)
    assert error.value.code == ErrorCode.NOT_SUPPORTED
    assert not hasattr(Module, "set_pch") and not hasattr(ModuleType, "link_cmake")


def test_bundled_types_have_their_capabilities():
    from ecobuild import HasDependencies, HasFiles, HasProjects
    from ecobuild_cpp import CppType
    from ecobuild_generic import GenericType
    assert all(issubclass(CppType, c) for c in (Builds, HasProjects, HasFiles, HasDependencies))
    assert issubclass(GenericType, Builds) and not issubclass(GenericType, HasProjects)


def test_cpp_ci_workflow_follows_ci_settings():
    from ecobuild.config import CiSettings, ModuleConfig
    from ecobuild_cpp.type import CppType
    base = ModuleConfig.for_new_module("Calc", "cpp")
    default = CppType.ci_workflow(base)
    assert "os: [windows-latest, ubuntu-latest]" in default and "shared: [OFF]" in default
    assert "-DCMAKE_BUILD_TYPE=${{ matrix.configuration }}" in default
    custom = CppType.ci_workflow(base.with_ci(CiSettings(os=("linux",), configurations=("Release",), shared=True)))
    assert "os: [ubuntu-latest]" in custom and "configuration: [Release]" in custom and "shared: [OFF, ON]" in custom


@pytest.mark.parametrize("type_name", ["cpp", "generic"])
def test_ci_branch_patterns_are_quoted(type_name):
    """** や ! で始まるパターンも、正しいYAMLになるよう引用符で囲む（両方の型で同じ規則）。"""
    from ecobuild.config import CiSettings, ModuleConfig
    from ecobuild_cpp.type import CppType
    from ecobuild_generic.type import GenericType
    if type_name == "cpp":
        base, type_class = ModuleConfig.for_new_module("Calc", "cpp"), CppType
    else:
        base = ModuleConfig("Plain", None, type="generic", extra={"commands": {"build": "make all: x"}})
        type_class = GenericType
    workflow = type_class.ci_workflow(base.with_ci(CiSettings(branches=("main", "**", "!release/*", "on"))))
    assert 'branches: [main, "**", "!release/*", "on"]' in workflow
    if type_name == "generic":
        assert 'run: "make all: x"' in workflow


def test_yaml_text():
    from ecobuild.ci_workflow import yaml_list, yaml_text
    assert yaml_text("release/1.0") == "release/1.0" and yaml_text("1.0") == '"1.0"'
    assert yaml_text('a "b"') == '"a \\"b\\""' and yaml_list(()) == "[]"


def test_cpp_project_names_must_not_be_cmake_names(tmp_path):
    """CMakeのターゲット名はProject名そのもの。test・all 等は、GitHubのリポジトリを作る前に止める。"""
    from fakes import FakeGitHub
    github = FakeGitHub(tmp_path / "gh")
    for name, kind in (("Test", "app"), ("All", "library")):
        with pytest.raises(EcoBuildError) as error:
            ecobuild_bundle.Module.create(name, directory=tmp_path, type="cpp", kind=kind, github=github)
        assert error.value.code == ErrorCode.INVALID_ARGUMENT
    assert not hasattr(github, "bare") and not (tmp_path / "Test").exists()   # リポジトリを作っていない
