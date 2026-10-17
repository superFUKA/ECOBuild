"""ecoagent.start：新しい画面でエージェントを起動する（本物のプロセスは起動せず、Popen に渡すものを確かめる）。"""

import pytest

import ecoagent
from ecoagent import launch


class _Popen:
    calls = []

    def __init__(self, args, **kwargs):
        self.pid = 4321
        _Popen.calls.append((args, kwargs))


@pytest.fixture
def popen(monkeypatch):
    _Popen.calls = []
    monkeypatch.setattr(launch.subprocess, "Popen", _Popen)
    monkeypatch.setattr(launch.shutil, "which", lambda name: f"/bin/{name}")
    return _Popen.calls


def test_starts_in_the_directory_in_a_new_window(popen, tmp_path, monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "win32")
    monkeypatch.setattr(launch.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)
    session = ecoagent.start(tmp_path)
    assert session == ecoagent.Session(4321, ("claude",), tmp_path.resolve())
    args, kwargs = popen[0]
    assert args == ["/bin/claude"]
    assert kwargs["cwd"] == tmp_path.resolve() and kwargs["creationflags"] == 16


def test_other_systems_use_a_terminal(popen, tmp_path, monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "linux")
    monkeypatch.delenv("TERMINAL", raising=False)
    ecoagent.start(tmp_path, ["codex", "--full-auto"])
    args, kwargs = popen[0]
    assert args == ["/bin/x-terminal-emulator", "-e", "/bin/codex", "--full-auto"]
    assert kwargs["start_new_session"]


def test_missing_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(launch.shutil, "which", lambda name: None)
    with pytest.raises(ecoagent.AgentError) as raised:
        ecoagent.start(tmp_path)
    assert raised.value.code == ecoagent.ErrorCode.AGENT_NOT_FOUND and "claude" in raised.value.hint


def test_missing_directory(tmp_path):
    with pytest.raises(ecoagent.AgentError) as raised:
        ecoagent.start(tmp_path / "nosuch")
    assert raised.value.code == ecoagent.ErrorCode.DIRECTORY_NOT_FOUND

