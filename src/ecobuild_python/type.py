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
from ecobuild.fsutil import remove_tree
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

# 管理するファイルの既定（ソース・設定・文書・コンテナ・Web の素材。.gitignore・.gitattributes は本体が常に含める）
TRACKED_PATTERNS = ("*.py", "*.pyi", "*.toml", "*.cfg", "*.ini", "*.txt", "*.md", "py.typed", "Dockerfile",
                    "*.html", "*.js", "*.css", "*.json")

# 足りないツールの導入コマンド（ecobuild setup --install）
INSTALL = {
    "nt": ("winget", "install", "--id", "Python.Python.3.12", "--exact", "--silent"),
    "posix": ("sudo", "apt-get", "install", "--yes", "python3-venv"),
}


@dataclass(frozen=True)
class PythonOptions:
    configuration: str = "Debug"


@dataclass(frozen=True)
class PythonRunResult(RunResult):
    """run の結果（output は今までどおり標準出力。stream で流したときは、ためないので空）。"""
    stdout: str = ""
    stderr: str = ""
    command: str = ""                    # 実行したコマンド（そのまま貼って使える形）
    arguments: tuple[str, ...] = ()      # プログラムに渡した引数（分けたもの）


class PythonType(ModuleType, Builds, HasFiles):
    name = "python"
    description = "Python。venv・pip・pytest でビルド・テスト・実行する"

    # モジュールの作成 -------------------------------------------------------------

    new_kinds = _scaffold.NEW_KINDS
    default_new_kind = "app"

    @classmethod
    def populate(cls, root: Path, config: ModuleConfig, kind: str | None, project: str | None = None, *,
                 test: bool = True) -> None:
        _scaffold.populate(root, config.name, kind or cls.default_new_kind, project, test=test)

    @classmethod
    def adopt(cls, root: Path, config: ModuleConfig) -> None:
        """ビルド・テストには pyproject.toml が要る（中身はリポジトリのものを使う。何も置かない）。"""
        if not (root / _python.PYPROJECT).is_file():
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{_python.PYPROJECT} がないので、型 python のモジュールにできません。",
                                hint="ルートに pyproject.toml を置いてコミットするか、ほかの型（--type generic 等）を選んでください。")

    @classmethod
    def gitignore(cls) -> str:
        return GITIGNORE

    @classmethod
    def tracked_patterns(cls) -> tuple[str, ...]:
        return TRACKED_PATTERNS

    @classmethod
    def readme_usage(cls, config: ModuleConfig) -> str:
        return """## 開発

Python 3.11以上で、次のようにインストール・テストできます。

Windows：

```bat
py -m venv .venv
.venv\\Scripts\\python -m pip install --editable ".[dev]"
.venv\\Scripts\\python -m pytest
```

Linux・macOS（`python` がなければ `python3`）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --editable ".[dev]"
.venv/bin/python -m pytest
```
"""

    @classmethod
    def ecobuild_usage(cls, config: ModuleConfig) -> str:
        return """## 型 python

- `ecobuild build` が `.venv` を作り、`pip install --editable ".[dev]"` で入れます（`pyproject.toml` が変わったときだけ）。
  `--configuration Release` なら配布用のパッケージ（wheel・sdist）も `dist/` に作ります。
- `ecobuild test` は pytest で全部を流します。絞るときは `ecobuild test tests/test_x.py tests/y.py::test_a`、
  `--filter "式"`（pytest の -k）、`--last-failed`（前回失敗したものだけ）。
- `ecobuild run -- <引数…>` は `pyproject.toml` の `[project.scripts]` の最初のコマンドを `.venv` で実行します。
- venv・pip・pytest を直接使う手順はルートの `README.md` にあります（ECOBuild なしで使うとき）。
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
            "# 変えるときは ecobuild ci init の --os・--configuration・--branches（設定は .ecobuild/ecobuild.toml の [ci]）と、",
            "# [python] の versions（Pythonの版）。Release の構成ではパッケージ（wheel・sdist）も作る。",
            "name: build", "", *ci_workflow.trigger(config), "",
            "jobs:", "  build:", "    strategy:", "      fail-fast: false", "      matrix:",
            f"        os: {ci_workflow.runners(ci, ('linux',))}",
            f"        configuration: {ci_workflow.yaml_list(ci.configurations)}",
            f"        python: {ci_workflow.yaml_list(versions)}",
            "    runs-on: ${{ matrix.os }}", "    steps:", "      - uses: actions/checkout@v4",
            "      - uses: actions/setup-python@v5", "        with:", "          python-version: ${{ matrix.python }}",
            "      - name: Install", '        run: python -m pip install --editable ".[dev]"',
            # pytest-xdist が入っていれば並べて流す（ひな形の dev に入る。前に作ったモジュールにはないこともある）
            "      - name: Test", "        shell: bash",
            '        run: if python -c "import xdist" 2>/dev/null; then python -m pytest -n auto; else python -m pytest; fi',
        ]
        if release:
            lines += ["      - name: Package", "        if: matrix.configuration == 'Release'",
                      "        run: python -m pip install build && python -m build"]
        return "\n".join(lines) + "\n"

    # このPCの準備 -------------------------------------------------------------------

    @classmethod
    def build_outputs(cls) -> tuple[str, ...]:
        return (".venv", "build", "dist")   # 仮想環境（中の Python のもの）・配布の出力

    @classmethod
    def tool_settings(cls) -> dict[str, str]:
        return {"python": "モジュールの .venv を作る Python のパス（このPCだけ。既定は ECOBuild と同じ Python）"}

    @classmethod
    def doctor_items(cls):
        from ecobuild.results import DoctorItem
        try:
            import ensurepip, venv  # noqa: E401,F401
            ok, detail = True, "venv・pip を使えます"
        except ImportError as error:
            ok, detail = False, f"venv か ensurepip がありません（{error}）"
        return [DoctorItem("Python の venv", ok, True, detail,
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
        _no_project(project)
        if action in ("clean", "rebuild"):
            _python.clean(self.root)
        if action == "clean":
            return BuildResult(None, options.configuration, (), None, action)
        python = self._environment(force=action == "rebuild")
        artifacts = _python.build_distribution(self.root, python) if options.configuration == "Release" else ()
        return BuildResult(None, options.configuration, artifacts, None, action)

    def test(self, project: str | None, options: PythonOptions, tests: tuple[str, ...] = (), *,
             filter: str | None = None, last_failed: bool = False) -> TestResult:
        """tests：pytest に渡すファイル・フォルダ・テスト（tests/x.py::test_a）。空なら全部。
        filter：pytest の -k の式。last_failed：前回失敗したものだけ（check は使わず、いつも全部）。
        cases はテストごとの nodeid・状態・理由・時間（_python.PythonTestCase）。"""
        _no_project(project)
        cases = _python.run_tests(self.root, self._environment(), tests, filter=filter, last_failed=last_failed)
        count = lambda status: sum(1 for c in cases if c.status == status)  # noqa: E731
        return TestResult(None, options.configuration, count("passed"), count("failed"), count("skipped"),
                          tuple(cases))

    def run(self, project: str | None, options: PythonOptions, arguments: str) -> RunResult:
        """arguments：1つの文字列（_python.split_arguments で分ける）。出力はためて返す（stdin は渡さない）。"""
        _no_project(project)
        return self.run_program(options, _python.split_arguments(arguments))

    def run_program(self, options: PythonOptions, arguments: list[str], *, stream: bool = False,
                    stdin: str | None = None, echo: bool = False, on_start=None) -> "PythonRunResult":
        """分けた引数で実行する（ecobuild run が使う。stream・stdin・echo・on_start は _python.run_script のとおり）。"""
        script = _python.script_name(self.root)
        if script is None:
            raise EcoBuildError(ErrorCode.NOT_SUPPORTED, "実行できるものがありません（pyproject.toml の [project.scripts]）。",
                                hint="module new の --kind app で作るか、[project.scripts] にコマンドを書いてください"
                                     "（タスクブランチでコミットします）。")
        self._environment()
        completed = _python.run_script(self.root, script, list(arguments), stream=stream, stdin=stdin, echo=echo,
                                       on_start=on_start)
        return PythonRunResult(None, options.configuration, completed.returncode, completed.stdout, completed.stdout,
                               completed.stderr, _python.command_text(completed.args), tuple(arguments))

    def _environment(self, *, force: bool = False) -> Path:
        from ecobuild import settings
        return _python.ensure_environment(self.root, _python.base_python(settings.load_config().get("python")),
                                          force=force)

    # ファイル ---------------------------------------------------------------------

    def add_file(self, path: Path, *, test: bool, template: str | None = None) -> FilesChanged:
        """src/<パッケージ>/ のソースなら、tests/ の同じ構成の場所にテストも足す。tests/ の中ならテストだけ。"""
        if template is not None:
            raise self.not_supported("ファイルテンプレート")
        relative = self._relative(path)
        parts = relative.parts
        if self._exists(relative):
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{relative.as_posix()} は既にあります。")
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
        for item in list(removed):
            removed += self._tidy(item.parent)
        return FilesChanged("file remove", tuple(p.as_posix() for p in removed))

    def _tidy(self, folder: Path) -> list[Path]:
        """消して空になったフォルダーを片付ける（file add が作る空の __init__.py だけが残ったものも）。
        src/<パッケージ>/・tests/ そのものは残す。消した __init__.py を返す。"""
        removed = []
        while len(folder.parts) > 2 or (folder.parts[0] == "tests" and len(folder.parts) > 1):
            path = self.root / folder
            if not path.is_dir():
                break
            rest = [p for p in path.iterdir() if p.name != "__pycache__"]
            init = path / "__init__.py"
            if rest == [init] and init.stat().st_size == 0:
                init.unlink()
                removed.append(folder / "__init__.py")
            elif rest:
                break
            remove_tree(path)   # 中身は __pycache__ だけ
            folder = folder.parent
        return removed

    def move_file(self, source: Path, destination: Path, *, test: bool) -> FilesChanged:
        origin, target = self._relative(source), self._relative(destination)
        if not self._exists(origin):
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{origin.as_posix()} はありません。")
        if self._exists(target):
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{target.as_posix()} は既にあります。")
        if target.parts[0] == "src":
            self._packages(target)   # 新しいパッケージの __init__.py（*.py なので commit に含まれる）
        self._move(origin, target)
        moved = [origin, target]     # 移動元・移動先の組（cpp と同じ形。CLI が「a → b」で表示する）
        mirror, mirror_target = _mirror(origin), _mirror(target)
        if test and mirror and mirror_target and self._exists(mirror) and not self._exists(mirror_target):
            self._move(mirror, mirror_target)
            self._retarget_import(mirror_target, origin, target)
            moved += [mirror, mirror_target]
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

    def _retarget_import(self, test: Path, origin: Path, target: Path) -> None:
        """動かしたテストの import（file add が書いた形）を、移動先のモジュールに向ける。名前が変わったら、
        テストの中の名前はそのまま使えるように as で元の名前にする。"""
        path = self.root / test
        old, new = _import_line(origin), _import_line(target)
        if origin.stem != target.stem:
            new += f" as {origin.stem}"
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        lines = [new + "\n" if line.rstrip() == old else line for line in lines]
        path.write_text("".join(lines), encoding="utf-8", newline="\n")

    def _packages(self, relative: Path) -> list[Path]:
        """src/ の中の、まだ __init__.py がないパッケージのフォルダーに作る（setuptools の packages.find が見つけるのに
        要る）。hatchling 等（ひな形）は __init__.py のないフォルダーも入れるので作らない。"""
        if not _python.needs_init(self.root):
            return []
        created = []
        for depth in range(2, len(relative.parts)):
            init = Path(*relative.parts[:depth]) / "__init__.py"
            if not self._exists(init) and init != relative:
                self._write(init, "")
                created.append(init)
        return created


_TEST_TEXT = "def test_todo():\n    assert True\n"


def _no_project(project: str | None) -> None:
    """Project を持たないので、指定されたら黙って全体にせず止める（run の引数の書き間違いにも気づける）。"""
    if project:
        raise EcoBuildError(ErrorCode.NOT_SUPPORTED, f"型 python には Project がありません（{project} を指定しました）。",
                            hint="build・test・run はモジュール全体が対象です。run の引数は ecobuild run -- <引数…> で渡します。")


def _mirror(relative: Path) -> Path | None:
    """src/<パッケージ>/a/b.py に対応するテスト tests/a/test_b.py（ソースでなければ None）。"""
    parts = relative.parts
    if parts[0] != "src" or relative.suffix != ".py" or relative.stem in ("__init__", "__main__"):
        return None
    return Path("tests", *parts[2:-1], f"test_{relative.stem}.py")


def _module_text(relative: Path) -> str:
    return "" if relative.suffix != ".py" else f'"""{relative.stem}。"""\n'


def _import_line(relative: Path) -> str:
    return f"from {'.'.join(relative.parts[1:-1])} import {relative.stem}"


def _test_text(relative: Path) -> str:
    return f"{_import_line(relative)}\n\n\ndef test_{relative.stem}():\n    assert {relative.stem} is not None\n"


def _versions(config: ModuleConfig) -> tuple[str, ...]:
    value = config.extra.get(TABLE, {}).get("versions", list(DEFAULT_VERSIONS))
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"[{TABLE}] の versions は文字列の配列です（例：versions = [\"3.12\"]）。")
    return tuple(value)
