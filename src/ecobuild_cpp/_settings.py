"""モジュール（CppBuildのSolution）とProjectの、保存する設定（.cppbuild の管理ファイル。コミットする）。

ビルドのたびに渡す設定（構成・生成器・C++の規格等）は名前付きビルド設定（ecobuild.toml の [profiles]）にあり、
_cppbuild.BuildOptions で渡す。ここは CppBuild が保存する設定だけを扱う。
"""

from __future__ import annotations

import re
from pathlib import Path

from cppbuild import ProjectType, Solution
from cppbuild.models import CMakePackage, CMakeSource, Dependency, ImportedLibrary

from ecobuild.errors import EcoBuildError, ErrorCode

from . import _cppbuild

KIND_NAMES = {kind: name for name, kind in _cppbuild.LIBRARY_TYPES.items()}
_TOKEN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")   # CppBuildのテンプレートの差し込み口
_TARGET = re.compile(r"[A-Za-z_][A-Za-z0-9_:.+-]*")         # CMakeのターゲット名（CppBuildの検証と同じ）
_PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


# モジュール（Solution） ------------------------------------------------------------------

def module_settings(root: Path) -> dict:
    """main_project・ソリューションフォルダー・ファイルテンプレート。依存先の置き場所は ECOBuild が決める（deps）。"""
    data = _cppbuild.open_solution(root).settings.get()
    folders = data.solution_folders
    return {
        "main_project": data.main_project,
        "folders": None if folders is None else {
            "projects": folders.projects, "linked_projects": folders.linked_projects,
            "external": folders.external, "project_folders": dict(sorted(folders.project_folders.items()))},
        "templates": {name: {"path": path, "builtin": name in _cppbuild.TEMPLATES}
                      for name, path in sorted(data.file_templates.items())},
    }


def set_module_settings(root: Path, *, main: str | None = None, clear_main: bool = False,
                        projects_folder: str | None = None, linked_folder: str | None = None,
                        external_folder: str | None = None) -> dict:
    solution = _cppbuild.open_solution(root)
    data = solution.settings.get()
    if main is not None:
        _require(solution, main)
        data.main_project = main
    if clear_main:
        data.main_project = None
    if any(v is not None for v in (projects_folder, linked_folder, external_folder)):
        folders = data.solution_folders
        for value in (projects_folder, linked_folder, external_folder):
            if value is not None:
                _folder_name(value)
        if projects_folder is not None:
            folders.projects = projects_folder
        if linked_folder is not None:
            folders.linked_projects = linked_folder
        if external_folder is not None:
            folders.external = external_folder
    _save(solution, lambda: solution.settings.save(data), "モジュールの設定を変えられません。")
    return module_settings(root)


# ファイルテンプレート --------------------------------------------------------------------

def add_template(root: Path, name: str, source: Path) -> dict:
    """ファイルテンプレートを登録する（同じ名前なら差し替える。ECOBuildの既定のテンプレートも差し替えられる）。
    差し込み口は {{名前}}（file add --template が header・suite・name・project を渡す）。"""
    if not _PACKAGE.fullmatch(name) or "-" in name:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"テンプレート名 {name!r} は使えません。",
                            hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
    if not source.is_file():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{source} がありません。")
    solution = _cppbuild.open_solution(root)
    data = solution.settings.get()
    old = data.file_templates.get(name)
    staging = solution.root / f".ecobuild-template{source.suffix}"
    staging.write_bytes(source.read_bytes())
    try:
        def change():
            if old is not None:
                solution.settings.remove_file_template(name)
                (solution.root / old).unlink(missing_ok=True)
            solution.create_file_template(name, staging.name)
        _save(solution, change, f"テンプレート {name} を登録できません。", update=False)
    finally:
        staging.unlink(missing_ok=True)
    return module_settings(root)["templates"]


