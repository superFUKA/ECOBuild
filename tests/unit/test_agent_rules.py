"""全エージェント共通の文（ecobuild_agent.rules）と、子・起動の文がモジュールの登録を使うこと。"""

import subprocess
from types import SimpleNamespace

from ecobuild_agent import children, registry, rules
from ecobuild_bundle import Module


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _module(tmp_path, base="main"):
    """作成元が base の、コミット済みのモジュール（ecobuild.toml だけ）。"""
    _git(tmp_path, "init", "-q", "-b", base)
    (tmp_path / ".ecobuild").mkdir()
    (tmp_path / ".ecobuild" / "ecobuild.toml").write_text(
        f'format = 4\n\n[module]\nname = "calc"\ntype = "python"\n\n[branches]\ndefault_base = "{base}"\n', encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _commit(root, message="change"):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def test_write_and_read_back(tmp_path):
    assert rules.write(tmp_path, "分けすぎない") == [rules.COMMON_FILE]
    assert rules.read(tmp_path) == "分けすぎない\n"
    assert rules.write(tmp_path, "分けすぎない") == []                    # 中身が同じなら書かない
    assert rules.write(tmp_path, "") == [rules.COMMON_FILE] and rules.read(tmp_path) == ""


def test_only_the_base_branch_common_text_is_in_force(tmp_path):
    root = _module(tmp_path)
    rules.write(root, "基準")
    _commit(root)
    _git(root, "switch", "-q", "-c", "task/1-x")
    rules.write(root, "書き換えた")
    assert rules.in_force(root) == "基準\n"


def test_children_use_the_module_registrations_in_force(tmp_path):
    root = _module(tmp_path)
    registry.update(root, "worker", tools=["task_*"], children=[])
    _commit(root)
    record = SimpleNamespace(registration="worker", workspace=str(root))
    found = children._registration(record)
    assert found.tools == ("task_*",) and not registry.allows_tool(found, "report_to_parent")
    gone = children._registration(SimpleNamespace(registration="nobody", workspace=str(root)))
    assert gone.tools == ()                                               # 知らない登録：ツールなし


def test_the_briefing_has_the_common_text(tmp_path):
    root = _module(tmp_path)
    stub = SimpleNamespace(root=root)
    assert Module._module_rules(stub, SimpleNamespace(registration="manager")) == []
    rules.write(root, "前後がつながった段階は分けない")
    _commit(root)
    assert "前後がつながった段階は分けない" in "\n".join(Module._module_rules(stub, SimpleNamespace(registration="manager")))
