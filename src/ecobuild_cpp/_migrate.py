"""CppBuildの管理ファイル（.cppbuild）の古い形式を、今の形式にする（module upgrade で行う）。

CppBuildは Project を Subproject に改名した（1ee1e10〜。schema 5 → 6）。CppBuildは古い形式を読まないので、
ECOBuild が移す：
  .cppbuild/project.json                         → .cppbuild/solution.json
  .cppbuild/projects/<名前>/project.json         → .cppbuild/subprojects/<名前>/subproject.json
  .cppbuild/projects/<名前>/types/<種類>-<hash>.json → .cppbuild/subprojects/<名前>/types/<種類>-<新しい hash>.json
キー（projects・main_project・project_guid 等 → subproject…）・依存の kind（project → subproject）・schema_version。
ソリューションフォルダーの名前が CppBuildの古い既定（Projects・LinkedProjects）のままなら、新しい既定
（Subprojects・LinkedSubprojects）にする（ECOBuild が既定のまま入れた値で、新しく作るモジュールとそろえる）。
生成ファイル（CMakeLists.txt 等）は移さず消す（移したあとの CppBuild の update で作り直す）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from ecobuild.errors import EcoBuildError

from .errors import ErrorCode

OLD_SCHEMA = 5
SCHEMA = 6
OLD_SOLUTION = "project.json"
OLD_SUBPROJECTS = "projects"
OLD_SUBPROJECT = "project.json"
SOLUTION = "solution.json"
SUBPROJECTS = "subprojects"
SUBPROJECT = "subproject.json"

_SOLUTION_KEYS = {"projects": "subprojects", "main_project": "main_subproject"}
_FOLDER_KEYS = {"projects": "subprojects", "linked_projects": "linked_subprojects", "project_folders": "subproject_folders"}
_FOLDER_DEFAULTS = {"subprojects": ("Projects", "Subprojects"), "linked_subprojects": ("LinkedProjects", "LinkedSubprojects")}
_SUBPROJECT_KEYS = {"project_headers": "subproject_headers"}
_TEMPORARY = ".ecobuild-tmp"   # 書きかけの一時ファイル（残っていれば、次に移すときに消す）
_DEPENDENCY_KEYS = {"project_guid": "subproject_guid", "project_type": "subproject_type"}


def is_old(config: Path) -> bool:
    """config（.cppbuild）が古い形式（project.json がある）か。今のCppBuildは project.json を作らない。"""
    return (Path(config) / OLD_SOLUTION).is_file()


def needs_cleanup(config: Path) -> bool:
    """移し終えた（solution.json がある・project.json がない）のに、古い置き場所（projects/）が残っているか。"""
    config = Path(config)
    return not is_old(config) and (config / SOLUTION).is_file() and (config / OLD_SUBPROJECTS).is_dir()


def plan(config: Path) -> tuple[dict[str, bytes], tuple[tuple[str, str], ...]]:
    """移したあとのファイル（.cppbuild からの相対 → 中身）と、移すファイル（元, 先。消すだけなら 先 は空）。何も変えない。"""
    config = Path(config)
    solution = _envelope(config / OLD_SOLUTION, "solution")
    documents: dict[str, bytes] = {}
    moves: list[tuple[str, str]] = []
    for name in solution.get("projects", {}):
        old = f"{OLD_SUBPROJECTS}/{name}"
        new = f"{SUBPROJECTS}/{name}"
        data, types = _subproject(config / old)
        for kind, (old_file, content) in types.items():
            file_name = f"{kind}-{hashlib.sha256(content).hexdigest()}.json"
            data["types"][kind] = file_name
            documents[f"{new}/types/{file_name}"] = content
            moves.append((f"{old}/types/{old_file}", f"{new}/types/{file_name}"))
        documents[f"{new}/{SUBPROJECT}"] = _encoded({"schema_version": SCHEMA, "kind": "subproject", "data": data})
        moves.append((f"{old}/{OLD_SUBPROJECT}", f"{new}/{SUBPROJECT}"))
    documents[SOLUTION] = _encoded({"schema_version": SCHEMA, "kind": "solution", "data": _solution(solution)})
    moves.append((OLD_SOLUTION, SOLUTION))

    # 古い形式の場所にあるほかのファイル（生成ファイル・登録されていない Project や型の設定）は消す。分からないものは移す
    moved = {old for old, _ in moves}
    old_root = config / OLD_SUBPROJECTS
    if old_root.is_dir():
        for path in sorted(p for p in old_root.rglob("*") if p.is_file() and p.name != _TEMPORARY):
            relative = path.relative_to(config).as_posix()
            if relative in moved:
                continue
            parts = path.relative_to(old_root).parts
            if parts[-1] in ("CMakeLists.txt", OLD_SUBPROJECT) or (len(parts) == 3 and parts[1] == "types"):
                moves.append((relative, ""))
            else:
                target = f"{SUBPROJECTS}/{'/'.join(parts)}"
                documents.setdefault(target, path.read_bytes())
                moves.append((relative, target))
    return documents, tuple(moves)


def convert(config: Path) -> tuple[tuple[str, str], ...]:
    """config（.cppbuild）を今の形式にする。移したファイル（.cppbuild からの相対の 元, 先。消しただけなら 先 は空）を返す。

    全部を読んで変換してから書く（読めなければ何も変えない）。新しいファイルを全部書いたら、まず project.json を消す
    （ここで移し終わり。それまでに止まれば、もう一度行えば最後まで移る）。古い置き場所の片付けはその後で、失敗しても
    止めない（残れば needs_cleanup が真になり、cleanup でやり直す）。
    """
    config = Path(config)
    _remove_temporaries(config)
    documents, moves = plan(config)
    for relative in documents:
        path = config / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, documents[relative])
    (config / OLD_SOLUTION).unlink()
    cleanup(config)
    return moves


def cleanup(config: Path) -> bool:
    """移し終えた後の古い置き場所（projects/）と、書きかけの一時ファイルを消す。消せなければ False（止めない）。"""
    config = Path(config)
    _remove_temporaries(config)
    try:
        if (config / OLD_SUBPROJECTS).is_dir():
            shutil.rmtree(config / OLD_SUBPROJECTS)
    except OSError:   # 他のプログラム（Visual Studio 等）がつかんでいる。次の module upgrade で片付ける
        return False
    return True


def _remove_temporaries(config: Path) -> None:
    for path in config.rglob(_TEMPORARY):
        try:
            path.unlink()
        except OSError:
            pass


def _solution(data: dict) -> dict:
    data = _renamed(data, _SOLUTION_KEYS)
    for reference in data.get("references", {}).values():
        _rename_in_place(reference, _DEPENDENCY_KEYS)
    folders = data.get("solution_folders")
    if isinstance(folders, dict):
        folders = data["solution_folders"] = _renamed(folders, _FOLDER_KEYS)
        for key, (old, new) in _FOLDER_DEFAULTS.items():
            if folders.get(key) == old:
                folders[key] = new
    return data


def _subproject(directory: Path) -> tuple[dict, dict[str, tuple[str, bytes]]]:
    """Projectの設定（キーを改名した data）と、型ごとの設定（種類 → (元のファイル名, 新しい中身)）。"""
    data = _renamed(_envelope(directory / OLD_SUBPROJECT, "project"), _SUBPROJECT_KEYS)
    for dependency in data.get("dependencies", {}).values():
        if not isinstance(dependency, dict):
            raise _broken(directory / OLD_SUBPROJECT, "dependencies の形が違います")
        if dependency.get("kind") == "project":
            dependency["kind"] = "subproject"
        if isinstance(dependency.get("values"), dict):
            _rename_in_place(dependency["values"], _DEPENDENCY_KEYS)
    types = {}
    for kind, file_name in data.get("types", {}).items():
        path = directory / "types" / file_name
        content = _envelope(path, kind)
        types[kind] = (file_name, _encoded({"schema_version": SCHEMA, "kind": kind, "data": content}))
    return data, types


def _renamed(data: dict, keys: dict[str, str]) -> dict:
    return {keys.get(key, key): value for key, value in data.items()}


def _rename_in_place(data: dict, keys: dict[str, str]) -> None:
    for old, new in keys.items():
        if old in data:
            data[new] = data.pop(old)


def _envelope(path: Path, kind: str) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise _broken(path, f"読めません（{error}）") from error
    if not isinstance(document, dict) or not isinstance(document.get("data"), dict):
        raise _broken(path, "CppBuildの管理ファイルの形ではありません")
    if document.get("schema_version") != OLD_SCHEMA or document.get("kind") != kind:
        raise _broken(path, f"変換できる形式（schema {OLD_SCHEMA}・{kind}）ではありません"
                            f"（schema {document.get('schema_version')}・{document.get('kind')}）")
    return document["data"]


def _encoded(value) -> bytes:
    # CppBuildの書き方（storage.encoded）と同じ：キーの順・字下げ・UTF-8・最後の改行
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write(path: Path, data: bytes) -> None:
    temporary = path.with_name(_TEMPORARY)   # 長い名前（型の設定は hash 入り）をさらに長くしない
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _broken(path: Path, reason: str) -> EcoBuildError:
    return EcoBuildError(ErrorCode.CPPBUILD_ERROR, f"CppBuildの管理ファイル {path} を新しい形式にできません：{reason}。",
                         hint="ファイルを直すか、壊れる前のコミットに戻してから、もう一度実行してください。")
