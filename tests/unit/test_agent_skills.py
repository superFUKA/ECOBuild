"""エージェントのスキル（ecobuild_agent.skills）：このPCのスキル・モジュールのスキル・エージェントへの渡し方。"""

import json
import subprocess

import pytest

from ecobuild.errors import EcoBuildError
from ecobuild_agent import registry, skills


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _module(root):
    """作成元が main のモジュール（最初のコミットまで）。"""
    _git(root, "init", "-q", "-b", "main")
    (root / ".ecobuild").mkdir()
    (root / ".ecobuild" / "ecobuild.toml").write_text(
        'format = 5\n\n[module]\nname = "calc"\ntype = "python"\n\n[branches]\ndefault_base = "main"\n', encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")


def _commit(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def test_add_writes_skill_md(tmp_path):
    """説明と本文から SKILL.md（先頭の --- の間に name・description）を作り、読み直せる。"""
    added = skills.add(tmp_path, "release-notes", description='リリースノートを書くときの "手順"',
                       document="# 手順\n\n1. 変更を集める\n")
    text = (tmp_path / skills.MODULE_FOLDER / "release-notes" / skills.SKILL_FILE).read_text(encoding="utf-8")
    assert text.startswith('---\nname: release-notes\ndescription: "リリースノートを書くときの \\"手順\\""\n---\n# 手順')
    assert (added.description, added.document, added.source) == ('リリースノートを書くときの "手順"', "# 手順\n\n1. 変更を集める\n",
                                                                skills.MODULE)
    assert skills.load("release-notes", tmp_path) == added
    with pytest.raises(EcoBuildError, match="もうあります"):
        skills.add(tmp_path, "release-notes", description="x")
    with pytest.raises(EcoBuildError, match="説明"):
        skills.add(tmp_path, "empty")


def test_a_folder_is_imported_with_its_files(tmp_path):
    """フォルダー（~/.claude/skills/<名前> 等）を、ほかのファイル・前置きのほかの行ごと取り込む。set はそれらを残す。"""
    given = tmp_path / "given" / "pdf"
    (given / "scripts").mkdir(parents=True)
    (given / skills.SKILL_FILE).write_text("---\nname: pdf\ndescription: PDF を扱う\nallowed-tools: Bash(python:*)\n---\n本文\n",
                                           encoding="utf-8")
    (given / "scripts" / "fill.py").write_bytes(b"print('x')\n")
    module = tmp_path / "module"
    imported = skills.add(module, "pdf-tools", from_dir=given)
    assert (imported.description, imported.extra, imported.files) == ("PDF を扱う", ("allowed-tools: Bash(python:*)",),
                                                                      ("scripts/fill.py",))
    changed = skills.update(module, "pdf-tools", description="PDF を読む・埋める")
    assert (changed.extra, changed.files, changed.document) == (imported.extra, imported.files, "本文\n")
    assert "name: pdf-tools" in (module / skills.MODULE_FOLDER / "pdf-tools" / skills.SKILL_FILE).read_text(encoding="utf-8")
    with pytest.raises(EcoBuildError, match="SKILL.md がありません"):
        skills.add(module, "nothing", from_dir=tmp_path)
    skills.remove(module, "pdf-tools")
    assert skills.list_skills(module) == []


def test_presets_are_kept_on_this_pc_and_copied_into_modules(tmp_path):
    """このPCのスキルを作ってモジュールへ写す。モジュールのスキルはこのPCのスキルにもできる。"""
    skills.add_preset("review", description="見直しの観点", document="観点\n")
    assert [s.name for s in skills.presets()] == ["review"]
    assert skills.list_skills(tmp_path) == []                      # 写すまではモジュールにない
    copied = skills.add(tmp_path, "review", from_preset="review")
    assert (copied.description, copied.document, copied.source) == ("見直しの観点", "観点\n", skills.MODULE)
    skills.update(tmp_path, "review", document="直した観点\n")
    kept = skills.add_preset("review2", from_module=(tmp_path, "review"))
    assert (kept.document, kept.source) == ("直した観点\n", registry.PRESET)
    skills.remove_preset("review")
    assert skills.load("review", tmp_path).document == "直した観点\n"   # 写したものは残る


@pytest.mark.parametrize("name", ["Bad", "-x", "a_b", "a/b", ""])
def test_bad_names_are_refused(tmp_path, name):
    with pytest.raises(EcoBuildError, match="使えません"):
        skills.add(tmp_path, name, description="x")


def test_only_what_the_base_branch_has_is_provided(tmp_path):
    """エージェントに渡すのは、作成元に取り込まれたスキルのうち登録の skills に合うものだけ。"""
    _module(tmp_path)
    skills.add(tmp_path, "build-help", description="ビルドの手順")
    skills.add(tmp_path, "deploy", description="配る手順")
    _commit(tmp_path, "skills")
    _git(tmp_path, "switch", "-q", "-c", "task/1-x")
    skills.add(tmp_path, "sneaky", description="作業空間で書いたもの")
    skills.update(tmp_path, "deploy", document="変えた\n")
    _commit(tmp_path, "task")
    assert [s.name for s in skills.list_skills(tmp_path, in_force=True)] == ["build-help", "deploy"]
    assert skills.pending(tmp_path) == {"sneaky", "deploy"}

    into = tmp_path / ".ecobuild" / "ai" / "a1" / "skills"
    assert skills.provide(tmp_path, ("*",), into) == ["build-help", "deploy"]
    assert (into / "deploy" / skills.SKILL_FILE).read_text(encoding="utf-8").endswith("<手順・決まり・例を書きます>\n")
    assert skills.provide(tmp_path, ("build-*",), into) == ["build-help"]
    assert not (into / "deploy").exists()                          # 前に写したものは消す
    assert skills.provide(tmp_path, (), into) == []


def test_registrations_use_every_skill_unless_narrowed(tmp_path):
    """登録の skills は既定ですべて（前からの agent.toml にもない）。狭めた値は保存して読み直せる。"""
    assert registry.load("worker", tmp_path).skills == ("*",)
    narrowed = registry.update(tmp_path, "worker", skills=["build-*"])
    assert registry.load("worker", tmp_path).skills == narrowed.skills == ("build-*",)
    written = tmp_path / "registration.json"                       # コンテナの中の MCP サーバーへ渡す写し
    written.write_text(json.dumps(registry.to_data(narrowed), ensure_ascii=False), encoding="utf-8")
    assert registry.from_file(written).skills == ("build-*",)
    assert skills.allowed(narrowed.skills, "build-help") and not skills.allowed(narrowed.skills, "deploy")
