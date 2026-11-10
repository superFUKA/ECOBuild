"""eco_gui のエージェントの設定（登録・スキル・共通の文・このPCのプリセット）・オペレーター・ヘルプの画面。

ecobuild は呼ばない（偽のバックエンドで、正しいコマンドと引数で呼ばれることを確かめる）。
"""

import importlib

import pytest

from test_eco_gui import FakeEcobuild, answer, nodes

from guiframework import create_app  # noqa: E402

TEXT = {"type": "string"}
SETTINGS = {"title": TEXT, "human_start": {"type": "boolean"}, "model": TEXT, "tools": TEXT, "children": TEXT, "skills": TEXT,
            "max_children": {"type": "integer"}, "first_prompt": TEXT, "evaluation": TEXT, "max_rounds": {"type": "integer"},
            "max_turns": {"type": "integer"}, "max_cost": {"type": "number"}, "lessons": TEXT, "document": TEXT}


def spec(weight, required=(), **properties):
    return {"description": "", "weight": weight, "args": {"type": "object", "required": list(required), "properties": properties}}


class FakeAgents(FakeEcobuild):
    """エージェントまわりのコマンドを足した、偽の ecobuild。人がする（human）のコマンドは、本物と同じく confirm として出る。"""

    def __init__(self):
        super().__init__()
        self.rules = "決まり1"
        self.style = None
        self.registrations = [
            {"name": "lead", "title": "進行役", "source": "sample", "human_start": True, "model": "", "tools": ["*"], "skills": ["*"],
             "children": ["worker"], "max_children": 6, "pending": False},
            {"name": "worker", "title": "作業役", "source": "module", "human_start": False, "model": "sonnet", "tools": ["status", "diff"],
             "skills": [], "children": [], "max_children": 0, "pending": True}]
        self.skills = [{"name": "release-notes", "description": "リリースノートを書く手順", "used_by": ["lead"], "pending": False, "files": []}]

    def _specs(self, text):
        specs = super()._specs(text)
        for group, extra in (("agent registry", {"from_preset": text, "from_dir": text}),
                             ("agent preset", {"from_preset": text, "from_module": text, "from_dir": text})):
            specs[f"{group} list"] = spec("read")
            specs[f"{group} show"] = spec("read", ["name"], name=text)
            specs[f"{group} add"] = spec("confirm", ["name"], name=text, **extra)
            specs[f"{group} set"] = spec("confirm", ["name"], name=text, **SETTINGS)
            specs[f"{group} remove"] = spec("confirm", ["name"], name=text)
        for group, extra in (("agent skill", {"from_preset": text}), ("agent skill preset", {"from_module": text})):
            specs[f"{group} list"] = spec("read")
            specs[f"{group} show"] = spec("read", ["name"], name=text)
            specs[f"{group} add"] = spec("confirm", ["name"], name=text, description=text, document=text, from_dir=text, **extra)
            specs[f"{group} set"] = spec("confirm", ["name"], name=text, description=text, document=text)
            specs[f"{group} remove"] = spec("confirm", ["name"], name=text)
        specs.update({
            "agent registry tools": spec("read"),
            "agent rules show": spec("read"),
            "agent rules set": spec("confirm", ["common"], common=text),
            "agent version list": spec("read", limit={"type": "integer"}),
            "agent version status": spec("read"),
            "agent list": spec("read"),
            "agent status": spec("read", id={"type": "array", "items": text}),
            "agent children": spec("read", ["id"], id=text, recent={"type": "integer"}),
            "agent stop": spec("change", ["id"], id=text),
            "agent restart": spec("change", ["id"], id=text, resume={"type": "boolean"}),
            "agent close": spec("confirm", ["id"], id=text, force={"type": "boolean"}),
            "agent send": spec("change", ["id"], id=text, text={"type": "array", "items": text}, cancel=text, replace=text),
            "config get": spec("read", ["key"], key=text),
            "config set": spec("change", ["key", "value"], key=text, value=text),
            "config unset": spec("change", ["key"], key=text),
        })
        return specs

    def run(self, name, args, context, on_event):
        result = super().run(name, args, context, on_event)
        args = {key: value for key, value in args.items() if key != "module"}
        if name in ("agent registry list", "agent preset list"):
            return {"ok": True, "result": [dict(r) for r in self.registrations]}
        if name in ("agent registry show", "agent preset show"):
            found = next(r for r in self.registrations if r["name"] == args["name"])
            return {"ok": True, "result": {**found, "document": f"## あなたの役：{found['title']}", "first_prompt": "始めてください",
                                           "evaluation": "", "lessons": "", "max_rounds": 0, "max_turns": 0, "max_cost": 0.0,
                                           "folder": "C:/agents/" + found["name"], "committed": ""}}
        if name in ("agent registry set", "agent preset set"):
            found = next(r for r in self.registrations if r["name"] == args["name"])
            found.update({key: value for key, value in args.items() if key in ("title", "model")})
        if name in ("agent registry add", "agent preset add"):
            self.registrations.append({**self.registrations[-1], "name": args["name"], "title": args["name"], "source": "module"})
        if name in ("agent skill add", "agent skill preset add"):
            self.skills.append({"name": args["name"], "description": args.get("description", ""), "used_by": [], "pending": True, "files": []})
        if name == "agent registry tools":
            return {"ok": True, "result": [{"name": "status", "mark": "read", "summary": "今の状態を表示します。"},
                                           {"name": "task_commit", "mark": "owner", "summary": "コミットします。"}]}
        if name in ("agent skill list", "agent skill preset list"):
            return {"ok": True, "result": [dict(s) for s in self.skills]}
        if name in ("agent skill show", "agent skill preset show"):
            found = next(s for s in self.skills if s["name"] == args["name"])
            return {"ok": True, "result": {**found, "document": "# 手順\n1. 変更を集める", "folder": "C:/skills/" + found["name"], "committed": ""}}
        if name == "agent rules show":
            return {"ok": True, "result": {"root": "C:/work/Calc", "in_force": "origin/main", "pending": False, "common": self.rules,
                                           "changed": [], "committed": ""}}
        if name == "agent rules set":
            self.rules = args["common"]
        if name == "agent version status":
            return {"ok": True, "result": {"setting": "", "key": "agent_claude_version", "installed": None, "reason": "コンテナが動いていません"}}
        if name == "agent version list":
            return {"ok": True, "result": {"channels": {"stable": "2.1.311", "latest": "2.1.322"}, "versions": ["2.1.322", "2.1.321"], "reason": None}}
        if name == "agent list":
            return {"ok": True, "result": [
                {"id": "a-0000000001", "name": "lead", "title": "進行役", "branch": "task/12-login", "task": {"number": 12},
                 "state": "idle", "waiting": 0, "last_reply": "終わりました"},
                {"id": "a-0000000002", "name": "worker", "title": "作業役", "branch": "task/13-log", "task": {"number": 13},
                 "state": "stopped", "waiting": 1, "last_reply": ""}]}
        if name == "agent status":
            return {"ok": True, "result": {"id": args["id"][0], "name": "lead", "registration": "lead", "kind": "owner",
                                           "workspace": "C:/work/Calc/.ecobuild/w/12", "model": "", "state": "idle", "waiting": 0,
                                           "doing": "", "last_reply": "終わりました"}}
        if name == "agent children":
            return {"ok": True, "result": {"id": args["id"], "name": "lead", "members": [
                {"id": "a-0000000002", "name": "worker", "title": "作業役", "branch": "task/13-log", "state": "stopped",
                 "reported": True, "last_reply": ""}]}}
        if name == "config get":
            return {"ok": True, "result": {"key": args["key"], "value": self.style}}
        if name == "config set" and args["key"] == "operator_style":
            self.style = args["value"]
        if name == "config unset" and args["key"] == "operator_style":
            self.style = None
        return result


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeAgents(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def opened(relay, screen, **args):
    window = relay.execute({"command": "open", "screen": screen, "args": args})["window"]
    relay.idle()
    return window


def notices(relay):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify"]


def test_every_binding_matches_the_backend_commands(relay):
    relay.verify()


def test_agents_screen_lists_registrations_and_shows_the_chosen_one(relay):
    window = opened(relay, "agents", module="C:/work/Calc")
    view = nodes(relay, window)
    assert (view["nav"]["props"]["current"], view["sub"]["props"]["current"]) == ("agents", "agents")
    assert [row["name"] for row in view["list"]["props"]["rows"]] == ["lead", "worker"]
    assert [row["name"] for row in view["tools"]["props"]["rows"]] == ["status", "task_commit"]
    assert [row["name"] for row in view["new_from"]["props"]["rows"]] == ["lead", "worker"]  # 写すプリセットは、読んだ一覧から選ぶ
    assert not [call for call in relay.backend.calls if call[0] == "agent registry show"]  # 選ぶまで、中身は読まない
    assert view["save"]["wrap"]["kind"] == "unavailable"  # まだ選んでいない

    relay.input(window, "list", "action", {"id": "worker", "action": "show"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["selected"]["props"]["text"] == "worker"
    assert view["info"]["props"]["data"]["tools"] == ["status", "diff"]
    assert view["document"]["props"]["text"] == "## あなたの役：作業役"
    assert (view["e_title"]["props"]["text"], view["e_model"]["props"]["text"]) == ("作業役", "sonnet")  # 今の値が入っている
    assert view["e_first_prompt"]["props"]["text"] == "始めてください"
    assert relay.backend.calls.count(("agent registry show", {"name": "worker"})) == 1  # いくつもの部品へ出しても、1回
    assert relay.backend.modules[-1] == "C:/work/Calc"
    assert notices(relay) == []


def test_agents_screen_saves_only_what_was_rewritten_after_a_confirmation(relay):
    window = opened(relay, "agents", module="C:/work/Calc/.ecobuild/w/12")
    relay.input(window, "list", "action", {"id": "worker", "action": "show"}, human=True)
    relay.input(window, "e_title", "changed", {"text": "実装役"}, human=True)
    relay.input(window, "e_human_start", "changed", {"value": "false"}, human=True)
    relay.input(window, "e_tools", "changed", {"text": "status,diff,task_*"}, human=True)
    relay.input(window, "e_max_children", "changed", {"text": "2"}, human=True)
    relay.input(window, "e_max_cost", "changed", {"text": "1.5"}, human=True)
    relay.idle()
    relay.input(window, "save", "pressed", {}, human=True)
    assert answer(relay, window, True)["part"] == "confirm-box"  # 人がする（human）のコマンドは、確かめてから
    assert ("agent registry set", {"name": "worker", "title": "実装役", "human_start": False, "tools": "status,diff,task_*",
                                   "max_children": 2, "max_cost": 1.5}) in relay.backend.calls  # 書いた項目だけ・コマンドの型で
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"
    values = relay.display.values(window)
    assert values["reg_title"] is None and values["reg_tools"] is None  # 保存したら、書き直しの控えを空に
    assert nodes(relay, window)["e_title"]["props"]["text"] == "実装役"  # 変えたら読み直す


def test_agents_screen_adds_removes_and_copies_to_a_preset(relay):
    window = opened(relay, "agents", module="C:/work/Calc")
    relay.input(window, "new_name", "changed", {"text": "reviewer"}, human=True)
    relay.idle()
    relay.input(window, "do_add", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent registry add", {"name": "reviewer"}) in relay.backend.calls  # 写す元（任意）は、選ばなければ渡さない
    relay.input(window, "new_from", "changed", {"value": "worker"}, human=True)
    relay.idle()
    assert nodes(relay, window)["new_from"]["props"]["value"] == "worker"
    relay.input(window, "do_add", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent registry add", {"name": "reviewer", "from_preset": "worker"}) in relay.backend.calls

    relay.input(window, "list", "action", {"id": "worker", "action": "to_preset"}, human=True)
    answer(relay, window, True)
    assert ("agent preset add", {"name": "worker", "from_module": "worker"}) in relay.backend.calls
    relay.input(window, "list", "action", {"id": "worker", "action": "remove"}, human=True)
    answer(relay, window, False)  # いいえ：実行しない
    assert ("agent registry remove", {"name": "worker"}) not in relay.backend.calls
    relay.input(window, "list", "action", {"id": "worker", "action": "remove"}, human=True)
    answer(relay, window, True)
    assert ("agent registry remove", {"name": "worker"}) in relay.backend.calls


def test_the_agents_menu_switches_between_the_agent_screens_in_the_same_window(relay):
    window = opened(relay, "agents", module="C:/work/Calc")
    for screen in ("agent-skills", "agent-rules", "agent-presets", "agents"):
        relay.input(window, "sub", "selected", {"id": screen}, human=True)
        relay.idle()
        view = nodes(relay, window)
        assert relay.display.tree(window)["screen"] == screen
        assert (view["nav"]["props"]["current"], view["sub"]["props"]["current"]) == ("agents", screen)
        assert relay.display.tree(window)["args"] == {"module": "C:/work/Calc"}
    assert [w["id"] for w in relay.display.windows()] == [window]  # 窓は増えない
    assert notices(relay) == []


def test_skills_screen_shows_edits_adds_and_removes(relay):
    window = opened(relay, "agent-skills", module="C:/work/Calc")
    assert nodes(relay, window)["list"]["props"]["rows"][0]["name"] == "release-notes"
    relay.input(window, "list", "action", {"id": "release-notes", "action": "show"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["document"]["props"]["text"].startswith("# 手順")
    assert view["e_description"]["props"]["text"] == "リリースノートを書く手順"
    relay.input(window, "e_description", "changed", {"text": "リリースノートを書く手順。\nリリースの前に使う。"}, human=True)
    relay.idle()
    relay.input(window, "save", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent skill set", {"name": "release-notes", "description": "リリースノートを書く手順。\nリリースの前に使う。"}) in relay.backend.calls

    relay.input(window, "new_name", "changed", {"text": "pdf"}, human=True)
    relay.input(window, "new_dir", "changed", {"text": "C:/skills/pdf"}, human=True)
    relay.idle()
    relay.input(window, "do_add", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent skill add", {"name": "pdf", "from_dir": "C:/skills/pdf"}) in relay.backend.calls
    relay.input(window, "list", "action", {"id": "release-notes", "action": "to_preset"}, human=True)
    answer(relay, window, True)
    assert ("agent skill preset add", {"name": "release-notes", "from_module": "release-notes"}) in relay.backend.calls
    relay.input(window, "list", "action", {"id": "release-notes", "action": "remove"}, human=True)
    answer(relay, window, True)
    assert ("agent skill remove", {"name": "release-notes"}) in relay.backend.calls
    assert relay.display.values(window)["skill"] is None  # 消したら、選択を空に


def test_rules_screen_shows_the_text_and_saves_the_rewritten_one(relay):
    window = opened(relay, "agent-rules", module="C:/work/Calc/.ecobuild/w/12")
    view = nodes(relay, window)
    assert view["common"]["props"]["text"] == "決まり1" and view["state"]["props"]["data"]["in_force"] == "origin/main"
    assert view["save"]["wrap"]["kind"] == "unavailable"  # 書き直すまで、保存できない
    relay.input(window, "common", "changed", {"text": "決まり1\n決まり2"}, human=True)
    relay.idle()
    assert nodes(relay, window)["save"]["wrap"] is None
    relay.input(window, "save", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent rules set", {"common": "決まり1\n決まり2"}) in relay.backend.calls
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"
    assert nodes(relay, window)["common"]["props"]["text"] == "決まり1\n決まり2"  # 変えたら読み直す
    relay.input(window, "common", "changed", {"text": ""}, human=True)  # 空にして保存すると、消す
    relay.idle()
    relay.input(window, "save", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent rules set", {"common": ""}) in relay.backend.calls


def test_pc_agents_screen_handles_presets_pc_skills_and_the_claude_code_version(relay):
    window = opened(relay, "pc-agents")
    view = nodes(relay, window)
    assert [row["name"] for row in view["p_list"]["props"]["rows"]] == ["lead", "worker"]
    assert view["v_channels"]["props"]["data"] == {"stable": "2.1.311", "latest": "2.1.322"}
    assert view["v_list"]["props"]["lines"] == ["2.1.322", "2.1.321"]
    assert relay.backend.modules[-1] is None  # このPCのもの：モジュールを決めない

    relay.input(window, "p_list", "action", {"id": "lead", "action": "show"}, human=True)
    relay.input(window, "p_model", "changed", {"text": "opus"}, human=True)
    relay.idle()
    assert nodes(relay, window)["p_document"]["props"]["text"] == "## あなたの役：進行役"
    relay.input(window, "p_save", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent preset set", {"name": "lead", "model": "opus"}) in relay.backend.calls
    relay.input(window, "p_new_name", "changed", {"text": "my-worker"}, human=True)
    relay.input(window, "p_new_from", "changed", {"value": "worker"}, human=True)
    relay.idle()
    relay.input(window, "p_do_add", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent preset add", {"name": "my-worker", "from_preset": "worker"}) in relay.backend.calls
    relay.input(window, "p_list", "action", {"id": "worker", "action": "remove"}, human=True)
    answer(relay, window, True)
    assert ("agent preset remove", {"name": "worker"}) in relay.backend.calls

    relay.input(window, "s_list", "action", {"id": "release-notes", "action": "show"}, human=True)
    relay.input(window, "s_description", "changed", {"text": "新しい説明"}, human=True)
    relay.idle()
    relay.input(window, "s_save", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent skill preset set", {"name": "release-notes", "description": "新しい説明"}) in relay.backend.calls
    relay.input(window, "s_new_name", "changed", {"text": "notes"}, human=True)
    relay.input(window, "s_new_description", "changed", {"text": "メモの書き方"}, human=True)
    relay.idle()
    relay.input(window, "s_do_add", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent skill preset add", {"name": "notes", "description": "メモの書き方"}) in relay.backend.calls
    relay.input(window, "s_list", "action", {"id": "release-notes", "action": "remove"}, human=True)
    answer(relay, window, True)
    assert ("agent skill preset remove", {"name": "release-notes"}) in relay.backend.calls

    relay.input(window, "v_value", "changed", {"text": "stable"}, human=True)
    relay.idle()
    relay.input(window, "v_save", "pressed", {}, human=True)
    relay.idle()
    assert ("config set", {"key": "agent_claude_version", "value": "stable"}) in relay.backend.calls
    relay.input(window, "v_unset", "pressed", {}, human=True)
    relay.idle()
    assert ("config unset", {"key": "agent_claude_version"}) in relay.backend.calls
    assert notices(relay) == []


def test_agent_presets_screen_puts_the_pc_settings_inside_the_module_window(relay):
    window = opened(relay, "agent-presets", module="C:/work/Calc")
    view = nodes(relay, window)
    assert view["sub"]["props"]["current"] == "agent-presets"
    assert [row["name"] for row in view["body:p_list"]["props"]["rows"]] == ["lead", "worker"]
    relay.input(window, "body:p_list", "action", {"id": "lead", "action": "show"}, human=True)
    relay.idle()
    assert nodes(relay, window)["body:p_info"]["props"]["data"]["title"] == "進行役"


def test_operator_screen_lists_agents_and_stops_restarts_closes_and_sends(relay):
    window = opened(relay, "operator")
    view = nodes(relay, window)
    assert [row["id"] for row in view["list"]["props"]["rows"]] == ["a-0000000001", "a-0000000002"]
    assert view["do_send"]["wrap"]["kind"] == "unavailable"  # だれに送るか、まだ決まっていない
    assert relay.backend.modules[-1] is None

    relay.input(window, "list", "action", {"id": "a-0000000001", "action": "show"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["status"]["props"]["data"]["last_reply"] == "終わりました"
    assert ("agent status", {"id": ["a-0000000001"]}) in relay.backend.calls
    assert [row["id"] for row in view["children"]["props"]["rows"]] == ["a-0000000002"]
    relay.input(window, "message", "changed", {"text": "試験も流してください"}, human=True)
    relay.idle()
    relay.input(window, "do_send", "pressed", {}, human=True)
    relay.idle()
    assert ("agent send", {"id": "a-0000000001", "text": ["試験も流してください"]}) in relay.backend.calls

    relay.input(window, "children", "action", {"id": "a-0000000002", "action": "show"}, human=True)  # 子を選ぶと、その子の様子
    relay.idle()
    assert relay.display.values(window)["operator_agent"] == "a-0000000002"
    for action in ("stop", "restart", "resume"):
        relay.input(window, "list", "action", {"id": "a-0000000002", "action": action}, human=True)
        relay.idle()
    assert ("agent stop", {"id": "a-0000000002"}) in relay.backend.calls
    assert ("agent restart", {"id": "a-0000000002"}) in relay.backend.calls
    assert ("agent restart", {"id": "a-0000000002", "resume": True}) in relay.backend.calls
    relay.input(window, "list", "action", {"id": "a-0000000002", "action": "close"}, human=True)
    answer(relay, window, True)  # 閉じるのは、確かめてから
    assert ("agent close", {"id": "a-0000000002"}) in relay.backend.calls
    assert relay.display.values(window)["operator_agent"] is None
    assert notices(relay) == []


def test_operator_screen_edits_the_way_the_operator_talks(relay):
    window = opened(relay, "operator")
    assert ("config get", {"key": "operator_style"}) in relay.backend.calls
    assert nodes(relay, window)["style_text"]["props"]["text"] is None  # まだ決めていない
    relay.input(window, "style_text", "changed", {"text": "やさしい敬語で、短く。"}, human=True)
    relay.idle()
    relay.input(window, "style_save", "pressed", {}, human=True)
    relay.idle()
    assert ("config set", {"key": "operator_style", "value": "やさしい敬語で、短く。"}) in relay.backend.calls
    assert nodes(relay, window)["style_text"]["props"]["text"] == "やさしい敬語で、短く。"
    relay.input(window, "style_unset", "pressed", {}, human=True)
    relay.idle()
    assert ("config unset", {"key": "operator_style"}) in relay.backend.calls
    assert notices(relay) == []


def test_help_screens_show_the_guide_inside_and_outside_a_module_window(relay):
    alone = opened(relay, "help-guide")
    assert nodes(relay, alone)["step1_title"]["props"]["text"].startswith("1.")
    assert nodes(relay, alone)["terms"]["props"]["data"]["task"].startswith("GitHub の Issue")
    assert [call for call in relay.backend.calls] == []  # 読むコマンドはない（決まった文だけ）
    window = opened(relay, "help", module="C:/work/Calc")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "help" and view["body:step6_title"]["props"]["text"].startswith("6.")
    assert notices(relay) == []