def remove_template(root: Path, name: str) -> dict:
    if name in _cppbuild.TEMPLATES:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{name} は ECOBuild の既定のテンプレートなので外せません。",
                            hint="中身を変えるには、ecobuild template add で同じ名前に差し替えてください。")
    solution = _cppbuild.open_solution(root)
    path = solution.settings.get().file_templates.get(name)
    if path is None:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"テンプレート {name} はありません。")

    def change():
        solution.settings.remove_file_template(name)
        (solution.root / path).unlink(missing_ok=True)
    _save(solution, change, f"テンプレート {name} を外せません。", update=False)
    return module_settings(root)["templates"]


def add_file_from_template(root: Path, project: str, path: str, template: str, values: dict[str, str]) -> str:
    """テンプレートからファイルを作る。差し込み口には values（header・suite・name・project）から渡す。"""
    solution = _cppbuild.open_solution(root)
    target = _require(solution, project)
    templates = solution.settings.get().file_templates
    if template not in templates:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"テンプレート {template} はありません。",
                            hint=f"{'・'.join(sorted(templates))}（ecobuild template list）")
    tokens = set(_TOKEN.findall((solution.root / templates[template]).read_text(encoding="utf-8")))
    missing = sorted(t for t in tokens if not values.get(t))
    if missing:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"テンプレート {template} の差し込み口 {'・'.join(missing)} に入れる値がありません。",
                            hint="file add が渡せるのは header（読み込むヘッダー）・suite・name（ファイル名）・project です。")
    try:
        target.add_file(path, template_name=template, replacements={t: values[t] for t in tokens} if tokens else None,
                        auto_update=False)
        solution.update()
    except FileExistsError:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{project}/{path} は既にあります。") from None
    except Exception as error:
        raise _cppbuild._cppbuild_error(f"{project}/{path} を作れません。", error) from error
    return f"{target.root.relative_to(Path(root).resolve()).as_posix()}/{path}"


# Project -------------------------------------------------------------------------------

def project_details(root: Path, name: str) -> dict:
    """Projectの保存する設定すべて。"""
    solution = _cppbuild.open_solution(root)
    project = _require(solution, name)
    data = project.settings.get()
    module = solution.settings.get()
    folders = module.solution_folders
    return {
        "name": name,
        "kind": data.initial_type.value,
        "directory": module.projects[name],
        "main": module.main_project == name,
        "folder": None if folders is None else folders.project_folders.get(name, folders.projects),
        "source_directories": list(data.source_directories),
        "types": {_type_name(kind): {"defines": list(t.compile_definitions),
                                     "public_defines": list(t.public_definitions),
                                     "include_directories": list(t.include_directories)}
                  for kind, t in data.types.items()},
        "links": [_link_view(key, value, _names(solution)) for key, value in data.dependencies.items()],
        "pch": {"headers": list(data.project_headers), "system_headers": list(data.system_headers)},
        "export_all_symbols": data.windows_export_all_symbols,
    }


def set_project(root: Path, name: str, *, types: tuple[str, ...] = (),
                add_defines=(), remove_defines=(), add_public_defines=(), remove_public_defines=(),
                add_include_directories=(), remove_include_directories=(),
                add_source_directories=(), remove_source_directories=(),
                export_all_symbols: bool | None = None, folder: str | None = None,
                clear_folder: bool = False) -> dict:
    """Projectの設定を変える。定義・インクルードは形式ごと（types。省略時はそのProjectのすべての形式）。"""
    solution = _cppbuild.open_solution(root)
    project = _require(solution, name)
    data = project.settings.get()
    library = data.initial_type in _cppbuild.LIBRARY_TYPES.values()
    if types and not library:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--for はライブラリのProjectでだけ使えます。",
                            hint="実行ファイル・テストの形式は1つだけです。")
    selected = [_cppbuild.LIBRARY_TYPES[_library_type(t)] for t in types] or list(data.types)
    for kind in selected:
        settings = data.types[kind]
        where = f"{name}（{_type_name(kind)}）"
        settings.compile_definitions = _edit(settings.compile_definitions, add_defines, remove_defines, where, "定義")
        settings.public_definitions = _edit(settings.public_definitions, add_public_defines, remove_public_defines,
                                            where, "公開する定義")
        settings.include_directories = _edit(settings.include_directories, add_include_directories,
                                             remove_include_directories, where, "インクルードディレクトリ")
    data.source_directories = _edit(data.source_directories, add_source_directories, remove_source_directories,
                                    name, "ソースディレクトリ")
    if export_all_symbols is not None:
        if not library:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--export-all はライブラリのProjectでだけ使えます。")
        data.windows_export_all_symbols = export_all_symbols
    module = solution.settings.get()
    if folder is not None or clear_folder:
        if module.solution_folders is None:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "このモジュールはソリューションフォルダーを使っていません。")
        if folder is not None:
            module.solution_folders.project_folders[name] = _folder_name(folder, nested=True)
        else:
            module.solution_folders.project_folders.pop(name, None)

    def change():
        project.settings.save(data)
        if folder is not None or clear_folder:
            solution.settings.save(module)
    _save(solution, change, f"Project {name} の設定を変えられません。")
    return project_details(root, name)


