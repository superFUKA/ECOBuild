"""ecobuild の CLI とのつなぎ。

GUIFrameWork が読むコマンドの一覧は、CLIFrameWork の構造化出力の形。今の ecobuild は、自前の形
（arguments と options に分かれた一覧・型ごとのコマンド・「人がする」の重さ）で出すので、ここで約束の形に直す。
ecobuild の CLI を構造化出力に載せ替えたら、この読み替えは要らなくなる。
"""

from __future__ import annotations

from typing import Any

from guiframework import MachineBackend


def convert(node: dict[str, Any]) -> dict[str, Any]:
    """ecobuild の一覧の1件を、約束の形にする。"""
    parameters = [
        {"name": item["param"], "type": item.get("type"), "kind": "argument", "help": item.get("help") or "",
         "required": bool(item.get("required")) and not item.get("multiple"), "variadic": bool(item.get("multiple")),
         "option": None, "negative": None}
        for item in node.get("arguments") or []
    ] + [
        {"name": item["param"], "type": item.get("type"), "kind": "option", "help": item.get("help") or "",
         "required": False, "variadic": False, "option": (item.get("names") or [None])[0], "negative": item.get("negative")}
        for item in node.get("options") or [] if item.get("param") != "json"  # --json は約束の側が付ける
    ]
    effect = node.get("effect")
    return {
        "name": node.get("name"), "path": node.get("path"), "help": node.get("help"),
        "command_help": node.get("summary") or node.get("default_help"),
        "runnable": bool(node.get("runnable")),
        # 「人がする」（human）の重さのコマンドは、窓の前の人に確かめてから実行する
        "effect": "confirm" if effect == "human" else effect,
        "parameters": parameters,
        "commands": [convert(child) for child in node.get("commands") or []],
    }


class EcobuildBackend(MachineBackend):
    """ecobuild とのつなぎ。どのコマンドも、引数 module（モジュールのフォルダー）を受ける。

    ecobuild は「どのモジュールで実行するか」を、コマンドの前の `-C <フォルダー>` で受ける（git -C と同じ）。
    一覧には出ないので、ここで全部のコマンドの引数に足し、呼ぶときに `-C` に直す。
    """

    def commands(self) -> dict[str, dict[str, Any]]:
        specs = super().commands()
        for spec in specs.values():
            spec["args"]["properties"]["module"] = {"type": "string", "description": "モジュールのフォルダー"}
        return specs

    def command_line(self, name: str, args: Any, extra: Any = ()) -> list[str]:
        rest = {key: value for key, value in args.items() if key != "module"}
        line = super().command_line(name, rest, extra)
        module = args.get("module")
        return [*self.argv, "-C", str(module), *line[len(self.argv):]] if module else line

    def catalog(self) -> dict[str, Any]:
        data = self.ask(["--help", "--json"])
        result = data.get("result") or {}
        commands = list(result.get("commands") or [])
        # 型ごとのコマンド（build・test・file 等）も足す。中継地点は1つでどの型のモジュールも扱うので、全部の型の分を足す
        # （同じ名前のコマンドは1つとして扱われる。その型でないモジュールで呼べば、ecobuild が「使えない」と答える）
        for kind in sorted(result.get("types") or {}):
            commands += result["types"][kind].get("commands") or []
        return {"name": "ecobuild", "path": "", "runnable": False, "effect": None, "parameters": [],
                "commands": [convert(node) for node in commands]}
