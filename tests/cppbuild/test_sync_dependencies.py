import os
from pathlib import Path

import pytest
from cppbuild import ProjectType

from helpers import git, write, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecobuild_cpp import _cppbuild
from ecobuild_bundle import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def url(path: Path) -> str:
    return "file:///" + path.as_posix()


def new_stl_commit(stl_root: Path, text: str) -> str:
    write(stl_root / "STL" / "include" / "STL" / "STL.h", text)
    git(stl_root, "commit", "--quiet", "-am", "STLを更新")
    git(stl_root, "push", "--quiet", "origin", "main")
    return git(stl_root, "rev-parse", "HEAD")


def test_sync_aligns_dependencies(short_tmp):
    stl_github = FakeGitHub(short_tmp / "gh1")
    stl = Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=FakeGitHub(short_tmp / "gh2"))
    solution = _cppbuild.open_solution(ecs.root)
    solution.get_project("ECS").settings.link_git(url(stl_github.bare), solution_path=_cppbuild.CONFIG_DIRECTORY, link_type=ProjectType.STATIC_LIBRARY)
    clone = ecs.root / "deps" / "STL"
    first = git(clone, "rev-parse", "HEAD")

    # STLが進み、ECSの記録を新しい版へ更新した（手元のcloneは古いまま）
    second = new_stl_commit(stl.root, "#pragma once\n// v2\n")
    solution.set_git_source(url(stl_github.bare))
    assert git(clone, "rev-parse", "HEAD") == first
    result = ecs.sync()
    assert [(d.name, d.action) for d in result.dependencies] == [("STL", "aligned")]
    assert git(clone, "rev-parse", "HEAD") == second and result.regenerated

    # 手元で編集中の依存先は触らない
    new_stl_commit(stl.root, "#pragma once\n// v3\n")
    solution.set_git_source(url(stl_github.bare))
    write(clone / "STL" / "src" / "STL.cpp", "// 編集中\n")
    result = ecs.sync()
    assert [(d.name, d.action) for d in result.dependencies] == [("STL", "skipped")]
    assert git(clone, "rev-parse", "HEAD") == second

    # 消した依存先は取り直す
    git(clone, "checkout", "--quiet", "--", ".")
    remove_tree(clone)
    result = ecs.sync()
    assert [(d.name, d.action) for d in result.dependencies] == [("STL", "cloned")]


def test_sync_regenerates_conflicted_generated_files(short_tmp):
    """生成ファイルだけが衝突したら、管理ファイルから作り直して取り込みを完了する。"""
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, kind="library", github=github)
    top = ".ecobuild/.cppbuild/CppBuildTopLevel.cmake"
    expected = (module.root / top).read_text(encoding="utf-8")
    task_branch = module.repository.create_task("t").start()
    write(module.root / top, expected + "# 手元\n")
    task_branch.commit("手元で生成ファイルを変えた", all=True)
    other = short_tmp / "other"
    git(short_tmp, "clone", "--quiet", str(github.bare), str(other))
    write(other / top, expected + "# GitHub\n")
    git(other, "commit", "--quiet", "-am", "GitHubで生成ファイルを変えた")
    git(other, "push", "--quiet", "origin", "main")
    result = module.sync()
    assert result.merged == ("merge",) and result.regenerated
    assert (module.root / top).read_text(encoding="utf-8") == expected
    assert not module.status().merging


