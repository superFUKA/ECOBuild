"""エージェントの状態の書き出しと、画面を持つアプリがいないときの受け箱の届け方（ecobuild_agent.status）。"""

import json
import subprocess
import sys

from ecobuild_agent import status


def hook(folder, *args, data=None):
    """置き場所 folder のスクリプトを、Claude Code のフックとして動かす（標準入力に JSON）。"""
    done = subprocess.run([sys.executable, str(folder / status.SCRIPT), *args], input=json.dumps(data or {}).encode(),
                          capture_output=True, check=True)
    return done.stdout.decode("utf-8")


def test_without_an_app_the_hooks_deliver_the_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    folder = status.prepare("box", tmp_path)
    settings = json.loads(status.claude_settings(folder.as_posix(), "python", app=False))
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("replied deliver")
    assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"].endswith("prompt deliver")
    assert "voice" not in settings                                                       # 音声入力はアプリのとき

    assert hook(folder, "replied", "deliver", data={"last_assistant_message": "済み"}) == ""   # 何も届いていない
    status.put(folder, "[ECOBuild] 作業役「画面」の返答が終わりました")
    status.put(folder, "二つ目")
    out = json.loads(hook(folder, "replied", "deliver", data={"last_assistant_message": "済み"}))
    assert out["decision"] == "block" and "作業役「画面」" in out["reason"] and out["reason"].endswith("二つ目")
    assert status.take(folder) is None and status.read(folder / "replied.json")["message"] == "済み"

    status.put(folder, "言付け")
    added = json.loads(hook(folder, "prompt", "deliver"))["hookSpecificOutput"]
    assert added["hookEventName"] == "UserPromptSubmit" and added["additionalContext"].endswith("言付け")

    assert settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"].endswith("midturn deliver")
    assert hook(folder, "midturn", "deliver") == ""                                      # 届いていなければ何もしない
    status.put(folder, "ボタンは左に変更")
    added = json.loads(hook(folder, "midturn", "deliver"))["hookSpecificOutput"]         # 作業中でも届く
    assert added["hookEventName"] == "PostToolUse" and added["additionalContext"].endswith("ボタンは左に変更")
    assert status.take(folder) is None


def test_with_an_app_the_app_delivers(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    folder = status.prepare("box", tmp_path)
    settings = json.loads(status.claude_settings(folder.as_posix(), "python"))
    assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"].endswith(" prompt")   # 作業中かを見るだけ
    assert "PostToolUse" not in settings["hooks"]                                       # 届けるのはアプリ
    assert settings["voice"]["mode"] == "hold"
    status.put(folder, "言付け")
    assert hook(folder, "replied") == "" and hook(folder, "prompt") == ""
    assert status.take(folder)["text"] == "言付け"                                     # フックは取らない


def test_the_activity_tells_working_idle_and_stopped(tmp_path, monkeypatch):
    """様子：動かしているプロセスが生きていて、発言を受け取ったのが返答の終わりより新しければ作業中。"""
    import os
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    folder = status.prepare("box", tmp_path)
    assert status.activity(folder)["state"] == status.STOPPED                          # 起動していない
    status.started(folder, os.getpid())
    assert status.activity(folder)["state"] == status.WORKING                          # 起動して最初の仕事
    hook(folder, "replied", data={"last_assistant_message": "できました。\n  確かめました"})
    seen = status.activity(folder)
    assert seen["state"] == status.IDLE and seen["last_reply"] == "できました。 確かめました"
    hook(folder, "prompt")
    status.put(folder, "言付け")
    seen = status.activity(folder)
    assert seen["state"] == status.WORKING and seen["waiting"] == 1

    status.ended(folder, os.getpid() + 1)                                              # ほかのプロセスの終わりでは消さない
    assert status.activity(folder)["state"] == status.WORKING
    status.ended(folder, os.getpid())
    assert status.activity(folder)["state"] == status.UNKNOWN                          # 記録はないが動いた跡がある
    status.started(folder, 2 ** 22 + 12345)                                            # 動いていないプロセス
    assert status.activity(folder)["state"] == status.STOPPED and not status.alive(2 ** 22 + 12345)


def test_stop_stops_the_process_and_its_children(tmp_path):
    child = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); time.sleep(60)"
    process = subprocess.Popen([sys.executable, "-c", child], start_new_session=True)
    assert status.alive(process.pid)
    status.stop(process.pid)
    process.wait(10)
    assert not status.alive(process.pid)


def test_every_agent_has_its_own_folder_under_the_workspace(tmp_path, monkeypatch):
    """置き場所はエージェントごと（<コンテナの名前>/<ID>）。ID で探せる。前の版の直下のものは数えない。編集を絞る
    フック（前の進行役の lead-edit）は付けない。"""
    import ecobuild_container as container
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    root = tmp_path / "work"
    root.mkdir()
    first = status.create_directory(root, "a-0000000001")
    second = status.create_directory(root, "a-0000000002")
    assert first.parent == second.parent == status.place(container.name(root))
    assert status.directory("a-0000000002") == second and status.directory("a-9999999999") is None
    assert status.workspace_of(first) == root
    status.prepare(container.name(root), root)                       # 前の版：作業空間の置き場所の直下
    assert status.folders() == [first, second]
    assert status.directory("../x") is None and status.inside("a-0000000001") == f"{status.INSIDE}/a-0000000001"
    settings = json.loads(status.claude_settings(first.as_posix(), "python", app=False))
    assert "PreToolUse" not in settings["hooks"] and "lead-edit" not in status.REPORT


def test_the_hook_leaves_notices_for_other_conversations(tmp_path):
    """受け箱のうち、ほかの会話宛て（owner）のものは、フックが取らずに残す。"""
    folder = status.prepare("n", tmp_path)
    status.put(folder, "甲宛て", owner="a")
    status.put(folder, "乙宛て", owner="b")
    status.put(folder, "だれでも")
    ns = {"__name__": "x"}
    import json as _json, io, sys as _sys
    old = _sys.stdin, _sys.argv
    _sys.argv = [str(folder / status.SCRIPT), "prompt", "deliver"]
    _sys.stdin = type("S", (), {"buffer": io.BytesIO(_json.dumps({"session_id": "b"}).encode())})()
    try:
        exec(compile(status.REPORT, "report", "exec"), {"__file__": str(folder / status.SCRIPT), "__name__": "x"})
    finally:
        _sys.stdin, _sys.argv = old
    assert status.take(folder, "a")["text"] == "甲宛て"
    assert status.take(folder) is None
