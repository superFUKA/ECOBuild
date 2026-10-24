"""エージェントの登録：起動できるエージェントの文書（agent.md）と設定（agent.toml）。

ECOBuild は役を既定として持たない。起動するエージェントは、モジュールに登録したもの（文書・渡すツールの範囲・人が
起動できるか・起動してよい子）から選ぶ。置き場所は3つ：
- 見本：ECOBuild が配るもの（インストールの場所の samples/<名前>/。更新で入れ替わる。どのモジュールでもそのまま使える）
- プリセット：このPCの手持ち（ECOBUILD_HOME/agents/presets/<名前>/。コミットしない）。モジュールの登録の元にする
  （add の from_preset）。同じ名前なら見本より優先
- モジュールの登録：リポジトリの .ecobuild/agents/registry/<名前>/（コミットする。チームで共有し、PR で見直す）。
  同じ名前なら見本より優先
モジュールで使えるのは、見本とモジュールの登録（プリセットは写してから）。

起動したエージェントに効くのは、作成元のブランチに取り込まれた登録（in_force）。エージェントは自分の作業空間の
ファイル（タスクブランチ）を書き換えられるので、作業空間の登録を使うと、自分の渡すツールを広げられてしまう。作成元の
名前は元の clone（作業空間のエージェントからは見えない）の ecobuild.toml から読み、GitHub の写し origin/<作成元>
（なければ手元の作成元）の中身を使う。ただし人が起動できるか（human_start）だけは作業ツリーの値ですぐ効く（人が選べる
役を決めるだけで、渡すツールは広げない。起動したエージェントの文書・ツール・子は作成元のもの）。

渡すツールの範囲（tools）が、そのエージェントにできることになる（エージェントはツールを通してしか ECOBuild を使えない）。
起動してよい子（children）には、自分より強い登録（自分に許されないツールを許すもの）を入れられない。
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from ecobuild import config as _config
from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError, WorkError
from ecowork.git import Git

from .errors import ErrorCode

SAMPLES = Path(__file__).parent / "samples"
PRESETS = Path("agents") / "presets"                  # ECOBUILD_HOME の下：このPCのプリセット
MODULE_FOLDER = f"{_config.DIRECTORY}/agents/registry"   # モジュールの中：モジュールの登録
SETTINGS_FILE = "agent.toml"
DOCUMENT_FILE = "agent.md"
SAMPLE = "sample"
PRESET = "preset"
MODULE = "module"
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_WILDCARDS = re.compile(r"[*?\[]")


@dataclass(frozen=True)
class Registration:
    """1つの登録。document：エージェントに渡す文書（agent.md）。source：見本（sample）・プリセット（preset）・
    モジュールの登録（module）。folder：置き場所（表示用。作成元の版なら ref:パス）。"""
    name: str
    title: str
    document: str
    human_start: bool = False           # 人が起動できる（人と話すトップの役）
    model: str = ""                     # 空なら Claude Code の既定
    children: tuple[str, ...] = ()      # 起動してよい登録の名前
    max_children: int = 0               # 同時に持てる子の数の上限
    tools: tuple[str, ...] = ()         # 渡すツールの名前の fnmatch の並び
    first_prompt: str = ""              # 起動のときの最初の発言
    source: str = MODULE
    folder: str = ""


FIELDS = ("title", "human_start", "model", "children", "max_children", "tools", "first_prompt")


# ---- 置き場所 ------------------------------------------------------------------------------------------
class _Folder:
    """ディスクのフォルダー（<名前>/agent.toml・agent.md の並び）。"""

    def __init__(self, root: Path, source: str):
        self.root, self.source = root, source

    def names(self) -> list[str]:
        try:
            return sorted(p.name for p in self.root.iterdir() if _NAME.match(p.name) and (p / SETTINGS_FILE).is_file())
        except OSError:
            return []

    def text(self, name: str, file: str) -> str | None:
        try:
            return (self.root / name / file).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as error:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{self.root / name / file} を読めません。",
                                details=str(error)) from error

    def where(self, name: str) -> str:
        return (self.root / name).as_posix()


class _Ref:
    """git の版の中のフォルダー（作成元に取り込まれた登録）。"""

    def __init__(self, git: Git, ref: str, folder: str):
        self.git, self.ref, self.folder, self.source = git, ref, folder, MODULE
        listed = git.run("ls-tree", "-r", "--name-only", ref, "--", folder, check=False)
        self.paths = set(listed.stdout.split("\n")) if listed.ok else set()

    def names(self) -> list[str]:
        depth = self.folder.count("/") + 2
        return sorted({p.split("/")[depth - 1] for p in self.paths
                       if p.count("/") == depth and p.endswith("/" + SETTINGS_FILE) and _NAME.match(p.split("/")[depth - 1])})

    def text(self, name: str, file: str) -> str | None:
        path = f"{self.folder}/{name}/{file}"
        if path not in self.paths:
            return None
        found = self.git.run("show", f"{self.ref}:{path}", check=False)
        return found.stdout.replace("\r\n", "\n") if found.ok else None

    def where(self, name: str) -> str:
        return f"{short_ref(self.ref)}:{self.folder}/{name}"


def short_ref(ref: str) -> str:
    return ref.removeprefix("refs/remotes/").removeprefix("refs/heads/")


def base_ref(workspace: Path | str) -> str | None:
    """作成元のブランチ（GitHub の写しがあればそちら）。作成元の名前は、元の clone（作業空間のエージェントからは
    見えない・書き換えられない）の ecobuild.toml から。分からなければ None。"""
    try:
        git = Git(Path(workspace))
        base = _config.load(git.common_root() / _config.FILE_NAME).default_base
        for ref in (f"refs/remotes/origin/{base}", f"refs/heads/{base}"):
            if git.rev_parse(ref):
                return ref
    except (EcoBuildError, WorkError, OSError, ValueError):
        pass
    return None


def in_force_text(workspace: Path | str, path: str) -> str | None:
    """作成元のブランチに取り込まれたファイルの中身（なければ None）。"""
    ref = base_ref(workspace)
    if ref is None:
        return None
    try:
        found = Git(Path(workspace)).run("show", f"{ref}:{path}", check=False)
    except (WorkError, OSError):
        return None
    return found.stdout.replace("\r\n", "\n") if found.ok else None


def _samples() -> _Folder:
    return _Folder(SAMPLES, SAMPLE)


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


def _all(*stores) -> dict[str, Registration]:
    found: dict[str, Registration] = {}
    for store in stores:
        if store is not None:
            found.update({name: _read(store, name) for name in store.names()})
    return found


# ---- 読む ----------------------------------------------------------------------------------------------
def samples() -> list[Registration]:
    """ECOBuild が配る見本（名前の順）。"""
    return list(_all(_samples()).values())


def presets() -> list[Registration]:
    """このPCで選べるプリセット：見本と、このPCのプリセット（同じ名前ならこちら。名前の順）。"""
    found = _all(_samples(), _presets())
    return [found[name] for name in sorted(found)]


def load_preset(name: str) -> Registration:
    _check_name(name)
    found = _all(_samples(), _presets())
    if name not in found:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"プリセット「{name}」はありません。",
                            hint="プリセットは ecobuild agent preset list で見られます。")
    return found[name]


def list_registrations(root: Path | str, *, in_force: bool = False) -> list[Registration]:
    """モジュールで使える登録の全部（名前の順）：見本と、モジュールの登録（同じ名前ならこちら）。
    in_force：作成元に取り込まれたもの（起動・ツールの確かめはこちら）。偽なら作業ツリーのもの（見る・直す）。
    人が起動できるか（human_start）は、どちらも作業ツリーの値（モジュールの「エージェント」で変えたらすぐ選べる）。"""
    here = _all(_samples(), _module(root, False))
    if not in_force:
        return [here[name] for name in sorted(here)]
    found = _all(_samples(), _module(root, True))
    return [replace(found[name], human_start=here[name].human_start) if name in here else found[name]
            for name in sorted(found)]


def load(name: str, root: Path | str, *, in_force: bool = False) -> Registration:
    """モジュールの名前の登録（モジュールの登録、なければ見本）。"""
    if _NAME.match(name):
        for registration in list_registrations(root, in_force=in_force):
            if registration.name == name:
                return registration
    raise _unknown(name)


def effective(name: str, workspace: Path | str) -> Registration:
    """その作業空間で起動したエージェントに効く登録（作成元に取り込まれたもの）。"""
    return load(name, workspace, in_force=True)


def pending(root: Path | str) -> set[str]:
    """作業ツリーの登録のうち、作成元に取り込まれたものと中身が違う名前（まだ起動するエージェントに効いていない。
    見本をモジュールの登録に写しただけ・人が起動できるかだけの違いは、もう効いている）。"""
    here = {r.name: replace(r, folder="", source="") for r in list_registrations(root)}
    force = {r.name: replace(r, folder="", source="") for r in list_registrations(root, in_force=True)}
    return {name for name in {*here, *force} if here.get(name) != force.get(name)}


def to_data(registration: Registration) -> dict:
    """登録を JSON にできる形に（このPCで解決した登録を、コンテナの中の MCP サーバーへ渡す）。"""
    return {"name": registration.name, "title": registration.title, "document": registration.document,
            "human_start": registration.human_start, "model": registration.model,
            "children": list(registration.children), "max_children": registration.max_children,
            "tools": list(registration.tools), "first_prompt": registration.first_prompt, "source": registration.source}


def from_file(path: Path | str) -> Registration:
    """to_data で書いたファイルの登録（読めなければ誤り）。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Registration(
            name=str(data["name"]), title=str(data.get("title") or data["name"]), document=str(data.get("document", "")),
            human_start=bool(data.get("human_start", False)), model=str(data.get("model", "")),
            children=tuple(str(v) for v in data.get("children", [])), max_children=int(data.get("max_children", 0)),
            tools=tuple(str(v) for v in data.get("tools", [])), first_prompt=str(data.get("first_prompt", "")),
            source=str(data.get("source", MODULE)))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"登録のファイル {path} を読めません。",
                            details=str(error)) from error


