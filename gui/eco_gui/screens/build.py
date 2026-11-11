"""作業空間 › ビルドと試験：ビルド設定を選ぶ・足す。構成・引数を決めて、ビルド・試験・実行をする。結果（成果物・試験の数・終了コード）を見せる。

C++ のモジュールでだけ使えるもの（対象のサブプロジェクト・共有ライブラリ）は、モジュールの型が cpp のときだけ出す。"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ビルドと試験", "width": 820, "height": 800},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-page", "children": ["head", "place", "profile_card", "run_card", "test_card", "out"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ビルドと試験", "heading": True}},
        {"id": "place", "part": "note", "props": {"text": {"arg": "module"}, "tone": "muted"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        # まとまりごとの箱
        {"id": "profile_card", "layout": "column", "look": "card", "children": ["profile_head", "profiles", "profile_new"]},
        {"id": "profile_head", "layout": "row", "look": "bar", "children": ["profile_title", "no_profile"]},
        {"id": "run_card", "layout": "column", "look": "card", "children": ["run_title", "options", "tools", "results"]},
        {"id": "run_title", "part": "note", "props": {"text": "ビルド・実行・試験", "tone": "section"}},
        {"id": "test_card", "layout": "column", "look": "card", "children": ["test_title", "tests_bar", "tests", "test_pick", "test_filter"]},
        # ビルド設定（ecobuild profile list・profile use <名前>・profile remove <名前>）
        {"id": "profile_title", "part": "note", "props": {"text": "ビルド設定（この PC で使うもの）", "tone": "section"}},
        {"id": "profiles", "part": "named-table", "props": {
            "columns": [{"key": "configuration", "label": "構成"}, {"key": "shared", "label": "共有ライブラリ"}],
            "name_label": "ビルド設定", "current_mark": "使用中",
            "actions": [{"name": "use", "label": "使う"}, {"name": "remove", "label": "消す"}],
            "labels": {"shared": {"true": "はい", "false": ""}},
            "empty_text": "ビルド設定はありません（下の欄で足せます）。",
        }},
        {"id": "no_profile", "part": "button", "props": {"label": "ビルド設定を使わない", "quiet": True, "hint": "ecobuild profile use none"}},
        # ビルド設定を足す（ecobuild profile add <名前> [--configuration <構成>] [--parallel <数>] [--shared]。同じ名前なら上書き。
        # どの型にもある項目と、並列の数・共有ライブラリだけ。型ごとの細かい項目は CLI で）
        {"id": "profile_new", "layout": "row", "children": ["profile_name", "profile_configuration", "profile_parallel", "profile_shared", "do_profile_add"]},
        {"id": "profile_name", "part": "text-input", "props": {"title": "足すビルド設定の名前（同じ名前なら上書き）", "placeholder": "例：fast"}},
        {"id": "profile_configuration", "part": "select", "props": {"title": "構成", "options": [
            {"value": "", "label": "（既定：Debug）"}, {"value": "Debug", "label": "Debug"}, {"value": "Release", "label": "Release"},
            {"value": "RelWithDebInfo", "label": "RelWithDebInfo（C++）"}, {"value": "MinSizeRel", "label": "MinSizeRel（C++）"}]}},
        {"id": "profile_parallel", "part": "text-input", "props": {"title": "並列の数（空なら 1）", "placeholder": "例：8"}},
        {"id": "profile_shared", "part": "toggle", "props": {"label": "共有ライブラリにする（C++）", "hint": "ライブラリ（依存先を含む）を共有ライブラリにする"}},
        {"id": "do_profile_add", "part": "button", "props": {"label": "＋ 足す"}},
        # 構成と、実行に渡す引数（C++ は、対象のサブプロジェクトも）
        {"id": "options", "layout": "row", "children": ["configuration", "project", "run_arguments"]},
        {"id": "project", "part": "text-input", "props": {
            "title": "対象のサブプロジェクト（C++。空なら全体）", "placeholder": "例：Calc（ビルド・クリーン・実行・試験（全部）に効く）"}},
        {"id": "configuration", "part": "select", "props": {"title": "構成", "options": [
            {"value": "", "label": "ビルド設定のまま"}, {"value": "Debug", "label": "Debug"}, {"value": "Release", "label": "Release"},
            {"value": "RelWithDebInfo", "label": "RelWithDebInfo（C++）"}, {"value": "MinSizeRel", "label": "MinSizeRel（C++）"}]}},
        {"id": "run_arguments", "part": "text-input", "props": {"title": "「実行」でプログラムに渡す引数", "placeholder": "例：--verbose input.txt"}},
        {"id": "tools", "layout": "row", "look": "tools", "children": ["build", "rebuild", "clean", "run", "test"]},
        {"id": "build", "part": "button", "props": {"label": "ビルド", "primary": True}},
        {"id": "rebuild", "part": "button", "props": {"label": "リビルド", "hint": "クリーンしてからビルドし直す"}},
        {"id": "clean", "part": "button", "props": {"label": "クリーン", "hint": "ビルドで作ったものを消す"}},
        {"id": "run", "part": "button", "props": {"label": "実行"}},
        {"id": "test", "part": "button", "props": {"label": "試験（全部）"}},
        # 最後にうまくいった実行の結果（実行の結果を、共有の値 build_result・test_result・run_result へ入れて見せる）
        {"id": "results", "layout": "row", "children": ["build_facts", "artifacts", "test_facts", "run_facts"]},
        {"id": "build_facts", "part": "facts", "props": {"items": [
            {"key": "action", "label": "したこと"}, {"key": "project", "label": "対象"}, {"key": "configuration", "label": "構成"},
            {"key": "profile", "label": "ビルド設定"}],
            "labels": {"action": {"build": "ビルド", "rebuild": "リビルド", "clean": "クリーン"}}}},
        {"id": "artifacts", "part": "string-list", "props": {"empty_text": "成果物はありません。"}},
        {"id": "test_facts", "part": "facts", "props": {"items": [
            {"key": "passed", "label": "成功した試験"}, {"key": "failed", "label": "失敗した試験"}, {"key": "skipped", "label": "飛ばした試験"},
            {"key": "configuration", "label": "構成"}]}},
        {"id": "run_facts", "part": "facts", "props": {"items": [
            {"key": "returncode", "label": "終了コード"}, {"key": "project", "label": "実行したもの"}, {"key": "configuration", "label": "構成"}]}},
        # 試験を選ぶ（ecobuild test <試験> ／ ecobuild test --filter <式> --last-failed）
        {"id": "test_title", "part": "note", "props": {"text": "試験を選んで流す", "tone": "section"}},
        # 一覧から選ぶ（ecobuild tests：流さずに読む。型 python・cpp）。読むのは押したとき
        # （Python は pytest が集めるので時間がかかり、コンテナの作業空間ではコンテナを動かす。画面を開くたびには読まない）
        {"id": "tests_bar", "layout": "row", "look": "tools", "children": ["tests_load", "test_checked"]},
        {"id": "tests_load", "part": "button", "props": {"label": "試験の一覧を読む", "hint": "流さずに、流せる試験を集める（ecobuild tests）"}},
        # 木で選ぶ（C++：サブプロジェクト › Suite › Test／Python：フォルダー › ファイル › クラス › 試験。前に流した結果の ✗ ✓ - つき）
        {"id": "tests", "part": "ws-test-tree", "props": {
            "empty_text": "「試験の一覧を読む」を押すと、流せる試験が出ます（C++・Python）。"}},
        {"id": "test_checked", "part": "button", "props": {"label": "選んだ試験を流す", "primary": True, "hint": "1つも選ばなければ、全部を流す"}},
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
        {"on": "profile_name.changed", "set": {"profile_name": {"payload": "text"}}},
        {"on": "profile_configuration.changed", "set": {"profile_configuration": {"payload": "value"}}},
        {"value": "profile_configuration", "to": "profile_configuration.value"},
        {"on": "profile_parallel.changed", "set": {"profile_parallel": {"payload": "text"}}},
        {"on": "profile_shared.changed", "set": {"profile_shared": {"payload": "on"}}},
        {"value": "profile_shared", "to": "profile_shared.on"},
        {"on": "do_profile_add.pressed", "run": "profile add", "args": {
            "module": {"arg": "module"}, "name": {"value": "profile_name"}, "configuration": {"value": "profile_configuration"},
            "parallel": {"value": "profile_parallel"}, "shared": {"value": "profile_shared"}}},
        # モジュールの型（ecobuild module show の type）で、型だけの部品を出し分ける
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_type", "from": "type"},
        {"show": "project", "when": {"module_type": "cpp"}},
        {"show": "profile_shared", "when": {"module_type": "cpp"}},
        {"show": "profile_parallel", "when": {"module_type": ["cpp", "python"]}},
        # 結果は、最後にうまくいった実行のものだけを出す
        {"show": "build_facts", "when": {"last_run": "build"}},
        {"show": "artifacts", "when": {"last_run": "build"}},
        {"show": "test_facts", "when": {"last_run": "test"}},
        {"show": "run_facts", "when": {"last_run": "run"}},
        {"value": "build_result", "to": "build_facts.data"},
        {"value": "build_result", "to": "artifacts.items", "from": "artifacts"},
        {"value": "test_result", "to": "test_facts.data"},
        {"value": "run_result", "to": "run_facts.data"},
        # 選ぶ・書く
        {"on": "configuration.changed", "set": {"build_configuration": {"payload": "value"}}},
        {"value": "build_configuration", "to": "configuration.value"},
        {"on": "run_arguments.changed", "set": {"run_arguments": {"payload": "text"}}},
        {"on": "project.changed", "set": {"build_project": {"payload": "text"}}},
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
        # 動かす：道具の出力を、続けて出す。うまくいったら、結果を共有の値へ（上の結果の欄に出る）
        {"on": "build.pressed", "run": "build", "output": "out.lines", "set": {"build_result": {"result": ""}, "last_run": "build"},
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}}},
        {"on": "rebuild.pressed", "run": "rebuild", "output": "out.lines", "set": {"build_result": {"result": ""}, "last_run": "build"},
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}}},
        {"on": "clean.pressed", "run": "clean", "output": "out.lines", "set": {"build_result": {"result": ""}, "last_run": "build"},
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}}},
        {"on": "run.pressed", "run": "run", "output": "out.lines", "set": {"run_result": {"result": ""}, "last_run": "run"},
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "arguments": {"value": "run_arguments"},
                  "project": {"value": "build_project"}}},
        {"on": "test.pressed", "run": "test", "output": "out.lines", "set": {"test_result": {"result": ""}, "last_run": "test"},
         "args": {"module": {"arg": "module"}, "configuration": {"value": "build_configuration"}, "project": {"value": "build_project"}}},
        {"on": "test_checked.pressed", "run": "test", "output": "out.lines", "set": {"test_result": {"result": ""}, "last_run": "test"},
         "args": {"module": {"arg": "module"}, "tests": {"value": "tests_checked"}, "configuration": {"value": "build_configuration"},
                  "project": {"value": "build_project"}}},
        {"on": "test_one.pressed", "run": "test", "output": "out.lines", "set": {"test_result": {"result": ""}, "last_run": "test"},
         "args": {"module": {"arg": "module"}, "tests": [{"value": "test_name"}], "configuration": {"value": "build_configuration"}}},
        {"on": "test_filtered.pressed", "run": "test", "output": "out.lines", "set": {"test_result": {"result": ""}, "last_run": "test"},
         "args": {"module": {"arg": "module"}, "filter": {"value": "test_filter"}, "last_failed": {"value": "test_last_failed"},
                  "configuration": {"value": "build_configuration"}}},
    ],
}
