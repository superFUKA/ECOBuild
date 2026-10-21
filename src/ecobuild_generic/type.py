"""型 generic：[commands] に書いたコマンドで、ビルド・テスト・実行・クリーンを行う。

{configuration}（構成）・{arguments}（run の引数）を、コマンドの中に書ける。
コマンドはすべてのOSで同じ文字列か、OSごとの表（{ windows = "...", linux = "..." }）で書く。
Windows では cmd.exe、それ以外では sh で実行する（CIでも同じシェルを使う）。
書いていない操作は not_supported。ファイルは空で作る・移す・消すだけ（file add・move・remove）。Project・依存先の管理は持たない。
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ecobuild import ci_workflow
from ecobuild.config import ModuleConfig, Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module_type import Builds, HasFiles, ModuleType
from ecobuild.results import BuildResult, FilesChanged, RunResult, TestCaseResult, TestResult

TABLE = "commands"
OPERATIONS = ("build", "test", "run", "clean")
OS_NAMES = ("windows", "linux", "macos")
# CIのOS → GitHub Actions の runner.os と、手元と同じシェル
CI_OS = {"windows": ("Windows", "cmd"), "linux": ("Linux", "sh")}


def current_os() -> str:
    if os.name == "nt":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def command_for(commands: dict, operation: str, os_name: str) -> str:
    """そのOSで operation に使うコマンド（書いていなければ空）。"""
    value = commands.get(operation, "")
    if not isinstance(value, dict):
        return value
    unknown = [name for name in value if name not in OS_NAMES]
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"[{TABLE}] の {operation} に、OS {'、'.join(unknown)} はありません。",
                            hint=f"{'・'.join(OS_NAMES)} から選んでください。")
    return value.get(os_name, "")


@dataclass(frozen=True)
class GenericOptions:
    configuration: str = "Debug"


class GenericType(ModuleType, Builds, HasFiles):
    name = "generic"
    description = "ビルド・テスト・実行のコマンドを .ecobuild/ecobuild.toml の [commands] に書く（言語を問わない）"

    @classmethod
    def new_config(cls, name: str) -> ModuleConfig:
        # 空のコマンドは「まだ書いていない」（その操作は not_supported）
        return ModuleConfig(name=name, projects=None, type=cls.name,
                            extra={TABLE: {operation: "" for operation in OPERATIONS}})

    @classmethod
    def ecobuild_usage(cls, config: ModuleConfig) -> str:
        return """## コマンド

ビルド・テスト・実行は `.ecobuild/ecobuild.toml` の `[commands]` に書いたコマンドで行います（`{configuration}` に構成、
`run` では `{arguments}` に引数が入ります）。Windows では cmd.exe、Linux では sh で実行します（CIでも同じ）。
OSごとに変えるときは、OSごとの表で書きます：

