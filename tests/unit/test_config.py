import pytest

from ecobuild import config
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module import Module


def test_roundtrip(tmp_path):
    original = config.ModuleConfig.for_new_module("Calc", app=True)
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    assert config.load(path) == original


def test_roundtrip_without_app(tmp_path):
    original = config.ModuleConfig.for_new_module("Calc", app=False)
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    loaded = config.load(path)
    assert loaded.projects.app is None
    assert loaded.projects.test == "CalcTest"
    assert loaded.default_base == "main"


def test_quoting_survives_special_characters(tmp_path):
    original = config.ModuleConfig.for_new_module(r'Ca"l\c', app=False)
    path = tmp_path / config.FILE_NAME
    config.save(original, path)
    assert config.load(path).name == r'Ca"l\c'


def test_invalid_file(tmp_path):
    path = tmp_path / config.FILE_NAME
    path.write_text("format = 1\n[module]\nname = 'x'\n", encoding="utf-8")
    with pytest.raises(EcoBuildError) as error:
        config.load(path)
    assert error.value.code == ErrorCode.INVALID_CONFIG


def test_find_nearest_module_upwards(tmp_path):
    outer = tmp_path / "ECS"
    inner = outer / "deps" / "STL"
    (inner / "Containers" / "src").mkdir(parents=True)
    config.save(config.ModuleConfig.for_new_module("ECS", app=False), outer / config.FILE_NAME)
    config.save(config.ModuleConfig.for_new_module("STL", app=False), inner / config.FILE_NAME)
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
    settings = config.ModuleConfig.for_new_module("Calc", app=False)
    broken = config.ModuleConfig(**{**settings.__dict__, "extra": {config.CI_TABLE: table}})
    with pytest.raises(EcoBuildError) as error:
        broken.ci
    assert error.value.code == ErrorCode.INVALID_CONFIG


def test_ci_branches_roundtrip():
    settings = config.ModuleConfig.for_new_module("Calc", app=False)
    saved = settings.with_ci(config.CiSettings(branches=("main", "release/**")))
    assert saved.ci.branches == ("main", "release/**") and saved.ci.configurations == ("Debug",)
