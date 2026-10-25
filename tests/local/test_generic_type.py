"""型 generic：[commands] に書いたコマンドでビルド・テスト・実行する。本体と型の境目を確かめる2つ目の型。"""

import sys

import pytest

from fakes import FakeGitHub
from ecobuild import config
from ecobuild import module as module_mod
from ecobuild.errors import EcoBuildError, ErrorCode
from ecowork import WorkError
from ecobuild_bundle import Module

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_generic_module(tmp_path):
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    root = module.root
    assert sorted(p.name for p in root.iterdir() if p.name != ".git") == [".ecobuild", "README.md"]
    assert sorted(p.name for p in (root / ".ecobuild").iterdir()) == [".gitattributes", ".gitignore", "README.md", "container",
                                                                    "ecobuild.toml"]
    assert "[commands]" in (root / ".ecobuild" / "README.md").read_text(encoding="utf-8")
    assert "ECOBuild" not in (root / "README.md").read_text(encoding="utf-8")
    assert module.config.projects is None and module.project_names == ()
    assert code_of(lambda: Module.create("X", directory=tmp_path, type="generic", kind="app",
                                         github=FakeGitHub(tmp_path / "gh2"))) == ErrorCode.INVALID_ARGUMENT

    # コマンドを書くまでは対応しない
    assert code_of(module.build) == ErrorCode.NOT_SUPPORTED
    assert code_of(module.projects) == ErrorCode.NOT_SUPPORTED
    assert code_of(lambda: module.link("STL")) == ErrorCode.NOT_ON_TASK_BRANCH

    task_branch = module.repository.create_task("コマンドを書く").start()
    commands = {"build": python("print('built {configuration}')"), "test": python("print('tested')"),
                "run": python("import sys; print('run {arguments}')"), "clean": ""}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    reloaded = Module.find(root, github=module.repository.github)
    assert reloaded.config.extra["commands"]["test"] == commands["test"]  # ecobuild.toml に書き戻せる

    assert reloaded.build(configuration="Release").configuration == "Release"
    assert reloaded.test().passed == 1
    assert reloaded.run(arguments="a b").output.strip() == "run a b"
    assert code_of(lambda: reloaded.build(action="clean")) == ErrorCode.NOT_SUPPORTED  # clean は空
    assert reloaded.build(action="rebuild").action == "rebuild"  # clean がなければビルドだけ
    assert [(i.name, i.ok) for i in reloaded.check().items] == [
        ("generated", True), ("conflict_markers", True), ("build", True), ("test", True)]

    failing = {**commands, "test": python("import sys; sys.exit(3)")}
    reloaded._save_config(config.ModuleConfig(**{**reloaded.config.__dict__, "extra": {"commands": failing}}))
    with pytest.raises(EcoBuildError) as error:
        reloaded.test()
    assert error.value.code == ErrorCode.TEST_FAILED and error.value.details["returncode"] == 3

    ci = reloaded.write_ci()
    workflow = (root / ci.path).read_text(encoding="utf-8")
    assert "ubuntu-latest" in workflow and "Build" in workflow and "workflow_dispatch" in workflow
    # file add：書いた名前（拡張子込み）の空のファイルを作るだけ
    added = reloaded.add_files([root / "a.txt", root / "docs" / "memo.md"])
    assert [c.paths for c in added] == [("a.txt",), ("docs/memo.md",)]
    assert (root / "docs" / "memo.md").read_bytes() == b""
    assert code_of(lambda: reloaded.add_file(root / "a.txt")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: reloaded.add_file(root / ".ecobuild" / "x.txt")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: reloaded.add_file(tmp_path / "outside.txt")) == ErrorCode.NOT_IN_MODULE
    assert code_of(lambda: reloaded.add_file(root / "b.txt", template="t")) == ErrorCode.NOT_SUPPORTED
    assert reloaded.move_file(root / "a.txt", root / "docs" / "b.txt").paths == ("a.txt", "docs/b.txt")
    assert code_of(lambda: reloaded.move_file(root / "docs" / "b.txt", root / "docs" / "memo.md")) == ErrorCode.ALREADY_EXISTS
    assert reloaded.remove_file(root / "docs" / "b.txt").paths == ("docs/b.txt",)
    assert not (root / "docs" / "b.txt").exists()
    assert code_of(lambda: reloaded.remove_file(root / "docs" / "b.txt")) == ErrorCode.FILE_NOT_FOUND
    task_branch.stage(all=True)
    task_branch.commit("コマンドとCI")
    assert task_branch.submit().number


