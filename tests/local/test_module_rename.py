"""module rename：GitHub のリポジトリ名・origin・中の名前（作成元のブランチへ1コミット）・元の clone のフォルダーを変える。"""

import pytest

from fakes import FakeGitHub
from helpers import git
from ecobuild import config, usage, workspaces
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import Module

pytestmark = [pytest.mark.local, pytest.mark.needs_git_2_48]


def code_of(action):
    with pytest.raises(EcoBuildError) as error:
        action()
    return error.value.code


def made(tmp_path, name="Plain", type="generic", **options):
    github = FakeGitHub(tmp_path / "gh")
    module = Module.create(name, directory=tmp_path / "mods", type=type, github=github, **options)
    workspaces.record(module.root)
    return module, github


def test_rename_moves_everything(tmp_path):
    module, github = made(tmp_path)
    root = module.root
    task = module.repository.create_task("作業")
    workspace = module.start_task(task.number)
    (workspace.root / "note.txt").write_text("作業中\n", encoding="utf-8")   # 新しいファイル（未追跡）は一緒に動く
    head = git(root, "rev-parse", "origin/main").strip()

    planned = workspace.rename("Tool", dry_run=True)   # 作業空間から呼んでも、元の clone のモジュール
    assert planned.dry_run and (planned.name, planned.new_name) == ("Plain", "Tool")
    assert (planned.repository, planned.new_repository) == ("tester/Plain", "tester/Tool") and planned.github
    assert planned.origins == (root,) and planned.branch == "main"
    assert {config.FILE_NAME, ".ecobuild/README.md", "AGENTS.md"} <= set(planned.paths)
    assert planned.root == root and planned.new_root == root.with_name("Tool")
    assert planned.workspaces == (workspace.root,)
    assert github.renamed_repositories == [] and git(root, "rev-parse", "origin/main").strip() == head   # 何も変えない
    assert root.is_dir() and not root.with_name("Tool").exists()

    steps = []
    done = module.rename("Tool", progress=steps.append)
    new_root = root.with_name("Tool")
    assert not done.dry_run and done.moved and done.commit and done.pushed
    assert github.renamed_repositories == [("tester/Plain", "Tool")]
    assert not root.exists() and (new_root / config.FILE_NAME).is_file()
    assert git(new_root, "config", "--get", "remote.origin.url").strip() == str(github.bare)
    assert github.bare.name == "Tool.git"
    # 作成元へ「モジュールの改名」の1コミット。手元の main も進む
    assert git(new_root, "log", "-1", "--format=%s", "origin/main").strip() == "モジュールの改名（Plain → Tool）"
    assert git(new_root, "rev-parse", "origin/main").strip() == done.commit == git(new_root, "rev-parse", "HEAD").strip()
    assert git(new_root, "rev-parse", f"{done.commit}^").strip() == head
    assert config.load(new_root / config.FILE_NAME).name == "Tool"
    assert "Tool" in (new_root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Plain" not in (new_root / ".ecobuild/README.md").read_text(encoding="utf-8")
    assert git(new_root, "status", "--porcelain").strip() == ""
    # 作業空間も一緒に動いて使える（タスクブランチは sync で新しい名前を取り込む）
    moved = new_root / ".ecobuild" / "w" / str(task.number)
    assert done.workspaces == (moved,)
    assert (moved / "note.txt").is_file()
    assert git(moved, "rev-parse", "--abbrev-ref", "HEAD").strip().startswith(f"task/{task.number}")
    assert Module.find(moved, github=github).workspace_root.resolve() == new_root.resolve()
    # このPCの一覧は新しい場所に。途中の印は残らない
    assert [item.path for item in workspaces.recorded()] == [new_root.resolve()]
    assert workspaces.recorded()[0].url == str(github.bare)
    assert "ecobuild.renaming" not in git(new_root, "config", "--local", "--list")
    assert steps and not any((new_root / ".git/ecowork").iterdir())   # 一時的な作業ツリーも残らない

    again = Module.find(new_root, github=github).rename("Tool")   # もう一度：変えるものはない
    assert not again.github and again.paths == () and again.commit is None and not again.moved


def test_rename_refuses_beforehand(tmp_path):
    module, github = made(tmp_path)
    root = module.root
    assert code_of(lambda: module.rename("1st")) == ErrorCode.INVALID_ARGUMENT
    (root / "README.md").write_text("書きかけ\n", encoding="utf-8")
    assert code_of(lambda: module.rename("Tool")) == ErrorCode.DIRTY_WORKING_TREE
    git(root, "checkout", "--quiet", "--", "README.md")
    with usage.running(root, "build"):
        assert code_of(lambda: module.rename("Tool")) == ErrorCode.WORKSPACE_IN_USE
    root.with_name("Tool").mkdir()
    assert code_of(lambda: module.rename("Tool")) == ErrorCode.ALREADY_EXISTS
    root.with_name("Tool").rmdir()
    github.others["Taken"] = tmp_path / "Taken.git"
    assert code_of(lambda: module.rename("Taken")) == ErrorCode.ALREADY_EXISTS
    try:
        workspaces.caller_directory = root   # 呼んだシェルが移すフォルダーの中
        assert code_of(lambda: module.rename("Tool")) == ErrorCode.IN_USE
    finally:
        workspaces.caller_directory = None
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "format": 1}))
    git(root, "commit", "--quiet", "-am", "古い版")
    assert code_of(lambda: Module.find(root, github=github).rename("Tool")) == ErrorCode.INVALID_CONFIG
    assert github.renamed_repositories == [] and root.is_dir()