def test_branch_merge_regenerates_conflicted_generated_files(short_tmp):
    """ブランチ同士の取り込み（branch merge --into）でも、生成ファイルだけの衝突は作り直して取り込む（一時的な作業ツリーで。
    手元には触れない）。"""
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, kind="library", github=github)
    top = ".ecobuild/.cppbuild/CppBuildTopLevel.cmake"
    expected = (module.root / top).read_text(encoding="utf-8")
    other = short_tmp / "other"
    git(short_tmp, "clone", "--quiet", str(github.bare), str(other))
    git(other, "switch", "--quiet", "-c", "dev")
    write(other / top, expected + "# dev\n")
    git(other, "commit", "--quiet", "-am", "dev で生成ファイルを変えた")
    git(other, "push", "--quiet", "origin", "dev")
    git(other, "switch", "--quiet", "main")
    write(other / top, expected + "# main\n")
    git(other, "commit", "--quiet", "-am", "main で生成ファイルを変えた")
    git(other, "push", "--quiet", "origin", "main")
    here = git(module.root, "rev-parse", "HEAD")

    plan = module.repository.plan_branch_merge("dev", "main")
    assert (plan.method, plan.conflicts, plan.resolved) == ("merge", (), (top,))
    merged = module.repository.merge_branch_into("dev", "main")
    assert merged.method == "merge" and merged.resolved == (top,)
    assert git(module.root, "rev-parse", "origin/main") == merged.commit
    assert len(git(module.root, "rev-list", "--parents", "-1", merged.commit).split()) == 3   # マージコミット
    assert git(module.root, "show", f"{merged.commit}:{top}") == expected.strip()   # 管理ファイルから作り直した
    assert git(module.root, "rev-parse", "HEAD") == here and not module.status().merging
    assert len(git(module.root, "worktree", "list", "--porcelain").split("worktree ")) == 2


def test_gitignore_conflicts_are_merged_by_lines(short_tmp):
    """.gitignore 等（行の集まり）の衝突は両方の行を合わせて直す：sync でも、ブランチ同士の取り込みでも止まらない。"""
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, kind="library", github=github)
    base = (module.root / ".gitignore").read_text(encoding="utf-8")
    other = short_tmp / "other"
    git(short_tmp, "clone", "--quiet", str(github.bare), str(other))
    git(other, "switch", "--quiet", "-c", "dev")
    write(other / ".gitignore", base + "/same/\n")
    git(other, "commit", "--quiet", "-am", "dev で除外を足した")
    git(other, "push", "--quiet", "origin", "dev")
    git(other, "switch", "--quiet", "main")
    write(other / ".gitignore", base + "/same/\n\n# main\n*.exe\n")
    git(other, "commit", "--quiet", "-am", "main で除外を足した")
    git(other, "push", "--quiet", "origin", "main")

    plan = module.repository.plan_branch_merge("dev", "main")
    assert (plan.method, plan.conflicts, plan.resolved) == ("merge", (), (".gitignore",))
    merged = module.repository.merge_branch_into("dev", "main")
    assert git(module.root, "show", f"{merged.commit}:.gitignore") == (base + "/same/\n\n# main\n*.exe").strip()

    task_branch = module.repository.create_task("t").start()
    started = (module.root / ".gitignore").read_text(encoding="utf-8")
    write(module.root / ".gitignore", started + "/mine/\n")
    task_branch.commit("手元で除外を足した", all=True)
    git(other, "pull", "--quiet", "--ff-only", "origin", "main")
    write(other / ".gitignore", started + "/theirs/\n")
    git(other, "commit", "--quiet", "-am", "main でさらに除外を足した")
    git(other, "push", "--quiet", "origin", "main")
    module.sync()
    text = (module.root / ".gitignore").read_text(encoding="utf-8")
    assert "/mine/" in text and "/theirs/" in text and "*.exe" in text and "<<<<<<<" not in text and not module.status().merging


def test_a_task_whose_gitignore_lines_are_in_the_base_loses_nothing(short_tmp):
    """.gitignore が衝突しても、両方の行を合わせると作成元と同じなら、タスクブランチの変更は作成元に入っている。"""
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, kind="library", github=github)
    base = (module.root / ".gitignore").read_text(encoding="utf-8")
    task_branch = module.repository.create_task("t").start()
    write(module.root / ".gitignore", base + "/same/\n")
    task_branch.commit("除外を足した", all=True)
    task_branch.push()
    other = short_tmp / "other"
    git(short_tmp, "clone", "--quiet", str(github.bare), str(other))
    write(other / ".gitignore", base + "/same/\n\n# main\n*.exe\n")
    git(other, "commit", "--quiet", "-am", "別のタスクで同じ除外と、さらに除外を足した")
    git(other, "push", "--quiet", "origin", "main")
    module.repository.git.fetch()
    assert not module.repository._lost_commits(task_branch.branch, "main", local=True, remote=True)