def allows_tool(registration: Registration, tool_name: str) -> bool:
    """登録がそのツールを許すか（tools のどれかの fnmatch に合う）。"""
    return any(fnmatch.fnmatchcase(tool_name, pattern) for pattern in registration.tools)


def stronger(child: Registration, parent: Registration) -> bool:
    """child が parent より強いか（parent の tools では許されないツールを、child が許すことがあるか）。"""
    return any(not _covered(pattern, parent.tools) for pattern in child.tools)


# ---- 変える：モジュールの登録（作業ツリー） --------------------------------------------------------------
def add(root: Path | str, name: str, *, from_preset: str | None = None, from_dir: str | Path | None = None) -> Registration:
    """モジュールの登録を足す（作業ツリーに書く。コミットは呼び手）。from_preset：プリセット（見本も）を写す。
    from_dir：agent.toml・agent.md のあるフォルダーを取り込む。どちらもなければ、同じ名前のプリセットを写すか、空の登録。"""
    store = _Folder(Path(root) / MODULE_FOLDER, MODULE)
    if name in store.names():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"登録「{name}」はもうあります。",
                            hint="中身を変えるには ecobuild agent registry set を使います。")
    new = _new(name, from_preset, from_dir, MODULE)
    _check(new, {r.name: r for r in list_registrations(root)})
    _write(store, new)
    return _read(store, name)


