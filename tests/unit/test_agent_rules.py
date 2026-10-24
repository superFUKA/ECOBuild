"""モジュールのエージェント向けの決まり（ecobuild_agent.rules）：共通の文・登録ごとの文・使わせないツール。"""

import json
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ecobuild.errors import EcoBuildError
from ecobuild_agent import children, registry, rules
from ecobuild_bundle import Module


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _module(tmp_path, base="main"):
    """作成元が base の、コミット済みのモジュール（ecobuild.toml だけ）。"""
    _git(tmp_path, "init", "-q", "-b", base)
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".ecobuild").mkdir()
    (tmp_path / ".ecobuild" / "ecobuild.toml").write_text(
        f'format = 4\n\n[module]\nname = "calc"\ntype = "python"\n\n[branches]\ndefault_base = "{base}"\n', encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_write_and_read_back(tmp_path):
    changed = rules.write(tmp_path, common="分けすぎない", role="worker", text="自分で進める", deny=("children_*", "task_submit"))
    assert changed == [rules.COMMON_FILE, rules.role_path("worker"), rules.TOOLS_FILE]
    found = rules.read(tmp_path)
    assert found.common == "分けすぎない\n" and found.text_for("worker") == "自分で進める\n"
    assert found.deny_for("worker") == ("children_*", "task_submit") and found.deny_for("lead") == ()
    assert rules.write(tmp_path, common="分けすぎない") == []                    # 中身が同じなら書かない
    rules.write(tmp_path, role="manager", deny=("task_finish",))                  # ほかの登録の分は残す
    assert rules.read(tmp_path).deny == {"worker": ("children_*", "task_submit"), "manager": ("task_finish",)}
    assert rules.write(tmp_path, role="worker", text="", deny=()) == [rules.role_path("worker"), rules.TOOLS_FILE]
    found = rules.read(tmp_path)                                                  # 空は消す・絞らない
    assert found.roles == {} and found.deny == {"manager": ("task_finish",)}
    assert not (tmp_path / rules.role_path("worker")).exists()


def test_write_refuses_bad_input(tmp_path):
    with pytest.raises(EcoBuildError):
        rules.write(tmp_path, text="文")                       # どの登録か
    with pytest.raises(EcoBuildError):
        rules.write(tmp_path, role="Worker!", text="文")       # 登録の名前ではない
    with pytest.raises(EcoBuildError):
        rules.write(tmp_path, role="worker", deny=("task submit",))


def test_only_what_the_base_branch_has_is_in_force(tmp_path):
    """エージェントは作業空間（タスクブランチ）のファイルを書き換えられるので、効くのは作成元に取り込まれたものだけ。"""
    root = _module(tmp_path)
    assert rules.in_force(root) == rules.Rules()
    rules.write(root, common="基準", role="worker", text="役の文", deny=("task_submit",))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "rules")
    _git(root, "switch", "-q", "-c", "task/1-x")
    rules.write(root, role="worker", deny=())                      # タスクブランチで外しても
    _git(root, "commit", "-q", "-am", "loosen")
    found = rules.in_force(root)
    assert found.common == "基準\n" and found.text_for("worker") == "役の文\n" and found.deny_for("worker") == ("task_submit",)
    worker = rules.effective(registry.load("worker"), root)
    assert worker.deny == ("task_submit",) and not registry.allows_tool(worker, "task_submit")
    assert registry.allows_tool(worker, "task_status")
    assert rules.view(root).pending                               # 作業ツリーのものは、まだ効いていない


def test_deny_only_narrows_and_counts_for_children():
    parent = registry.Registration(name="manager", title="管理", document="", tools=("*",), deny=("task_submit",))
    child = registry.Registration(name="worker", title="作業", document="", tools=("*",))
    assert registry.stronger(child, parent)                              # 親に使わせないものを子が使える
    assert not registry.stronger(replace(child, deny=("task_submit",)), parent)
    assert not registry.stronger(replace(child, deny=("task_*",)), parent)   # 広く使わせない子はよい
    assert not registry.stronger(registry.Registration(name="x", title="x", document=""), parent)   # ツールのない子


def test_the_registration_copy_keeps_deny(tmp_path):
    found = registry.Registration(name="worker", title="作業", document="", tools=("*",), deny=("children_*",))
    path = tmp_path / "registration.json"
    path.write_text(json.dumps(registry.to_data(found)), encoding="utf-8")
    assert registry.from_file(path).deny == ("children_*",)


def test_children_use_the_module_rules(tmp_path):
    root = _module(tmp_path)
    rules.write(root, role="worker", deny=("report_to_parent",))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "rules")
    record = SimpleNamespace(registration="worker", workspace=str(root))
    assert not registry.allows_tool(children._registration(record), "report_to_parent")
    assert registry.allows_tool(children._registration(SimpleNamespace(registration="worker", workspace="")),
                                "report_to_parent")


def test_the_briefing_has_the_module_rules(tmp_path):
    root = _module(tmp_path)
    stub = SimpleNamespace(root=root)
    record = SimpleNamespace(registration="manager")
    assert Module._module_rules(stub, record) == []
    rules.write(root, common="前後がつながった段階は分けない", role="manager", text="独立した仕事だけを子に")
    rules.write(root, role="worker", text="作業役への文")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "rules")
    text = "\n".join(Module._module_rules(stub, record))
    assert "前後がつながった段階は分けない" in text and "独立した仕事だけを子に" in text
    assert "作業役への文" not in text                              # ほかの登録への文は渡さない