def test_check_is_reused_while_unchanged(tmp_path):
    """ビルド・テストを含む check を通った版は、task submit --check で繰り返さない。変更・コミットで無効になる。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    task_branch = module.repository.create_task("確認の使い回し").start()
    commands = {"build": python("print('built')"), "test": python("print('tested')")}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    module.check()
    assert not module.checked()  # 変更が残っている（コミット前）
    task_branch.stage(all=True)
    task_branch.commit("コマンド")
    assert not module.checked()  # コミットした版はまだ確かめていない
    module.check()
    assert module.checked()
    module.check(build=False)
    assert not module.checked()  # ビルド・テストを省いた確認は記録しない

    module.check()
    (module.root / "note.txt").write_text("作業中\n", encoding="utf-8")
    assert not module.checked()
    (module.root / "note.txt").unlink()
    assert module.checked()
    failing = {**commands, "test": python("import sys; sys.exit(3)")}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": failing}}))
    task_branch.stage(all=True)
    task_branch.commit("失敗するテスト")
    with pytest.raises(EcoBuildError):
        module.check()
    assert not module.checked()



def test_check_warns_eol_only_changes(tmp_path):
    """改行コードだけが違うファイルは、check の項目として知らせる（失敗にはしない）。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    module.repository.git.set_config("core.autocrlf", "false")
    readme = module.root / "README.md"
    data = readme.read_bytes()
    readme.write_bytes(data.replace(b"\n", b"\r\n") if b"\r\n" not in data else data.replace(b"\r\n", b"\n"))
    report = module.check(build=False)
    item = next(i for i in report.items if i.name == "eol_only")
    assert report.ok and item.ok and "README.md" in item.detail and "改行コード" in item.detail
    readme.write_bytes(data)
    assert not any(i.name == "eol_only" for i in module.check(build=False).items)


def test_submit_writes_check_evidence(tmp_path):
    """提出の本文に、確認（check）がどの版で通ったかと項目を書く。出し直すと今の版のものに、確かめなければそう書く。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    task_branch = module.repository.create_task("証拠").start()
    commands = {"build": python("print('built')"), "test": python("print('tested')")}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    module.set_pipeline(config.Pipeline("full", ("build", "test")))
    module.set_trigger("before-submit", ("full",))
    task_branch.stage(all=True)
    task_branch.commit("コマンド")
    pr = module.submit(note="テストのコマンドを足した。戻すならこのPRを戻す。")
    head = module.repository.git.rev_parse("HEAD")[:7]
    body = module.repository.github.pulls[pr.number].body
    assert "テストのコマンドを足した" in body and "### 確認（ECOBuild）" in body
    assert f"版 `{head}`" in body and "- OK ビルド" in body and "- OK テスト：成功 1" in body

    (module.root / "a.txt").write_text("a\n", encoding="utf-8")
    task_branch.stage("a.txt")
    task_branch.commit("a")
    module.submit(check=False)
    body = module.repository.github.pulls[pr.number].body
    head = module.repository.git.rev_parse("HEAD")[:7]
    assert f"この版（`{head}`）は" in body and "--no-check" in body and "- OK テスト" not in body
    assert "テストのコマンドを足した" in body   # 説明は渡さなければそのまま
    module.submit(check=False, verified_by=("pytest tests/unit=成功 12", "ruff check src = 指摘なし"))
    body = module.repository.github.pulls[pr.number].body
    assert "--no-check" in body and "提出した人が確かめたこと" in body
    assert "- `pytest tests/unit`：成功 12" in body and "- `ruff check src`：指摘なし" in body
    assert module_mod.submitted_check(body)[0] is False   # 確かめたことを書いても、check を通した印にはしない
    with pytest.raises(EcoBuildError) as error:
        module.submit(check=False, verified_by=("pytest だけ",))
    assert error.value.code == ErrorCode.INVALID_ARGUMENT
    module.check()
    module.submit(check=False)   # 確かめた版なら、その結果を書く
    assert "- OK テスト：成功 1" in module.repository.github.pulls[pr.number].body


def test_submit_runs_only_the_pipelines_put_before_it(tmp_path):
    """提出の前に走るのは、before-submit に当てたパイプラインだけ。既定は何もせずに出し、そう書く。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    task_branch = module.repository.create_task("提出の確認").start()
    commands = {"build": python("import sys; sys.exit(5)"), "test": python("print('tested')")}   # ビルドは失敗する
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    assert module.pipelines() == config.Pipelines()
    task_branch.stage(all=True)
    task_branch.commit("コマンド")
    pr = module.submit()   # 何も確かめない（失敗するビルドも動かさない）
    body = module.repository.github.pulls[pr.number].body
    assert module_mod.NO_CHECKS_SET_NOTE in body and module_mod.submitted_check(body) == (None, None)

    module.set_pipeline(config.Pipeline("quick", ("conflict_markers", "test")))
    module.set_pipeline(config.Pipeline("full", ("build", "test")))
    assert module.pipelines().at("before-submit") == ()   # 作っただけでは走らない
    module.set_trigger("before-submit", ("quick",))
    assert config.load(module.root / config.FILE_NAME).pipelines.at("before-submit") == ("quick",)
    task_branch.stage(all=True)
    task_branch.commit("提出の確認")
    module.submit()        # 当てたものだけ（ビルドは動かさないので通る）
    body = module.repository.github.pulls[pr.number].body
    assert "- OK 衝突の印" in body and "- OK テスト" in body and "ビルド" not in body
    assert not module.checked()   # 一部だけの確認は、全部を通った版として残さない
    module.set_trigger("before-submit", ("quick", "full"))
    task_branch.stage(all=True)
    task_branch.commit("全部")
    with pytest.raises(EcoBuildError) as error:   # 前のものが失敗したら出さない
        module.submit()
    assert error.value.code == ErrorCode.CHECK_FAILED and "提出の前のパイプライン full" in error.value.message
    with pytest.raises(EcoBuildError) as error:   # 試験を絞れない型に絞る試験を書いたら、飛ばさずに失敗
        module.check(only=("test",), tests=("t",))
    assert error.value.code == ErrorCode.CHECK_FAILED


