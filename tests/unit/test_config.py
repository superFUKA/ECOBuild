import pytest

from ecobuild import config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import Module


def test_roundtrip(tmp_path):
    original = config.ModuleConfig.for_new_module("Calc", "cpp")
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    assert config.load(path) == original


def test_a_conflicted_config_is_read_as_our_side(tmp_path):
    """取り込みで衝突して印が残っている間も、自分の側（HEAD）で読める（直すのは人。ファイルは印のまま）。"""
    original = config.ModuleConfig.for_new_module("Calc", "cpp")
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    text = path.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("format"))
    conflicted = text.replace(line, f"<<<<<<< HEAD\n{line}\n||||||| base\nformat = 1\n=======\nformat = 999\n>>>>>>> origin/main")
    path.write_text(conflicted, encoding="utf-8")
    assert config.load(path) == original and path.read_text(encoding="utf-8") == conflicted
    assert config.ours("a\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> m\nz\n") == "a\nx\nz\n"


def test_roundtrip_keeps_projects_of_older_modules(tmp_path):
    """以前のモジュールの [projects]（作成時の基本のProject）は、使わないが読み書きでは消さない。"""
    original = config.ModuleConfig("Calc", config.ProjectNames("Calc", "CalcTest"), type="cpp")
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    loaded = config.load(path)
    assert loaded == original and loaded.projects.app is None
    assert config.ModuleConfig.for_new_module("Calc", "cpp").projects is None
    assert loaded.default_base == "main"


def test_profile_options_and_project_overrides_roundtrip(tmp_path):
    """ビルド設定の型ごとの項目と、Projectごとの上書き（[profiles.X.projects.Y]）は読み書きで残る。"""
    profile = config.Profile("Release", True, 4, {"cpp_standard": 23, "generator": "Ninja Multi-Config",
                                                  "fetch_git": False},
                             {"Core": {"type": "shared"}, "App": {"cpp_standard": 17, "artifact_directory": "dist"}})
    original = config.ModuleConfig.for_new_module("Calc", "cpp").with_profiles({"fast": profile})
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    text = path.read_text(encoding="utf-8")
    assert 'cpp_standard = 23' in text and '[profiles."fast".projects."Core"]' in text
    assert config.load(path) == original


@pytest.mark.parametrize("table", ['[profiles.p]\nnope = [1]\n', '[profiles.p]\nprojects = 1\n',
                                   '[profiles.p.projects.A]\ntype = [1]\n'])
def test_invalid_profile_values_are_invalid_config(tmp_path, table):
    path = tmp_path / "ecobuild.toml"
    path.write_text("format = 1\n[module]\nname = 'x'\ntype = 'cpp'\n" + table, encoding="utf-8")
    with pytest.raises(EcoBuildError) as error:
        config.load(path)
    assert error.value.code == ErrorCode.INVALID_CONFIG


def test_quoting_survives_special_characters(tmp_path):
    original = config.ModuleConfig.for_new_module(r'Ca"l\c', "cpp")
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    assert config.load(path).name == r'Ca"l\c'


def test_invalid_file(tmp_path):
    path = tmp_path / "ecobuild.toml"
    path.write_text("format = 1\n[module]\nname = 'x'\n", encoding="utf-8")
    with pytest.raises(EcoBuildError) as error:
        config.load(path)
    assert error.value.code == ErrorCode.INVALID_CONFIG


def test_find_nearest_module_upwards(tmp_path):
    outer = tmp_path / "ECS"
    inner = outer / "deps" / "STL"
    (inner / "Containers" / "src").mkdir(parents=True)
    config.save(config.ModuleConfig.for_new_module("ECS", "cpp"), outer / config.FILE_NAME)
    config.save(config.ModuleConfig.for_new_module("STL", "cpp"), inner / config.FILE_NAME)
    assert Module.find(outer / "deps").name == "ECS"
    assert Module.find(inner / "Containers" / "src").name == "STL"


def test_not_in_module(tmp_path):
    with pytest.raises(EcoBuildError) as error:
        Module.find(tmp_path)
    assert error.value.code == ErrorCode.NOT_IN_MODULE
    assert error.value.hint


@pytest.mark.parametrize("table", [{"branches": "main"}, {"os": "linux"}, {"configurations": [1]},
                                   {"branches": [1]}, {"shared": "yes"}])
def test_invalid_ci_table_is_invalid_config(table):
    """[ci] の型の誤りは、変換の前に設定の誤りにする（文字列が1文字ずつに分かれる・TypeError にならない）。"""
    settings = config.ModuleConfig.for_new_module("Calc", "cpp")
    broken = config.ModuleConfig(**{**settings.__dict__, "extra": {config.CI_TABLE: table}})
    with pytest.raises(EcoBuildError) as error:
        broken.ci
    assert error.value.code == ErrorCode.INVALID_CONFIG


def test_ci_branches_roundtrip():
    settings = config.ModuleConfig.for_new_module("Calc", "cpp")
    saved = settings.with_ci(config.CiSettings(branches=("main", "release/**")))
    assert saved.ci.branches == ("main", "release/**") and saved.ci.configurations == ("Debug",)
