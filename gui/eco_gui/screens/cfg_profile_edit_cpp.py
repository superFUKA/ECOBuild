"""ビルド設定を追加・編集（入力の窓）：C++ のモジュール。構成・並列・共有と、畳める節「C++・コンパイラ」「テスト・依存先」。"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・編集するビルド設定の名前（追加なら空）

SCREEN = {
    "root": "form",
    "window": {"title": "ビルド設定", "width": 720, "height": 760},
    "nodes": [
        {"id": "form", "part": "cfg-form", "props": {
            "title": "ビルド設定", "ok": "保存",
            "intro": "同じ名前のビルド設定があれば置き換えます（空にした項目は既定に戻ります）。ecobuild.toml が変わるので、タスクブランチでコミットしてください。",
            "at": [{"arg": "name"}],
            "fields": [
                {"name": "name", "label": "名前", "required": True, "value": {"arg": "name"}, "placeholder": "例：release"},
                {"name": "configuration", "label": "構成", "type": "select", "value": "Debug", "options": [
                    {"value": "Debug", "label": "Debug（開発用：最適化なし・デバッグ情報あり）"},
                    {"value": "Release", "label": "Release（配布用：速さ優先で最適化）"},
                    {"value": "RelWithDebInfo", "label": "RelWithDebInfo（Release＋デバッグ情報）"},
                    {"value": "MinSizeRel", "label": "MinSizeRel（小ささ優先で最適化）"}]},
                {"name": "parallel", "label": "並列ビルドの数", "type": "number", "min": 1, "value": 4},
                {"name": "shared", "label": "ライブラリ（依存先を含む）をすべて共有ライブラリにする", "type": "checkbox",
                 "help": "ライブラリごとに決めるには、表の「Projectごとの上書き」で形式を指定します。"},
                {"type": "section", "label": "C++・コンパイラ（空なら既定）", "collapsed": True},
                {"name": "cpp_standard", "label": "C++の規格", "type": "select", "value": "", "value_from": "options.cpp_standard", "options": [
                    {"value": "", "label": "既定（20）"}, {"value": "17", "label": "C++17"}, {"value": "20", "label": "C++20"}, {"value": "23", "label": "C++23"}]},
                {"name": "architecture", "label": "アーキテクチャ", "type": "select", "value": "", "value_from": "options.architecture", "options": [
                    {"value": "", "label": "既定"}, {"value": "x64", "label": "x64"}, {"value": "Win32", "label": "Win32"}, {"value": "ARM64", "label": "ARM64"}]},
                {"name": "generator", "label": "CMakeの生成器", "type": "select", "value": "", "value_from": "options.generator", "options": [
                    {"value": "", "label": "既定（OSごと）"}, {"value": "Visual Studio 18 2026", "label": "Visual Studio 18 2026"},
                    {"value": "Visual Studio 17 2022", "label": "Visual Studio 17 2022"}, {"value": "Ninja Multi-Config", "label": "Ninja Multi-Config"}]},
                {"name": "toolset", "label": "ツールセット", "value_from": "options.toolset", "placeholder": "v143、14.44 等"},
                {"name": "c_compiler", "label": "Cコンパイラ（Ninjaだけ）", "value_from": "options.c_compiler", "placeholder": "名前か絶対パス"},
                {"name": "cxx_compiler", "label": "C++コンパイラ（Ninjaだけ）", "value_from": "options.cxx_compiler", "placeholder": "例：clang++"},
                {"name": "toolchain_file", "label": "CMakeのツールチェーンファイル（絶対パス）", "value_from": "options.toolchain_file"},
                {"name": "windows_sdk", "label": "Windows SDK の版（MSVCだけ）", "value_from": "options.windows_sdk", "placeholder": "例：10.0.22621.0"},
                {"type": "section", "label": "テスト・依存先（空なら既定）", "collapsed": True},
                {"name": "test_parallel", "label": "テストを並列に実行する数", "type": "number", "min": 1, "value_from": "options.test_parallel", "placeholder": "1"},
                {"name": "stop_on_test_failure", "label": "テスト用のProjectが失敗したら、残りのテストを実行しない", "type": "checkbox",
                 "value_from": "options.test_continue_on_failure", "on_value": False},
                {"name": "googletest_archive", "label": "GoogleTestのZIP（オフラインで使う。空ならダウンロード）", "value_from": "options.googletest_archive"},
                {"name": "no_fetch", "label": "足りない依存先を、ビルドの前に自動でcloneしない", "type": "checkbox",
                 "value_from": "options.fetch_git", "on_value": False},
            ],
        }},
    ],
    "bindings": [
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "form.values", "from": "profiles"},
        {"on": "form.cancelled", "close": True},
        # ecobuild profile add <名前> --configuration … --parallel … [--shared] [--cpp-standard …] …（空の欄は渡さない＝既定）
        {"on": "form.submitted", "run": "profile add",
         "args": {"module": {"arg": "module"}, "name": {"payload": "values.name"}, "configuration": {"payload": "values.configuration"},
                  "parallel": {"payload": "values.parallel"}, "shared": {"payload": "values.shared"},
                  "cpp_standard": {"payload": "values.cpp_standard"}, "architecture": {"payload": "values.architecture"},
                  "generator": {"payload": "values.generator"}, "toolset": {"payload": "values.toolset"},
                  "c_compiler": {"payload": "values.c_compiler"}, "cxx_compiler": {"payload": "values.cxx_compiler"},
                  "toolchain_file": {"payload": "values.toolchain_file"}, "windows_sdk": {"payload": "values.windows_sdk"},
                  "test_parallel": {"payload": "values.test_parallel"}, "stop_on_test_failure": {"payload": "values.stop_on_test_failure"},
                  "googletest_archive": {"payload": "values.googletest_archive"}, "no_fetch": {"payload": "values.no_fetch"}},
         "notify": "ビルド設定を保存しました。", "close": True},
    ],
}
