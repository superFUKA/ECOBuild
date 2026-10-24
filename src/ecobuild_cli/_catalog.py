"""コマンドの一覧（ecobuild --help --json）：コマンドの説明・引数・オプションを、エージェントやGUIが読めるJSONで出す。

- ecobuild --help --json：共通のコマンドと、型ごとのコマンド（型のcliパッケージにあるもの）のすべて。
- ecobuild <コマンド>... --help --json：そのコマンド（今いるモジュールの型のコマンドも含む）だけ。ほかの型のコマンド
  （モジュールの外・型の違うモジュールの中で、型のコマンドを指定した）は、ない名前ではなく not_supported で、どの型の
  モジュールの中で使えるかを言う（コマンドを実行したときと同じ）。
実行できるコマンドには重さ（effect：read・change・confirm・human。_effects）と、エージェントに許すか（agent）を付ける。
- agent：コマンドのファイルの先頭の定数 AGENT（read・change・owner）。書いていなければ null（エージェントのツールにしない）。
  owner はタスクの持ち主にだけ渡すもの（ブランチを変える commit・push・submit・sync 等）。import せずに AST で読む。
- 引数・オプションには、Python の引数の名前（param。--brief-dir → brief_dir）も付ける（エージェントのツールの入力の名前）。
--json と --help（どのコマンドにもある）は、一覧に入れない。
オプションは names・help・flag・required・multiple・type（bool・str・int・float）・negative（真偽のオプションの否定形。
なければ null）・choices（選べる値。なければ null）、既定値があれば default（真偽のオプションはいつも）。
説明に「例：」の段落があれば、その中の ecobuild で始まる行を examples に。
全体（ecobuild --help --json）には、誤りの種類の一覧（errors：code・retryable。_errors）、今いるモジュールの型
（type。モジュールの外なら null）、--json の結果の形（output：標準出力の JSON のキー）と標準エラーのイベントの形
（events：_events）も入れる。
"""

from __future__ import annotations

import ast
import functools
import inspect
from pathlib import Path
from typing import Any, Callable

import click

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import REGISTRY

from . import _effects, _errors, _events, _help, _output, _types

COMMON_OPTIONS = ("--json", "--help")
AGENT_MARKS = ("read", "change", "owner")     # コマンドのファイルの AGENT に書ける値


def emit(build_cli: Callable[..., click.Command], path: list[str], sections: dict[tuple[str, ...], tuple]) -> int:
    """一覧のJSONを1つ出す。ない名前を指定したら usage_error と同じ形で失敗する（終了コード2）。"""
    if path:
        cli = build_cli()
        command, ctx = _find(cli, path)
        owners = _types.owners(command)
        if owners:
            return _unavailable(path, owners)
        if command is None:
            return _output.usage_error(f"不明なコマンドです: '{' '.join(path)}'", True,
                                       hint="ecobuild --help で使い方を確認してください。")
        result = _node(command, ctx, tuple(path), sections)
    else:
        result = catalog(build_cli, sections)
    _print(result, None, path)
    return 0


def catalog(build_cli: Callable[..., click.Command], sections: dict[tuple[str, ...], tuple]) -> dict:
    """共通のコマンドと、型ごとのコマンド（型の名前 → その型だけにあるコマンド・共通のグループに足すコマンド）。"""
    common = build_cli(None)
    ctx = click.Context(common, info_name="ecobuild")
    types = {}
    for name, entry in REGISTRY.entries().items():
        found = _types.package(name)
        if found is None:
            continue
        routes = _types.routes(found)
        cli = build_cli(name)
        typed_ctx = click.Context(cli, info_name="ecobuild")
        types[name] = {"description": entry.description,
                       "commands": _children(cli, typed_ctx, (), sections, routes, common)}
    from . import _extensions
    names = {c["name"] for c in _children(common, ctx, (), {})}
    extensions = [{"name": n, "path": path, "help": f"ecobuild {n} --help --json"}
                  for n, path in sorted(_extensions.available().items()) if n not in names]
    return {"commands": _children(common, ctx, (), sections), "types": types, "extensions": extensions,
            "errors": _errors.codes(), "type": _types.current(Path.cwd()), "output": OUTPUT_KEYS,
            "events": _events.schema()}