def update(root: Path | str, name: str, *, document: str | None = None, **fields) -> Registration:
    """モジュールの登録の設定（FIELDS）・文書を変える。見本だけの名前なら、モジュールの登録として写してから変える。"""
    store = _Folder(Path(root) / MODULE_FOLDER, MODULE)
    new = _changed(load(name, root), document, fields)
    _check(new, {r.name: r for r in list_registrations(root)})
    _write(store, new)
    return _read(store, name)


def remove(root: Path | str, name: str) -> Registration:
    """モジュールの登録を消す（同じ名前の見本があれば、それがまた使われる）。見本は消せない。"""
    store = _Folder(Path(root) / MODULE_FOLDER, MODULE)
    _check_name(name)
    if name not in store.names():
        if name in _samples().names():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{name}」は ECOBuild の見本なので消せません。")
        raise _unknown(name)
    removed = _read(store, name)
    if name not in _samples().names():    # 見本に戻るなら、名前は残る
        users = [r.name for r in list_registrations(root) if r.name != name and name in r.children]
        if users:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"「{name}」を子として起動できる登録があります：" + "、".join(users),
                                hint="先にそれらの children から外してください。")
    shutil.rmtree(store.root / name)
    return removed


# ---- 変える：このPCのプリセット ------------------------------------------------------------------------
def add_preset(name: str, *, from_preset: str | None = None, from_dir: str | Path | None = None,
               registration: Registration | None = None) -> Registration:
    """このPCのプリセットを足す。from_preset：ほかのプリセット・見本を写す。registration：モジュールの登録を写す
    （モジュールで直したものを手持ちにする）。"""
    store = _presets()
    if name in store.names():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"プリセット「{name}」はもうあります。",
                            hint="中身を変えるには ecobuild agent preset set を使います。")
    new = replace(registration, name=name, source=PRESET) if registration is not None \
        else _new(name, from_preset, from_dir, PRESET)
    _check_name(name)
    _check(new, {r.name: r for r in presets()}, children_known=False)
    _write(store, new)
    return _read(store, name)


