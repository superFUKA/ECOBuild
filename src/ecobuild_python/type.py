"""型 python：venv・pip・pytest で、ビルド・テスト・実行・ファイルの追加を行う。

環境はモジュール直下の .venv。構成は Python に本来ない概念なので、Debug＝開発用（editable install）、
Release＝配布用（さらに wheel と sdist を dist/ に作る）に当てはめる。Project・依存先の管理は持たない
（依存先は今後。持たない能力の操作は Module が not_supported で止める）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ecobuild import ci_workflow
from ecobuild.config import ModuleConfig, Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module_type import Builds, HasFiles, ModuleType
from ecobuild.results import BuildResult, FilesChanged, RunResult, TestResult

from . import _python, _scaffold

TABLE = "python"
DEFAULT_VERSIONS = ("3.12",)

GITIGNORE = """\
# 仮想環境・Pythonの中間ファイル・成果物
.venv/
__pycache__/
*.py[cod]
*.egg-info/
/build/
/dist/
.pytest_cache/
"""

# 管理するファイルの既定（ソース・設定・文書）
TRACKED_PATTERNS = ("*.py", "*.pyi", "*.toml", "*.cfg", "*.ini", "*.txt", "*.md", "py.typed")

# 足りないツールの導入コマンド（ecobuild setup --install）
INSTALL = {
    "nt": ("winget", "install", "--id", "Python.Python.3.12", "--exact", "--silent"),
    "posix": ("sudo", "apt-get", "install", "--yes", "python3-venv"),
}


@dataclass(frozen=True)
class PythonOptions:
    configuration: str = "Debug"


class PythonType(ModuleType, Builds, HasFiles):
    name = "python"
    description = "Python。venv・pip・pytest でビルド・テスト・実行する"

    # モジュールの作成 -------------------------------------------------------------

    new_kinds = _scaffold.NEW_KINDS
    default_new_kind = "app"

    @classmethod
    def populate(cls, root: Path, config: ModuleConfig, kind: str | None, project: str | None = None) -> None:
        _scaffold.populate(root, config.name, kind or cls.default_new_kind, project)

    @classmethod
    def gitignore(cls) -> str:
        return GITIGNORE

    @classmethod
    def tracked_patterns(cls) -> tuple[str, ...]:
        return TRACKED_PATTERNS

    @classmethod
    def readme_usage(cls, config: ModuleConfig) -> str:
        return """## ECOBuildなしで使う

Python 3.11以上があれば、cloneしたまま使えます。

