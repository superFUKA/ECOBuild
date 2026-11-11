"""オペレーター：話し方の設定と、このPCのエージェントの一覧（様子・止める・起こし直す・閉じる・言付け）。

モジュールの外の画面（ハブの窓の左のメニューから開く）。オペレーター・エージェントと対話する窓（端末・会話）は、今の窓のまま。
"""

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild Hub", "width": 1000, "height": 720},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "hub-menu", "args": {"current": "operator"}},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "tabs"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "オペレーター", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "tabs", "layout": "tabs", "props": {"labels": ["エージェント", "オペレーターの話し方"]}, "children": ["agents", "style"]},

        # --- このPCのエージェント（ecobuild agent list・status・children・stop・restart・close・send） ---
        {"id": "agents", "layout": "column", "children": ["list", "selected", "status", "children_title", "children", "send"]},
        {"id": "list", "part": "pick-rows", "props": {
            "columns": [{"key": "title", "label": "役"}, {"key": "name", "label": "名前"}, {"key": "task.number", "label": "タスク"},
                        {"key": "branch", "label": "タスクブランチ"}, {"key": "state", "label": "様子"},
                        {"key": "started_at", "label": "起動した時", "format": "time"},
                        {"key": "replied_at", "label": "最後に返答した時", "format": "time"},
                        {"key": "waiting", "label": "届いていない言付け"}, {"key": "id", "label": "ID"}],
            "key": "id", "selectable": False,
            "actions": [{"name": "show", "label": "見る"}, {"name": "stop", "label": "止める"}, {"name": "restart", "label": "起こし直す"},
                        {"name": "resume", "label": "続きから起こす"}, {"name": "close", "label": "閉じる"}],
            "labels": {"state": {"working": "作業中", "idle": "待機中", "stopped": "止まっている", "starting": "起動中", "unknown": "分からない"},
                       "waiting": {"0": ""}},
            "empty_text": "このPCにエージェントはいません。",
        }},
        {"id": "selected", "part": "note", "props": {"prefix": "選んでいるエージェント："}},
        {"id": "status", "part": "facts", "props": {
            "items": [{"key": "name", "label": "名前"}, {"key": "registration", "label": "登録"}, {"key": "kind", "label": "立場"},
                      {"key": "workspace", "label": "作業空間"}, {"key": "model", "label": "モデル"}, {"key": "state", "label": "様子"},
                      {"key": "doing", "label": "今していること"}, {"key": "waiting", "label": "届いていない言付け"},
                      {"key": "last_reply", "label": "最後の返答"}],
            "labels": {"state": {"working": "作業中", "idle": "待機中", "stopped": "止まっている", "starting": "起動中", "unknown": "分からない"},
                       "kind": {"owner": "タスクの持ち主", "helper": "手伝い"}, "model": {"": "（Claude Code の既定）"}},
        }},
        {"id": "children_title", "part": "note", "props": {"text": "選んだエージェントの子"}},
        {"id": "children", "part": "table", "props": {
            "columns": [{"key": "title", "label": "役"}, {"key": "name", "label": "名前"}, {"key": "branch", "label": "タスクブランチ"},
                        {"key": "state", "label": "様子"}, {"key": "reported", "label": "報告"}, {"key": "last_reply", "label": "最後の返答"}],
            "key": "id",
            "actions": [{"name": "show", "label": "見る"}],
            "labels": {"state": {"working": "作業中", "idle": "待機中", "stopped": "止まっている", "starting": "起動中", "unknown": "分からない"},
                       "reported": {"true": "あり", "false": ""}},
            "empty_text": "子はいません（「見る」で選ぶと出ます）。",
        }},
        {"id": "send", "layout": "row", "children": ["message", "do_send"]},
        {"id": "message", "part": "text-input", "props": {"title": "選んだエージェントへの言付け", "placeholder": "伝えること（作業中でも、次の区切りで届きます）"}},
        {"id": "do_send", "part": "button", "props": {"label": "送る", "primary": True}},

        # --- オペレーターの話し方（設定 operator_style） ---
        {"id": "style", "layout": "column", "children": ["style_note", "style_text", "style_actions"]},
        {"id": "style_note", "part": "note", "props": {"text": "オペレーター（GUI の案内・操作係のエージェント）の口調・答え方です。口調・言い回しだけが変わります（結果・エラー・数字はそのまま）。次にオペレーターを起動したときから効きます。オペレーターとの会話は、今の ECOBuild GUI の窓で行います。"}},
        {"id": "style_text", "part": "text-area", "props": {"title": "口調・答え方", "rows": 5, "placeholder": "例：やさしい敬語で、短く。結果は最初に一言で"}},
        {"id": "style_actions", "layout": "row", "children": ["style_save", "style_unset"]},
        {"id": "style_save", "part": "button", "props": {"label": "保存", "primary": True, "hint": "書き直してから押します"}},
        {"id": "style_unset", "part": "button", "props": {"label": "指定をやめる"}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        # エージェント
        {"read": "agent list", "to": "list.rows"},
        {"on": "list.action", "when": {"action": "show"}, "set": {"operator_agent": {"payload": "id"}}},
        {"on": "children.action", "when": {"action": "show"}, "set": {"operator_agent": {"payload": "id"}}},
        {"value": "operator_agent", "to": "selected.text"},
        {"read": "agent status", "args": {"id": [{"value": "operator_agent"}]}, "to": "status.data"},
        {"read": "agent children", "args": {"id": {"value": "operator_agent"}}, "to": "children.rows", "from": "members"},
        # 行のボタン（ecobuild agent stop <ID>・agent restart <ID> [--resume]・agent close <ID>）
        {"on": "list.action", "when": {"action": "stop"}, "run": "agent stop", "args": {"id": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "restart"}, "run": "agent restart", "args": {"id": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "resume"}, "run": "agent restart", "args": {"id": {"payload": "id"}, "resume": True}},
        {"on": "list.action", "when": {"action": "close"}, "run": "agent close", "args": {"id": {"payload": "id"}},
         "set": {"operator_agent": None}},
        # 言付け（ecobuild agent send <ID> <伝えること>）
        {"on": "message.changed", "set": {"operator_message": {"payload": "text"}}},
        {"on": "do_send.pressed", "run": "agent send",
         "args": {"id": {"value": "operator_agent"}, "text": [{"value": "operator_message"}]}},
        # 話し方（ecobuild config get operator_style・config set operator_style <文>・config unset operator_style）
        {"read": "config get", "args": {"key": "operator_style"}, "to": "style_text.text", "from": "value"},
        {"on": "style_text.changed", "set": {"operator_style": {"payload": "text"}}},
        {"on": "style_save.pressed", "run": "config set", "args": {"key": "operator_style", "value": {"value": "operator_style"}},
         "set": {"operator_style": None}},
        {"on": "style_unset.pressed", "run": "config unset", "args": {"key": "operator_style"}},
    ],
}
