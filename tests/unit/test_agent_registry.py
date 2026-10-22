"""エージェントの登録（ecobuild_agent.registry）と CLI（agent registry）。"""

import json
import re

import pytest
from click.testing import CliRunner

from ecobuild.errors import EcoBuildError
from ecobuild_agent import registry
from ecobuild_cli import build_cli


def test_every_sample_can_be_read():
    """見本が全部読め、子の名前が見本の中にあり、自分より強い子を持たないこと。"""
    found = {r.name: r for r in registry.samples()}
    assert {"lead", "manager", "worker"} <= set(found)
    for sample in found.values():
        assert sample.source == registry.SAMPLE
        assert sample.title and sample.document.strip() and sample.first_prompt
        assert set(sample.children) <= set(found)
        assert not any(registry.stronger(found[child], sample) for child in sample.children)
    assert found["lead"].human_start and not found["worker"].human_start
    assert found["manager"].model == "opus" and found["worker"].model == "sonnet"


def test_sample_documents_name_tools_not_commands():
    """見本の文書は ecobuild のコマンドではなく、ツールの名前で案内する。"""
    for sample in registry.samples():
        assert not re.search(r"\becobuild ", sample.document), sample.name   # 製品名の ECOBuild は書いてよい
        assert "children_start" in sample.document or sample.name == "worker"


def test_user_registration_overrides_the_sample():
    assert registry.load("worker").source == registry.SAMPLE
    changed = registry.update("worker", model="haiku", document="# 自分用\n")
    assert changed.source == registry.USER
    loaded = registry.load("worker")
    assert (loaded.model, loaded.document, loaded.source) == ("haiku", "# 自分用\n", registry.USER)
    assert [r for r in registry.list_registrations() if r.name == "worker"] == [loaded]
    assert next(r for r in registry.samples() if r.name == "worker").model == "sonnet"   # 見本は変わらない
    registry.remove("worker")
    assert registry.load("worker").source == registry.SAMPLE


def test_add_copies_a_sample_or_imports_a_folder(tmp_path):
    copied = registry.add("reviewer", from_sample="worker")
    assert (copied.title, copied.source, copied.tools) == ("作業役", registry.USER, ("*",))
    assert (registry.user_root() / "reviewer" / registry.DOCUMENT_FILE).read_text(encoding="utf-8") == copied.document
    with pytest.raises(EcoBuildError, match="もうあります"):
        registry.add("reviewer")

    folder = tmp_path / "given"
    folder.mkdir()
    (folder / "agent.toml").write_text('title = "調べ役"\ntools = ["task_status"]\nfirst_prompt = "調べて"\n',
                                       encoding="utf-8")
    (folder / "agent.md").write_text("調べます\n", encoding="utf-8")
    imported = registry.add("research", from_dir=folder)
    assert (imported.title, imported.tools, imported.document) == ("調べ役", ("task_status",), "調べます\n")
    assert registry.load("research") == imported


@pytest.mark.parametrize("name", ["Bad", "-x", "a/b", ""])
def test_bad_names_are_refused(name):
    with pytest.raises(EcoBuildError):
        registry.add(name)


def test_a_stronger_child_is_refused():
    """子に、自分の tools で許されないツールを許す登録は入れられない（知らない名前も）。"""
    registry.add("narrow")
    registry.update("narrow", tools=["task_*"], children=[])
    with pytest.raises(EcoBuildError, match="強い"):
        registry.update("narrow", children=["worker"])        # worker は * を許す
    registry.add("tiny")
    registry.update("tiny", tools=["task_status", "task_s*"], children=[])
    registry.update("narrow", children=["tiny"])              # task_* は task_status・task_s* を含む
    with pytest.raises(EcoBuildError, match="強く"):
        registry.update("tiny", tools=["build"])             # 子が親より強くなる変更も断る
    with pytest.raises(EcoBuildError, match="知らない"):
        registry.update("narrow", children=["nobody"])
    with pytest.raises(EcoBuildError, match="子として"):
        registry.remove("tiny")                               # 子にしている登録がある


def test_allows_tool_matches_patterns():
    reg = registry.Registration(name="x", title="x", document="", tools=("task_*", "build"))
    assert registry.allows_tool(reg, "task_status") and registry.allows_tool(reg, "build")
    assert not registry.allows_tool(reg, "children_start")
    assert not registry.allows_tool(registry.Registration(name="y", title="y", document=""), "build")


def test_samples_cannot_be_removed():
    with pytest.raises(EcoBuildError, match="見本"):
        registry.remove("lead")


def _run(*args, input=None):
    result = CliRunner().invoke(build_cli(None), ["agent", "registry", *args, "--json"], input=input)
    return json.loads(result.output)


def test_cli_list_show_set_add_remove(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    listed = _run("list")["result"]
    lead = next(r for r in listed if r["name"] == "lead")
    assert set(lead) == {"name", "title", "source", "human_start", "model", "children", "max_children", "tools",
                         "document_path"}
    shown = _run("show", "lead")["result"]
    assert shown["document"].startswith("## あなたの役：進行役")
    assert shown["first_prompt"]                                              # GUI の編集が今の値を出す
    assert _run("set", "lead", "--first-prompt", "始めて")["result"]["first_prompt"] == "始めて"

    changed = _run("set", "worker", "--model", "", "--no-human-start", "--document", "-", input="新しい文書\n")["result"]
    assert (changed["source"], changed["model"], changed["document"], changed["tools"]) == ("user", "", "新しい文書\n", ["*"])
    assert _run("set", "worker")["error"]["code"] == "invalid_argument"       # 変える項目がない

    assert _run("add", "mine", "--from-sample", "manager")["result"]["title"] == "管理役"
    refused = _run("remove", "mine")
    assert refused["error"]["code"] == "confirmation_required"
    assert _run("remove", "mine", "--yes")["ok"]
    assert not any(r["name"] == "mine" for r in _run("list")["result"])