def test_union_lines_keeps_both_sides():
    from ecobuild.module import union_lines
    text = "a\n<<<<<<< HEAD\nx\n||||||| base\nold\n=======\nx\n\n# y\ny\n>>>>>>> m\nz\n"
    assert union_lines(text) == "a\nx\n\n# y\ny\nz\n"


def test_clone_module_prepares_dependencies(short_tmp):
    """clone はモジュールをcloneし、依存先と生成ファイルを sync と同じく用意する。"""
    stl_github = FakeGitHub(short_tmp / "gh1")
    Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    ecs_github = FakeGitHub(short_tmp / "gh2")
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=ecs_github)
    task_branch = ecs.repository.create_task("STLを使う").start()
    _cppbuild.open_solution(ecs.root).get_project("ECS").settings.link_git(
        url(stl_github.bare), solution_path=_cppbuild.CONFIG_DIRECTORY, link_type=ProjectType.STATIC_LIBRARY)
    _cppbuild.update(ecs.root)
    task_branch.stage(all=True)
    task_branch.commit("STLを依存先にする")
    task_branch.submit()
    ecs.repository.pull_request().merge()

    second = short_tmp / "second"
    second.mkdir()
    module, dependencies = Module.clone("ECS", directory=second, github=ecs_github)
    assert module.root == (second / "ECS").resolve() and module.name == "ECS"
    assert [(d.name, d.action) for d in dependencies] == [("STL", "cloned")]
    assert (module.root / "deps" / "STL" / ".ecobuild" / "ecobuild.toml").exists()
    assert module.status().branch == "main" and not module.status().unstaged


def test_clone_refuses_non_module(short_tmp):
    github = FakeGitHub(short_tmp / "gh")
    bare = short_tmp / "Plain.git"
    git(short_tmp, "init", "--quiet", "--bare", "--initial-branch=main", str(bare))
    seed = short_tmp / "seed"
    git(short_tmp, "clone", "--quiet", str(bare), str(seed))
    write(seed / "README.md", "plain\n")
    git(seed, "add", "--all")
    git(seed, "commit", "--quiet", "-m", "init")
    git(seed, "push", "--quiet", "origin", "main")
    github.use_bare(bare)
    target = short_tmp / "target"
    target.mkdir()
    with pytest.raises(Exception) as error:
        Module.clone("Plain", directory=target, github=github)
    assert error.value.code == "not_in_module" and not (target / "Plain").exists()


def test_link_deps_and_work_version(short_tmp):
    """link → deps list → 依存先が進む → deps update → 作業版は触らない → unlink。"""
    stl_github = FakeGitHub(short_tmp / "gh1")
    stl = Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    github = FakeGitHub(short_tmp / "gh2")
    github.others["STL"] = stl_github.bare
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=github)
    with pytest.raises(Exception) as error:
        ecs.link("STL")
    assert error.value.code == "not_on_task_branch"  # 管理ファイルを変える操作はタスクブランチでだけ
    ecs.repository.create_task("STLを使う").start()
    with pytest.raises(Exception) as error:
        ecs.link("NoSuch")
    assert error.value.code == "repository_not_found"

    linked = ecs.link("STL")
    assert (linked.name, linked.projects) == ("STL", ("ECS",))
    assert (ecs.root / "deps/STL/.ecobuild/ecobuild.toml").exists()
    assert [(d.name, d.state) for d in ecs.dependencies()] == [("STL", "aligned")]
    with pytest.raises(Exception) as error:
        ecs.link("STL")
    assert error.value.code == "already_exists"
    assert ecs.test().failed == 0

    second = new_stl_commit(stl.root, "#pragma once\n// v2\n")
    assert [d.state for d in ecs.dependencies()] == ["aligned"]  # 記録はまだ古い
    changes = ecs.update_dependencies()
    assert [(c.name, c.action) for c in changes] == [("STL", "aligned")] and "→" in changes[0].reason
    assert ecs.dependencies()[0].recorded == second and ecs.dependencies()[0].state == "aligned"

    # 依存先の中で作業する（作業版）：sync・deps sync・deps update は触らない
    clone = ecs.root / "deps" / "STL"
    git(clone, "switch", "--quiet", "-c", "task/9")
    write(clone / "STL/include/STL/STL.h", "#pragma once\n// 作業中\n")
    git(clone, "commit", "--quiet", "-am", "作業中")
    state = ecs.dependencies()[0]
    assert (state.state, state.branch) == ("working", "task/9")
    assert [(c.action, c.reason) for c in ecs.sync_dependencies()] == [("skipped", "作業版です（task/9）")]
    assert git(clone, "branch", "--show-current") == "task/9"

    removed = ecs.unlink("STL")
    assert removed.projects == ("ECS",) and not removed.clone_removed and clone.exists()  # 作業版は残す
    assert ecs.dependencies() == ()
    with pytest.raises(Exception) as error:
        ecs.unlink("STL")
    assert error.value.code == "dependency_not_found"


