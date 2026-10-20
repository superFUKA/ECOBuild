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
    assert "UserPromptSubmit" not in settings["hooks"] and settings["voice"]["mode"] == "hold"
    status.put(folder, "言付け")
    assert hook(folder, "replied") == "" and status.take(folder)["text"] == "言付け"     # フックは取らない
