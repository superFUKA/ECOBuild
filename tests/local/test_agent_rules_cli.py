"""ecobuild agent rules：モジュールのエージェント向けの決まりは、タスクブランチで変えてコミットする。"""

import json

import pytest
from click.testing import CliRunner

from helpers import git
from ecowork import github as _github
from ecobuild_agent import rules
from ecobuild_cli import build_cli

pytestmark = pytest.mark.local


@pytest.fixture
def cli(module, monkeypatch):
    monkeypatch.setattr(_github, "default", lambda: module.repository.github)
    monkeypatch.chdir(module.root)
    runner = CliRunner()
    return lambda *args: runner.invoke(build_cli(), [*args, "--json"], catch_exceptions=False)


def test_rules_are_changed_on_a_task_branch_and_committed(module, cli):
    refused = json.loads(cli("agent", "rules", "set", "--common", "分けすぎない").stdout)
    assert not refused["ok"] and "タスクブランチ" in refused["error"]["message"]
    assert not (module.root / rules.COMMON_FILE).exists()

    module.repository.create_task("決まり").start(name="決まり")
    done = json.loads(cli("agent", "rules", "set", "--common", "分けすぎない").stdout)
    assert done["ok"] and done["result"]["changed"] == [rules.COMMON_FILE] and done["result"]["committed"]
    done = json.loads(cli("agent", "rules", "set", "--role", "worker", "--text", "自分で進める",
                          "--deny", "children_*,task_submit").stdout)
    assert done["result"]["changed"] == [rules.role_path("worker"), rules.TOOLS_FILE]
    assert git(module.root, "status", "--porcelain").strip() == ""             # どれもコミットした
    shown = json.loads(cli("agent", "rules", "show").stdout)["result"]
    worker = next(r for r in shown["roles"] if r["name"] == "worker")
    assert (shown["common"], worker["text"], worker["deny"]) == ("分けすぎない\n", "自分で進める\n", ["children_*", "task_submit"])
    assert shown["pending"] and shown["in_force"] == "origin/main"             # 取り込むまでは効かない
    assert not json.loads(cli("agent", "rules", "set", "--role", "worker").stdout)["ok"]   # 変える項目がない
