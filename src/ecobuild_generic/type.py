"""型 generic：[commands] に書いたコマンドで、ビルド・テスト・実行・クリーンを行う。

{configuration}（構成）・{arguments}（run の引数）を、コマンドの中に書ける。
書いていない操作は not_supported。Project・ファイル・依存先の管理は持たない。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ecobuild.config import CI_RUNNERS, ModuleConfig, Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module_type import ModuleType
from ecobuild.results import BuildResult, RunResult, TestCaseResult, TestResult

TABLE = "commands"
OPERATIONS = ("build", "test", "run", "clean")


@dataclass(frozen=True)
class GenericOptions:
    configuration: str = "Debug"


class GenericType(ModuleType):
    name = "generic"
    description = "ビルド・テスト・実行のコマンドを ecobuild.toml の [commands] に書く（言語を問わない）"

    @classmethod
    def new_config(cls, name: str, *, app: bool) -> ModuleConfig:
        if app:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--app は型 generic では使えません。",
                                hint="実行のコマンドは ecobuild.toml の [commands] の run に書きます。")
        # 空のコマンドは「まだ書いていない」（その操作は not_supported）
        return ModuleConfig(name=name, projects=None, type=cls.name,
                            extra={TABLE: {operation: "" for operation in OPERATIONS}})

    @classmethod
    def readme_usage(cls, config: ModuleConfig) -> str:
        return """## コマンド

ビルド・テスト・実行は `ecobuild.toml` の `[commands]` に書いたコマンドで行います（`{configuration}` に構成が入ります）。
"""

    @classmethod
    def ci_workflow(cls, config: ModuleConfig) -> str | None:
        ci = config.ci
        if ci.shared:
            raise EcoBuildError(ErrorCode.NOT_SUPPORTED, "型 generic のCIは --shared に対応していません。")
        commands = config.extra.get(TABLE, {})
        steps = [(label, commands.get(key, "")) for key, label in (("build", "Build"), ("test", "Test"))]
        steps = [(label, command.replace("{configuration}", "${{ matrix.configuration }}"))
                 for label, command in steps if command]
        if not steps:
            return None
        runners = ", ".join(CI_RUNNERS[name] for name in (ci.os or ("linux",)))
        lines = [
            "# ECOBuild（ecobuild ci init）が作成：ecobuild.toml の [commands] の build・test を実行する。",
            "# 変えるときは ecobuild ci init の --os・--configuration（設定は ecobuild.toml の [ci]）。",
            "name: build", "", "on:", "  push:", f"    branches: [{config.default_base}]", "  pull_request:",
            "  workflow_dispatch:      # ecobuild ci run（手動での実行）", "",
            "jobs:", "  build:", "    strategy:", "      fail-fast: false", "      matrix:",
            f"        os: [{runners}]", f"        configuration: [{', '.join(ci.configurations)}]",
            "    runs-on: ${{ matrix.os }}", "    steps:", "      - uses: actions/checkout@v4",
        ]
        for label, command in steps:
            lines += [f"      - name: {label}", f"        run: {command}"]
        return "\n".join(lines) + "\n"

    # ビルド ---------------------------------------------------------------------

    def validate_profile(self, profile: Profile) -> None:
        """構成はコマンドの {configuration} に入るだけなので、名前の形だけ確かめる。"""
        if not profile.configuration:
            raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, "構成を指定してください。")

    def build_options(self, profile: Profile | None, configuration: str) -> GenericOptions:
        return GenericOptions(configuration or (profile.configuration if profile else "Debug"))

    def build(self, project: str | None, options: GenericOptions, action: str) -> BuildResult:
        if action == "rebuild":
            if self._command("clean", required=False):
                self._execute("clean", options, ErrorCode.BUILD_FAILED, "クリーンに失敗しました。")
            action_to_run = "build"
        else:
            action_to_run = action
        message = "クリーンに失敗しました。" if action == "clean" else "ビルドに失敗しました。"
        self._execute(action_to_run, options, ErrorCode.BUILD_FAILED, message)
        return BuildResult(None, options.configuration, (), None, action)

    def test(self, project: str | None, options: GenericOptions) -> TestResult:
        self._execute("test", options, ErrorCode.TEST_FAILED, "テストに失敗しました。")
        # 個々のテストの結果はコマンドの出力にある。ここではコマンド全体を1件として数える
        return TestResult(None, options.configuration, 1, 0, 0, (TestCaseResult("test", "passed"),))

    def run(self, project: str | None, options: GenericOptions, arguments: str) -> RunResult:
        completed = self._execute("run", options, ErrorCode.RUN_FAILED, "実行に失敗しました。", arguments=arguments)
        return RunResult(None, options.configuration, completed.returncode, completed.stdout)

    # 内部 ---------------------------------------------------------------------------

    def _command(self, operation: str, *, required: bool = True) -> str:
        command = self.module.config.extra.get(TABLE, {}).get(operation, "")
        if not command and required:
            raise EcoBuildError(ErrorCode.NOT_SUPPORTED, f"{operation} のコマンドがありません。",
                                hint=f"ecobuild.toml の [{TABLE}] に {operation} = \"<コマンド>\" を書いてください"
                                     "（作業空間でコミットします）。")
        return command

    def _execute(self, operation: str, options: GenericOptions, code: str, message: str, *,
                 arguments: str = "") -> subprocess.CompletedProcess:
        command = self._command(operation).replace("{configuration}", options.configuration) \
            .replace("{arguments}", arguments)
        completed = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
            raise EcoBuildError(code, f"{message}（{operation}：終了コード {completed.returncode}）",
                                details={"command": command, "returncode": completed.returncode, "output": output})
        return completed
