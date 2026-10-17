"""GUIの操作の一覧：画面のボタンも、外から呼ぶ口（ecobuild gui・MCP）も、ここにある操作を名前で呼ぶ。

ボタンと口が同じ操作を通るので、片方にだけある操作はできない（tests/test_actions.py が画面のコードを確かめる）。

- run：ecobuild のコマンドを、GUIを通して実行する。ボタンが行うことの大半はこれ（引数は ecobuild のコマンドそのもの。
  一覧と使い方は ecobuild --help --json）。開いている画面には、実行したことが伝わる（別の画面・エージェントが実行しても）。
- そのほか：GUIにしかない操作（画面を開く・移る、フォルダ・Visual Studio で開く、知らせを出す）。

呼ぶ側（origin）が画面なら、画面の中で行うこと（窓を開く・移る・開く）はその画面が行う（答えの "apply"）。
外（ecobuild gui・MCP）から呼んだときは、開いている画面に頼み（events）、なければサーバーが行う。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    name: str
    help: str
    kind: str = "string"          # string・integer・boolean・array（文字列の並び）
    required: bool = False
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    name: str
    summary: str
    help: str = ""
    params: tuple[Param, ...] = field(default_factory=tuple)

    def describe(self) -> dict:
        return {"name": self.name, "summary": self.summary, "help": self.help,
                "params": [{"name": p.name, "help": p.help, "kind": p.kind, "required": p.required,
                            **({"choices": list(p.choices)} if p.choices else {})} for p in self.params]}


PAGES = ("workspace", "tasks", "modinfo", "settings", "help")
# 「モジュール」の画面のタブと、「設定」の画面のタブ（profiles・general・templates）
TABS = ("home", "projects", "deps", "branches", "profiles", "general", "templates")

ACTIONS: dict[str, Action] = {a.name: a for a in (
    Action("run", "ECOBuild のコマンドを、GUIを通して実行します（開いている画面に反映されます）。",
           "引数は ecobuild のコマンドそのもの（例：task start 12）。コマンドの一覧と使い方は ecobuild --help --json。"
           "確認が要るコマンドは confirmation_required で止まるので、内容を確かめてから --yes を付けて実行し直します。",
           (Param("args", "ecobuild の引数（例：[\"task\", \"start\", \"12\"]）", "array", True),
            Param("dir", "実行する場所（モジュール・作業空間のフォルダ。省略時は ecobuild gui を実行したフォルダ）"),
            Param("stdin", "標準入力に渡す文字列（コミットメッセージ等を標準入力で渡すコマンド用）"))),
    Action("open", "GUIの画面を開くか、そこへ移ります。",
           "module を省くとハブ。module はモジュールのフォルダ（このPCの作業空間）か、ハブの一覧にあるモジュール名。"
           "開いている窓があればそこで移り、なければ開きます。",
           (Param("module", "モジュール（フォルダか名前）。省くとハブ"),
            Param("page", "モジュールの窓の画面", choices=PAGES),
            Param("tab", "「モジュール」・「設定」の画面のタブ（タブのある画面へ移る）", choices=TABS),
            Param("task", "タスク管理で選ぶタスクの番号", "integer"),
            Param("command", "ヘルプで説明を出す ecobuild のコマンド（例：task start）"))),
    Action("folder", "フォルダ・ファイルを、既定のアプリ（フォルダならエクスプローラー）で開きます。", "",
           (Param("dir", "場所（作業空間のフォルダ）", required=True),
            Param("path", "その中のファイル・フォルダ（省略時は dir そのもの）"),
            Param("reveal", "ファイルを開かず、エクスプローラーで選んだ状態で見せる", "boolean"))),
    Action("vs", "Visual Studio で開きます（作業空間のソリューション、または その中のファイル）。", "",
           (Param("dir", "作業空間のフォルダ", required=True),
            Param("path", "開くファイル（省略時はソリューション）"),
            Param("version", "Visual Studio の版（2026・2022。既定 2026）", choices=("2026", "2022")))),
    Action("notify", "開いているGUIの画面に知らせを出します（エージェントから人へ）。", "",
           (Param("message", "知らせる文", required=True),
            Param("kind", "種類", choices=("ok", "info", "bad")))),
    # 状況を見る（画面のボタンにはないが、エージェントが今の様子を知るために使う）
    Action("windows", "開いているGUIの窓と、それぞれが今表示しているもの（モジュール・画面・タブ・選んだタスク・作業空間）。"),
    Action("activity", "GUIで最近行われたこと（実行したコマンドと結果・知らせ・画面の移動。誰が行ったか付き）。", "",
           (Param("count", "いくつ（既定 30）", "integer"),)),
)}


def check(name: str, params: dict) -> dict:
    """名前と引数を確かめ、型をそろえた引数を返す。誤りなら ValueError（メッセージは日本語）。"""
    action = ACTIONS.get(name)
    if action is None:
        raise ValueError(f"GUIの操作 {name!r} はありません（{'・'.join(ACTIONS)}）。")
    known = {p.name: p for p in action.params}
    unknown = set(params) - set(known)
    if unknown:
        raise ValueError(f"{name} に {'・'.join(sorted(unknown))} は指定できません。")
    result = {}
    for p in action.params:
        value = params.get(p.name)
        if value is None or value == "":
            if p.required:
                raise ValueError(f"{name} には {p.name} が必要です（{p.help}）。")
            continue
        if p.kind == "integer":
            value = int(value)
        elif p.kind == "boolean":
            value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")
        elif p.kind == "array":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"{name} の {p.name} は文字列の並びで指定してください。")
        else:
            value = str(value)
        if p.choices and str(value) not in p.choices:
            raise ValueError(f"{name} の {p.name} は {'・'.join(p.choices)} のどれかです。")
        result[p.name] = value
    return result


def catalog() -> list[dict]:
    return [a.describe() for a in ACTIONS.values()]
