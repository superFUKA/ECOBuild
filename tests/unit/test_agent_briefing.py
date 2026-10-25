"""作業空間のエージェントを起動するときに渡すもの：ECOBuild の使い方（--append-system-prompt-file）と、コミットしない置き場所。"""

import json
import subprocess
from types import SimpleNamespace

from ecobuild_agent import registry, skills
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


def test_claude_gets_the_briefing_and_the_tools_as_files(tmp_path):
    """使い方の文は guide.md（--append-system-prompt-file）、エージェント専用の MCP サーバーは mcp.json（--mcp-config・
    --strict-mcp-config）。どちらもエージェントの置き場所に置く。"""
    prepared = []
    record = SimpleNamespace(id="a-0123456789", registration="worker", kind="owner")
    stub = SimpleNamespace(root=tmp_path / "plain", prepare_agent_area=lambda: prepared.append(True),
                           agent_briefing=lambda task, record: f"使い方（#{task.number}・{record.id}）",
                           mcp_config=lambda record, boxed: {"mcpServers": {"ecobuild": {"boxed": boxed}}},
                           _registration=lambda record: registry.Registration(name="worker", title="作業", document="",
                                                                               tools=("task_*",)))
    task = SimpleNamespace(number=12, branch="task/12-log")
    command = Module._briefed(stub, ("claude",), tmp_path, False, task, record)
    here = tmp_path.as_posix()
    assert command == ("claude", "--append-system-prompt-file", f"{here}/guide.md",
                       "--mcp-config", f"{here}/mcp.json", "--strict-mcp-config") and prepared
    assert (tmp_path / "guide.md").read_text(encoding="utf-8") == "使い方（#12・a-0123456789）"
    assert json.loads((tmp_path / "mcp.json").read_text(encoding="utf-8")) == {"mcpServers": {"ecobuild": {"boxed": False}}}
    inside = Module._briefed(stub, ("claude",), tmp_path, True, task, record)       # コンテナの中から見た、自分の置き場所
    assert inside[2] == f"{status.INSIDE}/a-0123456789/guide.md" and inside[4] == f"{status.INSIDE}/a-0123456789/mcp.json"
    assert registry.from_file(tmp_path / "registration.json").tools == ("task_*",)   # このPCで解決した登録の写し
    assert Module._briefed(stub, ("codex",), tmp_path, False, task, record) == ("codex",)   # Claude Code でなければ何もしない


def test_the_skills_the_registration_allows_are_given_by_add_dir(tmp_path):
    """作成元に取り込まれたスキルのうち、登録の skills に合うものを置き場所に写し、--add-dir で渡す（なければ渡さない）。"""
    root = tmp_path / "module"
    root.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / ".ecobuild").mkdir()
    (root / ".ecobuild" / "ecobuild.toml").write_text(
        'format = 5\n\n[module]\nname = "calc"\ntype = "python"\n\n[branches]\ndefault_base = "main"\n', encoding="utf-8")
    skills.add(root, "build-help", description="ビルドの手順")
    skills.add(root, "deploy", description="配る手順")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "skills"], check=True)
    record = SimpleNamespace(id="a-0123456789", registration="worker", kind="owner")
    allowed = []
    stub = SimpleNamespace(root=root, prepare_agent_area=lambda: None, agent_briefing=lambda task, record: "",
                           mcp_config=lambda record, boxed: {},
                           _registration=lambda record: registry.Registration(name="worker", title="作業", document="",
                                                                               skills=tuple(allowed)))
    task = SimpleNamespace(number=12, branch="task/12-log")
    folder = tmp_path / "area"
    folder.mkdir()
    assert "--add-dir" not in Module._briefed(stub, ("claude",), folder, True, task, record)   # 使えるスキルがない
    allowed.append("build-*")
    command = Module._briefed(stub, ("claude",), folder, True, task, record)
    assert command[command.index("--add-dir") + 1] == f"{status.INSIDE}/a-0123456789/skills"
    assert [p.name for p in (folder / "skills" / ".claude" / "skills").iterdir()] == ["build-help"]


def test_the_mcp_server_is_fixed_to_the_agent(tmp_path):
    """MCP の設定は、呼び手（ID・登録・持ち主か手伝いか）と作業空間を引数で固定する。コンテナの中では中の ecobuild で。"""
    record = SimpleNamespace(id="a-0123456789", registration="worker", kind="helper")
    stub = SimpleNamespace(root=tmp_path / "plain")
    server = Module.mcp_config(stub, record)["mcpServers"]["ecobuild"]
    assert server["command"] == "ecobuild" and server["args"] == [
        "agent", "mcp", "--agent", "a-0123456789", "--registration", "worker", "--kind", "helper", "--workspace", "/work",
        "--registration-file", f"{status.INSIDE}/a-0123456789/registration.json"]   # 中には このPCの登録がない
    outside = Module.mcp_config(stub, record, boxed=False)["mcpServers"]["ecobuild"]
    assert outside["args"][:2] == ["-m", "ecobuild_cli"] and outside["args"][-1] == str(tmp_path / "plain")
