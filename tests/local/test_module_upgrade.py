"""module upgrade：以前の ECOBuild の仕様のモジュールを、今の仕様に合わせる。"""

import pytest

from fakes import FakeGitHub
from helpers import git
import ecobuild_container as container
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
    assert "FROM ubuntu" in (root / container.DOCKERFILE).read_text(encoding="utf-8")   # 作るときに環境のひな型を置く
    # 以前の版のモジュール：版が1、.ecobuild/.gitignore の行が足りず（自分で足した行はある）、AGENTS.md が古い、コンテナの環境・.ecobuild/README.md がない
    (root / container.DOCKERFILE).unlink()
    (root / ".ecobuild/README.md").unlink()
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
    assert planned.dry_run and planned.paths == (".ecobuild/.gitignore", ".ecobuild/README.md", container.DOCKERFILE,
                                         ".ecobuild/ecobuild.toml", "AGENTS.md")
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
    assert (root / container.DOCKERFILE).is_file() and (root / ".ecobuild/README.md").is_file()
    assert Module.find(root, github=github).config.format == config.FORMAT
    assert old.status().format == config.FORMAT
    again = old.upgrade()
    assert again.paths == () and again.commit is None   # 今の版なら変えるものはない（コミットもしない）


def test_branch_not_checked_out_is_upgraded(tmp_path):
    """管理用のブランチ（作業空間で開かない）は --branch で：手元の作業ツリーに触れず、GitHub のそのブランチを更新する。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    root, github = module.root, module.repository.github
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "format": 1}))
    (root / "AGENTS.md").write_text("古い\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "以前の版")
    git(root, "push", "--quiet", "origin", "main")
    old = Module.find(root, github=github)
    old.repository.create_task("作業").start()   # 手元はタスクブランチ（main はどこでも取り出していない）
    here = git(root, "rev-parse", "HEAD").strip()
    assert {b.name: b.format for b in old.branches()}["main"] == 1

    planned = old.upgrade(dry_run=True, branch="main")
    assert planned.dry_run and planned.branch == "main" and planned.format == 1
    assert {".ecobuild/ecobuild.toml", "AGENTS.md"} <= set(planned.paths)
    done = old.upgrade(branch="main")
    assert done.commit and done.branch == "main" and done.pushed and done.git_config == ()
    assert git(root, "rev-parse", "origin/main").strip() == done.commit
    assert git(root, "rev-parse", "main").strip() == done.commit   # 取り出していない手元の main も進める
    assert git(root, "log", "-1", "--format=%s", "origin/main").strip() == "ECOBuild の更新"
    assert f"format = {config.FORMAT}" in git(root, "show", "origin/main:.ecobuild/ecobuild.toml")
    assert "古い" not in git(root, "show", "origin/main:AGENTS.md")
    # 手元はそのまま：同じタスクブランチ・同じコミット・変更なし・一時的な作業ツリーも残らない
    assert git(root, "rev-parse", "HEAD").strip() == here and git(root, "status", "--porcelain").strip() == ""
    assert len(git(root, "worktree", "list", "--porcelain").split("worktree ")) == 2
    assert not any((root / ".git/ecowork").iterdir())
    assert {b.name: b.format for b in old.branches()}["main"] == config.FORMAT
    again = old.upgrade(branch="main")
    assert again.paths == () and again.commit is None
    with pytest.raises(WorkError) as error:
        old.upgrade(branch=old.repository.git.current_branch().replace("task/1", "task/9"))
    assert error.value.code == ErrorCode.PROTECTED_BRANCH   # タスクブランチは切り替えて module upgrade
    assert code_of(lambda: old.upgrade(branch="nothing")) == ErrorCode.BRANCH_NOT_FOUND


def test_upgrade_sets_line_endings_like_clone(tmp_path):
    """以前に clone した作業空間の git の改行の設定を、clone するときと同じ（core.autocrlf=input）にする。コミットしない。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    root = module.root
    git(root, "config", "--local", "core.autocrlf", "true")
    planned = module.upgrade(dry_run=True)
    assert planned.git_config == ("core.autocrlf=input",)
    assert git(root, "config", "--local", "--get", "core.autocrlf").strip() == "true"   # dry_run は変えない
    head = git(root, "rev-parse", "HEAD").strip()
    done = module.upgrade()
    assert done.git_config == ("core.autocrlf=input",) and done.commit is None
    assert git(root, "config", "--local", "--get", "core.autocrlf").strip() == "input"
    assert git(root, "rev-parse", "HEAD").strip() == head
    assert module.upgrade().git_config == ()


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
