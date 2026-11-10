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


_HEAVIER = ("read", "change", "confirm")  # 重さの軽い順（型で違えば、重い方に合わせる）


def merge(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同じ名前（path）のコマンドを1つにまとめる（約束の形になった後の一覧で）。

    型（cpp・python・generic）ごとに同じ名前のコマンドがあり、受ける引数が型で違う（C++ だけの `--project`・
    `file add --template` 等）。まとめた1つは、どれかの型が受ける引数を全部受ける。そのモジュールの型が受けない
    引数を渡したら、ecobuild が断る。必須なのは、どの型でも必須の引数だけ。
    """
    merged: dict[Any, dict[str, Any]] = {}
    for node in nodes:
        known = merged.get(node.get("path"))
        if known is None:
            merged[node.get("path")] = {**node, "parameters": [dict(item) for item in node["parameters"]],
                                        "commands": list(node["commands"])}
            continue
        theirs = {item["name"]: item for item in node["parameters"]}
        for item in known["parameters"]:  # 型によってはない・任意の引数は、任意
            item["required"] = item["required"] and bool(theirs.get(item["name"], {}).get("required"))
        names = {item["name"] for item in known["parameters"]}
        known["parameters"] += [{**item, "required": False} for item in node["parameters"] if item["name"] not in names]
        known["commands"] += node["commands"]
        known["runnable"] = known["runnable"] or node["runnable"]
        if known["effect"] in _HEAVIER and node["effect"] in _HEAVIER:
            known["effect"] = max(known["effect"], node["effect"], key=_HEAVIER.index)
        else:
            known["effect"] = known["effect"] or node["effect"]
    for node in merged.values():
        node["commands"] = merge(node["commands"])
    return list(merged.values())


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

    def dry_run(self, name: str, args: dict[str, Any]) -> str:
        """確認に出す「前もっての確かめ」。人が `--dry-run` を付けて打ったときに出る文を、そのまま出す。

        ecobuild の --dry-run の結果（JSON）は、コマンドごとに形の違う辞書で、文字の `preview` を持たない。
        人向けの文は ecobuild が自分で組み立てる（--json なしの出力）ので、それを使う。できなかったときは、その理由の文。
        """
        import os
        import subprocess

        from guiframework import GuiFrameworkError

        try:
            line = self.command_line(name, args, ["dry_run"])
            # 人が打つのと同じにする：機械向けの --json（オプションの後ろ、位置引数の「--」の前に1つだけ付く）を外す
            at = next(index for index, word in enumerate(line)
                      if word == "--json" and (index + 1 == len(line) or line[index + 1] == "--"))
            env = {**os.environ, **self.extra_env}
            env.setdefault("PYTHONIOENCODING", "utf-8")
            done = subprocess.run(line[:at] + line[at + 1:], stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8",
                                  errors="replace", timeout=self.timeout, env=env)
        except (OSError, subprocess.SubprocessError, StopIteration, GuiFrameworkError):
            return ""
        return (done.stdout if done.returncode == 0 else done.stderr or done.stdout).strip()

    def catalog(self) -> dict[str, Any]:
        data = self.ask(["--help", "--json"])
        result = data.get("result") or {}
        commands = list(result.get("commands") or [])
        # 型ごとのコマンド（build・test・file 等）も足す。中継地点は1つでどの型のモジュールも扱うので、全部の型の分を足す
        # （同じ名前のコマンドは1つにまとめ、引数は合わせる。その型でないモジュールで呼べば、ecobuild が「使えない」と答える）
        for kind in sorted(result.get("types") or {}):
            commands += result["types"][kind].get("commands") or []
        return {"name": "ecobuild", "path": "", "runnable": False, "effect": None, "parameters": [],
                "commands": merge([convert(node) for node in commands])}
