"""エージェントの登録（ecobuild_agent.registry）：見本・このPCのプリセット・モジュールの登録。"""

import re
import subprocess

import pytest

from ecobuild.errors import EcoBuildError
from ecobuild_agent import registry


def test_every_sample_can_be_read(tmp_path):
    """見本が全部読め、子の名前が見本の中にあり、自分より強い子を持たないこと。モジュールに何もなくても使える。"""
    found = {r.name: r for r in registry.samples()}
    assert {"lead", "manager", "worker"} <= set(found)
    for sample in found.values():
        assert sample.source == registry.SAMPLE
        assert sample.title and sample.document.strip() and sample.first_prompt
        assert set(sample.children) <= set(found)
        assert not any(registry.stronger(found[child], sample) for child in sample.children)
    assert found["lead"].human_start and not found["worker"].human_start
    assert found["manager"].model == "opus" and found["worker"].model == "sonnet"
    assert [r.name for r in registry.list_registrations(tmp_path)] == sorted(found)


def test_sample_documents_name_tools_not_commands():
    """見本の文書は ecobuild のコマンドではなく、ツールの名前で案内する。"""
    for sample in registry.samples():
        assert not re.search(r"\becobuild ", sample.document), sample.name   # 製品名の ECOBuild は書いてよい
        assert "children_start" in sample.document or sample.name == "worker"


def test_module_registration_overrides_the_sample(tmp_path):
    assert registry.load("worker", tmp_path).source == registry.SAMPLE
    changed = registry.update(tmp_path, "worker", model="haiku", document="# 自分用\n")
    assert changed.source == registry.MODULE
    assert (tmp_path / registry.MODULE_FOLDER / "worker" / registry.DOCUMENT_FILE).read_text(encoding="utf-8") == "# 自分用\n"
    loaded = registry.load("worker", tmp_path)
    assert (loaded.model, loaded.document, loaded.source) == ("haiku", "# 自分用\n", registry.MODULE)
    assert next(r for r in registry.samples() if r.name == "worker").model == "sonnet"   # 見本は変わらない
    registry.remove(tmp_path, "worker")
    assert registry.load("worker", tmp_path).source == registry.SAMPLE


def test_add_copies_a_preset_or_imports_a_folder(tmp_path):
    module = tmp_path / "module"
    copied = registry.add(module, "reviewer", from_preset="worker")
    assert (copied.title, copied.source, copied.tools) == ("作業役", registry.MODULE, ("*",))
    with pytest.raises(EcoBuildError, match="もうあります"):
        registry.add(module, "reviewer")

    folder = tmp_path / "given"
    folder.mkdir()
    (folder / "agent.toml").write_text('title = "調べ役"\ntools = ["task_status"]\nfirst_prompt = "調べて"\n',
                                       encoding="utf-8")
    (folder / "agent.md").write_text("調べます\n", encoding="utf-8")
    imported = registry.add(module, "research", from_dir=folder)
    assert (imported.title, imported.tools, imported.document) == ("調べ役", ("task_status",), "調べます\n")
    assert registry.load("research", module) == imported


def test_presets_are_kept_on_this_pc_and_copied_into_modules(tmp_path):
    """プリセット（このPCの手持ち）を作り、モジュールにそのまま写して登録する。モジュールの登録はプリセットにもできる。"""
    preset = registry.add_preset("careful", from_preset="worker")
    registry.update_preset("careful", title="慎重な作業役", tools=["task_*"], children=[], document="慎重に\n")
    assert preset.source == registry.PRESET and "careful" in [r.name for r in registry.presets()]
    assert "careful" not in [r.name for r in registry.list_registrations(tmp_path)]   # 写すまではモジュールにない
    copied = registry.add(tmp_path, "careful", from_preset="careful")
    assert (copied.title, copied.tools, copied.document, copied.source) == ("慎重な作業役", ("task_*",), "慎重に\n", registry.MODULE)
    registry.update(tmp_path, "careful", model="opus")
    kept = registry.add_preset("careful2", registration=registry.load("careful", tmp_path))
    assert (kept.model, kept.source) == ("opus", registry.PRESET)
    registry.remove_preset("careful")
    assert registry.load("careful", tmp_path).title == "慎重な作業役"                # 写したものは残る
    with pytest.raises(EcoBuildError, match="見本"):
        registry.remove_preset("lead")


