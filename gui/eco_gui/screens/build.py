"""作業空間 › ビルドと試験：作業空間のツールバーの「構成・ビルド設定…」「テストを選んで実行…」から開く窓。

上に、構成・ビルド設定（今使われるもの「Debug · fast」。構成・この PC で使うビルド設定・実行の対象の Project・実行時の引数を選ぶ）と、
ビルド・リビルド・クリーン・提出前の確認・実行・テスト。真ん中に、テストを選ぶ木（流さずに集めた一覧。前に流した結果の ✗ ✓ - つき）と、
名前・式での指定。下に出力（見出し・状態の印・秒数・結果の要約：試験の数と1件ずつ、終了コード、成果物、確認の項目）。
"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ビルドと試験", "width": 900, "height": 860},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-page", "children": ["head", "place", "setting_card", "test_card", "out"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ビルドと試験", "heading": True}},
        {"id": "place", "part": "note", "props": {"text": {"arg": "module"}, "tone": "muted"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        # 構成・ビルド設定と、動かすボタン
        {"id": "setting_card", "layout": "column", "look": "card", "children": ["setting", "tools"]},
        {"id": "setting", "part": "ws-build-setting"},
        {"id": "tools", "layout": "row", "look": "ws-build-tools", "children": ["build", "rebuild", "clean", "check", "run", "test"]},
        {"id": "build", "part": "button", "props": {"label": "ビルド", "primary": True}},
        {"id": "rebuild", "part": "button", "props": {"label": "リビルド", "hint": "クリーンしてからビルドし直す"}},
        {"id": "clean", "part": "button", "props": {"label": "クリーン", "hint": "ビルドで作ったものを消す"}},
        {"id": "check", "part": "button", "props": {"label": "提出前の確認", "hint": "生成ファイル・衝突の印・ビルド・テストを確かめる（ecobuild check）"}},
        {"id": "run", "part": "button", "props": {"label": "▶ 実行", "hint": "対象の Project を、実行時の引数で動かす"}},
        {"id": "test", "part": "button", "props": {"label": "すべてのテスト"}},
        # テストを選んで実行（ecobuild tests で集め、ecobuild test <試験…> で流す）
        {"id": "test_card", "layout": "column", "look": "card", "children": ["test_head", "tests", "named_title", "named", "filtered"]},
        {"id": "test_head", "layout": "row", "look": "bar", "children": ["test_title", "test_tools"]},
        {"id": "test_title", "part": "note", "props": {"text": "テストを選んで実行", "tone": "section"}},
        {"id": "test_tools", "layout": "row", "look": "tools", "children": ["tests_load", "test_checked"]},
        # 一覧を読むのは押したとき（Python は pytest が集めるので時間がかかり、コンテナの作業空間ではコンテナを動かす。窓を開くたびには読まない）
        {"id": "tests_load", "part": "button", "props": {"label": "テストの一覧を読む", "hint": "流さずに、流せるテストを集める（ecobuild tests）"}},
        {"id": "test_checked", "part": "button", "props": {"label": "選んだテストを実行", "primary": True, "hint": "チェックを付けたテストを流す（1つも選ばなければ、全部を流す）"}},
        # 木で選ぶ（C++：Project › Suite › Test／Python：フォルダー › ファイル › クラス › 試験）
        {"id": "tests", "part": "ws-test-tree", "props": {
            "empty_text": "「テストの一覧を読む」を押すと、流せるテストが出ます。流すテストにチェックを付けます（まとまりのチェックで、中の全部）。"}},
        {"id": "named_title", "part": "note", "props": {"text": "名前で指定", "tone": "section"}},
        {"id": "named", "layout": "row", "look": "ws-build-named", "children": ["test_name", "test_named"]},
        {"id": "filtered", "layout": "row", "look": "ws-build-named", "children": ["filter", "last_failed", "test_filtered"]},
        {"id": "test_name", "part": "text-input", "props": {
            "title": "テストの名前（ファイル・フォルダー・<Project>.<Suite>.<Test>。* ? が使えます）", "placeholder": "例：tests/test_calc.py ／ CalcTest.Add.*"}},
        {"id": "filter", "part": "text-input", "props": {"title": "名前で選ぶ式（Python：pytest の -k）", "placeholder": "例：add and not slow"}},
        {"id": "last_failed", "part": "toggle", "props": {"label": "前回失敗したテストだけ（Python）", "hint": "前回の失敗がなければ全部"}},
        {"id": "test_named", "part": "button", "props": {"label": "この名前で実行"}},
        {"id": "test_filtered", "part": "button", "props": {"label": "絞って実行"}},
        {"id": "out", "part": "output", "props": {"empty_text": "ビルド・テスト・実行の出力が、ここに出ます。"}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        # 構成・ビルド設定（ecobuild profile list・profile use <名前>）。Project は、モジュールの型が持っていれば届く（ecobuild module show）
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "setting.profiles"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "setting.module_type", "from": "type"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "setting.projects", "from": "project_list"},
        {"on": "setting.configuration", "set": {"build_configuration": {"payload": "value"}}},
        {"value": "build_configuration", "to": "setting.configuration"},
        {"on": "setting.profile", "run": "profile use", "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}},
        {"on": "setting.target", "set": {"build_project": {"payload": "project"}}},
        {"value": "build_project", "to": "setting.target"},
        {"on": "setting.arguments", "set": {"run_arguments": {"payload": "text"}}},
        {"value": "run_arguments", "to": "setting.arguments"},
        {"on": "setting.settings", "open": "settings", "args": {"module": {"arg": "module"}}},
        # 出力欄：何を動かしたか・状態・結果（要約は、部品 output が種類ごとに作る）
        {"value": "run_title", "to": "out.title"},
        {"value": "run_kind", "to": "out.kind"},
        {"value": "run_state", "to": "out.state"},
        {"value": "run_result", "to": "out.result"},
        # テストの木
        {"on": "tests_load.pressed", "run": "tests", "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}},
         "set": {"tests_found": {"result": "tests"}}},
        {"value": "tests_found", "to": "tests.rows"},
        {"on": "tests.changed", "set": {"tests_checked": {"payload": "values"}}},
        {"value": "tests_checked", "to": "tests.checked"},
        {"value": "test_result", "to": "tests.last"},
        {"on": "test_name.changed", "set": {"test_name": {"payload": "text"}}},
        {"on": "filter.changed", "set": {"test_filter": {"payload": "text"}}},
        {"on": "last_failed.changed", "set": {"test_last_failed": {"payload": "on"}}},
        {"value": "test_last_failed", "to": "last_failed.on"},
        # 動かす：押したら見出しと「実行中」を出し、道具の出力を続けて出す。終わったら、結果を共有の値へ（出力欄の要約に出る）
        {"on": "build.pressed", "set": {"run_title": "ビルド", "run_kind": "build", "run_state": "run", "run_result": None}},
        {"on": "build.pressed", "run": "build", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}}, "failed": {"run_state": "bad"}},
        {"on": "rebuild.pressed", "set": {"run_title": "リビルド", "run_kind": "rebuild", "run_state": "run", "run_result": None}},
        {"on": "rebuild.pressed", "run": "rebuild", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}}, "failed": {"run_state": "bad"}},
        {"on": "clean.pressed", "set": {"run_title": "クリーン", "run_kind": "clean", "run_state": "run", "run_result": None}},
        {"on": "clean.pressed", "run": "clean", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}}, "failed": {"run_state": "bad"}},
        {"on": "check.pressed", "set": {"run_title": "提出前の確認", "run_kind": "check", "run_state": "run", "run_result": None}},
        {"on": "check.pressed", "run": "check", "output": "out.lines", "args": {"module": {"arg": "module"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}}, "failed": {"run_state": "bad"}},
        {"on": "run.pressed", "set": {"run_title": "実行", "run_kind": "run", "run_state": "run", "run_result": None}},
        {"on": "run.pressed", "run": "run", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "arguments": {"value": "run_arguments"},
                  "project": {"value": "build_project"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}}, "failed": {"run_state": "bad"}},
        {"on": "test.pressed", "set": {"run_title": "テスト", "run_kind": "test", "run_state": "run", "run_result": None}},
        {"on": "test.pressed", "run": "test", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}, "test_result": {"result": ""}}, "failed": {"run_state": "bad"}},
        # 選んだテスト：名前が自分の Project を言うので、対象の Project は使わない
        {"on": "test_checked.pressed", "set": {"run_title": "テスト（選んだもの）", "run_kind": "test", "run_state": "run", "run_result": None}},
        {"on": "test_checked.pressed", "run": "test", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "tests": {"value": "tests_checked"}, "configuration": {"value": "build_configuration"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}, "test_result": {"result": ""}}, "failed": {"run_state": "bad"}},
        # 名前で流す（名前を書くまで押せない）・式で絞って流す。見出しと状態は、終わったときに出す
        {"on": "test_named.pressed", "run": "test", "output": "out.lines", "require": ["tests"],
         "args": {"module": {"arg": "module"}, "tests": [{"value": "test_name"}], "configuration": {"value": "build_configuration"}},
         "set": {"run_title": "テスト（名前で指定）", "run_kind": "test", "run_state": "ok", "run_result": {"result": ""}, "test_result": {"result": ""}},
         "failed": {"run_title": "テスト（名前で指定）", "run_kind": "test", "run_state": "bad", "run_result": None}},
        {"on": "test_filtered.pressed", "set": {"run_title": "テスト（絞り込み）", "run_kind": "test", "run_state": "run", "run_result": None}},
        {"on": "test_filtered.pressed", "run": "test", "output": "out.lines",
         "args": {"module": {"arg": "module"}, "filter": {"value": "test_filter"}, "last_failed": {"value": "test_last_failed"},
                  "configuration": {"value": "build_configuration"}},
         "set": {"run_state": "ok", "run_result": {"result": ""}, "test_result": {"result": ""}}, "failed": {"run_state": "bad"}},
    ],
}