def test_link_aligns_existing_clone(short_tmp):
    """依存先の依存先として clone 済みのモジュールを link すると、手元の clone も記録した版に合わせる（実用試験 D-3）。"""
    base_github, stl_github = FakeGitHub(short_tmp / "gh1"), FakeGitHub(short_tmp / "gh2")
    base = Module.create("Base", directory=short_tmp, kind="library", github=base_github)
    stl = Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    solution = _cppbuild.open_solution(stl.root)
    solution.get_project("STL").settings.link_git(url(base_github.bare), solution_path=_cppbuild.CONFIG_DIRECTORY,
                                            link_type=ProjectType.STATIC_LIBRARY)
    solution.update()
    git(stl.root, "add", "--all")
    git(stl.root, "commit", "--quiet", "-m", "Baseを使う")
    git(stl.root, "push", "--quiet", "origin", "main")
    github = FakeGitHub(short_tmp / "gh3")
    github.others.update(STL=stl_github.bare, Base=base_github.bare)
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=github)
    ecs.repository.create_task("STLとBaseを使う").start()
    assert ecs.link("STL").clone.action == "unchanged"
    clone = ecs.root / "deps" / "Base"
    first = git(clone, "rev-parse", "HEAD")

    def new_base_commit(text: str) -> str:
        write(base.root / "Base" / "include" / "Base" / "Base.h", text)
        git(base.root, "commit", "--quiet", "-am", "Baseを更新")
        git(base.root, "push", "--quiet", "origin", "main")
        return git(base.root, "rev-parse", "HEAD")

    # 作業版は合わせない
    new_base_commit("#pragma once\n// v2\n")
    git(clone, "switch", "--quiet", "-c", "task/9")
    linked = ecs.link("Base")
    assert (linked.clone.action, linked.clone.reason) == ("skipped", "作業版です（task/9）")
    assert git(clone, "branch", "--show-current") == "task/9"
    git(clone, "switch", "--quiet", "--detach", first)
    git(clone, "branch", "--quiet", "-D", "task/9")
    ecs.unlink("Base")

    third = new_base_commit("#pragma once\n// v3\n")
    linked = ecs.link("Base")
    assert (linked.revision, linked.clone.action) == (third, "aligned")
    assert git(clone, "rev-parse", "HEAD") == third
    assert {d.name: d.state for d in ecs.dependencies()}["Base"] == "aligned"
    from ecobuild_cpp.cli.deps import add as link
    assert link._text(linked).splitlines()[1] == "既にあった deps/Base を、記録した版に合わせました。"
    assert ecs.test().failed == 0


