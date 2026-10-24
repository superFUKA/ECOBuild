import subprocess

import pytest

from helpers import git, remove_tree, short_temporary_directory
from fakes import FakeGitHub
from ecowork import WorkError
from ecobuild import config
from ecobuild.errors import EcoBuildError
from ecobuild_cpp.errors import ErrorCode
from ecobuild_bundle import Module

pytestmark = [pytest.mark.cppbuild, pytest.mark.local]


@pytest.fixture
def short_tmp():
    base = short_temporary_directory()
    yield base
    remove_tree(base)


def test_create_module(short_tmp):
    github = FakeGitHub(short_tmp / "gh")
    steps = []
    module = Module.create("Calc", directory=short_tmp, kind="library", description="電卓", github=github,
                           progress=steps.append)
    root = short_tmp / "Calc"
    # 経過（GUIが作成中に出す）：今している作業を順に知らせる
    assert steps[0] == "GitHubにリポジトリを作成中…" and "ライブラリとテストを用意中…" in steps
    assert steps.index("ライブラリとテストを用意中…") < steps.index("GitHubへpush中…") < steps.index("タスク管理を準備中…")
    assert module.root == root
    assert config.load(root / config.FILE_NAME).projects is None   # 基本のProjectは決めない
    assert "/deps/" in (root / ".gitignore").read_text(encoding="utf-8")
    assert github.private is True
    # 初回コミットがGitHub（bare）のmainにある
    assert git(github.bare, "log", "--format=%s", "main") == "ECOBuildでモジュールを作成"
    files = git(github.bare, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert ".ecobuild/.cppbuild/CMakeLists.txt" in files and ".ecobuild/.cppbuild/projects/Calc/CMakeLists.txt" in files
    assert not any(f.startswith(".ecobuild/.cppbuild/output") for f in files)
    # ルートには、ECOBuild・CppBuildの内部のファイルを置かない（.ecobuild/ にまとめる）
    # AGENTS.md は作らない（エージェントを使うモジュールだけ agent init で作る）
    assert sorted({f.split("/")[0] for f in files}) == [".ecobuild", ".gitattributes", ".gitignore", "Calc", "CalcTest", "README.md"]
    assert {".ecobuild/.gitattributes", ".ecobuild/.gitignore", ".ecobuild/ecobuild.toml"} <= set(files)
    assert git(root, "status", "--porcelain") == ""
    assert Module.find(root / "Calc" / "src").name == "Calc"
    assert module.summary().projects == ("Calc", "CalcTest")

    # cloneしただけの人が、CMakeだけでビルド・テストできる
    clone = short_tmp / "c"
    git(short_tmp, "clone", "--quiet", "--config", "core.autocrlf=true", str(github.bare), str(clone))
    # 改行を変換する設定でcloneしても、生成し直した生成ファイルが「変更あり」にならない
    from ecobuild_cpp import _cppbuild
    _cppbuild.update(clone)
    assert git(clone, "status", "--porcelain") == ""
    for args in (["cmake", "-S", ".ecobuild/.cppbuild", "-B", "b"], ["cmake", "--build", "b", "--config", "Debug"],
                 ["ctest", "--test-dir", "b", "-C", "Debug"]):
        completed = subprocess.run(args, cwd=clone, capture_output=True, text=True, errors="replace")
        assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]