@pytest.mark.parametrize("name", ["Bad", "-x", "a/b", ""])
def test_bad_names_are_refused(tmp_path, name):
    with pytest.raises(EcoBuildError):
        registry.add(tmp_path, name)


def test_a_stronger_child_is_refused(tmp_path):
    """子に、自分の tools で許されないツールを許す登録は入れられない（モジュールにない名前も）。"""
    registry.add(tmp_path, "narrow")
    registry.update(tmp_path, "narrow", tools=["task_*"], children=[])
    with pytest.raises(EcoBuildError, match="強い"):
        registry.update(tmp_path, "narrow", children=["worker"])        # worker は * を許す
    registry.add(tmp_path, "tiny")
    registry.update(tmp_path, "tiny", tools=["task_status", "task_s*"], children=[])
    registry.update(tmp_path, "narrow", children=["tiny"])              # task_* は task_status・task_s* を含む
    with pytest.raises(EcoBuildError, match="強く"):
        registry.update(tmp_path, "tiny", tools=["build"])             # 子が親より強くなる変更も断る
    with pytest.raises(EcoBuildError, match="ない登録"):
        registry.update(tmp_path, "narrow", children=["nobody"])
    with pytest.raises(EcoBuildError, match="子として"):
        registry.remove(tmp_path, "tiny")                               # 子にしている登録がある


def test_allows_tool_matches_patterns():
    reg = registry.Registration(name="x", title="x", document="", tools=("task_*", "build"))
    assert registry.allows_tool(reg, "task_status") and registry.allows_tool(reg, "build")
    assert not registry.allows_tool(reg, "children_start")
    assert not registry.allows_tool(registry.Registration(name="y", title="y", document=""), "build")


def test_samples_cannot_be_removed(tmp_path):
    with pytest.raises(EcoBuildError, match="見本"):
        registry.remove(tmp_path, "lead")


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_only_what_the_base_branch_has_is_in_force(tmp_path):
    """エージェントは作業空間（タスクブランチ）のファイルを書き換えられるので、効くのは作成元に取り込まれた登録だけ。"""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".ecobuild").mkdir()
    (tmp_path / ".ecobuild" / "ecobuild.toml").write_text(
        'format = 4\n\n[module]\nname = "calc"\ntype = "python"\n\n[branches]\ndefault_base = "main"\n', encoding="utf-8")
    registry.update(tmp_path, "worker", tools=["task_status"], children=[])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "narrow")
    _git(tmp_path, "switch", "-q", "-c", "task/1-x")
    registry.update(tmp_path, "worker", tools=["*"], children=["worker", "manager"])   # タスクブランチで広げても
    registry.add(tmp_path, "sneaky", from_preset="worker")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "loosen")
    assert registry.effective("worker", tmp_path).tools == ("task_status",)
    assert registry.effective("worker", tmp_path).source == registry.MODULE
    with pytest.raises(EcoBuildError):
        registry.effective("sneaky", tmp_path)                         # 取り込まれていない登録は起動できない
    assert registry.effective("lead", tmp_path).source == registry.SAMPLE
    assert registry.pending(tmp_path) == {"worker", "sneaky"}
    assert registry.load("worker", tmp_path).tools == ("*",)            # 見る・直すのは作業ツリーのもの


def test_human_start_takes_effect_from_the_working_tree(tmp_path):
    """人が起動できるかは作業ツリーの値ですぐ効く（ツールは広げない）。ほかの項目は作成元のまま。"""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".ecobuild").mkdir()
    (tmp_path / ".ecobuild" / "ecobuild.toml").write_text(
        'format = 4\n\n[module]\nname = "calc"\ntype = "python"\n\n[branches]\ndefault_base = "main"\n', encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    _git(tmp_path, "switch", "-q", "-c", "task/1-x")
    sample = registry.effective("worker", tmp_path)
    registry.update(tmp_path, "worker", human_start=True, model="opus")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "start worker by hand")
    worker = registry.effective("worker", tmp_path)
    assert worker.human_start                                          # すぐ選べる
    assert worker.model == sample.model and worker.source == registry.SAMPLE   # ほかの項目は作成元のまま
    assert "worker" in registry.pending(tmp_path)                       # モデルの違いはまだ効いていない
    registry.update(tmp_path, "worker", model=sample.model)
    assert "worker" not in registry.pending(tmp_path)                   # 人が起動できるかだけの違いは、もう効いている
