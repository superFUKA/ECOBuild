"""設定：モジュールの仕様・ビルド設定・（C++ の設定・ファイルテンプレート）・ブランチの保護・管理するファイル・リリース・コンテナ・アカウント・片付け。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "設定", "width": 1360, "height": 880},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "tabs"]},
        {"id": "nav", "screen": "menu", "args": {"current": "settings", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "設定", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "tabs", "layout": "tabs", "children": ["general", "profiles", "cpp_general", "cpp_templates", "protect", "track", "releases", "container", "account", "put_away"],
         "props": {"labels": ["全般", "ビルド設定", "C++ の設定", "ファイルテンプレート", "ブランチの保護", "管理するファイル", "リリース", "コンテナ", "アカウント",
                              "片付け"]}},
        # C++ のモジュールだけのタブ（中身は画面 cpp-general・cpp-templates）と、コンテナ（画面 container-body）
        {"id": "cpp_general", "screen": "cpp-general", "args": {"module": {"arg": "module"}}},
        {"id": "cpp_templates", "screen": "cpp-templates", "args": {"module": {"arg": "module"}}},
        {"id": "container", "screen": "container-body", "args": {"module": {"arg": "module"}}},

        # 全般：モジュールの今の姿と、今の ECOBuild の仕様に合わせる（module upgrade）
        {"id": "general", "layout": "column", "children": ["info", "upgrade_note", "upgrade_row"]},
        {"id": "info", "part": "facts", "props": {
            "items": [
                {"key": "name", "label": "名前"}, {"key": "type", "label": "型"}, {"key": "root", "label": "場所"},
                {"key": "repository", "label": "リポジトリ"}, {"key": "private", "label": "公開"}, {"key": "archived", "label": "アーカイブ"},
                {"key": "default_base", "label": "作成元のブランチ"},
                {"key": "format", "label": "仕様の版"}, {"key": "latest_format", "label": "今の ECOBuild の仕様の版"},
            ],
            "labels": {"private": {"true": "非公開", "false": "公開"}, "archived": {"true": "アーカイブ済み（読み取り専用）", "false": "していない"}},
        }},
        {"id": "upgrade_note", "part": "note", "props": {
            "text": "仕様の版が古いときは、今の ECOBuild の仕様に合わせます（「ECOBuild の更新」としてコミット。タスクブランチでなければ GitHub へ push も）。"}},
        {"id": "upgrade_row", "layout": "row", "children": ["upgrade_branch", "upgrade"]},
        {"id": "upgrade_branch", "part": "text-input", "props": {"title": "合わせるブランチ（空なら今いるブランチ）", "placeholder": "例：main"}},
        {"id": "upgrade", "part": "button", "props": {"label": "今の仕様に合わせる…", "hint": "変えるファイルを確かめてから合わせます"}},

        # ビルド設定（profile list・use・add・project・remove）。追加・編集・Project ごとの上書きは、入力の窓（cfg-profile-…）
        {"id": "profiles", "layout": "column", "children": ["profile_table"]},
        {"id": "profile_table", "part": "cfg-profiles"},

        # ブランチの保護（module protect）
        {"id": "protect", "layout": "column", "children": ["protect_note", "protect_now", "protect_form", "unprotect"]},
        {"id": "protect_now", "part": "facts", "props": {"items": [
            {"key": "branch", "label": "保護しているブランチ"}, {"key": "approvals", "label": "要る承認の数"},
            {"key": "checks", "label": "通っていること（CI）"}]}},
        {"id": "protect_note", "part": "note", "props": {
            "text": "作成元のブランチを、GitHub のブランチの保護で守ります（提出以外での変更・強制 push・削除を止める）。"}},
        {"id": "protect_form", "layout": "row", "children": ["approvals", "require_ci", "do_protect"]},
        {"id": "approvals", "part": "text-input", "props": {"title": "取り込みに要る承認の数（空なら既定）", "placeholder": "例：1"}},
        {"id": "require_ci", "part": "select", "props": {"title": "CI", "options": [
            {"value": "", "label": "見ない"}, {"value": "true", "label": "通っていることも必須にする"}]}},
        {"id": "do_protect", "part": "button", "props": {"label": "保護する", "primary": True}},
        {"id": "unprotect", "part": "button", "props": {"label": "保護を外す"}},

        # 管理するファイル（track・track add・track remove・ignore）
        {"id": "track", "layout": "column", "children": ["track_note", "patterns", "pattern_form"]},
        {"id": "track_note", "part": "note", "props": {
            "text": "新しいファイルのうち、コミットに自動で含めるもの。変えたら、タスクブランチでコミットします。"}},
        {"id": "patterns", "part": "table", "props": {
            "columns": [{"key": "pattern", "label": "パターン"}, {"key": "source", "label": "出どころ"}, {"key": "excluded", "label": "状態"}],
            "key": "pattern", "actions": [{"name": "remove", "label": "外す"}],
            "labels": {"source": {"ecobuild": "ECOBuild", "type": "型の既定", "module": "このモジュール"},
                       "excluded": {"true": "外している", "false": ""}},
            "empty_text": "パターンはありません。",
        }},
        {"id": "pattern_form", "layout": "row", "children": ["pattern", "track_add", "ignore_add"]},
        {"id": "pattern", "part": "text-input", "props": {"title": "パターン（.gitignore と同じ書き方）", "placeholder": "例：data/**"}},
        {"id": "track_add", "part": "button", "props": {"label": "＋ 管理に足す", "primary": True}},
        {"id": "ignore_add", "part": "button", "props": {"label": ".gitignore に足す", "hint": "git の管理から外す"}},

        # リリース（release list・release create）
        {"id": "releases", "layout": "column", "children": ["release_list", "release_form", "release_more"]},
        {"id": "release_list", "part": "table", "props": {
            "columns": [{"key": "tag", "label": "タグ"}, {"key": "name", "label": "題名"}, {"key": "latest", "label": ""}, {"key": "url", "label": "場所"}],
            "key": "tag", "labels": {"latest": {"true": "最新", "false": ""}},
            "empty_text": "リリースはまだありません。",
        }},
        {"id": "release_form", "layout": "row", "children": ["release_tag", "release_title", "release_target"]},
        {"id": "release_tag", "part": "text-input", "props": {"title": "タグ", "placeholder": "例：v1.0.0"}},
        {"id": "release_title", "part": "text-input", "props": {"title": "題名（空ならタグ）"}},
        {"id": "release_target", "part": "text-input", "props": {"title": "タグを付けるブランチ（空なら作成元）"}},
        {"id": "release_more", "layout": "row", "children": ["release_notes", "release_create"]},
        {"id": "release_notes", "part": "text-input", "props": {"title": "説明"}},
        {"id": "release_create", "part": "button", "props": {"label": "＋ リリースを作る", "primary": True}},

        # アカウント（account show・account use）
        {"id": "account", "layout": "column", "children": ["me", "account_note", "account_form", "account_clear"]},
        {"id": "me", "part": "facts", "props": {
            "items": [{"key": "login", "label": "あなた"}, {"key": "role", "label": "役割"}, {"key": "owner", "label": "リポジトリの所有者"},
                      {"key": "workspace_account", "label": "この作業空間に結び付けたアカウント"}],
            "labels": {"role": {"read": "読む", "triage": "タスクの整理", "write": "書き込み", "maintain": "管理の一部", "admin": "管理者"}},
        }},
        {"id": "account_note", "part": "note", "props": {
            "text": "この作業空間を、別の GitHub のアカウント（AI 用など）として動かせます。先に gh auth login でログインしておきます。"}},
        {"id": "account_form", "layout": "row", "children": ["account_name", "account_use"]},
        {"id": "account_name", "part": "text-input", "props": {"title": "GitHub のアカウント", "placeholder": "例：octocat"}},
        {"id": "account_use", "part": "button", "props": {"label": "このアカウントで動かす"}},
        {"id": "account_clear", "part": "button", "props": {"label": "結び付けを外す"}},

        # 片付け（module archive・unarchive・delete）。どのモジュールかは、module show で読んだリポジトリ（人は打たない）
        {"id": "put_away", "layout": "column", "children": ["away_note", "away_now", "away_row", "delete_note", "delete_row"]},
        {"id": "away_note", "part": "note", "props": {
            "text": "使わなくなったモジュールは、まずアーカイブ（読み取り専用）にします。削除できるのは、アーカイブしたものだけです。"}},
        {"id": "away_now", "part": "facts", "props": {
            "items": [{"key": "repository", "label": "片付けるモジュール"}, {"key": "archived", "label": "今の状態"}],
            "labels": {"archived": {"true": "アーカイブ済み（読み取り専用）", "false": "アーカイブしていない"}}}},
        {"id": "away_row", "layout": "row", "children": ["archive", "unarchive"]},
        {"id": "archive", "part": "button", "props": {"label": "アーカイブする"}},
        {"id": "unarchive", "part": "button", "props": {"label": "アーカイブを解除"}},
        {"id": "delete_note", "part": "note", "props": {
            "text": "削除すると、GitHub のリポジトリを Issue・PR ごと消します（90日以内なら GitHub のアカウントの設定から戻せます）。アーカイブ済みのときだけ、下に削除の欄が出ます。"}},
        {"id": "delete_row", "layout": "row", "children": ["delete_confirm", "remove_workspaces", "delete"]},
        {"id": "delete_confirm", "part": "text-input", "props": {
            "title": "削除の確かめ（取り違えないように、所有者/名前 を入力）", "placeholder": "例：owner/name"}},
        {"id": "remove_workspaces", "part": "select", "props": {"title": "この PC の作業空間", "options": [
            {"value": "", "label": "残す"}, {"value": "true", "label": "一緒に削除する"}]}},
        {"id": "delete", "part": "button", "props": {"label": "削除する"}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_type", "from": "type"},
        {"show": "cpp_general", "when": {"module_type": "cpp"}},
        {"show": "cpp_templates", "when": {"module_type": "cpp"}},
        # 全般
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "info.data"},
        {"on": "upgrade_branch.changed", "set": {"upgrade_branch": {"payload": "text"}}},
        # 入力の窓（下見で、変えるファイルを先に見せる。実行は、その窓から）
        {"on": "upgrade.pressed", "open": "mod-upgrade", "inside": True, "args": {"module": {"arg": "module"}, "branch": {"value": "upgrade_branch"}}},
        # ビルド設定（ecobuild profile use <名前>・profile remove <名前>・profile project <名前> <Project> --clear）
        # 表の列と、追加・編集の窓は、モジュールの型（module show の type）で変わる
        {"read": "profile list", "args": {"module": {"arg": "module"}}, "to": "profile_table.data"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "profile_table.kind", "from": "type"},
        # 追加・編集・上書き・削除は、窓の中で選んだタスクブランチの作業空間で（なければ灰色と「今は見るだけ」の帯）
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "profile_table.workspaces", "from": "workspaces"},
        {"on": "profile_table.open_tasks", "open": "tasks", "args": {"module": {"arg": "module"}}, "here": True},
        {"on": "profile_table.use", "when": {"stop": False}, "run": "profile use", "args": {"module": {"arg": "module"}, "name": {"payload": "name"}},
         "notify": "このPCではビルド設定 {selected} を使います。"},
        {"on": "profile_table.use", "when": {"stop": True}, "run": "profile use", "args": {"module": {"arg": "module"}, "name": "none"},
         "notify": "ビルド設定の使用をやめました。"},
        {"on": "profile_table.remove", "open": "cfg-profile-remove", "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "inside": True},
        {"on": "profile_table.add", "when": {"kind": "cpp"}, "open": "cfg-profile-edit-cpp",
         "args": {"module": {"arg": "module"}, "name": ""}, "inside": True},
        {"on": "profile_table.add", "when": {"kind": "python"}, "open": "cfg-profile-edit-python",
         "args": {"module": {"arg": "module"}, "name": ""}, "inside": True},
        {"on": "profile_table.add", "when": {"kind": "generic"}, "open": "cfg-profile-edit",
         "args": {"module": {"arg": "module"}, "name": ""}, "inside": True},
        {"on": "profile_table.edit", "when": {"kind": "cpp"}, "open": "cfg-profile-edit-cpp",
         "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "inside": True},
        {"on": "profile_table.edit", "when": {"kind": "python"}, "open": "cfg-profile-edit-python",
         "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "inside": True},
        {"on": "profile_table.edit", "when": {"kind": "generic"}, "open": "cfg-profile-edit",
         "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "inside": True},
        {"on": "profile_table.project", "open": "cfg-profile-project",
         "args": {"module": {"arg": "module"}, "name": {"payload": "name"}, "project": {"payload": "project"}}, "inside": True},
        {"on": "profile_table.project_clear", "open": "cfg-profile-project-clear",
         "args": {"module": {"arg": "module"}, "name": {"payload": "name"}, "project": {"payload": "project"}}, "inside": True},
        # ブランチの保護（ecobuild module protect [--approvals <数>] [--require-ci]・module protect --off）
        {"on": "approvals.changed", "set": {"approvals": {"payload": "text"}}},
        {"on": "require_ci.changed", "set": {"require_ci": {"payload": "value"}}},
        {"on": "do_protect.pressed", "run": "module protect",
         "args": {"module": {"arg": "module"}, "approvals": {"value": "approvals"}, "require_ci": {"value": "require_ci"}}},
        {"on": "unprotect.pressed", "run": "module protect", "args": {"module": {"arg": "module"}, "off": True}},
        {"read": "module protection", "args": {"module": {"arg": "module"}}, "to": "protect_now.data"},
        # 管理するファイル（ecobuild track add <パターン>・track remove <パターン>・ignore <パターン>）
        {"read": "track", "args": {"module": {"arg": "module"}}, "to": "patterns.rows", "from": "patterns"},
        {"on": "pattern.changed", "set": {"pattern": {"payload": "text"}}},
        {"on": "track_add.pressed", "run": "track add", "args": {"module": {"arg": "module"}, "patterns": [{"value": "pattern"}]}},
        {"on": "ignore_add.pressed", "run": "ignore", "args": {"module": {"arg": "module"}, "patterns": [{"value": "pattern"}]}},
        {"on": "patterns.action", "when": {"action": "remove"}, "run": "track remove",
         "args": {"module": {"arg": "module"}, "patterns": [{"payload": "id"}]}},
        # リリース（ecobuild release create <タグ> [--title <題名>] [--notes <説明>] [--target <ブランチ>]）
        {"read": "release list", "args": {"module": {"arg": "module"}}, "to": "release_list.rows"},
        {"on": "release_tag.changed", "set": {"release_tag": {"payload": "text"}}},
        {"on": "release_title.changed", "set": {"release_title": {"payload": "text"}}},
        {"on": "release_target.changed", "set": {"release_target": {"payload": "text"}}},
        {"on": "release_notes.changed", "set": {"release_notes": {"payload": "text"}}},
        {"on": "release_create.pressed", "run": "release create", "args": {
            "module": {"arg": "module"}, "tag": {"value": "release_tag"}, "title": {"value": "release_title"},
            "notes": {"value": "release_notes"}, "target": {"value": "release_target"}}},
        # アカウント（ecobuild account use --account <アカウント>・account use --clear）
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "me.data"},
        {"on": "account_name.changed", "set": {"account_name": {"payload": "text"}}},
        {"on": "account_use.pressed", "run": "account use", "args": {"module": {"arg": "module"}, "account": {"value": "account_name"}}},
        {"on": "account_clear.pressed", "run": "account use", "args": {"module": {"arg": "module"}, "clear": True}},
        # 片付け（ecobuild module archive <名前>・module unarchive <名前>・module delete <名前> --confirm <名前> [--remove-workspaces]）
        # 名前は、module show で読んだリポジトリを共有の値にして渡す。今の状態に合うボタンだけを出す
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "away_now.data"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_repository", "from": "repository"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_archived", "from": "archived"},
        {"show": "archive", "when": {"module_archived": False}},
        {"show": "unarchive", "when": {"module_archived": True}},
        {"show": "delete_confirm", "when": {"module_archived": True}},
        {"show": "remove_workspaces", "when": {"module_archived": True}},
        {"show": "delete", "when": {"module_archived": True}},
        {"on": "archive.pressed", "run": "module archive", "args": {"module": {"arg": "module"}, "name": {"value": "module_repository"}}},
        {"on": "unarchive.pressed", "run": "module unarchive", "args": {"module": {"arg": "module"}, "name": {"value": "module_repository"}}},
        # 削除の確かめ（--confirm）だけは、人が打った名前をそのまま渡す。合っているかは ecobuild が確かめる。打つまで押せない
        {"on": "delete_confirm.changed", "set": {"delete_confirm": {"payload": "text"}}},
        {"on": "remove_workspaces.changed", "set": {"remove_workspaces": {"payload": "value"}}},
        {"on": "delete.pressed", "run": "module delete", "require": ["confirm"], "args": {
            "module": {"arg": "module"}, "name": {"value": "module_repository"}, "confirm": {"value": "delete_confirm"},
            "remove_workspaces": {"value": "remove_workspaces"}}},
    ],
}
