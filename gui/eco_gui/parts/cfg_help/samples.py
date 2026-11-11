SAMPLES = [
    {"name": "使い方とコマンド一覧", "props": {
        "intro": "ECOBuild の作業は、タスク（GitHub の Issue）ごとに進めます。GUI のボタンは、ecobuild のコマンドを実行しています。",
        "steps": [
            {"title": "タスクを作る", "where": "モジュール › タスク › ＋ 作る", "text": "やることをタスク（Issue）にします。", "commands": ["task new", "task start"]},
            {"title": "作って、確かめて、コミットする", "where": "作業空間", "text": "ファイルを編集し、ビルド・テストして、変更をコミットします。",
             "commands": ["build", "status"]},
        ],
        "terms": [{"term": "タスク", "text": "GitHub の Issue。やることの単位です。"},
                  {"term": "作業空間", "text": "この PC でモジュールの作業をする場所（clone）。"}],
        "categories": [{"title": "タスクと作業", "commands": ["task", "status"]}, {"title": "ビルドと開発", "commands": ["build"]}],
        "first": "task start", "type_labels": {"cpp": "C++", "python": "Python"},
        "catalog": {
            "commands": [
                {"name": "status", "path": "status", "summary": "今の状態を表示します。", "help": "今の状態を表示します。\n\n次にすることは ecobuild task start で始めます。",
                 "runnable": True, "arguments": [], "options": [{"names": ["--json"], "help": "結果をJSONで出力する", "flag": True}]},
                {"name": "task", "path": "task", "summary": "タスクを扱います。", "help": "タスクを扱います。", "runnable": False, "commands": [
                    {"name": "new", "path": "task new", "summary": "タスクを作ります。", "help": "タスクを作ります。", "runnable": True, "section": "計画",
                     "arguments": [{"name": "title", "help": "題名", "required": True}], "options": []},
                    {"name": "start", "path": "task start", "summary": "タスクの作業を開始します。", "section": "作業",
                     "help": "タスクの作業を開始します。\n\nタスクブランチを作り、作業空間を用意します。\n\n- 番号を省くと、次のタスク\n- --name でブランチの名前",
                     "runnable": True, "arguments": [{"name": "number", "help": "タスクの番号", "required": False}],
                     "options": [{"names": ["--name"], "help": "ブランチの名前", "value": "名前", "default": ""},
                                 {"names": ["--base"], "help": "作成元のブランチ", "value": "ブランチ", "choices": ["main", "develop"], "default": "main"}]}]},
            ],
            "types": {
                "cpp": {"description": "C++", "commands": [
                    {"name": "build", "path": "build", "summary": "ビルドします（CMake）。", "help": "ビルドします（CMake）。", "runnable": True,
                     "arguments": [], "options": [{"names": ["--project"], "help": "ビルドする Project", "value": "名前"}]}]},
                "python": {"description": "Python", "commands": [
                    {"name": "build", "path": "build", "summary": "ビルドします（venv）。", "help": "ビルドします（venv）。", "runnable": True, "arguments": [], "options": []}]},
            },
        }}},
    {"name": "読み込み中", "props": {"loading": True, "steps": [{"title": "タスクを作る", "where": "モジュール › タスク", "text": "やることをタスクにします。", "commands": []}]}},
    {"name": "誤り", "props": {"error": "コマンドの一覧を読めません"}},
]
