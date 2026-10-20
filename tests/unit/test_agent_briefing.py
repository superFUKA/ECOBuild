"""作業空間のエージェントを起動するときに渡すもの：ECOBuild の使い方（--append-system-prompt-file）と、コミットしない置き場所。"""

import subprocess
from types import SimpleNamespace

from ecobuild_agent import AGENT_AREA, status
from ecobuild_bundle import Module
from ecowork.git import Git


def test_the_agent_area_is_excluded_without_changing_the_repository(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    workspace = SimpleNamespace(root=tmp_path, repository=SimpleNamespace(git=Git(tmp_path)))
    area = Module.prepare_agent_area(workspace)
    assert area == tmp_path / AGENT_AREA and area.is_dir()
    exclude = (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert f"/{AGENT_AREA}/" in exclude.splitlines()
    Module.prepare_agent_area(workspace)                                           # 二度目は足さない
    assert (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8").count(f"/{AGENT_AREA}/") == 1
    (area / "memo.md").write_text("下書き", encoding="utf-8")
    status = subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert ".ecobuild" not in status                                              # コミットの対象に出ない


def test_claude_gets_the_briefing_as_a_file(tmp_path):
    prepared = []
    stub = SimpleNamespace(prepare_agent_area=lambda: prepared.append(True),
                           agent_briefing=lambda task, role="worker": f"使い方（#{task.number}）")
    task = SimpleNamespace(number=12, branch="task/12-log")
    command = Module._briefed(stub, ("claude",), tmp_path, False, task)
    assert command == ("claude", "--append-system-prompt-file", f"{tmp_path.as_posix()}/guide.md") and prepared
    assert (tmp_path / "guide.md").read_text(encoding="utf-8") == "使い方（#12）"
    inside = Module._briefed(stub, ("claude",), tmp_path, True, task)               # コンテナの中から見た場所
    assert inside[-1] == f"{status.INSIDE}/guide.md"
    assert Module._briefed(stub, ("codex",), tmp_path, False, task) == ("codex",)   # Claude Code でなければ何もしない
