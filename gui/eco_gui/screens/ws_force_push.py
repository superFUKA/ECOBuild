"""作業空間 › 強制Push：Push 済みのコミットを直した（修正・取り消し）ときに、GitHub の側を上書きする（窓の中に重ねて開く）。

何が起きるかを読んでから押す。することは ecobuild task push --force。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "強制Push", "width": 560, "height": 300},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "about", "caution", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "強制Push", "heading": True}},
        {"id": "about", "part": "note", "props": {
            "text": "このタスクブランチの GitHub の側を、手元のコミットで上書きします。Push 済みのコミットを「直前のコミットを修正」で直した・取り消したときに使います。"}},
        {"id": "caution", "part": "note", "props": {
            "text": "GitHub にだけあるコミット（ほかの人・ほかの PC が Push したもの）は失われます。先に「取り込む」で確かめてください。", "tone": "warn"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "push"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "push", "part": "button", "props": {"label": "強制Push", "danger": True}},
    ],
    "bindings": [
        {"on": "push.pressed", "run": "task push", "args": {"module": {"arg": "module"}, "force": True}, "notify": "強制Pushしました。", "close": True},
        {"on": "cancel.pressed", "close": True},
    ],
}