def test_pipelines_are_made_put_and_run(tmp_path):
    """パイプラインは単体で作り、単体でも走らせ、どのタイミングにも当てられる。前のものは操作を止め、後のものは知らせるだけ。
    このPCだけで足す当て方は ecobuild.local.toml（共有の設定は変えない）。以前の [check] は before-submit のものとして読む。"""
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    task_branch = module.repository.create_task("パイプライン").start()
    commands = {"build": python("import sys; sys.exit(5)"), "test": python("print('tested')")}   # ビルドは失敗する
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {
        "commands": commands, "check": {"submit": ["test"]}}}))
    legacy = module.pipelines()
    assert legacy.at("before-submit") == (config.LEGACY_PIPELINE,) and legacy.get("check").steps == ("test",)

    module.set_pipeline(config.Pipeline("quick", ("generated", "test")))
    text = (module.root / config.FILE_NAME).read_text(encoding="utf-8")
    assert "[check]" not in text and "[pipelines]" in text and "[triggers]" in text   # 以前の設定は新しい形で書き直す
    module.set_pipeline(config.Pipeline("broken", ("build",)))
    assert module.run_pipeline("quick").ok
    failed = module.run_pipeline("broken")
    assert not failed.ok and failed.items[0].name == "build" and not failed.items[0].ok

    module.set_trigger("before-commit", ("broken",))
    (module.root / "a.txt").write_text("a\n", encoding="utf-8")
    with pytest.raises(EcoBuildError) as error:
        module.commit("a")
    assert error.value.code == ErrorCode.CHECK_FAILED and "コミットの前" in error.value.message
    assert module.repository.git.working_tree().untracked or module.repository.git.working_tree().unstaged
    module.commit("a", pipelines=False)   # 走らせずに進める
    module.set_trigger("before-commit", ())
    module.set_trigger("after-commit", ("broken",))
    (module.root / "b.txt").write_text("b\n", encoding="utf-8")
    module.repository.notices.clear()
    assert module.commit("b").sha                                     # 後のものの失敗は止めない
    assert any("コミットの後のパイプライン broken" in n for n in module.repository.notices)
    module.set_trigger("after-commit", ())

    module.set_trigger("before-push", ("broken",), local=True)        # このPCだけ（共有の設定は変わらない）
    assert module.pipelines().at("before-push") == ("broken",)
    assert config.load(module.root / config.FILE_NAME).pipelines.at("before-push") == ()
    assert "broken" in (module.root / config.LOCAL_FILE_NAME).read_text(encoding="utf-8")
    with pytest.raises(EcoBuildError) as error:
        module.push()
    assert "push の前" in error.value.message
    module.set_trigger("before-push", (), local=True)
    assert module.pipelines().local == {}

    module.set_trigger("before-submit", ("quick",))
    module.remove_pipeline("quick")                                     # 当てていたところからも外れる
    assert module.pipelines().at("before-submit") == () and module.pipelines().get("quick") is None
    for bad in (lambda: module.set_trigger("before-lunch", ("broken",)), lambda: module.set_trigger("after-push", ("none",)),
                lambda: module.set_pipeline(config.Pipeline("lint", ("lint",))),
                lambda: module.set_pipeline(config.Pipeline("a b", ("test",))),
                lambda: module.set_pipeline(config.Pipeline("t", ("build",), ("tests/x",))),
                lambda: module.run_pipeline("nothing")):
        with pytest.raises(EcoBuildError) as error:
            bad()
        assert error.value.code == ErrorCode.INVALID_ARGUMENT


