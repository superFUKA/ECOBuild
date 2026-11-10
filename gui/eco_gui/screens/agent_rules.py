"""モジュール › エージェント › 全エージェント共通の文：このモジュールで起動するどのエージェントにも渡す文。見る・書き直して保存。"""

ARGS = {"module": "."}  # モジュールのフォルダー（保存するときは、タスクブランチの作業空間）

SCREEN = {
    "root": "page",
    "window": {"title": "全エージェント共通の文", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["sub", "head", "where", "state", "common", "save"]},
        {"id": "nav", "screen": "menu", "args": {"current": "agents", "module": {"arg": "module"}}},
        {"id": "sub", "screen": "agents-menu", "args": {"current": "agent-rules", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "全エージェント共通の文", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "where", "part": "note", "props": {"text": "このモジュールで起動するどのエージェントにも、役の文書の後に渡します（基準・仕事の分け方の決まり 等）。保存は、タスクブランチの作業空間で実行するとコミットされ、提出して取り込まれると効きます。"}},
        {"id": "state", "part": "facts", "props": {
            "items": [{"key": "root", "label": "表示している場所"}, {"key": "in_force", "label": "効く版"}, {"key": "pending", "label": "状態"}],
            "labels": {"pending": {"true": "まだ効いていない（取り込まれると効く）", "false": "効いている"}},
        }},
        {"id": "common", "part": "text-area", "props": {
            "title": "共通の文（空にして保存すると、消します）", "rows": 16,
            "placeholder": "例：前後がつながった段階（調べる→設計→実装）は分けずに自分で進める。子に任せるのは、互いに独立した仕事と検証だけ。"}},
        {"id": "save", "part": "button", "props": {"label": "保存してコミット", "primary": True, "hint": "書き直してから押します"}},
    ],
    "bindings": [
        {"read": "agent rules show", "args": {"module": {"arg": "module"}}, "to": "state.data"},
        {"read": "agent rules show", "args": {"module": {"arg": "module"}}, "to": "common.text", "from": "common"},
        {"on": "reload.pressed", "refresh": True},
        # 書き直した文 → 共有の値 → ecobuild agent rules set -（文は標準入力で渡る。長くても、コマンドの行の上限に掛からない）
        {"on": "common.changed", "set": {"rules_common": {"payload": "text"}}},
        {"on": "save.pressed", "run": "agent rules set", "args": {"module": {"arg": "module"}, "common": {"value": "rules_common"}},
         "set": {"rules_common": None}},
    ],
}
