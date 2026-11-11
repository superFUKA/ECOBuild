"""設定 › C++ の設定：モジュールの設定の表（ecobuild module settings）。

C++ のモジュールの「設定」のタブに置く（部品 mod-cpp。変える操作は、入力の窓を重ねて開く）。
"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "general",
    "nodes": [
        {"id": "general", "part": "mod-cpp", "props": {"view": "general"}},
    ],
    "bindings": [
        {"on": "general.reload", "refresh": True},
        {"read": "module settings", "args": {"module": {"arg": "module"}}, "to": "general.settings"},
        {"on": "general.action", "when": {"name": "module_settings"}, "open": "mod-cpp-settings", "inside": True, "args": {"module": {"arg": "module"}}},
    ],
}