# --json の結果（標準出力の JSON。どのコマンドでも同じ形）のキー
OUTPUT_KEYS = {
    "ok": "成功したか",
    "command": "実行したコマンド（task start 等）",
    "module": "対象のモジュールの場所（なければ null）",
    "result": "結果（コマンドごとの形。失敗なら null）",
    "notices": "知らせ（成功したが知らせておくこと）の文の一覧",
    "error": "誤り（{code, message, hint, details, retryable}。成功なら null）",
    "log": "このコマンドのログ（{run：ログの行の run, file：その行のあるファイル}。ログを書いていなければ null）",
}


def _find(cli: click.Command, path: list[str]) -> tuple[click.Command | None, click.Context | None]:
    command, ctx = cli, click.Context(cli, info_name="ecobuild")
    for name in path:
        if not isinstance(command, click.Group):
            return None, None
        child = command.get_command(ctx, name)
        if _types.owners(child):
            return child, None        # ほかの型のコマンド（その下の名前は読まない）
        if child is None or child.hidden:
            return None, None
        command, ctx = child, click.Context(child, info_name=name, parent=ctx)
    return command, ctx


def _unavailable(path: list[str], owners: list[str]) -> int:
    """ほかの型のコマンドの一覧を求められた：この場所では使えないこと（どの型のモジュールの中で使えるか）。終了コードは1。"""
    command, kinds, here = " ".join(path), "・".join(owners), _types.current(Path.cwd())
    where = f"このモジュールの型：{here}" if here else "モジュールの外"
    error = EcoBuildError(ErrorCode.NOT_SUPPORTED, f"{command} は型 {kinds} のモジュールのコマンドです。この場所では使えません"
                                                   f"（{where}）。",
                          hint=f"型 {kinds} のモジュールの中（または ecobuild -C <モジュールのフォルダ>）で "
                               f"ecobuild {command} --help --json を実行すると、説明が出ます。")
    _output.log_error(f"help {command}", error)
    _print(None, _output.error_data(error), path)
    return _output.FAILURE


def _children(group: click.Group, ctx: click.Context, path: tuple[str, ...], sections, routes=None,
              common: click.Group | None = None) -> list[dict]:
    """group の下のコマンド。routes を渡したら、その道筋にあるもの（型のコマンド）だけ。"""
    titles = {name: title for title, names in sections.get(path, ()) for name in names}
    result = []
    for name in group.list_commands(ctx):
        route = (*path, name)
        if routes is not None and route not in routes:
            continue
        command = group.get_command(ctx, name)
        if command is None or command.hidden:
            continue
        child_ctx = click.Context(command, info_name=name, parent=ctx)
        node = _node(command, child_ctx, route, sections, routes)
        if titles:
            node["section"] = titles.get(name, "その他")
        if routes is not None and isinstance(command, click.Group) and _has(common, route):
            node["extends"] = True      # 共通のグループ（module・profile 等）に、型がコマンドを足している
        result.append(node)
    if titles:      # 見出しの順（ecobuild task --help と同じ）。見出しにないものは後ろ
        order = [name for _, names in sections[path] for name in names]
        result.sort(key=lambda node: order.index(node["name"]) if node["name"] in order else len(order))
    return result


def _has(cli: click.Group | None, route: tuple[str, ...]) -> bool:
    command = cli
    for name in route:
        command = command.commands.get(name) if isinstance(command, click.Group) else None
    return command is not None


