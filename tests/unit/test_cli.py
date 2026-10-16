import json

import click
import pytest
from click.testing import CliRunner

from ecobuild_cli import _types, build_cli

TYPES = (None, "cpp", "python", "generic")


def test_help():
    result = CliRunner().invoke(build_cli(None), ["--help"])
    assert result.exit_code == 0
    assert "ecobuild" in result.output


@pytest.mark.parametrize("module_type", TYPES)
def test_short_help_is_not_cut(module_type):
    """一覧に出る説明（最初の段落）が長いと、Click が空白の位置で切って「...」にする（日本語では丸ごと消える）。
    最初の段落は短い1文にし、続きは次の段落に書く。"""
    cut = []

    def walk(group, path):
        ctx = click.Context(group, info_name=path)
        names = group.list_commands(ctx)
        limit = 78 - 6 - max(len(n) for n in names)   # 幅80の端末での一覧（Click の既定）
        for name in names:
            command = group.get_command(ctx, name)
            if command.get_short_help_str(limit).endswith("..."):
                cut.append(f"{path} {name}")
            if isinstance(command, click.Group):
                walk(command, f"{path} {name}")

    walk(build_cli(module_type), "ecobuild")
    assert cut == []


def _names(cli, *path):
    group = cli
    for name in path:
        group = group.commands[name]
    return set(group.commands)


def test_each_type_has_its_own_commands():
    """型ごとのコマンドは、その型のモジュールの中でだけ出る。共通のコマンドはどこでも出る。"""
    outside, cpp, python, generic = (build_cli(t) for t in TYPES)
    for cli in (outside, cpp, python, generic):
        assert {"task", "status", "sync", "check", "module", "profile"} <= _names(cli)
    assert not {"build", "file", "project", "deps", "link"} & _names(outside)
    assert {"build", "test", "run", "clean", "rebuild", "file", "deps", "project", "template", "link", "unlink"} \
        <= _names(cpp)
    assert {"build", "test", "run", "clean", "rebuild", "file"} <= _names(python)
    assert not {"project", "template", "deps", "link"} & _names(python)
    assert {"build", "test", "run", "clean", "rebuild"} <= _names(generic)
    assert not {"file", "project", "deps"} & _names(generic)
    # 共通のグループに、型がコマンドを足す
    assert _names(outside, "profile") == {"list", "use", "remove"}
    assert _names(cpp, "profile") == {"add", "list", "use", "remove", "project"}
    assert _names(python, "profile") == {"add", "list", "use", "remove"}
    assert "settings" in _names(cpp, "module") and "settings" not in _names(python, "module")


def test_options_belong_to_the_type():
    """型だけのオプションは、その型のコマンドにだけある。"""
    def options(cli, *path):
        command = cli
        for name in path:
            command = command.get_command(click.Context(command), name)
        return {o for p in command.get_params(click.Context(command)) for o in p.opts}

    assert "--template" in options(build_cli("cpp"), "file", "add")
    assert "--template" not in options(build_cli("python"), "file", "add")
    assert "--project" in options(build_cli("cpp"), "build")
    assert "--project" not in options(build_cli("python"), "build")
    assert "--architecture" in options(build_cli("cpp"), "profile", "add")
    assert "--architecture" not in options(build_cli("generic"), "profile", "add")


def test_help_lists_type_commands_under_a_heading():
    shown = CliRunner().invoke(build_cli("python"), ["--help"]).output
    assert shown.index("コマンド:") < shown.index("型 python のコマンド:")
    assert shown.split("型 python のコマンド:")[1].split() [0] == "build"
    outside = CliRunner().invoke(build_cli(None), ["--help"]).output
    assert "型ごとのコマンド:" in outside and "型 " not in outside.split("型ごとのコマンド:")[0]


def test_every_type_package_is_found():
    found = _types.all_routes()
    assert set(found) == {"cpp", "python", "generic"}
    assert ("project", "pch") in found["cpp"] and ("file", "add") in found["python"]


def test_other_type_command_is_not_supported(tmp_path, monkeypatch):
    """ほかの型のコマンドは、引数の誤り（2）ではなく not_supported（1）。--json でも同じ。"""
    (tmp_path / "ecobuild.toml").write_text('format = 1\n\n[module]\nname = "M"\ntype = "generic"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(build_cli(), ["project", "add", "Foo", "--kind", "library", "--json"])
    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert document["error"]["code"] == "not_supported"
    assert "型 cpp" in document["error"]["message"] and "generic" in document["error"]["message"]
    result = CliRunner().invoke(build_cli(), ["file", "add", "a.txt"])
    assert result.exit_code == 1 and "cpp・python" in result.output
    assert CliRunner().invoke(build_cli(), ["nosuch"]).exit_code == 2


def test_type_command_outside_module_says_why(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(build_cli(), ["build", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "not_in_module"


def test_current_type(tmp_path):
    assert _types.current(tmp_path) is None
    (tmp_path / "ecobuild.toml").write_text('format = 1\n\n[module]\nname = "M"\ntype = "python"\n', encoding="utf-8")
    (tmp_path / "src").mkdir()
    assert _types.current(tmp_path / "src") == "python"
    (tmp_path / "ecobuild.toml").write_text("壊れた", encoding="utf-8")
    assert _types.current(tmp_path) is None
