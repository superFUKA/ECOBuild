"""作業空間 › ビルドと試験：ビルド設定を選ぶ。構成・引数を決めて、ビルド・試験・実行をする。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ビルドと試験", "width": 820, "height": 800},
    "nodes": [
        {"id": "page", "layout": "column", "children": [
            "head", "profile_title", "profiles", "no_profile", "options", "tools",
            "test_title", "test_pick", "test_filter", "out"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "module"}, "prefix": "ビルドと試験：", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        # ビルド設定（ecobuild profile list・profile use <名前>・profile remove <名前>）
        {"id": "profile_title", "part": "note", "props": {"text": "ビルド設定（この PC で使うもの）"}},
        {"id": "profiles", "part": "named-table", "props": {
            "columns": [{"key": "configuration", "label": "構成"}, {"key": "shared", "label": "共有ライブラリ"}],
            "name_label": "ビルド設定", "current_mark": "使用中",
            "actions": [{"name": "use", "label": "使う"}, {"name": "remove", "label": "消す"}],
            "labels": {"shared": {"true": "はい", "false": ""}},
            "empty_text": "ビルド設定はありません（ecobuild profile add で足せます）。",
        }},
        {"id": "no_profile", "part": "button", "props": {"label": "ビルド設定を使わない", "hint": "ecobuild profile use none"}},
        # 構成と、実行に渡す引数
        {"id": "options", "layout": "row", "children": ["configuration", "run_arguments"]},
        {"id": "configuration", "part": "select", "props": {"title": "構成", "options": [
            {"value": "", "label": "ビルド設定のまま"}, {"value": "Debug", "label": "Debug"}, {"value": "Release", "label": "Release"},
            {"value": "RelWithDebInfo", "label": "RelWithDebInfo（C++）"}, {"value": "MinSizeRel", "label": "MinSizeRel（C++）"}]}},
        {"id": "run_arguments", "part": "text-input", "props": {"title": "「実行」でプログラムに渡す引数", "placeholder": "例：--verbose input.txt"}},
        {"id": "tools", "layout": "row", "children": ["build", "rebuild", "clean", "run", "test"]},
        {"id": "build", "part": "button", "props": {"label": "ビルド", "primary": True}},
        {"id": "rebuild", "part": "button", "props": {"label": "リビルド", "hint": "クリーンしてからビルドし直す"}},
        {"id": "clean", "part": "button", "props": {"label": "クリーン", "hint": "ビルドで作ったものを消す"}},
        {"id": "run", "part": "button", "props": {"label": "実行"}},
        {"id": "test", "part": "button", "props": {"label": "試験（全部）"}},
        # 試験を選ぶ（ecobuild test <試験> ／ ecobuild test --filter <式> --last-failed）
        {"id": "test_title", "part": "note", "props": {"text": "試験を選んで流す"}},
        {"id": "test_pick", "layout": "row", "children": ["test_name", "test_one"]},
        {"id": "test_name", "part": "text-input", "props": {
            "title": "流す試験（ファイル・フォルダー・試験の名前）", "placeholder": "例：tests/test_app.py::test_add ／ CalcTest.Add.*"}},
        {"id": "test_one", "part": "button", "props": {"label": "この試験だけ"}},
        {"id": "test_filter", "layout": "row", "children": ["filter", "last_failed", "test_filtered"]},
        {"id": "filter", "part": "text-input", "props": {"title": "名前で絞る（Python：pytest -k の式）", "placeholder": "例：login and not slow"}},
        {"id": "last_failed", "part": "toggle", "props": {"label": "前回失敗した試験だけ（Python）"}},
        {"id": "test_filtered", "part": "button", "props": {"label": "絞って流す"}},
        {"id": "out", "part": "output"},
    ],
    "bindings": [
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "profiles.entries", "from": "profiles"},
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "profiles.current", "from": "selected"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "profiles.action", "when": {"action": "use"}, "run": "profile use", "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
        {"on": "profiles.action", "when": {"action": "remove"}, "run": "profile remove", "args": {"module": {"arg": "module"}, "name": {"payload": "id"}}},
        {"on": "no_profile.pressed", "run": "profile use", "args": {"module": {"arg": "module"}, "name": "none"}},
        # 選ぶ・書く
        {"on": "configuration.changed", "set": {"build_configuration": {"payload": "value"}}},
        {"value": "build_configuration", "to": "configuration.value"},
        {"on": "run_arguments.changed", "set": {"run_arguments": {"payload": "text"}}},
        {"on": "test_name.changed", "set": {"test_name": {"payload": "text"}}},
        {"on": "filter.changed", "set": {"test_filter": {"payload": "text"}}},
        {"on": "last_failed.changed", "set": {"test_last_failed": {"payload": "on"}}},
        {"value": "test_last_failed", "to": "last_failed.on"},
        # 動かす：道具の出力を、続けて出す
        {"on": "build.pressed", "run": "build", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}}},
        {"on": "rebuild.pressed", "run": "rebuild", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}}},
        {"on": "clean.pressed", "run": "clean", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}}},
        {"on": "run.pressed", "run": "run", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "arguments": {"value": "run_arguments"}}},
        {"on": "test.pressed", "run": "test", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}}},
        {"on": "test_one.pressed", "run": "test", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "tests": [{"value": "test_name"}], "configuration": {"value": "build_configuration"}}},
        {"on": "test_filtered.pressed", "run": "test", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "filter": {"value": "test_filter"}, "last_failed": {"value": "test_last_failed"},
                  "configuration": {"value": "build_configuration"}}},
    ],
}
