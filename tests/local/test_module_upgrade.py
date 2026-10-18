"""module upgrade：以前の ECOBuild の仕様のモジュールを、今の仕様に合わせる。"""

import pytest

from fakes import FakeGitHub
from helpers import git
from ecobuild import config
from ecobuild.errors import ErrorCode
from ecowork import WorkError
from ecobuild_bundle import Module

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_old_module_is_upgraded(tmp_path):
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    root, github = module.root, module.repository.github
    # 以前の版のモジュール：版が1、.ecobuild/.gitignore の行が足りず（自分で足した行はある）、AGENTS.md が古い
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "format": 1}))
    (root / ".ecobuild/.gitignore").write_text("logs/\nmine/\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("古い\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "以前の版")
    git(root, "push", "--quiet", "origin", "main")   # タスクブランチは GitHub の main から作る
    old = Module.find(root, github=github)
    assert old.config.format == 1
    status = old.status()
    assert (status.format, status.latest_format) == (1, config.FORMAT)
    assert old.info().format == 1

    planned = old.upgrade(dry_run=True)
    assert planned.dry_run and planned.paths == (".ecobuild/.gitignore", ".ecobuild/ecobuild.toml", "AGENTS.md")
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == "古い\n"   # 何も変えない
    (root / "README.md").write_text("書きかけ\n", encoding="utf-8")
    assert code_of(old.upgrade) == ErrorCode.DIRTY_WORKING_TREE   # 人の変更と混ざらないように
    git(root, "checkout", "--quiet", "--", "README.md")

    # タスクブランチでなくてもよい：「ECOBuild の更新」としてコミットし、GitHub へ push する
    done = old.upgrade()
    assert done.commit and done.branch == "main" and done.pushed
    assert git(root, "log", "-1", "--format=%s").strip() == "ECOBuild の更新"
    assert git(root, "rev-parse", "origin/main").strip() == done.commit
    assert git(root, "status", "--porcelain").strip() == ""
    assert (done.format, done.latest_format) == (1, config.FORMAT)
    assert set(planned.paths) <= set(done.paths)
    assert (root / ".ecobuild/.gitignore").read_text(encoding="utf-8") == "logs/\nmine/\necobuild.local.toml\n"
    assert "古い" not in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert Module.find(root, github=github).config.format == config.FORMAT
    assert old.status().format == config.FORMAT
    again = old.upgrade()
    assert again.paths == () and again.commit is None   # 今の版なら変えるものはない（コミットもしない）


def test_hand_edited_workflow_is_kept(tmp_path):
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    module.repository.create_task("CI").start()
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": {"build": "make"}}}))
    path = module.root / ".github/workflows/ecobuild.yml"
    module.write_ci()
    path.write_text(path.read_text(encoding="utf-8") + "# 手で足した\n", encoding="utf-8")
    module.commit("CI")
    result = module.upgrade()
    assert not result.pushed   # タスクブランチでは push しない（いつもの Push・提出で）
    assert result.skipped == (".github/workflows/ecobuild.yml",)
    assert "# 手で足した" in path.read_text(encoding="utf-8")


def test_newer_module_asks_for_a_newer_ecobuild(tmp_path):
    path = tmp_path / config.FILE_NAME
    path.parent.mkdir()
    path.write_text(f"format = {config.FORMAT + 1}\n[module]\nname = 'x'\ntype = 'generic'\n", encoding="utf-8")
    assert code_of(lambda: config.load(path)) == ErrorCode.INVALID_CONFIG
    path.write_text("format = 0\n[module]\nname = 'x'\ntype = 'generic'\n", encoding="utf-8")
    assert code_of(lambda: config.load(path)) == ErrorCode.INVALID_CONFIG
