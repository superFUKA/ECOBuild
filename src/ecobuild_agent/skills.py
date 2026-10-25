"""エージェントのスキル：手順・知識の文書（SKILL.md）と、それが使うファイル（スクリプト・資料）のフォルダー。

スキルはエージェントが必要なときに読む手順書で、起動のときの文（登録の文書）に入れずに済む（使うときだけ読まれる）。
書き方は Agent Skills の SKILL.md（先頭の --- の間に name・description、続けて本文）。置き場所は2つ：
- プリセット：このPCの手持ち（ECOBUILD_HOME/agents/skills/<名前>/。コミットしない）。モジュールのスキルの元にする
  （add の from_preset）。~/.claude/skills/<名前> 等のフォルダーから取り込める
- モジュールのスキル：リポジトリの .ecobuild/agents/skills/<名前>/（コミットする。チームで共有し、PR で見直す）

起動したエージェントに渡すのは、作成元のブランチに取り込まれたスキル（in_force。登録と同じく、エージェントが自分の
作業空間で書いたスキルは、取り込まれるまで渡さない）のうち、登録の skills に合うもの（provide）。
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from ecobuild import config as _config
from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError, WorkError
from ecowork.git import Git

from .errors import ErrorCode
from .registry import PRESET, MODULE, base_ref, short_ref

PRESETS = Path("agents") / "skills"                    # ECOBUILD_HOME の下：このPCのスキル（プリセット）
MODULE_FOLDER = f"{_config.DIRECTORY}/agents/skills"   # モジュールの中：モジュールのスキル
SKILL_FILE = "SKILL.md"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")       # Agent Skills の name（英小文字・数字・-、64文字まで）
MAX_DESCRIPTION = 1024
_FRONT = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


@dataclass(frozen=True)
class Skill:
    """1つのスキル。document：SKILL.md の本文（前置きの --- の後）。extra：前置きの name・description 以外の行
    （allowed-tools 等。そのまま残す）。files：SKILL.md のほかのファイル（スキルのフォルダーからの相対パス）。"""
    name: str
    description: str
    document: str
    extra: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    source: str = MODULE
    folder: str = ""


# ---- 置き場所 ------------------------------------------------------------------------------------------
class _Folder:
    """ディスクのフォルダー（<名前>/SKILL.md と、ほかのファイル）。"""

    def __init__(self, root: Path, source: str):
        self.root, self.source = root, source

    def names(self) -> list[str]:
        try:
            return sorted(p.name for p in self.root.iterdir() if _NAME.match(p.name) and (p / SKILL_FILE).is_file())
        except OSError:
            return []

    def paths(self, name: str) -> list[str]:
        folder = self.root / name
        return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())

    def data(self, name: str, path: str) -> bytes:
        return (self.root / name / path).read_bytes()

    def where(self, name: str) -> str:
        return (self.root / name).as_posix()


class _Ref:
    """git の版の中のフォルダー（作成元に取り込まれたスキル）。"""

    def __init__(self, git: Git, ref: str, folder: str):
        self.git, self.ref, self.folder, self.source = git, ref, folder, MODULE
        listed = git.run("ls-tree", "-r", "--name-only", ref, "--", folder, check=False)
        self.all = [p for p in listed.stdout.split("\n") if p] if listed.ok else []

    def names(self) -> list[str]:
        depth = self.folder.count("/") + 1
        return sorted({p.split("/")[depth] for p in self.all
                       if p.count("/") == depth + 1 and p.endswith("/" + SKILL_FILE) and _NAME.match(p.split("/")[depth])})

    def paths(self, name: str) -> list[str]:
        prefix = f"{self.folder}/{name}/"
        return sorted(p[len(prefix):] for p in self.all if p.startswith(prefix))

    def data(self, name: str, path: str) -> bytes:
        found = subprocess.run(["git", "-C", str(self.git.root), "show", f"{self.ref}:{self.folder}/{name}/{path}"],
                               capture_output=True, check=False)   # 中身はそのまま（文字とは限らない）
        if found.returncode:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{self.where(name)}/{path} を読めません。",
                                details=found.stderr.decode("utf-8", "replace").strip())
        return found.stdout

    def where(self, name: str) -> str:
        return f"{short_ref(self.ref)}:{self.folder}/{name}"


def _presets() -> _Folder:
    return _Folder(_settings.home() / PRESETS, PRESET)


def _module(root: Path | str, in_force: bool):
    if not in_force:
        return _Folder(Path(root) / MODULE_FOLDER, MODULE)
    ref = base_ref(root)
    if ref is None:
        return None
    try:
        return _Ref(Git(Path(root)), ref, MODULE_FOLDER)
    except (WorkError, OSError):
        return None


# ---- 読む ----------------------------------------------------------------------------------------------
def presets() -> list[Skill]:
    """このPCのスキル（名前の順）。"""
    store = _presets()
    return [_read(store, name) for name in store.names()]


def load_preset(name: str) -> Skill:
    store = _presets()
    _check_name(name)
    if name not in store.names():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"このPCのスキル「{name}」はありません。",
                            hint="このPCのスキルは ecobuild agent skill preset list で見られます。")
    return _read(store, name)


def list_skills(root: Path | str, *, in_force: bool = False) -> list[Skill]:
    """モジュールのスキル（名前の順）。in_force：作成元に取り込まれたもの（エージェントに渡すのはこちら）。"""
    store = _module(root, in_force)
    return [] if store is None else [_read(store, name) for name in store.names()]


def load(name: str, root: Path | str, *, in_force: bool = False) -> Skill:
    if _NAME.match(name):
        store = _module(root, in_force)
        if store is not None and name in store.names():
            return _read(store, name)
    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"スキル「{name}」はありません。",
                        hint="モジュールのスキルは ecobuild agent skill list で見られます。")


def pending(root: Path | str) -> set[str]:
    """作業ツリーのスキルのうち、作成元に取り込まれたものと中身が違う名前（まだエージェントに渡らない）。"""
    def contents(in_force: bool) -> dict[str, dict[str, bytes]]:
        store = _module(root, in_force)
        if store is None:
            return {}
        return {name: {p: store.data(name, p).replace(b"\r\n", b"\n") for p in store.paths(name)} for name in store.names()}
    here, force = contents(False), contents(True)
    return {name for name in {*here, *force} if here.get(name) != force.get(name)}


def allowed(patterns: tuple[str, ...], name: str) -> bool:
    """登録の skills（名前の fnmatch の並び）がそのスキルを使わせるか。"""
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def provide(root: Path | str, patterns: tuple[str, ...], into: Path) -> list[str]:
    """作成元に取り込まれたスキルのうち patterns に合うものを、into/<名前>/ に写す（前のものは消す）。写した名前を返す。"""
    into = Path(into)
    if into.exists():
        shutil.rmtree(into)
    store = _module(root, True)
    given = [name for name in (store.names() if store is not None else []) if allowed(patterns, name)]
    for name in given:
        for path in store.paths(name):
            target = into / name / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(store.data(name, path))
    return given


# ---- 変える：モジュールのスキル（作業ツリー） ------------------------------------------------------------
def add(root: Path | str, name: str, *, description: str = "", document: str | None = None,
        from_preset: str | None = None, from_dir: str | Path | None = None) -> Skill:
    """モジュールにスキルを足す（作業ツリーに書く。コミットは呼び手）。from_preset：このPCのスキルを写す。
    from_dir：SKILL.md のあるフォルダーを取り込む（~/.claude/skills/<名前> 等）。どちらもなければ、説明と本文から作る。"""
    store = _Folder(Path(root) / MODULE_FOLDER, MODULE)
    return _add(store, name, description, document, from_preset, from_dir)


def update(root: Path | str, name: str, *, description: str | None = None, document: str | None = None) -> Skill:
    """モジュールのスキルの説明・本文を変える（ほかのファイル・前置きのほかの行はそのまま）。"""
    store = _Folder(Path(root) / MODULE_FOLDER, MODULE)
    return _update(store, load(name, root), description, document)


def remove(root: Path | str, name: str) -> Skill:
    """モジュールのスキルをフォルダーごと消す。"""
    store = _Folder(Path(root) / MODULE_FOLDER, MODULE)
    removed = load(name, root)
    shutil.rmtree(store.root / name)
    return removed


# ---- 変える：このPCのスキル ----------------------------------------------------------------------------
def add_preset(name: str, *, description: str = "", document: str | None = None, from_dir: str | Path | None = None,
               from_module: tuple[Path | str, str] | None = None) -> Skill:
    """このPCにスキルを足す。from_dir：フォルダーを取り込む。from_module：(モジュールのルート, 名前) のスキルを写す
    （モジュールで直したものを手持ちにする）。"""
    if from_dir and from_module:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "写す元は1つだけ指定できます。")
    folder = None
    if from_module:
        module_root, source = from_module
        load(source, module_root)
        folder = Path(module_root) / MODULE_FOLDER / source
    return _add(_presets(), name, description, document, None, folder or from_dir)


def update_preset(name: str, *, description: str | None = None, document: str | None = None) -> Skill:
    return _update(_presets(), load_preset(name), description, document)


def remove_preset(name: str) -> Skill:
    removed = load_preset(name)
    shutil.rmtree(_presets().root / name)
    return removed


def _add(store: _Folder, name: str, description: str, document: str | None, from_preset, from_dir) -> Skill:
    _check_name(name)
    if from_preset and from_dir:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "このPCのスキルとフォルダーは、どちらか1つだけ指定できます。")
    if name in store.names():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"スキル「{name}」はもうあります。",
                            hint="中身を変えるには ecobuild agent skill set を使います。")
    source = None
    if from_preset:
        source = _presets().root / load_preset(from_preset).name
    elif from_dir:
        source = Path(from_dir).expanduser()
        if not (source / SKILL_FILE).is_file():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{source} に {SKILL_FILE} がありません。",
                                hint=f"取り込むフォルダーには {SKILL_FILE}（先頭の --- の間に name・description、続けて本文）を置きます。")
    folder = store.root / name
    if source is not None:
        copied = _read(_Folder(source.parent, store.source), source.name, check_name=False)
        new = replace(copied, name=name, description=description.strip() or copied.description,
                      document=copied.document if document is None else document)
        _check(new)
        shutil.copytree(source, folder, ignore=shutil.ignore_patterns(".git"))
    else:
        new = Skill(name=name, description=description.strip(), document=document if document is not None
                    else f"# {name}\n\n<手順・決まり・例を書きます>\n", source=store.source)
        _check(new)
        folder.mkdir(parents=True, exist_ok=True)
    (folder / SKILL_FILE).write_text(_text(new), encoding="utf-8", newline="\n")
    return _read(store, name)


def _update(store: _Folder, current: Skill, description: str | None, document: str | None) -> Skill:
    if description is None and document is None:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変える項目がありません。",
                            hint="--description か --document を書いてください。")
    new = replace(current, description=current.description if description is None else description.strip(),
                  document=current.document if document is None else document)
    _check(new)
    (store.root / current.name / SKILL_FILE).write_text(_text(new), encoding="utf-8", newline="\n")
    return _read(store, current.name)


def _check(skill: Skill) -> None:
    if not skill.description:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"スキル「{skill.name}」の説明（description）が空です。",
                            hint="エージェントは説明を見て、いつ使うかを決めます（何をするか・いつ使うかを書きます）。")
    if len(skill.description) > MAX_DESCRIPTION:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"説明（description）は {MAX_DESCRIPTION} 文字までです。")


def _check_name(name: str) -> None:
    if not _NAME.match(name):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"スキルの名前「{name}」は使えません。",
                            hint="英小文字・数字・- の64文字までで、先頭は英小文字か数字です。")


# ---- SKILL.md ------------------------------------------------------------------------------------------
def _read(store, name: str, *, check_name: bool = True) -> Skill:
    where = store.where(name)
    try:
        text = store.data(name, SKILL_FILE).decode("utf-8")
    except (OSError, UnicodeDecodeError, WorkError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{where}/{SKILL_FILE} を読めません。",
                            details=str(error)) from error
    description, extra, document = _parse(text)
    files = tuple(p for p in store.paths(name) if p != SKILL_FILE)
    return Skill(name=name, description=description, document=document, extra=extra, files=files,
                 source=store.source, folder=where)


def _parse(text: str) -> tuple[str, tuple[str, ...], str]:
    """SKILL.md を (説明, 前置きの name・description 以外の行, 本文) に。前置きがなければ、全部を本文に。"""
    text = text.replace("\r\n", "\n")
    found = _FRONT.match(text)
    if not found:
        return "", (), text
    description, extra = "", []
    for line in found.group(1).split("\n"):
        key, _, value = line.partition(":")
        if key.strip() == "description" and not line.startswith((" ", "\t")):
            description = _unquote(value.strip())
        elif key.strip() != "name" or line.startswith((" ", "\t")):
            extra.append(line)
    return description, tuple(extra), text[found.end():]


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if value[0] == '"' else inner.replace("''", "'")
    return value


def _text(skill: Skill) -> str:
    """SKILL.md の中身（説明は1行の "…"。改行は空白にする）。"""
    description = " ".join(skill.description.split()).replace("\\", "\\\\").replace('"', '\\"')
    front = [f"name: {skill.name}", f'description: "{description}"', *skill.extra]
    body = skill.document if skill.document.endswith("\n") or not skill.document else skill.document + "\n"
    return "---\n" + "\n".join(front) + "\n---\n" + body