def update_preset(name: str, *, document: str | None = None, **fields) -> Registration:
    """プリセットを変える。見本だけの名前なら、このPCのプリセットとして写してから変える（見本は変えない）。"""
    store = _presets()
    new = _changed(load_preset(name), document, fields, source=PRESET)
    _check(new, {r.name: r for r in presets()}, children_known=False)
    _write(store, new)
    return _read(store, name)


def remove_preset(name: str) -> Registration:
    """このPCのプリセットを消す（同じ名前の見本があれば、それがまた使われる）。見本は消せない。"""
    store = _presets()
    _check_name(name)
    if name not in store.names():
        if name in _samples().names():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{name}」は ECOBuild の見本なので消せません。")
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"プリセット「{name}」はありません。")
    removed = _read(store, name)
    shutil.rmtree(store.root / name)
    return removed


def _new(name: str, from_preset: str | None, from_dir, source: str) -> Registration:
    _check_name(name)
    if from_preset and from_dir:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "プリセットとフォルダーは、どちらか1つだけ指定できます。")
    if from_dir:
        folder = Path(from_dir)
        if not (folder / SETTINGS_FILE).is_file():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{folder} に {SETTINGS_FILE} がありません。",
                                hint=f"取り込むフォルダーには {SETTINGS_FILE}（設定）と {DOCUMENT_FILE}（文書）を置きます。")
        return replace(_read(_Folder(folder.parent, source), folder.name, check_name=False), name=name, source=source)
    known = {r.name: r for r in presets()}
    preset = from_preset or (name if name in known else None)
    if preset:
        if preset not in known:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"プリセット「{preset}」はありません。",
                                hint="プリセットは " + "・".join(known) + " です。")
        return replace(known[preset], name=name, source=source)
    return Registration(name=name, title=name, document=f"# {name}\n", tools=("*",), source=source)


def _changed(current: Registration, document: str | None, fields: dict, source: str = MODULE) -> Registration:
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変えられない項目です：" + "、".join(sorted(unknown)))
    for key in ("children", "tools"):
        if key in fields:
            fields[key] = tuple(fields[key])
    new = replace(current, source=source, **fields)
    return replace(new, document=document) if document is not None else new


