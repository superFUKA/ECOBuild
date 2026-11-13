"""モジュール › エージェント：モジュールのエージェントの設定。左に一覧（全エージェント共通 → 役 → スキル）、右に選んだものを直す。

見せるのは既定のブランチの内容（いま起動するエージェントに効いているもの）。保存・追加・削除は、上で選んだタスクブランチの
作業空間（共有の値 agent_place）で実行してコミットする（選ぶまでは押せない。「新しいタスクを作る…」で、そのための作業空間を作れる）。
"""

ARGS = {"module": "."}  # モジュールのフォルダー（変えるときは、タスクブランチの作業空間）

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "エージェント", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "cfg-fill-page", "children": ["head", "section", "where", "place", "editor"]},
        {"id": "place", "part": "mod-place", "props": {"title": "保存してコミットするタスクブランチ",
                                                       "note": "直して保存するときは、ここで選んだタスクブランチでコミットします。"}},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "agents", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "presets", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "presets", "part": "button", "props": {"label": "このPCのプリセット…", "hint": "このPCの手持ちのエージェント・スキル（モジュールの登録の元）"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "where", "part": "note", "props": {"text": "エージェントの設定はリポジトリのファイル（.ecobuild/agents/）です。保存は、タスクブランチの作業空間で実行するとコミットされ、提出して取り込まれると、起動するエージェントに効きます。"}},
        {"id": "editor", "part": "cfg-agent-editor", "look": "cfg-fill"},
    ],
    "bindings": [
        {"read": "agent registry list", "args": {"module": {"arg": "module"}}, "to": "editor.agents"},
        # コミットする場所（タスクブランチの作業空間）を選ぶ・そのためのタスクを作る
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "place.workspaces", "from": "workspaces"},
        {"value": "agent_place", "to": "place.value"},
        {"value": "agent_place", "to": "editor.place"},
        {"on": "place.changed", "set": {"agent_place": {"payload": "path"}}},
        {"on": "place.new_task", "open": "cfg-agent-task", "args": {"module": {"arg": "module"}}, "inside": True},
        {"read": "agent skill list", "args": {"module": {"arg": "module"}}, "to": "editor.skills"},
        {"read": "agent registry tools", "args": {"module": {"arg": "module"}}, "to": "editor.tools"},
        {"read": "agent preset list", "args": {"module": {"arg": "module"}}, "to": "editor.presets"},
        {"read": "agent rules show", "args": {"module": {"arg": "module"}}, "to": "editor.rules"},
        {"on": "reload.pressed", "refresh": True},
        # 外から選ぶ（共有の値 agent_select に {kind, name}）
        {"value": "agent_select", "to": "editor.select"},
        {"on": "presets.pressed", "open": "agent-presets", "args": {"module": {"arg": "module"}}, "here": True},
        # 選んだもの：役なら ecobuild agent registry show <名前>、スキルなら ecobuild agent skill show <名前>
        # （選び直したら、前の役で選んでいたツールの確かめは捨てる）
        {"on": "editor.selected", "when": {"kind": "role"}, "set": {"registration": {"payload": "name"}, "reg_fit_tools": None}},
        {"on": "editor.selected", "when": {"kind": "skill"}, "set": {"skill": {"payload": "name"}}},
        {"read": "agent registry show", "args": {"module": {"arg": "module"}, "name": {"value": "registration"}}, "to": "editor.registration"},
        {"read": "agent skill show", "args": {"module": {"arg": "module"}, "name": {"value": "skill"}}, "to": "editor.skill"},
        # 渡すツールを選ぶたびに、その並びでどうなるか（多すぎないか・この役より強い子）を確かめる
        # （ecobuild agent registry fit <名前> --tools …。まだ選び直していなければ、今の並び）
        {"on": "editor.tools_changed", "set": {"reg_fit_tools": {"payload": "text"}}},
        {"read": "agent registry fit", "require": ["name"],
         "args": {"module": {"arg": "module"}, "name": {"value": "registration"}, "tools": {"value": "reg_fit_tools"}}, "to": "editor.fit"},
        # 役：変えた項目だけを渡す（ecobuild agent registry set <名前> --title … --tools … --document -）
        {"on": "editor.save", "run": "agent registry set", "confirmed": True, "require": ["module"],
         "args": {"module": {"value": "agent_place"}, "name": {"payload": "name"},
                  "title": {"payload": "title"}, "model": {"payload": "model"}, "human_start": {"payload": "human_start"},
                  "tools": {"payload": "tools"}, "skills": {"payload": "skills"}, "children": {"payload": "children"},
                  "max_children": {"payload": "max_children"}, "first_prompt": {"payload": "first_prompt"},
                  "evaluation": {"payload": "evaluation"}, "lessons": {"payload": "lessons"},
                  "max_rounds": {"payload": "max_rounds"}, "max_turns": {"payload": "max_turns"}, "max_cost": {"payload": "max_cost"},
                  "document": {"payload": "document"}},
         "set": {"reg_fit_tools": None}, "notify": "保存してコミットしました。提出して取り込まれると効きます。"},
        {"on": "editor.remove", "run": "agent registry remove", "require": ["module"], "args": {"module": {"value": "agent_place"}, "name": {"payload": "name"}},
         "set": {"registration": None, "reg_fit_tools": None}},
        {"on": "editor.to_preset", "open": "cfg-agent-to-preset", "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "inside": True},
        {"on": "editor.add", "open": "cfg-agent-add", "args": {"module": {"arg": "module"}, "place": {"value": "agent_place"}}, "inside": True},
        # スキル（ecobuild agent skill set <名前> --description … --document -）
        {"on": "editor.save_skill", "run": "agent skill set", "confirmed": True, "require": ["module"],
         "args": {"module": {"value": "agent_place"}, "name": {"payload": "name"}, "description": {"payload": "description"},
                  "document": {"payload": "document"}},
         "notify": "スキルを保存してコミットしました。提出して取り込まれると渡ります。"},
        {"on": "editor.remove_skill", "run": "agent skill remove", "require": ["module"], "args": {"module": {"value": "agent_place"}, "name": {"payload": "name"}},
         "set": {"skill": None}},
        {"on": "editor.skill_to_preset", "open": "cfg-skill-to-preset", "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "inside": True},
        {"on": "editor.add_skill", "open": "cfg-skill-add", "args": {"module": {"arg": "module"}, "place": {"value": "agent_place"}}, "inside": True},
        # 全エージェント共通の文（ecobuild agent rules set -。文は標準入力で渡る。空なら消す）
        {"on": "editor.save_rules", "run": "agent rules set", "confirmed": True, "require": ["module"], "args": {"module": {"value": "agent_place"}, "common": {"payload": "common"}},
         "notify": "全エージェント共通の文を保存しました。"},
    ],
}