def test_pipeline_tests_are_written_as_test_steps(tmp_path):
    """流す試験は ecobuild.toml に「test:<試験>」として並べ、読むと手順 test と試験に戻る。"""
    pipeline = config.Pipeline("unit", ("generated", "test"), ("tests/unit", "tests/x.py"))
    assert pipeline.entries() == ["generated", "test:tests/unit", "test:tests/x.py"]
    base = config.ModuleConfig(name="M", type="generic")
    written = base.with_pipelines((pipeline,), {"before-push": ("unit",)})
    assert written.extra["pipelines"] == {"unit": pipeline.entries()} and written.pipelines.get("unit") == pipeline
    config.save(written, tmp_path / config.FILE_NAME)
    assert config.load(tmp_path / config.FILE_NAME).pipelines == written.pipelines



def test_ci_settings_and_hand_edited_workflow(tmp_path):
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    module.repository.create_task("CI").start()
    commands = {"build": "make {configuration}", "test": "make test"}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    path = module.root / ".github/workflows/ecobuild.yml"
    state = module.ci_state()
    assert (state.supported, state.exists, state.os, state.branches, state.default_base) == (True, False, None, None, "main")

    module.write_ci()
    state = module.ci_state()
    assert (state.exists, state.edited, state.current) == (True, False, True)
    workflow = path.read_text(encoding="utf-8")
    assert "os: [ubuntu-latest]" in workflow and "configuration: [Debug]" in workflow
    assert "make ${{ matrix.configuration }}" in workflow

    settings = config.CiSettings(os=("linux", "windows"), configurations=("Debug", "Release"))
    module.write_ci(settings)
    reloaded = Module.find(module.root, github=module.repository.github)
    assert reloaded.config.ci == settings  # ecobuild.toml の [ci] に残る
    workflow = path.read_text(encoding="utf-8")
    assert "os: [ubuntu-latest, windows-latest]" in workflow and "configuration: [Debug, Release]" in workflow
    reloaded.write_ci()  # 設定のまま作り直す（編集していなければ上書きしてよい）

    path.write_text(path.read_text(encoding="utf-8") + "# 手で足した\n", encoding="utf-8")
    assert code_of(reloaded.write_ci) == ErrorCode.ALREADY_EXISTS
    state = reloaded.ci_state()
    assert (state.edited, state.current, state.configurations) == (True, False, ("Debug", "Release"))
    reloaded.write_ci(force=True)
    assert "# 手で足した" not in path.read_text(encoding="utf-8")

    assert code_of(lambda: reloaded.write_ci(config.CiSettings(shared=True))) == ErrorCode.NOT_SUPPORTED
    assert code_of(lambda: reloaded.write_ci(config.CiSettings(os=("macos",)))) == ErrorCode.INVALID_ARGUMENT
    assert Module.find(module.root, github=module.repository.github).config.ci == settings  # 失敗したら変えない



