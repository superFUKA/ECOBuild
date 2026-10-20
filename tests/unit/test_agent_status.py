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


def test_with_an_app_the_app_delivers(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    folder = status.prepare("box", tmp_path)
    settings = json.loads(status.claude_settings(folder.as_posix(), "python"))
    assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"].endswith(" prompt")   # 作業中かを見るだけ
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


def test_a_lead_may_write_only_in_its_area(tmp_path, monkeypatch):
    """進行役の編集の道具は、エージェント用の置き場所（計画・任せる内容）の中だけ（PreToolUse フック）。"""
    import os
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    folder = status.prepare("box", tmp_path)
    area = (tmp_path / "work" / ".ecobuild" / "ai").as_posix()
    cwd = str(tmp_path / "work")

    def decide(path):
        out = hook(folder, "lead-edit", area, data={"cwd": cwd, "tool_input": {"file_path": path}})
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"
    assert decide(".ecobuild/ai/plan.md") == "allow"
    assert decide(os.path.join(area, "briefs", "a.md")) == "allow"
    assert decide("src/app.py") == "deny"
    assert decide(".ecobuild/ai/../../src/app.py") == "deny"
    assert decide(str(tmp_path / "work" / ".ecobuild" / "aiX" / "x")) == "deny"
