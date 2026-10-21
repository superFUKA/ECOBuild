"""module adopt：既にある GitHub のリポジトリ（clone）を、ECOBuild のモジュールにする。"""

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


@pytest.fixture
def plain(remote_and_clone, tmp_path):
    """ECOBuild を使っていないリポジトリ（README と自分の .gitignore がある）の clone と、偽の GitHub。"""
    remote, work = remote_and_clone
    (work / ".gitignore").write_text("/notes/\n", encoding="utf-8")
    git(work, "add", ".gitignore")
    git(work, "commit", "--quiet", "-m", "除外")
    git(work, "push", "--quiet", "origin", "main")
    github = FakeGitHub(tmp_path / "gh")
    github.use_bare(remote)
    return work, github


def test_a_plain_repository_becomes_a_module(plain):
    work, github = plain
    (work / "notes").mkdir()
    (work / "notes" / "memo.txt").write_text("メモ\n", encoding="utf-8")   # 除外したファイルは触らない
    (work / "draft.txt").write_text("書きかけ\n", encoding="utf-8")        # 管理していない新しいファイルも混ぜない

    _, planned = Module.adopt(work / "notes", type="generic", dry_run=True, github=github)   # 中のフォルダーからでもよい
    assert planned.dry_run and planned.root == work and planned.branch == "main" and planned.name == "remote"
    assert planned.paths == (".ecobuild/.gitattributes", ".ecobuild/.gitignore", ".ecobuild/README.md", container.DOCKERFILE,
                             config.FILE_NAME)
    assert not (work / ".ecobuild").exists()   # 何も変えない

    module, done = Module.adopt(work, type="generic", github=github)
    assert done.commit and done.pushed and done.branch == "main" and set(planned.paths) <= set(done.paths)
    assert git(work, "log", "-1", "--format=%s").strip() == "ECOBuild のモジュールにする"
    assert git(work, "rev-parse", "origin/main").strip() == done.commit
    assert git(work, "status", "--porcelain").strip() == "?? draft.txt"
    assert (work / "README.md").read_text(encoding="utf-8") == "seed\n"   # 元のファイルは変えない
    assert (work / ".gitignore").read_text(encoding="utf-8") == "/notes/\n"   # 型（generic）が除外するものはない
    found = Module.find(work, github=github)
    assert (found.name, found.config.type, found.config.default_base) == ("remote", "generic", "main")
    assert found.upgrade(dry_run=True).paths == ()   # 今の仕様のとおりに置いてある
    assert code_of(lambda: Module.adopt(work, github=github)) == ErrorCode.ALREADY_EXISTS


def test_the_type_adds_its_ignored_files(plain):
    work, github = plain
    (work / "pyproject.toml").write_text('[project]\nname = "remote"\nversion = "0.1.0"\n', encoding="utf-8")
    git(work, "add", "pyproject.toml")
    git(work, "commit", "--quiet", "-m", "Python")
    git(work, "push", "--quiet", "origin", "main")
    module, done = Module.adopt(work, type="python", github=github)
    assert ".gitignore" in done.paths and module.config.type == "python"
    text = (work / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("/notes/\n") and ".venv/" in text   # 自分の行は残して、型の行を足す
    assert (work / "pyproject.toml").read_text(encoding="utf-8").startswith("[project]")


def test_the_current_branch_becomes_the_base(plain):
    work, github = plain
    git(work, "switch", "--quiet", "-c", "develop")
    git(work, "push", "--quiet", "origin", "develop")
    module, done = Module.adopt(work, type="generic", github=github)
    assert done.branch == "develop" and module.config.default_base == "develop"
    assert git(work, "rev-parse", "origin/develop").strip() == done.commit
    assert git(work, "ls-tree", "--name-only", "origin/main", ".ecobuild/") == ""   # main には置かない


def test_new_workspaces_take_out_the_base(plain, tmp_path):
    """GitHub の既定のブランチ（main）にモジュールがなくても、新しい作業空間は作成元（develop）を取り出す。"""
    work, github = plain
    git(work, "switch", "--quiet", "-c", "develop")
    git(work, "push", "--quiet", "origin", "develop")
    module, _ = Module.adopt(work, type="generic", github=github)
    other, _ = module.create_workspace(tmp_path / "ws")
    assert other.repository.git.current_branch() == "develop" and other.config.default_base == "develop"
    task = module.repository.create_task("並行作業")
    started = module.start_task_in(task.number, tmp_path / "ws-1")
    assert started.repository.current_task_branch().base == "develop"
    # モジュールでないブランチ（main）は一覧に印が付き、タスクブランチの作成元にはできない（移るとモジュールでなくなる）
    branches = {b.name: b for b in module.repository.branches()}
    assert branches["main"].unusable and branches["develop"].unusable is None
    other_task = module.repository.create_task("main から")
    assert code_of(lambda: module.repository.task(other_task.number).start(base="main", name="x")) == "invalid_base"
    assert git(work, "branch", "--show-current").strip() == "develop" and module.repository.current_task_branch() is None


def test_refused_when_it_would_mix_with_other_work(plain):
    work, github = plain
    (work / "README.md").write_text("書きかけ\n", encoding="utf-8")
    assert code_of(lambda: Module.adopt(work, type="generic", github=github)) == ErrorCode.DIRTY_WORKING_TREE
    git(work, "checkout", "--quiet", "--", "README.md")
    git(work, "switch", "--quiet", "-c", "local-only")
    assert code_of(lambda: Module.adopt(work, type="generic", github=github)) == ErrorCode.BRANCH_NOT_FOUND
    assert not (work / ".ecobuild").exists()


def test_only_the_owner_can_adopt(plain):
    work, github = plain
    github.role = "write"   # ほかの人のリポジトリ（共同作業者）
    assert code_of(lambda: Module.adopt(work, type="generic", github=github)) == ErrorCode.PERMISSION_DENIED
    assert code_of(lambda: Module.adopt(work, type="generic", dry_run=True, github=github)) == ErrorCode.PERMISSION_DENIED
    assert not (work / ".ecobuild").exists()


def test_outside_a_git_repository(tmp_path):
    assert code_of(lambda: Module.adopt(tmp_path, github=FakeGitHub(tmp_path / "gh"))) == ErrorCode.REPOSITORY_NOT_FOUND


def test_the_type_can_refuse_and_nothing_is_left(plain):
    work, github = plain
    assert code_of(lambda: Module.adopt(work, type="python", github=github)) == ErrorCode.INVALID_CONFIG   # pyproject.toml がない
    assert git(work, "status", "--porcelain").strip() == ""
    assert not (work / ".ecobuild").exists()
    assert (work / ".gitignore").read_text(encoding="utf-8") == "/notes/\n"
