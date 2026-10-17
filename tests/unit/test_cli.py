import json

import click
import pytest
from click.testing import CliRunner

from ecobuild import config
from ecobuild_cli import _types, build_cli


def _module_file(root):
    """モジュールの印（.ecobuild/ecobuild.toml）。フォルダーも作る。"""
    path = root / config.FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

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
    assert {"build", "test", "run", "clean", "rebuild", "file", "deps", "project", "template"} <= _names(cpp)
    assert not {"link", "unlink"} & _names(cpp)              # deps add・deps remove になった
    assert {"add", "remove", "list", "sync", "tree", "update"} <= _names(cpp, "deps")
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
    _module_file(tmp_path).write_text('format = 1\n\n[module]\nname = "M"\ntype = "generic"\n', encoding="utf-8")
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
    _module_file(tmp_path).write_text('format = 1\n\n[module]\nname = "M"\ntype = "python"\n', encoding="utf-8")
    (tmp_path / "src").mkdir()
    assert _types.current(tmp_path / "src") == "python"
    _module_file(tmp_path).write_text("壊れた", encoding="utf-8")
    assert _types.current(tmp_path) is None


def _catalog(capsys, *args):
    from ecobuild_cli import main
    with pytest.raises(SystemExit) as stop:
        main([*args, "--help", "--json"])
    return stop.value.code, json.loads(capsys.readouterr().out)


def test_help_json_lists_every_command(tmp_path, monkeypatch, capsys):
    """ecobuild --help --json：共通のコマンドと、型ごとのコマンド（説明・引数・オプション）。"""
    monkeypatch.chdir(tmp_path)
    code, document = _catalog(capsys)
    assert code == 0 and document["ok"]
    common = {c["name"]: c for c in document["result"]["commands"]}
    assert {"task", "status", "sync", "module"} <= set(common) and "build" not in common
    close = next(c for c in common["task"]["commands"] if c["name"] == "close")
    assert close["path"] == "task close" and close["section"] == "計画" and close["runnable"]
    assert close["arguments"] == [{"name": "ISSUE", "help": "タスクの番号", "required": True, "multiple": False}]
    names = [o["names"] for o in close["options"]]
    assert ["--not-planned"] in names and ["--json"] not in names       # どのコマンドにもあるものは出さない
    assert not common["task"]["runnable"] and common["sync"]["runnable"]   # sync はグループでも実行できる
    types = document["result"]["types"]
    assert set(types) == {"cpp", "python", "generic"}
    cpp = {c["name"]: c for c in types["cpp"]["commands"]}
    assert {"build", "project", "deps"} <= set(cpp) and "task" not in cpp
    assert cpp["module"]["extends"] and [c["name"] for c in cpp["module"]["commands"]] == ["settings"]
    assert "file" not in {c["name"] for c in types["generic"]["commands"]}


def test_help_json_for_one_command(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, document = _catalog(capsys, "task", "close")
    assert code == 0 and document["result"]["path"] == "task close"
    code, document = _catalog(capsys, "nosuch")
    assert code == 2 and document["error"]["code"] == "usage_error"


def _external_command(folder, name, body):
    """PATH に置く外部サブコマンド ecobuild-<name>（Python のスクリプトを呼ぶ小さな起動役）。"""
    import os
    import sys
    script = folder / f"{name}.py"
    script.write_text(body, encoding="utf-8")
    if os.name == "nt":
        (folder / f"ecobuild-{name}.cmd").write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = folder / f"ecobuild-{name}"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)


def test_unknown_command_runs_the_external_one(tmp_path, monkeypatch, capfd):
    """ecobuild hello a b → PATH の ecobuild-hello に引数ごと（git と同じ）。終了コードもそのまま。"""
    import os
    from ecobuild_cli import main
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _external_command(bin_dir, "hello", "import sys, os; print('hello', sys.argv[1:], os.getcwd()); sys.exit(3)")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as stop:
        main(["-C", str(work), "hello", "a", "b"])
    assert stop.value.code == 3
    out = capfd.readouterr().out
    assert "hello ['a', 'b']" in out and str(work) in out          # -C のフォルダで実行
    from ecobuild_cli import _extensions
    assert "hello" in _extensions.available()
    result = CliRunner().invoke(build_cli(None), ["--help"])
    assert "拡張コマンド" in result.output and "hello" in result.output


def test_builtin_commands_win_over_external_ones(tmp_path, monkeypatch):
    import os
    from ecobuild_cli import _external
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _external_command(bin_dir, "status", "print('external')")
    _external_command(bin_dir, "build", "print('external')")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    assert _external("status") is None and _external("build") is None     # 共通・型のコマンドが先
    assert _external("nosuch") is None
