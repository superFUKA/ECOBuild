"""ecobuild agent registry・rules・preset：モジュールのエージェントの設定は、タスクブランチで変えてコミットする。"""

import json

import pytest
from click.testing import CliRunner

from helpers import git
from ecowork import github as _github
from ecobuild_agent import registry, rules
from ecobuild_cli import build_cli

pytestmark = pytest.mark.local


@pytest.fixture
def cli(module, monkeypatch):
    monkeypatch.setattr(_github, "default", lambda: module.repository.github)
    monkeypatch.chdir(module.root)
    runner = CliRunner()
    return lambda *args, input=None: json.loads(runner.invoke(build_cli(), [*args, "--json"], input=input,
                                                              catch_exceptions=False).stdout)


def test_module_settings_are_changed_on_a_task_branch_and_committed(module, cli):
    refused = cli("agent", "rules", "set", "分けすぎない")
    assert not refused["ok"] and "タスクブランチ" in refused["error"]["message"]
    assert not cli("agent", "registry", "add", "reviewer", "--from-preset", "worker")["ok"]
    assert not (module.root / rules.COMMON_FILE).exists()

    module.repository.create_task("決まり").start(name="決まり")
    done = cli("agent", "rules", "set", "分けすぎない")
    assert done["ok"] and done["result"]["changed"] == [rules.COMMON_FILE] and done["result"]["committed"]
    added = cli("agent", "registry", "add", "reviewer", "--from-preset", "worker")["result"]
    assert (added["source"], added["pending"], bool(added["committed"])) == ("module", True, True)
    changed = cli("agent", "registry", "set", "reviewer", "--tools", "task_*,build", "--children", "", "--document", "-",
                  input="見直す\n")
    assert changed["ok"], changed["error"]
    changed = changed["result"]
    assert (changed["tools"], changed["document"]) == (["task_*", "build"], "見直す\n")
    assert cli("agent", "registry", "set", "reviewer")["error"]["code"] == "invalid_argument"   # 変える項目がない
    assert git(module.root, "status", "--porcelain").strip() == ""             # どれもコミットした

    listed = {r["name"]: r for r in cli("agent", "registry", "list")["result"]}
    assert listed["reviewer"]["pending"] and not listed["lead"]["pending"]     # 取り込むまでは効かない
    assert "reviewer" not in {r["name"] for r in cli("agent", "registry", "list", "--in-force")["result"]}
    assert cli("agent", "rules", "show")["result"]["pending"]

    kept = cli("agent", "preset", "add", "my-reviewer", "--from-module", "reviewer")["result"]
    assert (kept["source"], kept["tools"]) == ("preset", ["task_*", "build"])
    assert "my-reviewer" in {r["name"] for r in cli("agent", "preset", "list")["result"]}
    assert cli("agent", "registry", "remove", "reviewer")["error"]["code"] == "confirmation_required"
    assert cli("agent", "registry", "remove", "reviewer", "--yes")["ok"]
    assert not (module.root / registry.MODULE_FOLDER / "reviewer").exists()
    assert cli("agent", "preset", "remove", "my-reviewer", "--yes")["ok"]


def test_tools_have_areas_and_fit_tells_what_a_choice_of_tools_comes_to(module, cli):
    tools = {t["name"]: t for t in cli("agent", "registry", "tools")["result"]}
    assert tools["task_commit"]["area"] == "タスク" and tools["status"]["area"] == "状態・履歴を見る"
    assert all(t["area"] for t in tools.values())

    now = cli("agent", "registry", "fit", "lead")["result"]             # 書かなければ、今の並び（見本の lead は *）
    assert (now["tools"], now["count"], now["total"]) == (["*"], len(tools), len(tools))
    assert now["owner"] > 0 and now["too_many"] == (len(tools) > now["limit"]) and now["stronger"] == []
    narrow = cli("agent", "registry", "fit", "lead", "--tools", "status,diff")["result"]
    assert (narrow["count"], narrow["owner"], narrow["too_many"]) == (2, 0, False)
    assert {"manager", "worker"} <= set(narrow["stronger"])            # 子より弱くなる（その子は選べない）
    child = cli("agent", "registry", "fit", "worker", "--tools", "*")["result"]
    assert isinstance(child["parents"], list)
    none = cli("agent", "registry", "fit", "lead", "--tools", "")["result"]
    assert (none["tools"], none["count"]) == ([], 0)
    assert cli("agent", "registry", "fit", "nobody")["ok"] is False


def test_add_can_set_the_title_who_starts_it_and_leave_out_the_owner_tools(module, cli):
    module.repository.create_task("役").start(name="役")
    added = cli("agent", "registry", "add", "reviewer", "--from-preset", "worker", "--title", "レビュー役", "--human-start",
                "--no-owner-tools")
    assert added["ok"], added["error"]
    assert any("外しました" in notice and "強くなります" in notice for notice in added["notices"])     # 外した子は知らせる
    added = added["result"]
    marks = {t["name"]: t["mark"] for t in cli("agent", "registry", "tools")["result"]}
    assert (added["title"], added["human_start"], bool(added["committed"])) == ("レビュー役", True, True)
    assert added["tools"] and all(marks[name] != "owner" for name in added["tools"])
    assert added["children"] == []                                      # 写した元の子（すべてのツールを持つ）は、強くなるので外れる
    assert git(module.root, "status", "--porcelain").strip() == ""
    plain = cli("agent", "registry", "add", "helper", "--from-preset", "worker")      # 書かなければ、写した元のまま
    assert not any("外しました" in notice for notice in plain["notices"])
    plain = plain["result"]
    worker = next(r for r in cli("agent", "preset", "list")["result"] if r["name"] == "worker")
    assert (plain["title"], plain["human_start"], plain["tools"]) == (worker["title"], worker["human_start"], worker["tools"])
