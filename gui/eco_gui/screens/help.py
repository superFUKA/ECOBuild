"""モジュール › ヘルプ：使い方（手順・用語）と、コマンドの一覧（ecobuild help）。手順のコマンドを押すと、そのコマンドへ飛ぶ。"""

ARGS = {"module": "."}  # モジュールのフォルダー（メニューで戻るため）

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "ヘルプ", "width": 1360, "height": 880},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "cfg-fill-page", "children": ["body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "help", "module": {"arg": "module"}}},
        {"id": "body", "part": "cfg-help", "look": "cfg-fill", "props": {
            "intro": "ECOBuild の作業は、タスク（GitHub の Issue）ごとに進めます。GUI のボタンは、ecobuild のコマンドを実行しています。",
            "steps": [
                {"title": "モジュールを用意する", "where": "ハブ › モジュールを足す",
                 "text": "新しく作るか、GitHub から取得するか、手元のフォルダを登録します。ECOBuild を使っていないリポジトリは、モジュールとして取り込めます（自分のリポジトリだけ）。",
                 "commands": ["module new", "module clone", "workspace add"]},
                {"title": "タスクを作る", "where": "モジュール › タスク › ＋ 作る",
                 "text": "やることをタスク（Issue）にします。担当者・期限・見積もり・スプリントも付けられます。",
                 "commands": ["task new", "task list", "task next"]},
                {"title": "作業を開始する", "where": "タスク › 始める",
                 "text": "タスクブランチ（task/番号-名前。名前は入力します。日本語も使えます）を作り、作業空間（このPCで作業する場所）を開きます。",
                 "commands": ["task start", "status"]},
                {"title": "作って、確かめて、コミットする", "where": "作業空間",
                 "text": "ファイルを編集し、ビルド・テストして、変更をコミットします。AI を起動して手伝わせることもできます。",
                 "commands": ["build", "test", "run", "task commit", "agent start"]},
                {"title": "提出して、レビューを受ける", "where": "作業空間 › 提出",
                 "text": "作成元へ提出（PR）します。作成元を自分が管理している（作った・管理者）なら、提出せずに入れて完了できます（次の手順は要りません）。提出の前にパイプライン（モジュール › パイプライン）を当てていれば、それが通ってから出します。",
                 "commands": ["pipeline run", "task submit", "task review", "task approve"]},
                {"title": "完了する", "where": "作業空間 › 提出 › 完了する",
                 "text": "提出を取り込み、タスクを閉じます。ほかの人の変更は同期で取り込みます。",
                 "commands": ["task finish", "task apply", "sync"]},
            ],
            "terms": [
                {"term": "モジュール", "text": "GitHub のリポジトリ1つ。制作・リンクの単位です。"},
                {"term": "型", "text": "モジュールの種類（C++・Python・汎用）。ビルドやファイルの扱いと、使えるコマンドが型で変わります。"},
                {"term": "タスク", "text": "GitHub の Issue。やることの単位です。"},
                {"term": "タスクブランチ", "text": "タスクの作業をするブランチ（task/番号-名前）。変更はここでコミットし、提出で作成元に入ります。"},
                {"term": "作業空間", "text": "このPCでモジュールの作業をする場所（clone）。"},
                {"term": "提出", "text": "タスクブランチの変更を取り込んでもらうための PR。レビューで承認されると完了できます。"},
                {"term": "ビルド設定（プロファイル）", "text": "名前を付けたビルドの設定（構成・並列数と、型ごとの項目）。"},
            ],
            # コマンド一覧の見出し（用途ごと。ここにないコマンドは「その他」に出る）
            "categories": [
                {"title": "タスクと作業", "commands": ["task", "status", "check", "pipeline", "diff", "log", "show", "blame", "restore", "stash", "track", "ignore"]},
                {"title": "ビルドと開発", "commands": ["build", "test", "tests", "run", "clean", "rebuild", "file", "files", "project", "template", "deps", "profile"]},
                {"title": "GitHubとの同期", "commands": ["sync", "branch", "ci", "release"]},
                {"title": "計画", "commands": ["milestone", "sprint"]},
                {"title": "モジュール", "commands": ["module", "workspace"]},
                {"title": "AI", "commands": ["agent"]},
                {"title": "環境と設定", "commands": ["init", "setup", "doctor", "config", "account", "container", "installer", "help"]},
            ],
            "first": "task start", "type_labels": {"cpp": "C++", "python": "Python", "generic": "汎用"},
        }},
    ],
    "bindings": [
        {"read": "help", "to": "body.catalog"},
    ],
}
