"""ecoagent.guard：シェルのコマンドの関所（ダメなものの列挙）。"""

import json

from ecoagent import guard


# ---- ダメなものの列挙（Denied） -----------------------------------------------------------------------------------

def _tool_rule(args):
    return "tool delete は止めます" if args[:1] == ["delete"] else None


DENIED = guard.Denied(programs={"secret": "secret は使えません"}, commands={"tool": _tool_rule})


def test_denied_stops_only_what_is_listed():
    assert guard.check_denied("rm -rf build && cat a.txt > b.txt", DENIED) is None   # 書かれていないものは通す
    assert guard.check_denied("tool list", DENIED) is None
    assert guard.check_denied("secret --x", DENIED) == "secret は使えません"
    assert guard.check_denied("C:/bin/Secret.exe", DENIED) == "secret は使えません"
    assert guard.check_denied("ls; tool delete 3", DENIED) == "tool delete は止めます"
    assert guard.check_denied('grep "tool delete" a.txt', DENIED) is None             # 引用符の中の文はコマンドではない
    assert guard.check_denied("echo 'a; secret'", DENIED) is None


def test_denied_looks_into_wrappers_and_embedded_commands():
    for command in ("FOO=1 tool delete", "env -i FOO=1 tool delete", "sudo -u x tool delete", "timeout 10 tool delete",
                    "xargs -n 1 tool delete", 'bash -c "ls && tool delete"', "sh -c 'tool delete'",
                    'echo "$(tool delete)"', "echo `tool delete`", "(cd x; tool delete)", "if true; then tool delete; fi",
                    "eval tool delete", "ls |\ntool delete", "nohup secret &"):
        assert guard.check_denied(command, DENIED) is not None, command
    assert guard.check_denied("echo 'can`t", DENIED) is not None                      # 読み取れないものは止める


def test_denied_hook_answers_with_two_and_the_reason():
    assert guard.hook_denied(json.dumps({"tool_input": {"command": "tool list"}}), DENIED) == (0, "")
    assert guard.hook_denied(json.dumps({"tool_input": {"command": "secret"}}), DENIED) == (2, "secret は使えません")
    assert guard.hook_denied("壊れた", DENIED) == (0, "")