def test_ci_review_workflow(tmp_path):
    """ci init --review：提出を Claude が見直すワークフローを本体が作る（型によらない）。設定は [ci] に残り、やめると消す。"""
    from ecobuild import ci_review
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    module.repository.create_task("見直し").start()
    commands = {"build": "make", "test": "make test"}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    path = module.root / ci_review.REVIEW_WORKFLOW
    assert module.write_ci().review_path is None and not path.exists()
    assert "Claude が見直し" not in module.agent_guide().text

    result = module.write_ci(config.CiSettings(review=True))
    workflow = path.read_text(encoding="utf-8")
    assert (result.review_path, result.review_secret, result.review_secret_missing) == (
        ci_review.REVIEW_WORKFLOW, "CLAUDE_CODE_OAUTH_TOKEN", True)
    assert "anthropics/claude-code-action@v1" in workflow and "claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}" in workflow
    assert "continue-on-error: true" in workflow and "github.event.pull_request.draft == false" in workflow
    assert "gh pr diff ${{ github.event.pull_request.number }}" in workflow and "REVIEW.md" in workflow
    assert "\t" not in workflow
    state = module.ci_state()
    assert (state.review, state.review_exists, state.review_current, state.review_secret) == (
        True, True, True, "CLAUDE_CODE_OAUTH_TOKEN")
    assert "Claude が見直し" in Module.find(module.root, github=module.repository.github).agent_guide().text

    module.repository.github.secrets["ANTHROPIC_API_KEY"] = "x"
    reloaded = Module.find(module.root, github=module.repository.github)
    result = reloaded.write_ci(config.CiSettings(review=True, review_auth="api-key"))
    assert (result.review_secret, result.review_secret_missing) == ("ANTHROPIC_API_KEY", False)
    assert "anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}" in path.read_text(encoding="utf-8")
    assert code_of(lambda: reloaded.write_ci(config.CiSettings(review=True, review_auth="x"))) == ErrorCode.INVALID_ARGUMENT

    path.write_text(path.read_text(encoding="utf-8") + "# 手で足した\n", encoding="utf-8")
    assert code_of(reloaded.write_ci) == ErrorCode.ALREADY_EXISTS
    assert not reloaded.ci_state().review_current
    assert reloaded.remove_ci().paths == (".github/workflows/ecobuild.yml", ci_review.REVIEW_WORKFLOW)
    reloaded.write_ci(force=True)   # [ci] の review は残っているので戻る
    assert path.is_file()
    result = reloaded.write_ci(config.CiSettings(review=False))
    assert result.removed == (ci_review.REVIEW_WORKFLOW,) and not path.exists()


def test_commands_per_os(tmp_path):
    """OSごとの表で書いたコマンドは、このOSのものを使う。CIはOSごとの手順になり、手元と同じシェルを使う。"""
    from ecobuild_generic.type import current_os
    module = Module.create("Plain", directory=tmp_path, type="generic", github=FakeGitHub(tmp_path / "gh"))
    module.repository.create_task("OSごと").start()
    other = "linux" if current_os() == "windows" else "windows"
    commands = {"build": {current_os(): python("print('here')"), other: "false"},
                "test": {other: "make test"}, "run": python("print('{arguments}')")}
    module._save_config(config.ModuleConfig(**{**module.config.__dict__, "extra": {"commands": commands}}))
    assert f'build = {{ "{current_os()}" = ' in (module.root / ".ecobuild" / "ecobuild.toml").read_text(encoding="utf-8")
    reloaded = Module.find(module.root, github=module.repository.github)
    assert reloaded.config.extra["commands"] == commands  # ecobuild.toml に書き戻せる

    assert reloaded.build().configuration == "Debug"
    with pytest.raises(EcoBuildError) as error:
        reloaded.test()  # このOSのコマンドがない
    assert error.value.code == ErrorCode.NOT_SUPPORTED and current_os() in error.value.message

    both = config.CiSettings(os=("linux", "windows"))
    assert code_of(lambda: reloaded.write_ci(both)) == ErrorCode.NOT_SUPPORTED  # test が片方のOSにない
    per_os = {**commands, "build": {"windows": "build.cmd {configuration}", "linux": "./build.sh {configuration}"},
              "test": "make test"}
    reloaded._save_config(config.ModuleConfig(**{**reloaded.config.__dict__, "extra": {"commands": per_os}}))
    workflow = (reloaded.root / reloaded.write_ci(both).path).read_text(encoding="utf-8")
    assert "if: runner.os == 'Windows'\n        shell: cmd\n        run: \"build.cmd ${{ matrix.configuration }}\"" in workflow
    assert "if: runner.os == 'Linux'\n        shell: sh\n        run: \"./build.sh ${{ matrix.configuration }}\"" in workflow
    assert workflow.count("make test") == 2  # すべてのOSで同じコマンドも、OSごとのシェルで実行する

    wrong = {**per_os, "build": {"win": "build.cmd"}}
    reloaded._save_config(config.ModuleConfig(**{**reloaded.config.__dict__, "extra": {"commands": wrong}}))
    with pytest.raises(EcoBuildError) as error:
        reloaded.build()
    assert error.value.code == ErrorCode.INVALID_CONFIG