def set_pch(root: Path, name: str, *, headers: tuple[str, ...], system_headers: tuple[str, ...]) -> dict:
    """PCHに入れるヘッダーを指定する（headers：Projectからの相対パス、system_headers：<vector> 等の名前）。"""
    solution = _cppbuild.open_solution(root)
    project = _require(solution, name)
    for header in headers:
        if not (project.root / header).is_file():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{name}/{header} がありません。",
                                hint="Projectのディレクトリからの相対パスで、あるヘッダーを指定してください。")
    _save(solution, lambda: project.settings.set_pch(project_headers=headers, system_headers=system_headers),
          f"Project {name} のPCHを設定できません。")
    return project_details(root, name)


def move_project(root: Path, name: str, destination: str) -> str:
    """Projectのディレクトリを移す（名前は変わらない）。移動先（モジュールからの相対）を返す。"""
    solution = _cppbuild.open_solution(root)
    _require(solution, name)
    if (Path(root) / destination).exists():
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{destination} は既にあります。")
    try:
        report = solution.move_project(name, destination)
    except Exception as error:
        raise _cppbuild._cppbuild_error(f"Project {name} を移せません。", error) from error
    if not report.success:
        raise EcoBuildError(ErrorCode.CPPBUILD_ERROR, f"Project {name} を移しましたが、構成の作り直しに失敗しました。",
                            hint="原因を直してから ecobuild build で作り直してください。", details=str(report.update_error))
    return solution.settings.get().projects[name]


# リンク ---------------------------------------------------------------------------------

def link_project(root: Path, name: str, library: str, as_type: str | None) -> dict:
    """同じモジュールのライブラリをリンクする。as_type：static・shared・interface（省略時はライブラリの作成時の形式）。"""
    solution = _cppbuild.open_solution(root)
    project, other = _require(solution, name), _require(solution, library)
    kinds = other.settings.get().types
    if not set(kinds) & set(_cppbuild.LIBRARY_TYPES.values()):
        raise EcoBuildError(ErrorCode.NOT_LINKABLE, f"{library} はライブラリではないので、リンクできません。")
    kind = _cppbuild.LIBRARY_TYPES[_library_type(as_type)] if as_type else other.settings.get().initial_type
    if name == library:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "自分自身はリンクできません。")
    _save(solution, lambda: project.settings.link_project(other, kind), f"{name} から {library} をリンクできません。")
    return project_details(root, name)


def link_package(root: Path, name: str, package: str, target: str, directory: str) -> dict:
    """CMakeのパッケージ（find_package の CONFIG。directory は <名前>Config.cmake の場所、Projectからの相対）をリンクする。"""
    if not _PACKAGE.fullmatch(package):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"パッケージ名 {package!r} は使えません。")
    _check_target(target)
    return _link(root, name, CMakePackage(package, target, directory), f"パッケージ {package}")


def link_cmake(root: Path, name: str, directory: str, target: str) -> dict:
    """CMakeのソース（add_subdirectory する CMakeLists.txt のあるディレクトリ、Projectからの相対）のターゲットをリンクする。"""
    _check_target(target)
    return _link(root, name, CMakeSource(directory, target), f"{directory} の {target}")