def test_working_dependency_is_reported(short_tmp):
    """依存先の依存先が作業版：status・check・deps list --all で知らせ、task submit は止める（実用試験 D-1）。"""
    base_github, stl_github = FakeGitHub(short_tmp / "gh1"), FakeGitHub(short_tmp / "gh2")
    Module.create("Base", directory=short_tmp, kind="library", github=base_github)
    stl = Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    solution = _cppbuild.open_solution(stl.root)
    solution.get_project("STL").settings.link_git(url(base_github.bare), solution_path=_cppbuild.CONFIG_DIRECTORY,
                                            link_type=ProjectType.STATIC_LIBRARY)
    solution.update()
    git(stl.root, "add", "--all")
    git(stl.root, "commit", "--quiet", "-m", "Baseを使う")
    git(stl.root, "push", "--quiet", "origin", "main")
    github = FakeGitHub(short_tmp / "gh3")
    github.others["STL"] = stl_github.bare
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=github)
    task_branch = ecs.repository.create_task("STLを使う").start()
    ecs.link("STL")   # リンクは、それだけでコミットする
    assert ecs.status().dependencies == ()
    assert [d.name for d in ecs.check(build=False).items if d.name == "dependencies"] == []

    git(ecs.root / "deps" / "Base", "switch", "--quiet", "-c", "task/9")
    assert [d.name for d in ecs.dependencies()] == ["STL"]
    assert {d.name: d.via for d in ecs.dependencies(all=True)} == {"STL": None, "Base": "STL"}
    [working] = ecs.status().dependencies
    assert (working.name, working.state, working.branch, working.via) == ("Base", "working", "task/9", "STL")
    with pytest.raises(Exception) as error:
        ecs.check(build=False)
    assert error.value.code == "check_failed"
    assert [d["name"] for d in error.value.details if not d["ok"]] == ["dependencies"]
    item = next(i for i in ecs.check(build=False, allow_dependency_mismatch=True).items if i.name == "dependencies")
    assert item.ok and "Base（作業版 task/9、STL 経由）" in item.detail
    with pytest.raises(Exception) as error:
        ecs.submit(check=False)
    assert error.value.code == "dependency_not_recorded"


def test_dependency_tree(short_tmp, monkeypatch):
    """deps tree：依存先の依存先も。2か所から使われる依存先は、2回目にその先を省く。"""
    base_github, stl_github = FakeGitHub(short_tmp / "gh1"), FakeGitHub(short_tmp / "gh2")
    Module.create("Base", directory=short_tmp, kind="library", github=base_github)
    stl = Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    _cppbuild.open_solution(stl.root).get_project("STL").settings.link_git(
        url(base_github.bare), solution_path=_cppbuild.CONFIG_DIRECTORY, link_type=ProjectType.STATIC_LIBRARY)
    git(stl.root, "add", "--all")
    git(stl.root, "commit", "--quiet", "-m", "Baseを使う")
    git(stl.root, "push", "--quiet", "origin", "main")
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=FakeGitHub(short_tmp / "gh3"))
    assert ecs.dependency_tree().direct == ()
    project = _cppbuild.open_solution(ecs.root).get_project("ECS").settings
    project.link_git(url(stl_github.bare), solution_path=_cppbuild.CONFIG_DIRECTORY, link_type=ProjectType.STATIC_LIBRARY)
    project.link_git(url(base_github.bare), solution_path=_cppbuild.CONFIG_DIRECTORY, link_type=ProjectType.STATIC_LIBRARY)

    tree = ecs.dependency_tree()
    assert tree.module == "ECS" and tree.direct == ("Base", "STL")
    assert {n.name: (n.present, n.depends_on) for n in tree.nodes} == {"Base": (True, ()), "STL": (True, ("Base",))}
    assert ecs.info().dependencies == ("Base", "STL")

    fetched = {d.name: (d.remote, d.latest == d.recorded) for d in ecs.dependencies(fetch=True)}
    assert fetched == {"Base": ("ok", True), "STL": ("ok", True)}
    new_stl_commit(stl.root, "#pragma once\n// v2\n")
    (short_tmp / "gh1" / "Base.git").rename(short_tmp / "gh1" / "Gone.git")    # GitHubで削除された
    fetched = {d.name: (d.remote, d.latest == d.recorded) for d in ecs.dependencies(fetch=True)}
    assert fetched == {"Base": ("gone", False), "STL": ("ok", False)}
    (short_tmp / "gh1" / "Gone.git").rename(short_tmp / "gh1" / "Base.git")

    from click.testing import CliRunner
    from ecobuild_cli import build_cli
    with monkeypatch.context() as patch:   # 片付けの前に、今いるディレクトリを戻す
        patch.chdir(ecs.root)
        shown = CliRunner().invoke(build_cli(), ["deps", "tree"]).output.splitlines()
    revision = tree.nodes[0].revision[:7]
    assert shown == ["ECS", f"├─ Base {revision}", f"└─ STL {tree.nodes[1].revision[:7]}", f"   └─ Base {revision}"]


