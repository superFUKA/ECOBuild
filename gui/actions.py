"""GUIの操作の一覧：画面のボタンも、外から呼ぶ口（ecobuild gui・MCP）も、ここにある操作を名前で呼ぶ。

ボタンと口が同じ操作を通るので、片方にだけある操作はできない（tests/test_actions.py が画面のコードを確かめる）。

- run：ecobuild のコマンドを、GUIを通して実行する。ボタンが行うことの大半はこれ（引数は ecobuild のコマンドそのもの。
  一覧と使い方は ecobuild --help --json）。開いている画面には、実行したことが伝わる（別の画面・エージェントが実行しても）。
- そのほか：GUIにしかない操作（画面を開く・移る、フォルダ・Visual Studio で開く、知らせを出す）。
- agents・agent-…：エージェントの窓（Electron の GUI だけ。タブ＝作業空間のエージェント）。番号はタブの番号（0 はオペレーター）。

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
    # 重さ（ecobuild のコマンドと同じ：read・change・confirm）。エージェント（オペレーター）は confirm を人に聞いてから使う
    effect: str = "change"

    def describe(self) -> dict:
        return {"name": self.name, "summary": self.summary, "help": self.help, "effect": self.effect,
                "params": [{"name": p.name, "help": p.help, "kind": p.kind, "required": p.required,
                            **({"choices": list(p.choices)} if p.choices else {})} for p in self.params]}


PAGES = ("workspace", "tasks", "submissions", "manage", "modinfo", "settings", "help")
# 「モジュール」の画面のタブと、「設定」の画面のタブ（profiles・general・templates）。branches・members・ci は「管理」の画面の「ブランチ」・「メンバー」・「CI」のタブへ移る
TABS = ("home", "projects", "deps", "branches", "members", "ci", "profiles", "general", "templates", "container")

ACTIONS: dict[str, Action] = {a.name: a for a in (
    Action("run", "ECOBuild のコマンドを、GUIを通して実行します（開いている画面に反映されます）。",
           "引数は ecobuild のコマンドそのもの（例：task start 12）。コマンドの一覧と使い方は ecobuild --help --json。"
           "確認が要るコマンドは confirmation_required で止まるので、内容を確かめてから --yes を付けて実行し直します。",
           (Param("args", "ecobuild の引数（例：[\"task\", \"start\", \"12\"]）", "array", True),
            Param("dir", "実行する場所（モジュール・作業空間のフォルダ。省略時は ecobuild gui を実行したフォルダ）"),
            Param("stdin", "標準入力に渡す文字列（コミットメッセージ等を標準入力で渡すコマンド用）")),
           effect="confirm"),   # 中のコマンドの重さは分からない（エージェントは ecobuild を直接使う）
    Action("open", "GUIの画面（ハブ・モジュールの開発環境の窓）を開くか、そこへ移ります。「〇〇を開いて」「〇〇の開発環境」はこれ（module に作業空間の場所か名前）。",
           "module を省くとハブ。module はモジュールのフォルダ（このPCの作業空間）か、ハブの一覧にあるモジュール名。"
           "開いている窓があればそこで移り、なければ開きます。",
           (Param("module", "モジュール（フォルダか名前）。省くとハブ"),
            Param("page", "モジュールの窓の画面", choices=PAGES),
            Param("tab", "「モジュール」・「設定」の画面のタブ（タブのある画面へ移る）", choices=TABS),
            Param("task", "タスク管理で選ぶタスクの番号", "integer"),
            Param("command", "ヘルプで説明を出す ecobuild のコマンド（例：task start）"))),
    Action("folder", "フォルダ・ファイルを、既定のアプリ（フォルダならエクスプローラー）で開きます。「フォルダを」「エクスプローラーで」と言われたときだけ。", "",
           (Param("dir", "場所（作業空間のフォルダ）", required=True),
            Param("path", "その中のファイル・フォルダ（省略時は dir そのもの）"),
            Param("reveal", "ファイルを開かず、エクスプローラーで選んだ状態で見せる", "boolean"))),
    Action("vs", "Visual Studio で開きます（作業空間のソリューション、または その中のファイル）。「VS で」「Visual Studio で」と言われたときだけ（ただの「開いて」「開発環境」は open）。", "",
           (Param("dir", "作業空間のフォルダ", required=True),
            Param("path", "開くファイル（省略時はソリューション）"),
            Param("version", "Visual Studio の版（2026・2022。既定 2026）", choices=("2026", "2022")))),
    Action("notify", "開いているGUIの画面に知らせを出します（エージェントから人へ）。", "",
           (Param("message", "知らせる文", required=True),
            Param("kind", "種類", choices=("ok", "info", "bad")))),
    # エージェントの窓（Electron の GUI：agents/。Edge の窓では使えない）
    Action("agents", "エージェントの窓のタブの一覧（番号・名前・作業空間・状態・最後の返答・最小化しているか）。", effect="read"),
    Action("agent-open", "作業空間のエージェントを、エージェントの窓のタブで開きます（あれば前に出す）。",
           "タスクブランチの作業空間でだけ起動できます。作業空間がコンテナなら、その中で確認なしに動きます。",
           (Param("dir", "作業空間のフォルダ", required=True),
            Param("name", "タブの名前（省略時はフォルダ名）"),
            Param("agent", "起動するエージェントのコマンド（省略時は claude）"))),
    Action("agent-send", "タブのエージェントに文字を送ります（enter で送信まで）。",
           "エージェントはそれを人からの指示として実行します。人が送ることをはっきり頼んだときだけ使います。",
           (Param("tab", "タブの番号", "integer", True),
            Param("text", "送る文字", required=True),
            Param("enter", "最後に Enter を押して送信する（既定 true）", "boolean")), effect="requested"),
    Action("agent-show", "タブを前に出します（最小化していれば戻す）。", "", (Param("tab", "タブの番号", "integer", True),)),
    Action("agent-close", "タブを閉じます（そのエージェントは終わります）。", "", (Param("tab", "タブの番号", "integer", True),),
           effect="confirm"),
    Action("agent-rename", "タブの名前を変えます（Claude の会話の名前もそろえます）。", "",
           (Param("tab", "タブの番号", "integer", True), Param("name", "新しい名前", required=True))),
    Action("agent-restart", "タブのエージェントを起動し直します。", "",
           (Param("tab", "タブの番号", "integer", True),
            Param("continue", "前の会話の続きから（既定 false：新しい会話）", "boolean"))),
    Action("agent-model", "タブのエージェントのモデルを変えます（待機中になってから /model を送ります）。", "",
           (Param("tab", "タブの番号", "integer", True), Param("model", "opus・sonnet・haiku など", required=True))),
    Action("agents-window", "エージェントの窓を最小化する（右下の小さな表示に）か、元に戻します。", "",
           (Param("state", "minimize・restore", required=True, choices=("minimize", "restore")),)),
    Action("operator", "オペレーター（裏で動いている ECOBuild の操作係）を、タブで開くか裏に戻します。", "",
           (Param("state", "show（タブで開く）・hide（裏に戻す）", required=True, choices=("show", "hide")),)),
    # 状況を見る（画面のボタンにはないが、エージェントが今の様子を知るために使う）
    Action("windows", "開いているGUIの窓と、それぞれが今表示しているもの（モジュール・画面・タブ・選んだタスク・作業空間）。"
                      "前に出た順で、人が今見ている窓（最後に前に出た窓）に looking: true。",
           effect="read"),
    Action("activity", "GUIで最近行われたこと（実行したコマンドと結果・知らせ・画面の移動。誰が行ったか付き）。", "",
           (Param("count", "いくつ（既定 30）", "integer"),), effect="read"),
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


# 話し言葉の例（エージェント・オペレーターが頼みを操作に読み替えるため。ecobuild gui --help --json の examples）
EXAMPLES = (
    ("「ECOSTL を開いて」「ECOSTL の開発環境出して」「エコ STL 見せて」", "ecobuild gui open --module C:/ECO/ECOSTL（場所は ecobuild workspace list で探す）"),
    ("「ハブ出して」「ハブに戻って」", "ecobuild gui open"),
    ("「これ提出して」「今のタスク」「この画面の」（モジュールの名前を言わない）",
     "ecobuild gui windows --json の looking: true の窓（module・タスク・作業空間）を対象に。ハブなら直前の会話から"),
    ("「ECOSTL でエージェント起動して」「ECOSTL の AI 開いて」「エコ STL で作業始めて」", "ecobuild gui agent-open --dir C:/ECO/ECOSTL（タスクブランチの作業空間でだけ）"),
    ("「みんな今どうなってる？」「エージェントの様子は？」", "ecobuild gui agents を読み、各タブの状態・最後の返答を1〜2行ずつ"),
    ("「1番に、テストを実行してって送って」", "ecobuild gui agent-send --tab 1 --text \"テストを実行して\"（「送って」「伝えて」と言われたときだけ。文はユーザーの言葉のまま）"),
    ("「1番を前に出して」「2番見せて」", "ecobuild gui agent-show --tab 1"),
    ("「2番の名前をレビューにして」", "ecobuild gui agent-rename --tab 2 --name レビュー"),
    ("「2番を再起動して」「レビューを起動し直して」／「続きから起動し直して」", "ecobuild gui agent-restart --tab 2 ／ --tab 2 --continue（名前で言われたら ecobuild gui agents で番号を探す）"),
    ("「3番のモデルをソネットに」", "ecobuild gui agent-model --tab 3 --model sonnet"),
    ("「1番と4番閉じて」", "ecobuild gui agent-close --tab 4 のあと --tab 1（[確認]。閉じると後ろの番号が詰まるので、番号の大きい方から）"),
    ("「エージェントの窓しまって」「最小化して」／「戻して」", "ecobuild gui agents-window --state minimize ／ restore"),
    ("「VS で開いて」「ビジュアルスタジオで ECOSTL」", "ecobuild gui vs --dir C:/ECO/ECOSTL"),
    ("「ECOSTL のフォルダ開いて」", "ecobuild gui folder --dir C:/ECO/ECOSTL"),
    ("「ECOSTL のタスク管理出して」", "ecobuild gui open --module C:/ECO/ECOSTL --page tasks"),
)


def catalog() -> list[dict]:
    return [a.describe() for a in ACTIONS.values()]