def link_library_file(root: Path, name: str, kind: str, locations: dict[str, str],
                      import_libraries: dict[str, str], include_directories: tuple[str, ...]) -> dict:
    """ビルド済みのライブラリ（構成ごとの .lib・.dll 等、Projectからの相対）をリンクする。"""
    kind_value = _cppbuild.LIBRARY_TYPES[_library_type(kind)]
    for configuration in (*locations, *import_libraries):
        if configuration not in _cppbuild.CONFIGURATIONS:
            raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, f"構成 {configuration} はありません。",
                                hint=f"{'・'.join(_cppbuild.CONFIGURATIONS)} のどれかを指定してください。")
    if kind_value != ProjectType.INTERFACE_LIBRARY and not locations:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "ライブラリのファイルを指定してください（--file Debug=…,Release=…）。")
    return _link(root, name, ImportedLibrary(kind_value, dict(locations), list(include_directories),
                                             dict(import_libraries)), "ビルド済みのライブラリ")


def unlink(root: Path, name: str, link: str) -> dict:
    """Projectのリンクを外す。link：project show に出る名前か、その id。
    依存先のモジュールは、他のProjectもリンクしていればここで外せる（最後の1つは ecobuild unlink）。"""
    solution = _cppbuild.open_solution(root)
    project = _require(solution, name)
    names = _names(solution)
    links = [_link_view(key, value, names) for key, value in project.settings.get().dependencies.items()]
    found = [view for view in links if link in (view["id"], view["name"])]
    if len(found) != 1:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"{name} のリンク {link} は{'ありません' if not found else 'いくつもあります（id で指定してください）'}。",
                            hint="ecobuild project show " + name + " でリンクの一覧（名前と id）を確かめてください。")
    view = found[0]
    if view["kind"] == "module":
        source = view["name"].split("/")[0]
        others = [p.name for p in solution.projects() if p.name != name and any(
            _link_view(k, v, names)["kind"] == "module" and _link_view(k, v, names)["name"].split("/")[0] == source
            for k, v in p.settings.get().dependencies.items())]
        if not others:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"依存先 {source} をリンクしているのは {name} だけです。",
                                hint=f"依存先ごと外すには ecobuild unlink {source} を使ってください（記録と clone も片付けます）。")
    _save(solution, lambda: project.settings.unlink(view["id"]), f"{name} のリンク {link} を外せません。")
    return project_details(root, name)


# 内部 -----------------------------------------------------------------------------------

def _link(root: Path, name: str, value, what: str) -> dict:
    solution = _cppbuild.open_solution(root)
    project = _require(solution, name)

    def change():
        try:
            getattr(project.settings, {CMakePackage: "link_package", CMakeSource: "link_cmake_source",
                                       ImportedLibrary: "link_imported_library"}[type(value)])(value)
        except Exception as error:
            if "already registered" in str(error):
                raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{name} は {what} を既にリンクしています。") from error
            raise
    _save(solution, change, f"{name} から {what} をリンクできません。")
    return project_details(root, name)


def _names(solution: Solution) -> dict[str, tuple[str, str]]:
    """GUID → (種類, 表示名)：同じモジュールのProjectは名前、依存先のは「依存先/Project」。"""
    names = {guid: ("project", name) for guid, name in _cppbuild._guid_names(solution).items()}
    for source in solution.git_sources():
        if source.present:
            names.update({guid: ("module", f"{source.name}/{project}")
                          for guid, project in _cppbuild._guid_names(Solution.open(source.config)).items()})
    return names