def _node(command: click.Command, ctx: click.Context, path: tuple[str, ...], sections, routes=None) -> dict:
    node: dict[str, Any] = {"name": path[-1] if path else "ecobuild", "path": " ".join(path),
                            "summary": command.get_short_help_str(limit=200), "help": _help_text(command.help)}
    if examples(node["help"]):
        node["examples"] = examples(node["help"])
    runnable, lazy = command, command
    if isinstance(command, click.Group):
        node["commands"] = _children(command, ctx, path, sections, routes)
        lazy = getattr(command, "default_command", None)    # グループそのものも実行できる（sync 等）
        runnable = lazy._load() if lazy is not None else None
        if runnable is not None and runnable.help and runnable.help != command.help:
            node["default_help"] = _help_text(runnable.help)
    node["runnable"] = runnable is not None
    if runnable is not None:
        node["effect"] = _effects.effect(" ".join(path))    # 見る・変える・確認が要る・人がする（_effects）
        node["agent"] = agent_mark(lazy)
        params = runnable.get_params(ctx)
        node["arguments"] = [_argument(p) for p in params if isinstance(p, click.Argument)]
        node["options"] = [_option(p, ctx) for p in params
                           if isinstance(p, click.Option) and not set(p.opts) & set(COMMON_OPTIONS)]
    return node


def agent_mark(command: click.Command) -> str | None:
    """コマンドのファイル（グループなら __init__.py）の先頭の AGENT。書いていない・場所が分からなければ None。"""
    source = getattr(getattr(command, "descriptor", None), "source", None)
    return _agent_constant(Path(source.path)) if source is not None else None


@functools.lru_cache(maxsize=None)
def _agent_constant(path: Path) -> str | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AGENT" for t in node.targets)                 and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    return None


def _help_text(text: str | None) -> str:
    """docstring の字下げと、click の段落の印（\\b の行）を取る。"""
    lines = [line for line in inspect.cleandoc(text or "").splitlines() if line.strip() != "\b"]
    return "\n".join(lines).strip()


def examples(help_text: str) -> list[str]:
    """説明の「例：」の段落（次の空行まで）の、ecobuild で始まる行。"""
    found, inside = [], False
    for line in help_text.splitlines():
        text = line.strip()
        if text.startswith(("例：", "例:")):
            inside = True
            text = text[2:].strip()
        elif not text:
            inside = False
        if inside and text.startswith("ecobuild "):
            found.append(text)
    return found


def _type_name(parameter: click.Parameter) -> str:
    """値の型：bool・int・float・str（CLIFrameWork の引数の型と同じ）。"""
    if getattr(parameter, "is_flag", False) or isinstance(parameter.type, click.types.BoolParamType):
        return "bool"
    if isinstance(parameter.type, click.types.IntParamType):
        return "int"
    if isinstance(parameter.type, click.types.FloatParamType):
        return "float"
    return "str"


def _argument(parameter: click.Argument) -> dict:
    return {"name": parameter.human_readable_name, "param": parameter.name,
            "help": getattr(parameter, "help_text", None) or "",
            "required": parameter.required, "multiple": parameter.nargs == -1 and not _help.single_argument(parameter),
            "type": _type_name(parameter)}


def _option(parameter: click.Option, ctx: click.Context) -> dict:
    result: dict[str, Any] = {"names": list(parameter.opts), "param": parameter.name, "help": parameter.help or "",
                              "flag": bool(parameter.is_flag), "required": parameter.required,
                              "multiple": bool(parameter.multiple), "type": _type_name(parameter),
                              "negative": parameter.secondary_opts[0] if parameter.secondary_opts else None,
                              "choices": list(parameter.type.choices) if isinstance(parameter.type, click.Choice)
                              else None}
    default = parameter.default
    if parameter.is_flag:
        result["default"] = bool(default)
    else:
        try:
            result["value"] = parameter.make_metavar(ctx)
        except TypeError:                     # click 8.1 以前
            result["value"] = parameter.make_metavar()
        # 既定はいつも書く（ない・空の文字列なら null）
        result["default"] = None if default in (None, "", (), []) or callable(default) else \
            default if isinstance(default, (str, int, float, bool)) else str(default)
    return result


def _print(result: Any, error: dict | None, path: list[str]) -> None:
    _output.print_document({"ok": error is None, "command": " ".join(["help", *path]), "module": None,
                            "result": result, "notices": [], "error": error})
