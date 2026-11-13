"""推測で打たれた名前：もしかして・-m の読み替え・位置引数付きの --help --json。"""
import json

import pytest

from ecobuild_cli import _suggest


def _run(capsys, *args):
    from ecobuild_cli import main
    with pytest.raises(SystemExit) as stop:
        main(list(args))
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    return stop.value.code, json.loads(lines[-1]) if lines else None, captured.err


@pytest.mark.parametrize(("typed", "told"), [
    (("task", "create", "x"), "もしかして：ecobuild task new x"),
    (("task", "show", "1"), "もしかして：ecobuild task status 1"),
    (("profile", "show"), "もしかして：ecobuild profile list"),
    (("member", "list"), "もしかして：ecobuild module members"),
    (("commit",), "もしかして：ecobuild task commit"),
    (("tsk", "list"), "もしかして：ecobuild task"),          # 似た名前
    (("task", "sumbit"), "もしかして：ecobuild task submit"),
])
def test_guessed_names_are_answered_with_the_right_command(tmp_path, monkeypatch, capsys, typed, told):
    """ない名前は今までどおり引数の誤り（終了コード2。実行しない）で、hint に正しいコマンドを示す。"""
    monkeypatch.chdir(tmp_path)
    code, document, _ = _run(capsys, *typed, "--json")
    assert code == 2 and document["error"]["code"] == "usage_error" and document["error"]["hint"] == told


def test_file_contents_are_not_a_command(tmp_path, monkeypatch, capsys):
    assert "ecobuild files" in _suggest.suggestion(["file", "read", "a.txt"])
    assert _suggest.suggestion(["task", "status", "1"]) is None          # ある名前（後ろは位置引数）
    assert _suggest.suggestion(["zzzzzz"]) is None                       # 似たものがなければ出さない


def test_suggestion_is_shown_to_people_too(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, err = _run(capsys, "task", "create", "x")
    assert code == 2 and "もしかして：ecobuild task new x" in err


def test_m_is_read_as_message_only_where_there_is_one():
    """-m は、打ったコマンドに --message があるときだけ --message（-- の後ろは位置引数のまま）。"""
    from ecobuild_cli import _catalog, build_cli

    def find(words):
        return _catalog.find_longest(build_cli(None), words)[0] if words else None
    assert _suggest.rewrite(["task", "commit", "-m", "直した"], find) == ["task", "commit", "--message", "直した"]
    assert _suggest.rewrite(["task", "commit", "--message", "a", "--", "-m"], find)[-1] == "-m"
    assert _suggest.rewrite(["task", "list", "-m"], find) == ["task", "list", "-m"]     # --message がない
    assert _suggest.rewrite(["status"], find) == ["status"]
    assert _suggest.rewrite(["task", "commit", "--message", "-m"], find) == ["task", "commit", "--message", "-m"]   # 値
    assert _suggest.rewrite(["task", "comment", "1", "-m", "a"], find)[3] == "--message"


def test_m_through_the_entry(tmp_path, monkeypatch, capsys):
    """入口（main）を通しても読み替える（--json を前に置いても）。モジュールの外なので、その理由で止まる（-m の誤りではない）。"""
    monkeypatch.chdir(tmp_path)
    code, document, _ = _run(capsys, "--json", "task", "commit", "-m", "直した")
    assert document["error"]["code"] != "usage_error"


def test_type_commands_that_no_type_has(tmp_path, monkeypatch, capsys):
    """file list（どの型にもない）は、モジュールの外でも、もしかして。project add x --help --json は位置引数を外す。"""
    monkeypatch.chdir(tmp_path)
    code, document, _ = _run(capsys, "file", "list", "--json")
    assert document["error"]["hint"] == "もしかして：ecobuild files"
    code, document, _ = _run(capsys, "file", "list", "--help", "--json")
    assert code == 2 and document["error"]["hint"] == "もしかして：ecobuild files"
    code, document, _ = _run(capsys, "project", "add", "x", "--help", "--json")
    assert document["error"]["code"] == "not_supported" and "project add は型" in document["error"]["message"]


def test_guess_keeps_the_typed_arguments(tmp_path, monkeypatch, capsys):
    assert _suggest.suggestion(["task", "show", "252"]) == "もしかして：ecobuild task status 252"


def test_help_json_with_positional_arguments(tmp_path, monkeypatch, capsys):
    """task status 252 --help --json：後ろの位置引数を外して、そのコマンドの説明を返す。グループの下のない名前は誤り。"""
    monkeypatch.chdir(tmp_path)
    code, document, _ = _run(capsys, "task", "status", "252", "--help", "--json")
    assert code == 0 and document["result"]["path"] == "task status"
    code, document, _ = _run(capsys, "task", "create", "--help", "--json")
    assert code == 2 and document["error"]["hint"] == "もしかして：ecobuild task new"
