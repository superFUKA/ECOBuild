"""モジュール › Project › 設定：入力の窓。Project の設定を変える（ecobuild project set --project <名前> …）。

上に、今の設定（ecobuild project show）。並びの設定（定義・インクルード・ソースディレクトリ等）は、足すものと外すものを書く
（コマンドと同じ：--add-…・--remove-…）。空の欄は変えない。
"""

ARGS = {"module": ".", "name": ""}  # モジュールのフォルダー・設定する Project

SCREEN = {
    "root": "page",
    "window": {"title": "Projectの設定", "width": 760, "height": 780},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["form"]},
        {"id": "form", "part": "form", "props": {
            "title": "Projectの設定", "subject": {"arg": "name"}, "ok": "保存", "sticky": True, "initial": {"place": {"arg": "module"}},
            "intro": "書いた項目だけを変えます（空の欄は変えません）。値をいくつも書くときは、カンマで区切ります。",
            "detail": "今の設定：{kind}・{directory}/　ソース {source_directories}　OSのライブラリ {system_libraries}　入口 {entry_point}",
            "fields": [
                {"name": "kind", "label": "種類を変える", "type": "select", "value": "", "options": [
                    {"value": "", "label": "変えない"}, {"value": "app", "label": "実行ファイル"}, {"value": "library", "label": "ライブラリ（静的）"},
                    {"value": "shared", "label": "共有ライブラリ（Windows は DLL）"}],
                 "help": "変えると、ソース・設定・リンクはそのままで作り直します（ほかの設定は、その後で変えてください）。"},
                {"name": "no_test", "label": "組のテスト用Project（名前Test）を作らない", "type": "checkbox", "show_if": {"kind": ["library", "shared"]}},
                {"type": "section", "label": "ソース・定義・インクルード", "note": "Project からの相対"},
                {"name": "add_source_dir", "label": "足すソースディレクトリ（中のファイルがビルドに入る）", "row": "src"},
                {"name": "remove_source_dir", "label": "外すソースディレクトリ", "row": "src"},
                {"name": "add_define", "label": "足す定義（このProjectだけ。例：USE_FOO, LEVEL=2）", "row": "def"},
                {"name": "remove_define", "label": "外す定義", "row": "def"},
                {"name": "add_public_define", "label": "足す公開の定義（使う側にも伝わる）", "row": "pub"},
                {"name": "remove_public_define", "label": "外す公開の定義", "row": "pub"},
                {"name": "add_include", "label": "足すインクルードディレクトリ", "row": "inc"},
                {"name": "remove_include", "label": "外すインクルードディレクトリ", "row": "inc"},
                {"name": "type", "label": "ライブラリの形式ごとに変えるとき（static・shared・interface。空なら全部）", "placeholder": "例：shared"},
                {"type": "section", "label": "実行ファイル・ライブラリ・ソリューション", "collapsed": True},
                {"name": "entry_point", "label": "入口の関数（実行ファイル）", "row": "entry", "placeholder": "main・wmain・WinMain・wWinMain か、関数名"},
                {"name": "gui", "label": "GUIアプリにする（コンソールを出さない）", "type": "select", "row": "entry", "value": "", "options": [
                    {"value": "", "label": "変えない"}, {"value": "on", "label": "する"}, {"value": "off", "label": "しない"}]},
                {"name": "add_system_lib", "label": "足すOSのライブラリ（例：ws2_32, d3d11）", "row": "sys"},
                {"name": "remove_system_lib", "label": "外すOSのライブラリ", "row": "sys"},
                {"name": "export_all", "label": "Windowsで共有ライブラリのすべての関数を書き出す（dllexport を書かなくてよい）", "type": "select", "value": "", "options": [
                    {"value": "", "label": "変えない"}, {"value": "on", "label": "書き出す"}, {"value": "off", "label": "書き出さない"}]},
                {"name": "folder", "label": "Visual Studio のソリューションフォルダー（/ 区切り）", "row": "folder", "placeholder": "例：Projects/Tools"},
                {"name": "clear_folder", "label": "ソリューションフォルダーを既定に戻す", "type": "checkbox", "row": "folder"},
                {"type": "section", "label": "コンパイル・リンク・警告", "note": "値は ; で区切る。条件（コンパイラの種類・構成）を付けられる", "collapsed": True},
                {"name": "add_compile_option", "label": "足すコンパイルオプション（例：/permissive-）", "row": "copt"},
                {"name": "remove_compile_option", "label": "外すコンパイルオプション", "row": "copt"},
                {"name": "add_link_option", "label": "足すリンクオプション（例：/STACK:8388608）", "row": "lopt"},
                {"name": "remove_link_option", "label": "外すリンクオプション", "row": "lopt"},
                {"name": "add_conditional_define", "label": "足す条件付きの定義（NAME か NAME=値）", "row": "cdef"},
                {"name": "remove_conditional_define", "label": "外す条件付きの定義", "row": "cdef"},
                {"name": "compiler", "label": "条件：コンパイラの種類（上の3つに付く）", "row": "cond", "placeholder": "例：MSVC"},
                {"name": "configuration", "label": "条件：構成", "row": "cond", "placeholder": "例：Debug"},
                {"name": "warning_level", "label": "警告のレベル", "type": "select", "row": "warn", "value": "", "options": [
                    {"value": "", "label": "変えない"}, {"value": "default", "label": "既定（MSVCは /W3）"}, {"value": "0", "label": "0（/W0）"},
                    {"value": "1", "label": "1（/W1）"}, {"value": "2", "label": "2（/W2）"}, {"value": "3", "label": "3（/W3）"}, {"value": "4", "label": "4（/W4）"}]},
                {"name": "warnings_as_errors", "label": "警告をエラーにする", "type": "select", "row": "warn", "value": "", "options": [
                    {"value": "", "label": "変えない"}, {"value": "on", "label": "する"}, {"value": "off", "label": "しない"}]},
                {"type": "section", "label": "ビルドイベント・出力ファイル", "note": "コマンドは ; で区切る（引数は空白で区切り、空白を含むものは引用符で囲む）", "collapsed": True},
                {"name": "event", "label": "ビルドイベントの段", "type": "select", "value": "", "options": [
                    {"value": "", "label": "（選ぶ）"}, {"value": "pre_build", "label": "コンパイルの前"}, {"value": "pre_link", "label": "リンクの前"},
                    {"value": "post_build", "label": "ビルドの後"}]},
                {"name": "add_build_event", "label": "足すコマンド", "row": "event"},
                {"name": "remove_build_event", "label": "外すコマンド", "row": "event"},
                {"name": "add_output_file", "label": "足す、できたファイルの横へコピーするファイル・フォルダー", "row": "outfile", "placeholder": "例：assets, config.ini"},
                {"name": "remove_output_file", "label": "外すファイル・フォルダー", "row": "outfile"},
                {"type": "section", "end": True},
                {"name": "place", "label": "変更するタスクブランチ（作業空間）", "type": "select", "required": True,
                 "options_from": {"source": "more", "value": "path", "label": "branch", "note": "path", "where": {"review": None}},
                 "empty_text": "タスクブランチの作業空間がありません（タスク管理で「作業を開始」）",
                 "help": "管理ファイルが変わります。タスクブランチでコミットし、PRで反映してください。"},
            ]}},
    ],
    "bindings": [
        {"read": "project show", "args": {"module": {"arg": "module"}, "project": {"arg": "name"}}, "require": ["project"], "to": "form.vars"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.more", "from": "workspaces"},
        # 人が打つのと同じ：（作業空間で）ecobuild project set --project <名前> [--kind …] [--add-define …] …（空の欄は渡さない）
        {"on": "form.submitted", "run": "project set", "require": ["module"],
         "args": {"module": {"payload": "values.place"}, "project": {"arg": "name"}, "kind": {"payload": "values.kind"}, "no_test": {"payload": "values.no_test"},
                  "type": {"payload": "values.type"},
                  "add_source_dir": {"payload": "values.add_source_dir"}, "remove_source_dir": {"payload": "values.remove_source_dir"},
                  "add_define": {"payload": "values.add_define"}, "remove_define": {"payload": "values.remove_define"},
                  "add_public_define": {"payload": "values.add_public_define"}, "remove_public_define": {"payload": "values.remove_public_define"},
                  "add_include": {"payload": "values.add_include"}, "remove_include": {"payload": "values.remove_include"},
                  "entry_point": {"payload": "values.entry_point"}, "gui": {"payload": "values.gui"},
                  "add_system_lib": {"payload": "values.add_system_lib"}, "remove_system_lib": {"payload": "values.remove_system_lib"},
                  "export_all": {"payload": "values.export_all"}, "folder": {"payload": "values.folder"}, "clear_folder": {"payload": "values.clear_folder"},
                  "add_compile_option": {"payload": "values.add_compile_option"}, "remove_compile_option": {"payload": "values.remove_compile_option"},
                  "add_link_option": {"payload": "values.add_link_option"}, "remove_link_option": {"payload": "values.remove_link_option"},
                  "add_conditional_define": {"payload": "values.add_conditional_define"},
                  "remove_conditional_define": {"payload": "values.remove_conditional_define"},
                  "compiler": {"payload": "values.compiler"}, "configuration": {"payload": "values.configuration"},
                  "warning_level": {"payload": "values.warning_level"}, "warnings_as_errors": {"payload": "values.warnings_as_errors"},
                  "event": {"payload": "values.event"}, "add_build_event": {"payload": "values.add_build_event"},
                  "remove_build_event": {"payload": "values.remove_build_event"},
                  "add_output_file": {"payload": "values.add_output_file"}, "remove_output_file": {"payload": "values.remove_output_file"}},
         "notify": "Projectの設定を保存しました。", "close": True},
        {"on": "form.cancelled", "close": True},
    ],
}
