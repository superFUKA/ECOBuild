"""エージェントの記録（ecobuild_agent.agents）：ID ごとの記録・親子・会話で引く・作業空間で引く・忘れる。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import ecobuild_bundle  # noqa: F401（拡張の判断の口をつなぐ）
from ecobuild.errors import EcoBuildError
from ecobuild_agent import AgentModule, agents, status


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))


def test_a_record_is_kept_per_agent(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    lead = agents.create(registration="lead", workspace=root, task={"number": 3, "branch": "task/3-x"}, model="opus",
                         session="s-1")
    assert agents.is_id(lead.id) and lead.name == "lead" and lead.parent is None and lead.kind == agents.OWNER
    assert lead.folder == status.directory(lead.id) and (lead.folder / agents.RECORD).is_file()
    assert agents.load(lead.id) == lead
    assert agents.by_session("s-1") == lead and agents.by_session("s-2") is None
    with pytest.raises(EcoBuildError):
        agents.load("a-0000000000")
    with pytest.raises(EcoBuildError):
        agents.load("../lead")
    with pytest.raises(EcoBuildError):
        agents.create(registration="lead", workspace=root, kind="boss")


def test_children_are_the_direct_ones_with_numbered_names(tmp_path):
    root, other = tmp_path / "ws", tmp_path / "ws2"
    root.mkdir()
    other.mkdir()
    lead = agents.create(registration="lead", workspace=root)
    first = agents.create(registration="worker", workspace=other, parent=lead.id, task={"number": 4, "branch": "b"})
    helper = agents.create(registration="worker", workspace=root, parent=lead.id, kind=agents.HELPER)
    grandchild = agents.create(registration="worker", workspace=other, parent=first.id, kind=agents.HELPER)
    assert (first.name, helper.name, grandchild.name) == ("worker-1", "worker-2", "worker-1")
    assert [c.id for c in agents.children(lead.id)] == [first.id, helper.id]           # 直接の子だけ
    assert [r.id for r in agents.in_workspace(root)] == [lead.id, helper.id]
    assert agents.update(first.id, session="s-9").session == "s-9" and agents.by_session("s-9").id == first.id
    agents.forget(helper.id)
    assert [c.id for c in agents.children(lead.id)] == [first.id] and status.directory(helper.id) is None


def module(root: Path, name="Calc"):
    """AgentModule の口だけを使う作業空間（本体の before_close_workspace は空）。"""
    class Base:
        def before_close_workspace(self, path):
            return []

    class Workspace(AgentModule, Base):
        pass
    found = Workspace()
    found.root, found.config, found.command = root, SimpleNamespace(name=name), "ecobuild"
    return found


def test_a_workspace_with_a_running_agent_or_an_open_child_task_is_not_closed(tmp_path):
    import os
    root, child_root = tmp_path / "ws", tmp_path / "ws2"
    root.mkdir()
    child_root.mkdir()
    owner = agents.create(registration="lead", workspace=root)
    assert module(root).before_close_workspace(root) == []
    status.started(owner.folder, os.getpid())
    assert any(owner.id in reason and "動いています" in reason for reason in module(root).before_close_workspace(root))
    status.ended(owner.folder, os.getpid())
    child = agents.create(registration="worker", workspace=child_root, parent=owner.id, task={"number": 7, "branch": "b"})
    reasons = module(root).before_close_workspace(root)
    assert len(reasons) == 1 and "#7" in reasons[0] and child.name in reasons[0]
    agents.forget(child.id)
    assert module(root).before_close_workspace(root) == []


def test_the_briefing_tells_who_owns_the_task(tmp_path, monkeypatch):
    """渡す文：共通の前置き（モジュール・タスク・作業空間・持ち主か手伝いか・持ち主）＋登録の文書。CLI の手順は入れない。"""
    root = tmp_path / "ws"
    root.mkdir()
    owner = agents.create(registration="manager", workspace=root)
    helper = agents.create(registration="worker", workspace=root, parent=owner.id, kind=agents.HELPER)
    found = module(root)
    task = SimpleNamespace(number=5, branch="task/5-画面")
    text = found.agent_briefing(task, owner)
    assert "「Calc」" in text and "task/5-画面" in text and "持ち主です（人が起動しました）" in text
    assert "## あなたの役：管理役" in text and "agent guide" not in text
    told = found.agent_briefing(task, helper)
    assert "手伝いです" in told and f"「{owner.name}」（{owner.id}）のもの" in told and "## あなたの役：作業役" in told