def test_library_without_its_test_project(short_tmp):
    """module new --kind library --no-test：テスト用のProjectを作らない。"""
    github = FakeGitHub(short_tmp / "gh")
    Module.create("Calc", directory=short_tmp, kind="library", github=github, test=False)
    files = git(github.bare, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert sorted({f.split("/")[0] for f in files}) == [".ecobuild", ".gitattributes", ".gitignore", "Calc", "README.md"]


def test_existing_directory_is_rejected(short_tmp):
    (short_tmp / "Calc").mkdir()
    with pytest.raises(WorkError) as error:  # 作業の進め方（ecowork）のエラー
        Module.create("Calc", directory=short_tmp, github=FakeGitHub(short_tmp / "gh"))
    assert error.value.code == ErrorCode.ALREADY_EXISTS


def test_invalid_name(short_tmp):
    with pytest.raises(EcoBuildError) as error:
        Module.create("1bad-name", directory=short_tmp, github=FakeGitHub(short_tmp / "gh"))
    assert error.value.code == ErrorCode.INVALID_CONFIG


def test_submit_commits_the_generated_files(short_tmp):
    """提出の前に生成ファイルを作り直し、作り直して変わったファイルはそれだけでコミットしてから提出する。"""
    github = FakeGitHub(short_tmp / "gh")
    module = Module.create("Calc", directory=short_tmp, github=github)
    task_branch = module.repository.create_task("生成ファイルの確認").start()
    # 生成ファイルを手で書き換えてコミットした（作り直すと戻る）
    generated = module.root / ".ecobuild/.cppbuild/projects/Calc/CMakeLists.txt"
    generated.write_text(generated.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    (module.root / "Calc" / "src" / "Extra.cpp").write_text("int extra() { return 1; }\n", encoding="utf-8")
    task_branch.stage(".ecobuild/.cppbuild/projects/Calc/CMakeLists.txt", "Calc/src/Extra.cpp")
    task_branch.commit("生成ファイルを書き換え")
    pr = task_branch.submit()
    assert pr.head == "task/1"
    git = module.repository.git
    assert git.output("log", "-1", "--format=%s") == "生成ファイルを作り直す（提出の前）"
    assert ".ecobuild/.cppbuild/projects/Calc/CMakeLists.txt" in git.output("show", "--name-only", "--format=", "HEAD").splitlines()
    assert not module.repository.status().unstaged


def test_only_link_commits_the_ecobuild_files(short_tmp):
    """ECOBuild のファイルが変わっても、何でもコミットはしない（Project の追加は作業者がコミットする）。リンクは、
    リンクが変えたファイルだけをリンクのメッセージでコミットする。作業者の変更はコミットに混ぜない。"""
    module = Module.create("Calc", directory=short_tmp, github=FakeGitHub(short_tmp / "gh"))
    module.repository.create_task("own").start()
    git_ = module.repository.git
    first = git_.output("rev-parse", "HEAD")
    (module.root / "Calc" / "src" / "Work.cpp").write_text("int work() { return 1; }\n", encoding="utf-8")   # 作業者の変更
    module.add_project("Lib", "library", test=False)   # .ecobuild の中と Lib/ を書き換える
    assert git_.output("rev-parse", "HEAD") == first and ".ecobuild/.cppbuild/projects/Lib/project.json" in module.own_changes()
    module.commit("Lib を追加", (".ecobuild", "Lib"))
    module.link_project("Calc", "Lib")
    assert git_.output("log", "-1", "--format=%s") == "Calc に Lib をリンク"
    linked = git_.output("show", "--name-only", "--format=", "HEAD").splitlines()
    assert linked and all(module.is_own_file(f) for f in linked)
    assert not module.own_changes() and "Calc/src/Work.cpp" in git_.working_tree().untracked   # 作業者の変更は残る


def test_create_module_names_its_first_project(short_tmp):
    """最初に作るProjectの名前は --project で決められる（既定はモジュール名）。ライブラリならテスト用は <名前>Test。"""
    app = Module.create("Game", directory=short_tmp, project="App", github=FakeGitHub(short_tmp / "gh1"))
    assert [(p.name, p.kind) for p in app.projects()] == [("App", "executable")]
    assert (app.root / "App/src/main.cpp").is_file() and not (app.root / "Game").exists()

    lib = Module.create("Math", directory=short_tmp, kind="library", project="Core", github=FakeGitHub(short_tmp / "gh2"))
    assert sorted(p.name for p in lib.projects()) == ["Core", "CoreTest"]
    assert (lib.root / "Core/include/Core/Core.h").is_file()

    for kind, project, gh in (("none", "App", "gh3"), ("", "1bad", "gh4")):
        with pytest.raises(EcoBuildError) as error:
            Module.create("Bad", directory=short_tmp, kind=kind, project=project, github=FakeGitHub(short_tmp / gh))
        assert error.value.code == ErrorCode.INVALID_ARGUMENT and not (short_tmp / "Bad").exists()


def test_create_module_starts_with_an_app_or_nothing(short_tmp):
    """既定は実行ファイルのProjectを1つ。--kind none なら何も作らず、後から project add で足す。
    他のモジュールからリンクされるのは最初に作ったProject（main）で、ライブラリでなければリンクできない。"""
    from ecobuild.errors import EcoBuildError
    from ecobuild_cpp.errors import ErrorCode

    tool = Module.create("Tool", directory=short_tmp, github=FakeGitHub(short_tmp / "gh1"))
    assert [(p.name, p.kind, p.links) for p in tool.projects()] == [("Tool", "executable", ())]
    assert "#include" not in (tool.root / "Tool/src/main.cpp").read_text(encoding="utf-8")
    assert "VS_STARTUP_PROJECT" in (tool.root / ".ecobuild/.cppbuild/CMakeLists.txt").read_text(encoding="utf-8")  # F5 で Tool を起動
    assert tool.build().project is None and tool.run().returncode == 0
    tested = tool.test()   # テスト用のProjectがなければ、何もせずに成功
    assert (tested.passed, tested.failed, tested.cases) == (0, 0, ())

    github = FakeGitHub(short_tmp / "gh2")
    empty = Module.create("Empty", directory=short_tmp, kind="none", github=github)
    assert empty.summary().projects == () and empty.build().project is None
    empty.repository.create_task("中身を足す").start()
    assert empty.add_project("Lib", "library").paths == ("Lib/include/Lib/Lib.h", "Lib/src/Lib.cpp",
                                                         "LibTest/src/LibTest.cpp")
    assert empty.test().failed == 0
    github.others["Tool"] = tool.repository.github.bare   # 実行ファイルが main のモジュールはリンクできない
    with pytest.raises(EcoBuildError) as error:
        empty.link("Tool", project="Lib")
    assert error.value.code == ErrorCode.NOT_LINKABLE
    assert empty.dependencies() == () and not (empty.root / "deps" / "Tool").exists()   # 何も残さない
    empty.remove_project("Lib")                            # main を外すと、他からリンクできなくなると知らせる
    assert any("リンクできなくなりました" in n for n in empty.repository.notices)
    assert {p.name for p in empty.projects()} == {"LibTest"}

    with pytest.raises(EcoBuildError) as error:
        Module.create("Bad", directory=short_tmp, kind="plugin", github=FakeGitHub(short_tmp / "gh3"))
    assert error.value.code == ErrorCode.INVALID_ARGUMENT and not (short_tmp / "Bad").exists()


def test_adopt_makes_a_solution_without_projects(short_tmp):
    remote, work = short_tmp / "remote.git", short_tmp / "work"
    git(short_tmp, "init", "--quiet", "--bare", "--initial-branch=main", str(remote))
    git(short_tmp, "clone", "--quiet", str(remote), str(work))
    (work / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    git(work, "add", "main.cpp")
    git(work, "commit", "--quiet", "-m", "init")
    git(work, "push", "--quiet", "origin", "main")
    github = FakeGitHub(short_tmp / "gh")
    github.use_bare(remote)
    module, done = Module.adopt(work, type="cpp", github=github)
    assert module.project_names == ()   # 今あるソースは Project に入れない（project add で足す）
    files = git(remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert ".ecobuild/.cppbuild/CMakeLists.txt" in files and "main.cpp" in files
    assert "/deps/" in (work / ".gitignore").read_text(encoding="utf-8")
    assert git(work, "status", "--porcelain").strip() == ""