def test_switching_aligns_dependencies(short_tmp):
    """task start・task prune で記録が変わる先へ移ったら、手元の依存先も合わせる（仮運用3回目で見つかった）。"""
    stl_github = FakeGitHub(short_tmp / "gh1")
    stl = Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    github = FakeGitHub(short_tmp / "gh2")
    github.others["STL"] = stl_github.bare
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=github)
    task_branch = ecs.repository.create_task("STLを使う").start()
    ecs.link("STL")   # リンクは、それだけでコミットする
    task_branch.submit()
    ecs.repository.pull_request().merge()
    ecs.repository.prune_task_branches()

    second = short_tmp / "second"
    second.mkdir()
    other, _ = Module.clone("ECS", directory=second, github=github)
    first = git(other.root / "deps" / "STL", "rev-parse", "HEAD")

    newer = new_stl_commit(stl.root, "#pragma once\n// v2\n")
    update = ecs.repository.create_task("STLを最新に").start()
    ecs.update_dependencies()   # 依存先の更新も、それだけでコミットする
    update.submit()
    ecs.repository.pull_request().merge()

    assert git(other.root / "deps" / "STL", "rev-parse", "HEAD") == first
    other.repository.create_task("続きの作業").start()  # 最新のmainからタスクブランチを作る → 依存先も新しい記録へ
    assert git(other.root / "deps" / "STL", "rev-parse", "HEAD") == newer


def test_dependency_clone_keeps_lf_line_endings(short_tmp, monkeypatch):
    """依存先は ECOBuild の clone と同じ改行コードの扱い（core.autocrlf=input）で取り出し、clone の設定にも書く：
    このPCの git が core.autocrlf=true（Windows の既定）でも CRLF にしない（コンテナの中の git から変更ありに見えない）。
    新しいモジュールには、改行を LF にそろえる .gitattributes を置く。"""
    stl_github = FakeGitHub(short_tmp / "gh1")
    stl = Module.create("STL", directory=short_tmp, kind="library", github=stl_github)
    assert (stl.root / ".gitattributes").read_text(encoding="utf-8").startswith("* text=auto eol=lf\n")
    git(stl.root, "rm", "--quiet", ".gitattributes")   # .gitattributes のない前の版のモジュール
    git(stl.root, "commit", "--quiet", "-m", ".gitattributes を外す")
    git(stl.root, "push", "--quiet", "origin", "main")
    github = FakeGitHub(short_tmp / "gh2")
    github.others["STL"] = stl_github.bare
    ecs = Module.create("ECS", directory=short_tmp, kind="library", github=github)
    ecs.repository.create_task("STLを使う").start()
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")   # このPCの設定に当たるもの（後ろに足し、消さない）
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.autocrlf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    ecs.link("STL")
    clone = ecs.root / "deps" / "STL"
    assert b"\r\n" not in (clone / "STL" / "include" / "STL" / "STL.h").read_bytes()
    assert git(clone, "config", "--local", "core.autocrlf") == "input"
    assert (os.environ["GIT_CONFIG_COUNT"], os.environ.get("GIT_CONFIG_KEY_1")) == ("1", None)   # 元に戻す
    # 前の版が clone した（設定のない）依存先にも、sync で書く
    git(clone, "config", "--local", "--unset", "core.autocrlf")
    ecs.sync_dependencies()
    assert git(clone, "config", "--local", "core.autocrlf") == "input"
    remove_tree(clone)   # ビルドの前の取得（足りない依存先）でも同じ
    ecs.build()
    assert b"\r\n" not in (clone / "STL" / "include" / "STL" / "STL.h").read_bytes()
    assert git(clone, "config", "--local", "core.autocrlf") == "input"
