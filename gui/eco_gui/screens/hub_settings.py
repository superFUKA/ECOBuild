"""ハブ › 設定：この PC の ECOBuild の設定（全モジュール共通）。アカウント・AI・コンテナのイメージ・ECOBuild の更新。"""

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild の設定", "width": 900, "height": 720},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "tabs"]},
        {"id": "head", "layout": "row", "children": ["title", "reload", "doctor"]},
        {"id": "title", "part": "note", "props": {"text": "ECOBuild の設定", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "doctor", "part": "button", "props": {"label": "環境チェック"}},
        {"id": "tabs", "layout": "tabs", "children": ["general", "ai", "images_tab", "ecobuild"],
         "props": {"labels": ["全般", "AI", "コンテナ", "ECOBuild"]}},

        # 全般：GitHub のアカウント・ツールの設定（config）・開発の環境の準備（setup）
        {"id": "general", "layout": "column", "children": ["accounts_title", "accounts", "config_title", "config", "config_form", "config_unset",
                                                              "setup_title", "setup_form"]},
        {"id": "accounts_title", "part": "note", "props": {"text": "GitHub のアカウント（この PC の gh でログイン中のもの）"}},
        {"id": "accounts", "part": "table", "props": {
            "columns": [{"key": "login", "label": "アカウント"}, {"key": "active", "label": "状態"}],
            "key": "login", "labels": {"active": {"true": "使用中", "false": ""}},
            "empty_text": "ログイン中のアカウントはありません（端末で gh auth login）。",
        }},
        {"id": "config_title", "part": "note", "props": {"text": "ツールの設定（空のものは既定）"}},
        {"id": "config", "part": "facts", "props": {"items": [
            {"key": "owner", "label": "owner：リポジトリの既定の所有者（既定はログイン中のユーザー）"},
            {"key": "log_level", "label": "log_level：ログに残す量（off・error・info・debug）"},
            {"key": "log_max_mb", "label": "log_max_mb：ログの大きさの上限（MB）"},
            {"key": "operator_style", "label": "operator_style：オペレーターの話し方"},
            {"key": "agent_deny", "label": "agent_deny：コンテナの中のエージェントに使わせないもの"},
            {"key": "agent_claude_version", "label": "agent_claude_version：コンテナに入れる Claude Code の版"},
            {"key": "cmake", "label": "cmake：C++ のビルドに使う cmake のパス"},
            {"key": "ctest", "label": "ctest：C++ のテストに使う ctest のパス"},
            {"key": "python", "label": "python：モジュールの .venv を作る Python のパス"},
        ]}},
        {"id": "config_form", "layout": "row", "children": ["config_key", "config_value", "config_set"]},
        {"id": "config_key", "part": "select", "props": {"title": "項目", "options": [
            {"value": "", "label": "（選ぶ）"}, {"value": "owner", "label": "owner"}, {"value": "log_level", "label": "log_level"},
            {"value": "log_max_mb", "label": "log_max_mb"}, {"value": "operator_style", "label": "operator_style"},
            {"value": "agent_deny", "label": "agent_deny"}, {"value": "agent_claude_version", "label": "agent_claude_version"},
            {"value": "cmake", "label": "cmake"}, {"value": "ctest", "label": "ctest"}, {"value": "python", "label": "python"}]}},
        {"id": "config_value", "part": "text-input", "props": {"title": "値"}},
        {"id": "config_set", "part": "button", "props": {"label": "設定する", "primary": True}},
        {"id": "config_unset", "part": "button", "props": {"label": "選んだ項目を既定に戻す"}},
        {"id": "setup_title", "part": "note", "props": {"text": "開発の環境の準備（git の名前・メールなど。変えるものだけ入力）"}},
        {"id": "setup_form", "layout": "row", "children": ["setup_name", "setup_email", "setup"]},
        {"id": "setup_name", "part": "text-input", "props": {"title": "git の名前"}},
        {"id": "setup_email", "part": "text-input", "props": {"title": "git のメール"}},
        {"id": "setup", "part": "button", "props": {"label": "準備する"}},

        # AI：コンテナの中のエージェントがログインに使うトークン（値は見せない）と、Claude Code の版
        {"id": "ai", "layout": "column", "children": ["token_title", "token", "token_row", "token_note", "version_title", "channels",
                                                       "version_status", "version_form", "version_now", "version_row"]},
        {"id": "token_title", "part": "note", "props": {"text": "エージェントのトークン"}},
        {"id": "token", "part": "facts", "props": {
            "items": [{"key": "saved", "label": "トークン"}, {"key": "path", "label": "置き場所"}],
            "labels": {"saved": {"true": "保存済み", "false": "未設定"}}}},
        {"id": "token_row", "layout": "row", "children": ["token_login", "token_remove"]},
        {"id": "token_login", "part": "button", "props": {
            "label": "トークンを作る", "hint": "窓が開く。ブラウザーで許可すると、出たトークンを自動で覚える"}},
        {"id": "token_remove", "part": "button", "props": {"label": "トークンを消す"}},
        {"id": "token_note", "part": "note", "props": {
            "text": "手元のトークンを入れるときは、端末で ecobuild agent token set（値は画面に出ず、コマンドの行にも残りません）。"}},
        {"id": "version_title", "part": "note", "props": {"text": "コンテナに入れる Claude Code の版（変えると、イメージを作り直します）"}},
        {"id": "channels", "part": "facts", "props": {
            "items": [{"key": "stable", "label": "stable の今の版"}, {"key": "latest", "label": "latest の今の版"}]}},
        {"id": "version_status", "part": "facts", "props": {
            "items": [{"key": "setting", "label": "今の設定（空なら、イメージを作るときの最新）"}, {"key": "reason", "label": "補足"}]}},
        {"id": "version_form", "layout": "row", "children": ["version_pick", "claude_version"]},
        {"id": "version_pick", "part": "select-text", "props": {"title": "版を選ぶ（新しい順）", "none_label": "（選ぶ）"}},
        {"id": "claude_version", "part": "text-input", "props": {"title": "または、打って決める", "placeholder": "例：2.1.302・stable・latest"}},
        {"id": "version_now", "part": "note", "props": {"prefix": "入れる版："}},
        {"id": "version_row", "layout": "row", "children": ["version_set", "version_unset"]},
        {"id": "version_set", "part": "button", "props": {"label": "この版にする"}},
        {"id": "version_unset", "part": "button", "props": {"label": "既定に戻す", "hint": "イメージを作るときの最新"}},

        # コンテナ：この PC にあるイメージ（container image list・build・prune）
        {"id": "images_tab", "layout": "column", "children": ["docker", "images", "images_row", "images_out"]},
        {"id": "docker", "part": "facts", "props": {
            "items": [{"key": "docker_ready", "label": "Docker"}, {"key": "docker_detail", "label": "Docker の状態"},
                      {"key": "missing", "label": "まだイメージを作っていない作業空間（動かすときに作ります）"}],
            "labels": {"docker_ready": {"true": "使える", "false": "まだ使えない"}}}},
        {"id": "images", "part": "table", "props": {
            "columns": [{"key": "module", "label": "モジュール"}, {"key": "name", "label": "イメージ"}, {"key": "current", "label": "作り方"},
                        {"key": "environment", "label": "種類"}, {"key": "size", "label": "大きさ"}, {"key": "created", "label": "作った時"},
                        {"key": "used_by", "label": "使っている作業空間"}],
            "key": "name",
            "labels": {"current": {"true": "今", "false": "古い"}, "environment": {"true": "環境", "false": "コンテナ"}},
            "empty_text": "イメージはまだありません。",
        }},
        {"id": "images_row", "layout": "row", "children": ["images_build", "images_prune"]},
        {"id": "images_build", "part": "button", "props": {"label": "今の作り方で作る", "hint": "1つ数分かかります"}},
        {"id": "images_prune", "part": "button", "props": {"label": "古いイメージを消す", "hint": "今の作り方でなく、どのコンテナも使っていないもの"}},
        {"id": "images_out", "part": "output"},

        # ECOBuild：入っている版と、更新・版を選んで入れ直す（installer show・versions・update）
        {"id": "ecobuild", "layout": "column", "children": ["installed", "update_note", "update", "ref_row", "versions_title", "branch_row", "versions"]},
        {"id": "installed", "part": "facts", "props": {
            "items": [{"key": "version", "label": "版"}, {"key": "source", "label": "入れた元"}, {"key": "ref", "label": "ブランチ・タグ"},
                      {"key": "commit", "label": "コミット"}, {"key": "editable", "label": "入れ方"}, {"key": "python", "label": "Python"},
                      {"key": "gui", "label": "GUI"}, {"key": "types", "label": "型"}],
            "labels": {"editable": {"true": "手元のソース（更新はできません）", "false": "インストーラー"}}}},
        {"id": "update_note", "part": "note", "props": {
            "text": "更新は、別の窓のインストーラーが入れ直します。GUI も入れ直すときは、開いている窓を閉じます。"}},
        {"id": "update", "part": "button", "props": {"label": "最新に更新する", "primary": True}},
        {"id": "ref_row", "layout": "row", "children": ["ref", "update_ref"]},
        {"id": "ref", "part": "text-input", "props": {"title": "入れる版（ブランチ・タグ・コミット）", "placeholder": "例：main"}},
        {"id": "update_ref", "part": "button", "props": {"label": "この版に入れ直す"}},
        {"id": "versions_title", "part": "note", "props": {"text": "ブランチの最近の版（新しい順。ブランチを選ばなければ、入れたときのブランチ）"}},
        {"id": "branch_row", "layout": "row", "children": ["branch", "update_branch"]},
        {"id": "branch", "part": "select-text", "props": {"title": "ブランチ", "none_label": "（入れたときのブランチ）"}},
        {"id": "update_branch", "part": "button", "props": {"label": "このブランチの最新に入れ直す"}},
        {"id": "versions", "part": "table", "props": {
            "columns": [{"key": "date", "label": "日時"}, {"key": "subject", "label": "何を"}, {"key": "current", "label": ""},
                        {"key": "latest", "label": ""}, {"key": "sha", "label": "コミット"}],
            "key": "sha", "actions": [{"name": "install", "label": "この版を入れる"}],
            "labels": {"current": {"true": "今の版", "false": ""}, "latest": {"true": "最新", "false": ""}},
            "empty_text": "入れられる版が分かりません。",
        }},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "doctor.pressed", "open": "doctor"},
        # 全般（ecobuild config set <項目> <値>・config unset <項目>・setup [--name <名前>] [--email <メール>]）
        {"read": "account list", "to": "accounts.rows"},
        {"read": "config list", "to": "config.data"},
        {"on": "config_key.changed", "set": {"config_key": {"payload": "value"}}},
        {"on": "config_value.changed", "set": {"config_value": {"payload": "text"}}},
        {"on": "config_set.pressed", "run": "config set", "args": {"key": {"value": "config_key"}, "value": {"value": "config_value"}}},
        {"on": "config_unset.pressed", "run": "config unset", "args": {"key": {"value": "config_key"}}},
        {"on": "setup_name.changed", "set": {"setup_name": {"payload": "text"}}},
        {"on": "setup_email.changed", "set": {"setup_email": {"payload": "text"}}},
        {"on": "setup.pressed", "run": "setup", "args": {"name": {"value": "setup_name"}, "email": {"value": "setup_email"}}},
        # AI（ecobuild agent token login・agent token remove。トークンの値は、画面を通さない）
        {"read": "agent token status", "to": "token.data"},
        {"read": "agent token status", "into": "token_saved", "from": "saved"},
        {"show": "token_remove", "when": {"token_saved": True}},  # 消せるのは、保存してあるときだけ
        {"on": "token_login.pressed", "run": "agent token login"},
        {"on": "token_remove.pressed", "run": "agent token remove"},
        {"read": "agent version list", "to": "channels.data", "from": "channels"},
        {"read": "agent version status", "to": "version_status.data"},
        # 版は、読んだ一覧から選ぶか、打つ（stable・latest も）。後から決めた方が入る
        {"read": "agent version list", "to": "version_pick.options", "from": "versions"},
        {"on": "version_pick.changed", "set": {"claude_version": {"payload": "value"}}},
        {"on": "claude_version.changed", "set": {"claude_version": {"payload": "text"}}},
        {"value": "claude_version", "to": "version_now.text"},
        {"on": "version_set.pressed", "run": "config set", "args": {"key": "agent_claude_version", "value": {"value": "claude_version"}}},
        {"on": "version_unset.pressed", "run": "config unset", "args": {"key": "agent_claude_version"}},
        # コンテナ（ecobuild container image build・container image prune）
        {"read": "container image list", "to": "docker.data"},
        {"read": "container image list", "to": "images.rows", "from": "images"},
        {"on": "images_build.pressed", "run": "container image build", "output": "images_out.lines"},
        {"on": "images_prune.pressed", "run": "container image prune"},
        # ECOBuild（ecobuild installer update [--ref <版>]）
        {"read": "installer show", "to": "installed.data"},
        # ブランチを選ぶと、そのブランチの版を読む（ecobuild installer versions --ref <ブランチ>）
        {"read": "installer versions", "to": "branch.options", "from": "branches"},
        {"on": "branch.changed", "set": {"versions_branch": {"payload": "value"}}},
        {"value": "versions_branch", "to": "branch.value"},
        {"read": "installer versions", "args": {"ref": {"value": "versions_branch"}}, "to": "versions.rows", "from": "commits"},
        {"on": "update_branch.pressed", "run": "installer update", "require": ["ref"], "args": {"ref": {"value": "versions_branch"}}},
        {"on": "update.pressed", "run": "installer update"},
        {"on": "ref.changed", "set": {"ref": {"payload": "text"}}},
        {"on": "update_ref.pressed", "run": "installer update", "require": ["ref"], "args": {"ref": {"value": "ref"}}},  # 版を入れるまで押せない
        {"on": "versions.action", "when": {"action": "install"}, "run": "installer update", "args": {"ref": {"payload": "id"}}},
    ],
}