```toml
[commands]
build = "python build.py {configuration}"
test = { windows = "test.cmd", linux = "./test.sh" }
```
"""

    @classmethod
    def ci_workflow(cls, config: ModuleConfig) -> str | None:
        ci = config.ci
        if ci.shared:
            raise EcoBuildError(ErrorCode.NOT_SUPPORTED, "型 generic のCIは --shared に対応していません。")
        commands = config.extra.get(TABLE, {})
        systems = ci.os or ("linux",)
        steps = []
        for key, label in (("build", "Build"), ("test", "Test")):
            found = {name: command_for(commands, key, name) for name in systems}
            if not any(found.values()):
                continue
            missing = [name for name, command in found.items() if not command]
            if missing:
                raise EcoBuildError(ErrorCode.NOT_SUPPORTED, f"{key} のコマンドが {'、'.join(missing)} にありません。",
                                    hint=f".ecobuild/ecobuild.toml の [{TABLE}] の {key} に書くか、ecobuild ci init の --os から"
                                         "外してください。")
            for name, command in found.items():
                runner_os, shell = CI_OS[name]
                steps.append((f"{label} ({name})" if len(systems) > 1 else label,
                              f"runner.os == '{runner_os}'" if len(systems) > 1 else "", shell,
                              command.replace("{configuration}", "${{ matrix.configuration }}")))
        if not steps:
            return None
        lines = [
            "# ECOBuild（ecobuild ci init）が作成：.ecobuild/ecobuild.toml の [commands] の build・test を実行する。",
            "# 変えるときは ecobuild ci init の --os・--configuration・--branches（設定は .ecobuild/ecobuild.toml の [ci]）。",
            "name: build", "", *ci_workflow.trigger(config), "",
            "jobs:", "  build:", "    strategy:", "      fail-fast: false", "      matrix:",
            f"        os: {ci_workflow.runners(ci, ('linux',))}",
            f"        configuration: {ci_workflow.yaml_list(ci.configurations)}",
            "    runs-on: ${{ matrix.os }}", "    steps:", "      - uses: actions/checkout@v4",
        ]
        for label, condition, shell, command in steps:
            lines.append(f"      - name: {ci_workflow.yaml_text(label)}")
            if condition:
                lines.append(f"        if: {condition}")
            lines += [f"        shell: {shell}", f"        run: {ci_workflow.yaml_text(command)}"]
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

    def test(self, project: str | None, options: GenericOptions, tests: tuple[str, ...] = ()) -> TestResult:
        if tests:
            raise self.not_supported("テストの絞り込み")
        self._execute("test", options, ErrorCode.TEST_FAILED, "テストに失敗しました。")
        # 個々のテストの結果はコマンドの出力にある。ここではコマンド全体を1件として数える
        return TestResult(None, options.configuration, 1, 0, 0, (TestCaseResult("test", "passed"),))

    def run(self, project: str | None, options: GenericOptions, arguments: str) -> RunResult:
        completed = self._execute("run", options, ErrorCode.RUN_FAILED, "実行に失敗しました。", arguments=arguments)
        return RunResult(None, options.configuration, completed.returncode, completed.stdout)

    # ファイル -------------------------------------------------------------------------

    def add_file(self, path: Path, *, test: bool, template: str | None = None) -> FilesChanged:
        """書いた名前（拡張子込み）の空のファイルを作る。テストは作らない。"""
        if template is not None:
            raise self.not_supported("ファイルテンプレート")
        relative = self._relative(path)
        if (self.root / relative).exists():
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{relative.as_posix()} は既にあります。")
        (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
        (self.root / relative).write_bytes(b"")
        return FilesChanged("file add", (relative.as_posix(),))

    def remove_file(self, path: Path, *, test: bool) -> FilesChanged:
        relative = self._existing(path)
        (self.root / relative).unlink()
        return FilesChanged("file remove", (relative.as_posix(),))

    def move_file(self, source: Path, destination: Path, *, test: bool) -> FilesChanged:
        origin, target = self._existing(source), self._relative(destination)
        if (self.root / target).exists():
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{target.as_posix()} は既にあります。")
        (self.root / target).parent.mkdir(parents=True, exist_ok=True)
        (self.root / origin).rename(self.root / target)
        return FilesChanged("file move", (origin.as_posix(), target.as_posix()))

    # 内部 ---------------------------------------------------------------------------

    def _relative(self, path: Path) -> Path:
        """今いるディレクトリからの相対か絶対のパスを、モジュールからの相対にする（.git・.ecobuild の中は不可）。"""
        absolute = (Path.cwd() / path).resolve()
        try:
            relative = absolute.relative_to(self.root.resolve())
        except ValueError:
            raise EcoBuildError(ErrorCode.NOT_IN_MODULE, f"{path} はモジュールの外です。") from None
        if not relative.parts or relative.parts[0] in (".git", ".ecobuild"):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{relative.as_posix()} のファイルは操作できません。")
        return relative

    def _existing(self, path: Path) -> Path:
        relative = self._relative(path)
        if not (self.root / relative).is_file():
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{relative.as_posix()} はありません。")
        return relative

    def _command(self, operation: str, *, required: bool = True) -> str:
        commands = self.module.config.extra.get(TABLE, {})
        system = current_os()
        command = command_for(commands, operation, system)
        if not command and required:
            per_os = isinstance(commands.get(operation), dict)
            raise EcoBuildError(ErrorCode.NOT_SUPPORTED,
                                f"{operation} の {system} のコマンドがありません。" if per_os
                                else f"{operation} のコマンドがありません。",
                                hint=f".ecobuild/ecobuild.toml の [{TABLE}] に {operation} = \"<コマンド>\"（すべてのOS）か "
                                     f"{operation} = {{ {system} = \"<コマンド>\" }}（OSごと）を書いてください"
                                     "（タスクブランチでコミットします）。")
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
