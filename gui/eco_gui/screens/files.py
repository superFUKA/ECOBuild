"""モジュール › ファイル：ファイルの木と、選んだファイルのまだコミットしていない変更。足す・動かす・消す・変更を捨てる。

C++ のモジュールでだけ使えるもの（サブプロジェクトの画面・試験を作る・テンプレート）は、モジュールの型が cpp のときだけ出す。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ファイル", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "body", "selected", "ops", "one", "many", "add", "ignore", "about"]},
        {"id": "nav", "screen": "menu", "args": {"current": "files", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload", "to_cpp"]},
        {"id": "title", "part": "note", "props": {"text": "ファイル", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "to_cpp", "part": "button", "props": {"label": "C++ のサブプロジェクト…", "hint": "サブプロジェクト・依存先・テンプレート（C++ のモジュール）"}},
        {"id": "body", "layout": "row", "children": ["tree", "diff"]},
        {"id": "tree", "part": "file-tree"},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "ファイルを選ぶと、まだコミットしていない変更が出ます。"}},
        # 選んだ1つ（ファイルか、フォルダー）に
        {"id": "selected", "part": "note", "props": {"prefix": "選んでいるファイル・フォルダー："}},
        {"id": "ops", "layout": "row", "children": ["destination", "move", "remove"]},
        {"id": "destination", "part": "text-input", "props": {"title": "動かす先（名前を変えるときも）", "placeholder": "例：src/new_name.py"}},
        {"id": "move", "part": "button", "props": {"label": "動かす"}},
        {"id": "remove", "part": "button", "props": {"label": "消す"}},
        {"id": "one", "layout": "row", "children": ["restore", "ignore_file", "blame", "make_test"]},
        {"id": "restore", "part": "button", "props": {"label": "変更を捨てる", "hint": "最後のコミットの状態に戻す"}},
        {"id": "ignore_file", "part": "button", "props": {"label": "無視に足す", "hint": ".gitignore に、このパスを足す"}},
        {"id": "blame", "part": "button", "props": {"label": "記録を見る…", "hint": "このファイルを変えたコミットと、行ごとの記録"}},
        {"id": "make_test", "part": "button", "props": {"label": "試験を作る（C++）", "hint": "ヘッダー・ソースの試験のひな形を作る（ecobuild file test）"}},
        # チェックしたファイルに
        {"id": "many", "layout": "row", "children": ["many_title", "remove_checked", "restore_checked", "uncheck"]},
        {"id": "many_title", "part": "note", "props": {"text": "チェックしたファイルを："}},
        {"id": "remove_checked", "part": "button", "props": {"label": "まとめて消す"}},
        {"id": "restore_checked", "part": "button", "props": {"label": "まとめて変更を捨てる"}},
        {"id": "uncheck", "part": "button", "props": {"label": "チェックを外す"}},
        # 足す
        {"id": "add", "layout": "row", "children": ["new_path", "template", "do_add"]},
        {"id": "new_path", "part": "text-input", "props": {"title": "新しいファイル（フォルダーごと書くと、フォルダーも作る）", "placeholder": "例：src/util/text.py"}},
        {"id": "template", "part": "text-input", "props": {
            "title": "テンプレート（C++。空なら拡張子で選ぶ）", "placeholder": "例：header（C++ のサブプロジェクト › テンプレート）"}},
        {"id": "do_add", "part": "button", "props": {"label": "＋ 足す", "primary": True}},
        {"id": "ignore", "layout": "row", "children": ["pattern", "do_ignore"]},
        {"id": "pattern", "part": "text-input", "props": {"title": "無視するパターン（.gitignore に足す）", "placeholder": "例：*.log"}},
        {"id": "do_ignore", "part": "button", "props": {"label": "無視に足す"}},
        {"id": "about", "part": "note", "props": {
            "text": "フォルダーは、名前の横の「選ぶ」で選びます。空のフォルダーは作れません（Git が持たないので、中にファイルを足します）。"}},
    ],
    "bindings": [
        {"read": "files", "args": {"module": {"arg": "module"}}, "to": "tree.paths", "from": "files"},
        # モジュールの型（ecobuild module show の type）で、C++ だけの部品を出し分ける
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_type", "from": "type"},
        {"show": "to_cpp", "when": {"module_type": "cpp"}},
        {"show": "make_test", "when": {"module_type": "cpp"}},
        {"show": "template", "when": {"module_type": "cpp"}},
        {"on": "reload.pressed", "refresh": True},
        {"on": "tree.selected", "set": {"file": {"payload": "path"}}},
        {"value": "file", "to": "tree.selected"},
        {"value": "file", "to": "selected.text"},
        {"on": "tree.changed", "set": {"files_checked": {"payload": "paths"}}},
        {"value": "files_checked", "to": "tree.checked"},
        {"on": "uncheck.pressed", "set": {"files_checked": None}},
        # 足す・動かす・消す（ecobuild file add <パス> [--template <名前>]・file move <元> <先>・file remove <パス…>。
        # 型が管理ファイルも合わせる）。チェックが1つもなければ、「まとめて…」は押せない（require）
        {"on": "new_path.changed", "set": {"new_path": {"payload": "text"}}},
        {"on": "template.changed", "set": {"new_template": {"payload": "text"}}},
        {"on": "do_add.pressed", "run": "file add",
         "args": {"module": {"arg": "module"}, "paths": [{"value": "new_path"}], "template": {"value": "new_template"}}},
        {"on": "destination.changed", "set": {"destination": {"payload": "text"}}},
        {"on": "move.pressed", "run": "file move",
         "args": {"module": {"arg": "module"}, "source": {"value": "file"}, "destination": {"value": "destination"}}, "set": {"file": None}},
        {"on": "remove.pressed", "run": "file remove", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}, "set": {"file": None}},
        {"on": "remove_checked.pressed", "run": "file remove",
         "args": {"module": {"arg": "module"}, "paths": {"value": "files_checked"}}, "require": ["paths"],
         "set": {"files_checked": None, "file": None}},
        # 変更を捨てる・無視に足す（ecobuild restore <パス…>・ecobuild ignore <パターン…>）
        {"on": "restore.pressed", "run": "restore", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}},
        {"on": "restore_checked.pressed", "run": "restore",
         "args": {"module": {"arg": "module"}, "paths": {"value": "files_checked"}}, "require": ["paths"], "set": {"files_checked": None}},
        {"on": "ignore_file.pressed", "run": "ignore", "args": {"module": {"arg": "module"}, "patterns": [{"value": "file"}]}},
        {"on": "pattern.changed", "set": {"ignore_pattern": {"payload": "text"}}},
        {"on": "do_ignore.pressed", "run": "ignore", "args": {"module": {"arg": "module"}, "patterns": [{"value": "ignore_pattern"}]}},
        # C++：選んだヘッダー・ソースの試験を作る（ecobuild file test <パス>）
        {"on": "make_test.pressed", "run": "file test", "args": {"module": {"arg": "module"}, "path": {"value": "file"}}},
        # 別の画面：ファイルの記録（新しい窓）・C++ のサブプロジェクト（この窓）
        {"on": "blame.pressed", "open": "blame", "args": {"module": {"arg": "module"}, "path": {"value": "file"}}},
        {"on": "to_cpp.pressed", "open": "cpp", "args": {"module": {"arg": "module"}}, "here": True},
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}, "to": "diff.text"},
    ],
}