def _link_view(key: str, value, names: dict) -> dict:
    if isinstance(value, Dependency):
        kind, label = names.get(value.project_guid, ("module", value.project_guid))
        return {"id": key, "kind": kind, "name": label, "as": _type_name(value.project_type)}
    if isinstance(value, CMakePackage):
        return {"id": key, "kind": "package", "name": value.name, "target": value.target, "directory": value.directory}
    if isinstance(value, CMakeSource):
        return {"id": key, "kind": "cmake", "name": value.target, "directory": value.directory}
    if isinstance(value, ImportedLibrary):
        files = list(value.locations.values())
        return {"id": key, "kind": "file", "name": Path(files[0]).stem if files else "(interface)",
                "as": _type_name(value.project_type), "files": dict(value.locations),
                "import_libraries": dict(value.import_libraries), "include_directories": list(value.include_directories)}
    return {"id": key, "kind": "other", "name": key}


def _require(solution: Solution, name: str):
    projects = solution.settings.get().projects
    if name not in projects:
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {name} はありません。",
                            hint=f"モジュールのProject：{'、'.join(projects) or 'なし'}")
    return solution.get_project(name)


def _save(solution: Solution, change, message: str, *, update: bool = True) -> None:
    """設定を変え、生成ファイルを作り直してCMakeで構成する。失敗したら管理ファイル・生成ファイルを元に戻す
    （ビルドできない設定を残さない。例：ないインクルードディレクトリ・見つからないパッケージ）。"""
    before = _snapshot(solution.root)
    try:
        change()
        report = solution.update() if update else None
    except Exception as error:
        _restore(solution.root, before)
        if isinstance(error, EcoBuildError):
            raise
        if "already registered" in str(error):
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{message}（既にあります）") from error
        raise _cppbuild._cppbuild_error(message, error) from error
    if report is not None and not report.success:
        _restore(solution.root, before)
        processes = report.processes if hasattr(report, "processes") else (report.process,)
        raise EcoBuildError(ErrorCode.CPPBUILD_ERROR, f"{message}CMakeの構成に失敗したので、設定を元に戻しました。",
                            hint="パス・ターゲット名等を確かめてください（詳細はCMakeの出力）。",
                            details="\n".join(p.output for p in processes if p.output))


def _managed_files(root: Path) -> list[Path]:
    """CppBuildの管理ファイル（.cppbuild の中。output は除く）と生成ファイル。依存先・ビルドツリーは見ない。"""
    found = []
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if parts[0] in (_cppbuild.DEPENDENCY_DIRECTORY, _cppbuild.BUILD_DIRECTORY, ".git") or not path.is_file():
            continue
        if (_cppbuild.CONFIG_DIRECTORY in parts and "output" not in parts) or path.name in _cppbuild.GENERATED_FILE_NAMES:
            found.append(path)
    return found


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in _managed_files(Path(root))}


def _restore(root: Path, snapshot: dict[Path, bytes]) -> None:
    for path in _managed_files(Path(root)):
        if path not in snapshot:
            path.unlink()             # 変更で増えたもの（形式ごとの設定ファイル等）
    for path, data in snapshot.items():
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def _edit(values: list[str], add, remove, where: str, what: str) -> list[str]:
    missing = [v for v in remove if v not in values]
    if missing:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{where} の{what}に {'、'.join(missing)} はありません。")
    duplicated = [v for v in add if v in values]
    if duplicated:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{where} の{what}に {'、'.join(duplicated)} は既にあります。")
    return [v for v in values if v not in remove] + list(add)


def _library_type(value: str) -> str:
    if value not in _cppbuild.LIBRARY_TYPES:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"ライブラリの形式 {value} はありません。",
                            hint=f"{'・'.join(_cppbuild.LIBRARY_TYPES)} のどれかを指定してください。")
    return value


def _type_name(kind: ProjectType) -> str:
    return KIND_NAMES.get(kind, kind.value)


def _check_target(target: str) -> None:
    if not _TARGET.fullmatch(target):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"CMakeのターゲット名 {target!r} は使えません。")


def _folder_name(value: str, *, nested: bool = False) -> str:
    parts = value.split("/")
    if not value or any(not p or p in (".", "..") or any(c in p for c in '\\:*?"<>|') for p in parts) \
            or (len(parts) > 1 and not nested):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"フォルダー名 {value!r} は使えません。",
                            hint="/ で区切った名前にしてください（例：Libraries/Math）。" if nested else None)
    return value
