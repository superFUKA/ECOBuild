"""エージェントの登録：起動できるエージェントの文書（agent.md）と設定（agent.toml）。

ECOBuild は役を既定として持たない。起動するエージェントは、ここに登録したもの（文書・渡すツールの範囲・人が起動できるか・
起動してよい子）から選ぶ。登録はモジュールではなく、このPCの ECOBuild 全体の設定（コミットしない）。
- 見本：ECOBuild が配るもの（インストールの場所の samples/<名前>/。更新で入れ替わる）
- ユーザーの登録：ECOBUILD_HOME/agents/registry/<名前>/（更新で消えない）。同じ名前なら、こちらが優先

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

from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError

from .errors import ErrorCode

SAMPLES = Path(__file__).parent / "samples"
REGISTRY = Path("agents") / "registry"     # ECOBUILD_HOME の下：ユーザーの登録
SETTINGS_FILE = "agent.toml"
DOCUMENT_FILE = "agent.md"
SAMPLE = "sample"
USER = "user"
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_WILDCARDS = re.compile(r"[*?\[]")


@dataclass(frozen=True)
class Registration:
    """1つの登録。document：エージェントに渡す文書（agent.md）。source：見本（sample）かユーザーの登録（user）。"""
    name: str
    title: str
    document: str
    human_start: bool = False           # 人が起動できるか
    model: str = ""                     # 空なら Claude Code の既定
    children: tuple[str, ...] = ()      # 起動してよい登録の名前
    max_children: int = 0               # 同時に持てる子の数の上限
    tools: tuple[str, ...] = ()         # 渡すツールの名前の fnmatch の並び
    first_prompt: str = ""              # 起動のときの最初の発言
    source: str = USER


FIELDS = ("title", "human_start", "model", "children", "max_children", "tools", "first_prompt")


def user_root() -> Path:
    return _settings.home() / REGISTRY


def directory(registration: Registration) -> Path:
    """登録の置き場所（agent.toml・agent.md のあるフォルダー）。"""
    return (SAMPLES if registration.source == SAMPLE else user_root()) / registration.name


def document_path(registration: Registration) -> Path:
    return directory(registration) / DOCUMENT_FILE


def samples() -> list[Registration]:
    """ECOBuild が配る見本（名前の順）。"""
    return [_read(folder, SAMPLE) for folder in _folders(SAMPLES)]


def list_registrations() -> list[Registration]:
    """使える登録の全部（名前の順）。同じ名前なら、ユーザーの登録を見本より優先する。"""
    found = {r.name: r for r in samples()}
    found.update({r.name: r for r in _users()})
    return [found[name] for name in sorted(found)]


def load(name: str) -> Registration:
    """名前の登録（ユーザーの登録、なければ見本）。"""
    for root, source in ((user_root(), USER), (SAMPLES, SAMPLE)):
        if _NAME.match(name) and (root / name / SETTINGS_FILE).is_file():
            return _read(root / name, source)
    raise _unknown(name)


def allows_tool(registration: Registration, tool_name: str) -> bool:
    """登録がそのツールを許すか（tools のどれかの fnmatch に合う）。"""
    return any(fnmatch.fnmatchcase(tool_name, pattern) for pattern in registration.tools)


def stronger(child: Registration, parent: Registration) -> bool:
    """child が parent より強いか（parent の tools では許されないツールを、child が許すことがあるか）。"""
    return any(not _covered(pattern, parent.tools) for pattern in child.tools)


def add(name: str, *, from_sample: str | None = None, from_dir: str | Path | None = None) -> Registration:
    """ユーザーの登録を足す。from_sample：見本を写す。from_dir：agent.toml・agent.md のあるフォルダーを取り込む。
    どちらもなければ、同じ名前の見本を写す（見本を上書きして使う）か、空の登録を作る。"""
    _check_name(name)
    if from_sample and from_dir:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "見本とフォルダーは、どちらか1つだけ指定できます。")
    if (user_root() / name).exists():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"登録「{name}」はもうあります。",
                            hint="中身を変えるには ecobuild agent registry set を使います。")
    if from_dir:
        source = Path(from_dir)
        if not (source / SETTINGS_FILE).is_file():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{source} に {SETTINGS_FILE} がありません。",
                                hint=f"取り込むフォルダーには {SETTINGS_FILE}（設定）と {DOCUMENT_FILE}（文書）を置きます。")
        new = replace(_read(source, USER), name=name)
    else:
        sample = from_sample or (name if (SAMPLES / name / SETTINGS_FILE).is_file() else None)
        if sample:
            if not _NAME.match(sample) or not (SAMPLES / sample / SETTINGS_FILE).is_file():
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"見本「{sample}」はありません。",
                                    hint="見本は " + "・".join(r.name for r in samples()) + " です。")
            new = replace(_read(SAMPLES / sample, SAMPLE), name=name, source=USER)
        else:
            new = Registration(name=name, title=name, document=f"# {name}\n", tools=("*",))
    _check(new)
    _write(new)
    return new


def update(name: str, *, document: str | None = None, **fields) -> Registration:
    """登録の設定（FIELDS）・文書を変える。見本だけの名前なら、ユーザーの登録として写してから変える（見本は変えない）。"""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "変えられない項目です：" + "、".join(sorted(unknown)))
    current = load(name)
    for key in ("children", "tools"):
        if key in fields:
            fields[key] = tuple(fields[key])
    new = replace(current, source=USER, **fields)
    if document is not None:
        new = replace(new, document=document)
    _check(new)
    _write(new)
    return new


def remove(name: str) -> Registration:
    """ユーザーの登録を消す（同じ名前の見本があれば、それがまた使われる）。見本は消せない。"""
    _check_name(name)
    if not (user_root() / name / SETTINGS_FILE).is_file():
        if (SAMPLES / name / SETTINGS_FILE).is_file():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"「{name}」は ECOBuild の見本なので消せません。")
        raise _unknown(name)
    removed = load(name)
    if not (SAMPLES / name / SETTINGS_FILE).is_file():    # 見本に戻るなら、名前は残る
        users = [r.name for r in list_registrations() if r.name != name and name in r.children]
        if users:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"「{name}」を子として起動できる登録があります：" + "、".join(users),
                                hint="先にそれらの children から外してください。")
    shutil.rmtree(user_root() / name)
    return removed


def _check(new: Registration) -> None:
    """保存する前の確かめ：子の名前が分かる・子が自分より強くない。new を子に持つ登録にとっても、new が強すぎない。"""
    if not new.title.strip():
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "表示名（title）が空です。")
    if new.max_children < 0:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "子の数の上限（max_children）は 0 以上です。")
    known = {r.name: r for r in list_registrations()}
    known[new.name] = new
    missing = [child for child in new.children if child not in known]
    if missing:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "知らない登録の名前です：" + "、".join(missing),
                            hint="登録は ecobuild agent registry list で見られます。")
    strong = [child for child in new.children if stronger(known[child], new)]
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


def _folders(root: Path) -> list[Path]:
    try:
        return sorted(p for p in root.iterdir() if _NAME.match(p.name) and (p / SETTINGS_FILE).is_file())
    except OSError:
        return []


def _users() -> list[Registration]:
    return [_read(folder, USER) for folder in _folders(user_root())]


def _read(folder: Path, source: str) -> Registration:
    try:
        data = tomllib.loads((folder / SETTINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{folder / SETTINGS_FILE} を読めません。",
                            details=str(error)) from error
    try:
        document = (folder / DOCUMENT_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        document = ""
    except (OSError, UnicodeDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{folder / DOCUMENT_FILE} を読めません。",
                            details=str(error)) from error

    def strings(key):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{folder / SETTINGS_FILE} の {key} は文字の並びです。")
        return tuple(value)

    try:
        return Registration(
            name=folder.name, title=str(data.get("title") or folder.name), document=document,
            human_start=bool(data.get("human_start", False)), model=str(data.get("model", "")),
            children=strings("children"), max_children=int(data.get("max_children", 0)), tools=strings("tools"),
            first_prompt=str(data.get("first_prompt", "")), source=source)
    except (TypeError, ValueError) as error:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{folder / SETTINGS_FILE} の値が読めません。",
                            details=str(error)) from error


def _write(registration: Registration) -> None:
    folder = user_root() / registration.name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SETTINGS_FILE).write_text(_toml(registration), encoding="utf-8")
    (folder / DOCUMENT_FILE).write_text(registration.document, encoding="utf-8")


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