```sh
python -m venv .venv
.venv/bin/python -m pip install --editable ".[dev]"   # Windows：.venv\\Scripts\\python
.venv/bin/python -m pytest
```
"""

    @classmethod
    def ci_workflow(cls, config: ModuleConfig) -> str:
        ci = config.ci
        if ci.shared:
            raise EcoBuildError(ErrorCode.NOT_SUPPORTED, "型 python のCIは --shared に対応していません。")
        versions = _versions(config)
        release = "Release" in ci.configurations
        lines = [
            "# ECOBuild（ecobuild ci init）が作成：ECOBuildなしで、pip と pytest だけでインストール・テストする。",
            "# 変えるときは ecobuild ci init の --os・--configuration・--branches（設定は ecobuild.toml の [ci]）と、",
            "# [python] の versions（Pythonの版）。Release の構成ではパッケージ（wheel・sdist）も作る。",
            "name: build", "", *ci_workflow.trigger(config), "",
            "jobs:", "  build:", "    strategy:", "      fail-fast: false", "      matrix:",
            f"        os: {ci_workflow.runners(ci, ('linux',))}",
            f"        configuration: {ci_workflow.yaml_list(ci.configurations)}",
            f"        python: {ci_workflow.yaml_list(versions)}",
            "    runs-on: ${{ matrix.os }}", "    steps:", "      - uses: actions/checkout@v4",
            "      - uses: actions/setup-python@v5", "        with:", "          python-version: ${{ matrix.python }}",
            "      - name: Install", '        run: python -m pip install --editable ".[dev]"',
            "      - name: Test", "        run: python -m pytest",
        ]
        if release:
            lines += ["      - name: Package", "        if: matrix.configuration == 'Release'",
                      "        run: python -m pip install build && python -m build"]
        return "\n".join(lines) + "\n"

    # このPCの準備 -------------------------------------------------------------------

    @classmethod
    def tool_settings(cls) -> dict[str, str]:
        return {"python": "モジュールの .venv を作る Python のパス（このPCだけ。既定は ECOBuild と同じ Python）"}

    @classmethod
    def doctor_items(cls):
        from ecobuild.tooling import CheckItem
        try:
            import ensurepip, venv  # noqa: E401,F401
            ok, detail = True, "venv・pip を使えます"
        except ImportError as error:
            ok, detail = False, f"venv か ensurepip がありません（{error}）"
        return [CheckItem("Python の venv", ok, True, detail,
                          "Python の venv が必要です（Linux：python3-venv）。", "install",
                          INSTALL["nt" if os.name == "nt" else "posix"])]

    # ビルド ---------------------------------------------------------------------

    def validate_profile(self, profile: Profile) -> None:
        if profile.configuration not in _python.CONFIGURATIONS:
            raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, f"構成 {profile.configuration} はありません。",
                                hint=f"{'・'.join(_python.CONFIGURATIONS)} のどちらかを指定してください"
                                     "（Release は配布用のパッケージも作ります）。")
        if profile.options or profile.projects or profile.shared:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "型 python では、構成と並列数以外のビルド設定は使えません。")
        if profile.parallel < 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "並列数は1以上にしてください。")

    def build_options(self, profile: Profile | None, configuration: str) -> PythonOptions:
        chosen = configuration or (profile.configuration if profile else "Debug")
        if chosen not in _python.CONFIGURATIONS:
            raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, f"構成 {chosen} はありません。",
                                hint=f"{'・'.join(_python.CONFIGURATIONS)} のどちらかを指定してください。")
        return PythonOptions(chosen)

    def build(self, project: str | None, options: PythonOptions, action: str) -> BuildResult:
        if action in ("clean", "rebuild"):
            _python.clean(self.root)
        if action == "clean":
            return BuildResult(None, options.configuration, (), None, action)
        python = self._environment(force=action == "rebuild")
        artifacts = _python.build_distribution(self.root, python) if options.configuration == "Release" else ()
        return BuildResult(None, options.configuration, artifacts, None, action)

    def test(self, project: str | None, options: PythonOptions) -> TestResult:
        cases = _python.run_tests(self.root, self._environment())
        count = lambda status: sum(1 for c in cases if c.status == status)  # noqa: E731
        return TestResult(None, options.configuration, count("passed"), count("failed"), count("skipped"),
                          tuple(cases))

    def run(self, project: str | None, options: PythonOptions, arguments: str) -> RunResult:
        script = _python.script_name(self.root)
        if script is None:
            raise EcoBuildError(ErrorCode.NOT_SUPPORTED, "実行できるものがありません（pyproject.toml の [project.scripts]）。",
                                hint="module new の --kind app で作るか、[project.scripts] にコマンドを書いてください"
                                     "（作業空間でコミットします）。")
        self._environment()
        completed = _python.run_script(self.root, script, arguments)
        return RunResult(None, options.configuration, completed.returncode, completed.stdout)

    def _environment(self, *, force: bool = False) -> Path:
        from ecobuild import tooling
        return _python.ensure_environment(self.root, _python.base_python(tooling.load_config().get("python")),
                                          force=force)

    # ファイル ---------------------------------------------------------------------

    def add_file(self, path: Path, *, test: bool, template: str | None = None) -> FilesChanged:
        """src/<パッケージ>/ のソースなら、tests/ の同じ構成の場所にテストも足す。tests/ の中ならテストだけ。"""
        if template is not None:
            raise self.not_supported("ファイルテンプレート")
        relative = self._relative(path)
        parts = relative.parts
        if self._exists(relative):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{relative.as_posix()} は既にあります。")
        added = []
        if parts[0] == "src":
            added += self._packages(relative)
            self._write(relative, _module_text(relative))
            added.append(relative)
            mirror = _mirror(relative)
            if test and mirror is not None and not self._exists(mirror):
                self._write(mirror, _test_text(relative))
                added.append(mirror)
        else:
            self._write(relative, _TEST_TEXT if relative.suffix == ".py" else "")
            added.append(relative)
        return FilesChanged("file add", tuple(p.as_posix() for p in added))

    def remove_file(self, path: Path, *, test: bool) -> FilesChanged:
        relative = self._relative(path)
        if not self._exists(relative):
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{relative.as_posix()} はありません。")
        removed = [relative]
        mirror = _mirror(relative)
        if test and mirror is not None and self._exists(mirror):
            removed.append(mirror)
        for item in removed:
            (self.root / item).unlink()
        return FilesChanged("file remove", tuple(p.as_posix() for p in removed))

    def move_file(self, source: Path, destination: Path, *, test: bool) -> FilesChanged:
        origin, target = self._relative(source), self._relative(destination)
        if not self._exists(origin):
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{origin.as_posix()} はありません。")
        if self._exists(target):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{target.as_posix()} は既にあります。")
        moved = []
        if target.parts[0] == "src":
            moved += self._packages(target)
        self._move(origin, target)
        moved.append(target)
        mirror, mirror_target = _mirror(origin), _mirror(target)
        if test and mirror and mirror_target and self._exists(mirror) and not self._exists(mirror_target):
            self._move(mirror, mirror_target)
            moved.append(mirror_target)
        return FilesChanged("file move", tuple(p.as_posix() for p in moved))

    def _relative(self, path: Path) -> Path:
        """今いるディレクトリからの相対か絶対のパスを、モジュールからの相対にする。src/ か tests/ の中だけ。"""
        absolute = (Path.cwd() / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        try:
            relative = absolute.relative_to(self.root.resolve())
        except ValueError:
            raise EcoBuildError(ErrorCode.NOT_IN_MODULE, f"{path} はモジュールの外です。") from None
        if len(relative.parts) < 2 or relative.parts[0] not in ("src", "tests") or (
                relative.parts[0] == "src" and len(relative.parts) < 3):
            raise EcoBuildError(ErrorCode.NOT_IN_SOURCE_DIRECTORY,
                                f"{relative.as_posix()} は、パッケージ（src/<パッケージ>/）かテスト（tests/）の外です。",
                                hint="パッケージに入らないファイルは、ビルドにもテストにも入りません。")
        return relative

    def _exists(self, relative: Path) -> bool:
        return (self.root / relative).is_file()

    def _write(self, relative: Path, text: str) -> None:
        _scaffold.write(self.root / relative, text)

    def _move(self, origin: Path, target: Path) -> None:
        (self.root / target).parent.mkdir(parents=True, exist_ok=True)
        (self.root / origin).rename(self.root / target)

    def _packages(self, relative: Path) -> list[Path]:
        """src/ の中の、まだ __init__.py がないパッケージのフォルダーに作る（setuptools が見つけるのに要る）。"""
        created = []
        for depth in range(2, len(relative.parts)):
            init = Path(*relative.parts[:depth]) / "__init__.py"
            if not self._exists(init) and init != relative:
                self._write(init, "")
                created.append(init)
        return created


_TEST_TEXT = "def test_todo():\n    assert True\n"


def _mirror(relative: Path) -> Path | None:
    """src/<パッケージ>/a/b.py に対応するテスト tests/a/test_b.py（ソースでなければ None）。"""
    parts = relative.parts
    if parts[0] != "src" or relative.suffix != ".py" or relative.stem in ("__init__", "__main__"):
        return None
    return Path("tests", *parts[2:-1], f"test_{relative.stem}.py")


def _module_text(relative: Path) -> str:
    return "" if relative.suffix != ".py" else f'"""{relative.stem}。"""\n'


def _test_text(relative: Path) -> str:
    parts = relative.parts
    package = ".".join(parts[1:-1])
    return f"from {package} import {relative.stem}\n\n\ndef test_{relative.stem}():\n    assert {relative.stem} is not None\n"


def _versions(config: ModuleConfig) -> tuple[str, ...]:
    value = config.extra.get(TABLE, {}).get("versions", list(DEFAULT_VERSIONS))
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"[{TABLE}] の versions は文字列の配列です（例：versions = [\"3.12\"]）。")
    return tuple(value)
