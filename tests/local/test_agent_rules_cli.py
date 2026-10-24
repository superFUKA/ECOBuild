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
