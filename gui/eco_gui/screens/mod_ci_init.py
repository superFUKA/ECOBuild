"""モジュール › CI › 用意する・設定を変える：入力の窓。作り直すタスクブランチ（作業空間）と、OS・構成・共有・ブランチを決める。

ワークフローのファイルを書くので、タスクブランチの作業空間で実行する（選んだ作業空間が、コマンドの実行先）。
"""

ARGS = {"module": ".", "os": "", "configuration": "Debug", "shared": "off", "branches": ""}  # モジュールのフォルダーと、今の設定（初めの値）

SCREEN = {
    "root": "page",
    "window": {"title": "CIの設定", "width": 620, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "CIの設定", "ok": "作る（作り直す）",
            "intro": "ワークフロー（.github/workflows/ecobuild.yml）を、この設定で作り直します。設定は ecobuild.toml の [ci] に残ります。"
                     "コミットして提出し、取り込むと反映されます。",
            "initial": {"os": {"arg": "os"}, "configuration": {"arg": "configuration"}, "shared": {"arg": "shared"}, "branches": {"arg": "branches"}},
            "fields": [
                {"name": "place", "label": "作り直すタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "rows", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）"},
                {"name": "os", "label": "動かすOS（どれも選ばなければ、今の設定のまま。初めは型の既定）", "type": "checks", "join": ",",
                 "options": [{"value": "windows", "label": "Windows"}, {"value": "linux", "label": "Linux"}]},
                {"name": "configuration", "label": "ビルドする構成（カンマ区切り）", "type": "text", "required": True, "placeholder": "例：Debug,Release"},
                {"name": "shared", "label": "ライブラリを共有ライブラリにした構成でもビルド・テストする（C++）", "type": "checkbox", "on": "on", "off": "off"},
                {"name": "branches", "label": "push で動かすブランチ（カンマ区切り。空欄なら今の設定のまま。初めは作成元のブランチ）", "type": "text",
                 "placeholder": "例：main,develop"},
                {"name": "force", "label": "手で編集したワークフローでも上書きする（編集した内容は失われます）", "type": "checkbox"},
            ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.rows", "from": "workspaces"},
        # 人が打つのと同じ：（作業空間で）ecobuild ci init --configuration … --shared on|off [--os …] [--branches …] [--force]
        {"on": "form.submitted", "run": "ci init", "args": {
            "module": {"payload": "values.place"}, "os": {"payload": "values.os"}, "configuration": {"payload": "values.configuration"},
            "shared": {"payload": "values.shared"}, "branches": {"payload": "values.branches"}, "force": {"payload": "values.force"}},
         "require": ["module"], "notify": "ワークフローを作りました。コミットして提出すると反映されます。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
