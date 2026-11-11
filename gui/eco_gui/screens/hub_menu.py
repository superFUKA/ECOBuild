"""ハブの窓の左のメニュー（ハブの画面に置く）：モジュール・オペレーター、下に設定・ヘルプとアカウント。選ぶと、同じ窓で画面が切り替わる。"""

ARGS = {"current": ""}

SCREEN = {
    "root": "menu",
    "nodes": [
        {"id": "menu", "part": "menu", "props": {"current": {"arg": "current"}, "title": "ECOBuild Hub", "items": [
            {"id": "hub", "label": "モジュール", "icon": "module"},
            {"id": "operator", "label": "オペレーター", "icon": "operator"},
            {"id": "hub-settings", "label": "設定", "icon": "settings", "bottom": True},
            {"id": "hub-help", "label": "ヘルプ", "icon": "help", "bottom": True},
        ]}},
    ],
    "bindings": [
        # モジュールの外：ログイン中のアカウントだけが分かる（役割はモジュールごと）
        {"read": "account show", "to": "menu.account"},
        {"on": "menu.selected", "open": {"payload": "id"}, "here": True},
        {"on": "menu.account", "open": "hub-account", "inside": True},
    ],
}
