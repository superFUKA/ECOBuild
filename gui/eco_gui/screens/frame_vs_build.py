"""Visual Studio で開く › ソリューションがまだない：ビルドしてから開くかを尋ねる（窓の中に重ねて開く）。

ソリューションはビルドで作られる（C++）。「ビルドする」でビルドし（ecobuild build）、できたら「Visual Studio で開く」
（ecobuild open --app vs --solution）。作業空間のタブの右クリック・ハブのカードの「Visual Studio で開く」が、
ソリューションがないとき（no_solution）にこれを開く。
ビルドと開くは2つのボタン（ビルドが終わってから開く。GUIFrameWork のつなぎは、実行の後に続けて実行できないため）。"""

ARGS = {"module": ".", "version": ""}  # 開く場所（作業空間・モジュールのフォルダー）・Visual Studio の版（空なら、この PC のいちばん新しい版）

SCREEN = {
    "root": "page",
    "window": {"title": "Visual Studio で開く", "width": 640, "height": 520},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["title", "about", "out", "built", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "Visual Studio で開く", "heading": True}},
        {"id": "about", "part": "note", "props": {
            "text": "ソリューション（.sln／.slnx）がまだありません（ビルドすると作成されます）。ビルドしてから開きますか？"}},
        {"id": "out", "part": "output", "props": {"empty_text": "ビルドの出力が、ここに出ます。"}},
        {"id": "built", "part": "note", "props": {"text": "ビルドしました。ソリューションを開けます。"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "build", "open"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "build", "part": "button", "props": {"label": "ビルドする", "primary": True}},
        {"id": "open", "part": "button", "props": {"label": "Visual Studio で開く", "primary": True}},
    ],
    "bindings": [
        {"on": "cancel.pressed", "close": True},
        # ecobuild build（そのフォルダーで。出力はここに続けて出す）。できたら、開くボタンに替わる
        {"on": "build.pressed", "run": "build", "args": {"module": {"arg": "module"}}, "output": "out.lines", "set": {"vs_built": True}},
        {"show": "build", "when": {"vs_built": [None, False]}},
        {"show": "built", "when": {"vs_built": True}},
        {"show": "open", "when": {"vs_built": True}},
        {"on": "open.pressed", "run": "open", "args": {"module": {"arg": "module"}, "app": "vs", "vs_version": {"arg": "version"}, "solution": True},
         "notify": "Visual Studio {version} で開きます：{name}", "close": True},
    ],
}