def _check(new: Registration, known: dict[str, Registration], *, children_known: bool = True) -> None:
    """保存する前の確かめ：子の名前が分かる・子が自分より強くない。new を子に持つ登録にとっても、new が強すぎない。
    children_known が偽（プリセット）なら、知らない子の名前は確かめない（写した先のモジュールで確かめる）。"""
    if not new.title.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "表示名（title）が空です。")
    if new.max_children < 0:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "子の数の上限（max_children）は 0 以上です。")
    known = {**known, new.name: new}
    missing = [child for child in new.children if child not in known]
    if missing and children_known:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "このモジュールにない登録の名前です：" + "、".join(missing),
                            hint="先にその登録を足す（ecobuild agent registry add <名前> --from-preset <プリセット>）か、"
                                 "children から外してください。")
    strong = [child for child in new.children if child in known and stronger(known[child], new)]
    if strong:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"「{new.name}」より強い（許すツールが多い）登録は子にできません：" + "、".join(strong),
                            hint="子の tools を狭めるか、children から外してください。")
    parents = [r.name for r in known.values() if r.name != new.name and new.name in r.children and stronger(new, r)]
    if parents:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"「{new.name}」を子に持つ登録より強く（許すツールが多く）なります：" + "、".join(parents),
                            hint="tools を狭めるか、先にそれらの children から外してください。")


def _covered(pattern: str, allowed: tuple[str, ...]) -> bool:
    """pattern に合うツールが、どれも allowed のどれかで許されるか（分からなければ許されないとみなす）。"""
    for given in allowed:
        if given == pattern or given == "*":
            return True
        if not _WILDCARDS.search(pattern):
            if fnmatch.fnmatchcase(pattern, given):
                return True
        elif given.endswith("*") and not _WILDCARDS.search(given[:-1]) and pattern.startswith(given[:-1]):
            return True     # task_* は task_s* を含む
    return False


def _check_name(name: str) -> None:
    if not _NAME.match(name):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"登録の名前「{name}」は使えません。",
                            hint=f"英小文字・数字・-・_ の40文字までで、先頭は英小文字か数字です。")


def _unknown(name: str) -> EcoBuildError:
    return EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"登録「{name}」はありません。",
                         hint="登録は ecobuild agent registry list で見られます。")


def _read(store, name: str, *, check_name: bool = True) -> Registration:
    where = store.where(name)
    settings = store.text(name, SETTINGS_FILE)
    try:
        data = tomllib.loads(settings or "")
    except tomllib.TOMLDecodeError as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{where}/{SETTINGS_FILE} を読めません。",
                            details=str(error)) from error
    document = store.text(name, DOCUMENT_FILE) or ""

    def strings(key):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{where}/{SETTINGS_FILE} の {key} は文字の並びです。")
        return tuple(value)

    try:
        return Registration(
            name=name, title=str(data.get("title") or name), document=document,
            human_start=bool(data.get("human_start", False)), model=str(data.get("model", "")),
            children=strings("children"), max_children=int(data.get("max_children", 0)), tools=strings("tools"),
            first_prompt=str(data.get("first_prompt", "")), source=store.source, folder=where)
    except (TypeError, ValueError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{where}/{SETTINGS_FILE} の値が読めません。",
                            details=str(error)) from error


def _write(store: _Folder, registration: Registration) -> None:
    folder = store.root / registration.name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SETTINGS_FILE).write_text(_toml(registration), encoding="utf-8", newline="\n")
    (folder / DOCUMENT_FILE).write_text(registration.document, encoding="utf-8", newline="\n")


def _toml(r: Registration) -> str:
    """agent.toml の中身（文字は JSON の書き方。TOML の基本の文字と同じ）。"""
    def text(value):
        return json.dumps(value, ensure_ascii=False)

    def strings(values):
        return "[" + ", ".join(text(v) for v in values) + "]"

    return "\n".join([
        f"title = {text(r.title)}",
        f"human_start = {'true' if r.human_start else 'false'}",
        f"model = {text(r.model)}",
        f"children = {strings(r.children)}",
        f"max_children = {r.max_children}",
        f"tools = {strings(r.tools)}",
        f"first_prompt = {text(r.first_prompt)}",
    ]) + "\n"