def test_a_refused_push_changes_nothing(tmp_path):
    """作成元への push を断られたら（ブランチの保護等）、GitHub の名前を変える前なので何も変わっていない。"""
    module, github = made(tmp_path)
    root = module.root
    hook = github.bare / "hooks" / "pre-receive"
    hook.write_bytes(b"#!/bin/sh" + b"\n" + b"exit 1" + b"\n")
    assert code_of(lambda: module.rename("Tool")) == ErrorCode.PROTECTED_BRANCH
    assert github.renamed_repositories == [] and root.is_dir()
    assert "ecobuild.renaming" not in git(root, "config", "--local", "--list")
    hook.unlink()
    assert module.rename("Tool").moved


def test_rename_continues_after_stopping_midway(tmp_path, monkeypatch):
    """GitHub の名前を変えるところで止まっても（push は済み）、もう一度呼ぶと続きから行う。フォルダーを移せずに止まっても同じ。"""
    module, github = made(tmp_path)
    root = module.root
    real = github.rename_repository

    def broken(name, new_name):
        raise EcoBuildError(ErrorCode.GIT_ERROR, "つながりません")
    monkeypatch.setattr(github, "rename_repository", broken)
    assert code_of(lambda: module.rename("Tool")) == ErrorCode.GIT_ERROR
    assert git(root, "show", "origin/main:.ecobuild/ecobuild.toml").count('name = "Tool"') == 1   # push は済み
    pushed = git(root, "rev-parse", "origin/main")
    monkeypatch.setattr(github, "rename_repository", real)

    import ecobuild.module as core
    monkeypatch.setattr(core, "_move_folder", lambda *a, **k: (_ for _ in ()).throw(
        EcoBuildError(ErrorCode.IN_USE, "使われています")))
    assert code_of(lambda: Module.find(root, github=github).rename("Tool")) == ErrorCode.IN_USE
    assert github.renamed_repositories == [("tester/Plain", "Tool")] and root.is_dir()
    assert config.load(root / config.FILE_NAME).name == "Tool"   # 手元の main は進んだ（フォルダーはまだ）
    monkeypatch.undo()

    done = Module.find(root, github=github).rename("Tool")   # 前の名前は途中の印から分かる
    assert done.moved and done.commit is None and not done.github
    assert git(root.with_name("Tool"), "rev-parse", "origin/main") == pushed and not root.exists()


def test_only_case_changes(tmp_path):
    module, github = made(tmp_path)
    done = module.rename("PLAIN")
    assert done.moved and github.bare.name == "PLAIN.git"
    assert [p.name for p in (tmp_path / "mods").iterdir()] == ["PLAIN"]


def test_worktree_outside_the_workspaces_is_refused(tmp_path):
    module, _ = made(tmp_path)
    git(module.root, "worktree", "add", "--quiet", "-b", "mine", str(tmp_path / "mine"))
    assert code_of(lambda: module.rename("Tool")) == ErrorCode.INVALID_ARGUMENT
    assert module.root.is_dir()


def test_folder_with_another_name_stays(tmp_path):
    """元の clone のフォルダーの名前がモジュール名と違えば、フォルダーはそのまま（名前だけ変える）。"""
    module, github = made(tmp_path)
    place = module.root.with_name("MyCopy")
    module.root.rename(place)
    workspaces.relocate(module.root, place)
    other = Module.find(place, github=github)
    done = other.rename("Tool")
    assert done.new_root is None and not done.moved and done.commit
    assert config.load(place / config.FILE_NAME).name == "Tool"
    assert [item.path for item in workspaces.recorded()] == [place.resolve()]


def test_python_package_is_renamed(tmp_path):
    module, github = made(tmp_path, "Calc", type="python")
    root = module.root
    (root / "src" / "calc" / "core.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "tests" / "test_core.py").write_text(
        "from calc.core import add\nimport calc\n\n\ndef test_add(monkeypatch):\n    assert add(1, 2) == 3 and calc.__doc__\n"
        "    monkeypatch.setattr(\"calc.core.add\", add)\n", encoding="utf-8")
    (root / "src" / "calc" / "files.py").write_text(   # 関係のない文字列・名前・コメントは変えない
        "def save(calc):\n    # calc の結果を書く\n    open(\"calc.csv\", \"w\").write(\"calc: done\")\n    return calc\n",
        encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "足し算")
    git(root, "push", "--quiet", "origin", "main")

    planned = module.rename("Adder", dry_run=True)
    assert {"pyproject.toml", "src/calc", "src/adder", "tests/test_calc.py", "tests/test_adder.py",
            "tests/test_core.py"} <= set(planned.paths)
    done = module.rename("Adder")
    new_root = root.with_name("Adder")
    pyproject = (new_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "Adder"' in pyproject and 'Adder = "adder.__main__:main"' in pyproject and '"calc' not in pyproject
    assert (new_root / "src" / "adder" / "__main__.py").is_file() and not (new_root / "src" / "calc").exists()
    assert "import adder" in (new_root / "tests" / "test_adder.py").read_text(encoding="utf-8")
    core_test = (new_root / "tests" / "test_core.py").read_text(encoding="utf-8")
    assert "from adder.core import add" in core_test and "adder.__doc__" in core_test and "calc" not in core_test
    assert '"adder.core.add"' in core_test
    files = (new_root / "src" / "adder" / "files.py").read_text(encoding="utf-8")
    assert files.count("calc") == 5 and "adder" not in files
    assert git(new_root, "show", "--name-status", "--format=", done.commit).count("R") >= 2   # 移したものは移動として
