"""作業空間 › 直前のコミットを修正：ファイルを選ばずに「直前のコミットを修正」を押したとき、すべての変更を含めてよいか確かめる
（窓の中に重ねて開く。前の GUI と同じ）。「修正する」で ecobuild task commit --message <文> --amend。"""

ARGS = {"module": ".", "message": "", "hint": ""}  # 作業空間のフォルダー・コミットメッセージ・下に添える案内（Push 済みなら強制Push）

SCREEN = {
    "root": "page",
    "window": {"title": "直前のコミットを修正", "width": 520, "height": 300},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "text", "hint", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "直前のコミットを修正", "heading": True}},
        {"id": "text", "part": "note", "props": {"text": "ファイルを選んでいないので、すべての変更を直前のコミットに含めます。よろしいですか？"}},
        {"id": "hint", "part": "note", "props": {"text": {"arg": "hint"}, "tone": "muted"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "amend"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "amend", "part": "button", "props": {"label": "修正する", "primary": True}},
    ],
    "bindings": [
        {"on": "amend.pressed", "run": "task commit", "args": {"module": {"arg": "module"}, "message": {"arg": "message"}, "amend": True},
         "parent": {"paths": None, "amend": None, "message": None}, "close": True, "notify": "コミットしました：{message}"},
        {"on": "cancel.pressed", "close": True},
    ],
}
