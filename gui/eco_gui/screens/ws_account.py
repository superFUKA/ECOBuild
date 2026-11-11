"""作業空間 › アカウント：この作業空間で使う GitHub のアカウントを見る・結び付ける・外す（窓の中に重ねて開く）。

結び付けると、この作業空間の ecobuild・git push・コミットの作成者が、そのアカウントになる（ecobuild account use）。
先に、そのアカウントで gh auth login しておく。鍵・トークンは、ここでは扱わない。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "この作業空間のアカウント", "width": 600, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "now", "list_title", "list", "other", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "この作業空間のアカウント", "heading": True}},
        {"id": "now", "part": "facts", "props": {
            "items": [{"key": "login", "label": "今のアカウント"}, {"key": "workspace_account", "label": "この作業空間だけの結び付け"}, {"key": "role", "label": "役割"}],
            "labels": {"workspace_account": {"": "なし（gh の使用中のアカウントで動きます）"},
                       "role": {"admin": "管理者", "maintain": "管理", "write": "書き込み", "triage": "整理", "read": "読み取り"}}}},
        {"id": "list_title", "part": "note", "props": {"tone": "section", "text": "この PC でログインしてあるアカウント"}},
        {"id": "list", "part": "table", "props": {
            "columns": [{"key": "login", "label": "アカウント"}, {"key": "active", "label": "gh"}], "key": "login",
            "labels": {"active": {"true": "使用中", "false": ""}}, "tones": {"active": {"true": "ok"}},
            "actions": [{"name": "use", "label": "この作業空間で使う"}], "empty_text": "ログインしてあるアカウントはありません（gh auth login）。"}},
        {"id": "other", "layout": "row", "children": ["other_name", "other_use"]},
        {"id": "other_name", "part": "text-input", "props": {"title": "ほかのアカウント（先に、そのアカウントで gh auth login しておく）", "placeholder": "例：my-ai-account"}},
        {"id": "other_use", "part": "button", "props": {"label": "結び付ける"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["clear", "close"]},
        {"id": "clear", "part": "button", "props": {"label": "結び付けを外す", "hint": "gh の使用中のアカウントに戻す（ecobuild account use --clear）"}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
    ],
    "bindings": [
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "now.data"},
        {"read": "account list", "args": {"module": {"arg": "module"}}, "to": "list.rows"},
        {"on": "list.action", "when": {"action": "use"}, "run": "account use", "args": {"module": {"arg": "module"}, "account": {"payload": "id"}},
         "notify": "この作業空間のアカウントを変えました。"},
        {"on": "other_name.changed", "set": {"other_account": {"payload": "text"}}},
        {"on": "other_use.pressed", "run": "account use", "args": {"module": {"arg": "module"}, "account": {"value": "other_account"}}, "require": ["account"],
         "notify": "この作業空間のアカウントを変えました。"},
        {"on": "clear.pressed", "run": "account use", "args": {"module": {"arg": "module"}, "clear": True}, "notify": "結び付けを外しました。"},
        {"on": "close.pressed", "close": True},
    ],
}
