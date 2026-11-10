"""eco_gui のエージェントの設定（登録・スキル・共通の文・このPCのプリセット）・オペレーター・ヘルプの画面。

ecobuild は呼ばない（偽のバックエンドで、正しいコマンドと引数で呼ばれることを確かめる）。
"""

import importlib
import sys

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
                 "state": "idle", "waiting": 0, "last_reply": "終わりました", "started_at": 1792754845.3, "replied_at": 1792758445.0},
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
    # 並び・数の今の値も欄に入っている。選べるものは、読んだ一覧（ツール・スキル・登録）
    assert view["e_tools"]["props"]["items"] == ["status", "diff"] and view["e_children"]["props"]["items"] == []
    assert [row["name"] for row in view["e_tools"]["props"]["rows"]] == ["status", "task_commit"]
    assert [row["name"] for row in view["e_skills"]["props"]["rows"]] == ["release-notes"]
    assert [row["name"] for row in view["e_children"]["props"]["rows"]] == ["lead", "worker"]
    assert (view["e_max_children"]["props"]["value"], view["e_max_cost"]["props"]["value"]) == (0, 0.0)
    assert relay.backend.calls.count(("agent registry show", {"name": "worker"})) == 1  # いくつもの部品へ出しても、1回
    assert relay.backend.modules[-1] == "C:/work/Calc"
    assert notices(relay) == []


def test_agents_screen_saves_only_what_was_rewritten_after_a_confirmation(relay):
    window = opened(relay, "agents", module="C:/work/Calc/.ecobuild/w/12")
    relay.input(window, "list", "action", {"id": "worker", "action": "show"}, human=True)
    relay.input(window, "e_title", "changed", {"text": "実装役"}, human=True)
    relay.input(window, "e_human_start", "changed", {"value": "false"}, human=True)
    relay.input(window, "e_tools", "changed", {"items": ["status", "diff", "task_*"], "text": "status,diff,task_*"}, human=True)
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


def test_agents_screen_saves_the_rewritten_document_and_forgets_edits_when_another_is_chosen(relay):
    window = opened(relay, "agents", module="C:/work/Calc/.ecobuild/w/12")
    assert nodes(relay, window)["save_document"]["wrap"]["kind"] == "unavailable"  # 選んで、書き直すまで押せない
    relay.input(window, "list", "action", {"id": "worker", "action": "show"}, human=True)
    relay.idle()
    assert nodes(relay, window)["save_document"]["wrap"]["kind"] == "unavailable"
    relay.input(window, "document", "changed", {"text": "## あなたの役：実装役\n\n1. 読む\n2. 直す"}, human=True)
    relay.idle()
    relay.input(window, "save_document", "pressed", {}, human=True)
    answer(relay, window, True)
    # 画面からは本文の文字が渡る（本物のつなぎが、コマンドの行には - を書き、本文を標準入力へ渡す）
    assert ("agent registry set", {"name": "worker", "document": "## あなたの役：実装役\n\n1. 読む\n2. 直す"}) in relay.backend.calls
    assert relay.display.values(window)["reg_document"] is None

    relay.input(window, "e_title", "changed", {"text": "実装役"}, human=True)
    relay.input(window, "document", "changed", {"text": "書きかけ"}, human=True)
    relay.input(window, "list", "action", {"id": "lead", "action": "show"}, human=True)  # 別の登録を選ぶ
    relay.idle()
    values = relay.display.values(window)
    assert (values["registration"], values["reg_title"], values["reg_document"]) == ("lead", None, None)  # 前の書き直しは渡さない
    assert nodes(relay, window)["e_tools"]["props"]["items"] == ["*"]


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

    assert nodes(relay, window)["save_document"]["wrap"]["kind"] == "unavailable"  # 本文を書き直すまで押せない
    relay.input(window, "document", "changed", {"text": "# 手順\n1. 変更を集める\n2. 書く"}, human=True)
    relay.idle()
    relay.input(window, "save_document", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent skill set", {"name": "release-notes", "document": "# 手順\n1. 変更を集める\n2. 書く"}) in relay.backend.calls

    relay.input(window, "new_name", "changed", {"text": "notes"}, human=True)
    relay.input(window, "new_description", "changed", {"text": "メモの書き方"}, human=True)
    relay.input(window, "new_document", "changed", {"text": "# メモ\n短く書く"}, human=True)
    relay.idle()
    relay.input(window, "do_add", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent skill add", {"name": "notes", "description": "メモの書き方", "document": "# メモ\n短く書く"}) in relay.backend.calls
    relay.input(window, "new_description", "changed", {"text": ""}, human=True)
    relay.input(window, "new_document", "changed", {"text": ""}, human=True)
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
    assert view["v_pick"]["props"]["options"] == ["2.1.322", "2.1.321"]  # 版は、読んだ一覧から選べる
    assert relay.backend.modules[-1] is None  # このPCのもの：モジュールを決めない

    relay.input(window, "p_list", "action", {"id": "lead", "action": "show"}, human=True)
    relay.input(window, "p_model", "changed", {"text": "opus"}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["p_document"]["props"]["text"] == "## あなたの役：進行役"
    assert view["p_tools"]["props"]["items"] == ["*"] and view["p_max_children"]["props"]["value"] == 6  # 今の値が入っている
    assert [row["name"] for row in view["p_tools"]["props"]["rows"]] == ["status", "task_commit"]
    relay.input(window, "p_save", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent preset set", {"name": "lead", "model": "opus"}) in relay.backend.calls
    relay.input(window, "p_document", "changed", {"text": "## あなたの役：進行役\n短く進める"}, human=True)
    relay.idle()
    relay.input(window, "p_save_document", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent preset set", {"name": "lead", "document": "## あなたの役：進行役\n短く進める"}) in relay.backend.calls
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
    relay.input(window, "s_document", "changed", {"text": "# 手順\n書き直した"}, human=True)
    relay.idle()
    relay.input(window, "s_save_document", "pressed", {}, human=True)
    answer(relay, window, True)
    assert ("agent skill preset set", {"name": "release-notes", "document": "# 手順\n書き直した"}) in relay.backend.calls
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
    relay.input(window, "v_pick", "changed", {"value": "2.1.321"}, human=True)
    relay.idle()
    assert nodes(relay, window)["v_now"]["props"]["text"] == "2.1.321"
    relay.input(window, "v_save", "pressed", {}, human=True)
    relay.idle()
    assert ("config set", {"key": "agent_claude_version", "value": "2.1.321"}) in relay.backend.calls
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
    columns = {column["key"]: column.get("format") for column in view["list"]["props"]["columns"]}
    assert "task.number" in columns and (columns["started_at"], columns["replied_at"]) == ("time", "time")  # タスク番号と時刻の列
    assert view["list"]["props"]["rows"][0]["task"]["number"] == 12 and view["list"]["props"]["rows"][0]["started_at"] == 1792754845.3
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


COMMANDS_READING_STANDARD_INPUT = (
    ("agent registry set", "document"), ("agent preset set", "document"), ("agent skill set", "document"), ("agent skill add", "document"),
    ("agent skill preset set", "document"), ("agent skill preset add", "document"))


def echo_backend(tmp_path):
    """本物のつなぎ（EcobuildBackend）を、受けたコマンドの行と標準入力をそのまま答える小さなコマンドにつなぐ。"""
    from eco_gui.backend import EcobuildBackend

    script = tmp_path / "echo.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdout.reconfigure(encoding='utf-8')\n"
        "sys.stdin.reconfigure(encoding='utf-8')\n"
        "print(json.dumps({'ok': True, 'result': {'argv': sys.argv[1:], 'stdin': sys.stdin.read()}}))\n", encoding="utf-8")

    def option(param):
        return {"names": ["--" + param.replace("_", "-")], "param": param, "help": param, "type": "str", "negative": None}

    def name_argument(param):
        return {"name": param.upper(), "param": param, "help": param, "required": True, "multiple": False, "type": "str"}

    def node(path, argument, *options):
        return {"name": path.split()[-1], "path": path, "summary": path, "runnable": True, "effect": "human",
                "arguments": [name_argument(argument)], "options": [option(o) for o in options]}

    catalog = {"ok": True, "result": {"commands": [
        *[node(path, "name", "description", key) for path, key in COMMANDS_READING_STANDARD_INPUT],
        node("agent rules set", "common"), node("agent token set", "token"), node("config set", "key", "value")], "types": {}}}
    backend = EcobuildBackend([sys.executable, str(script)])
    backend.ask = lambda argv: catalog
    backend.commands()
    return backend


def test_the_backend_passes_long_texts_through_standard_input_not_the_command_line(tmp_path):
    backend = echo_backend(tmp_path)
    text = "## あなたの役\n\n" + "1. 読む・直す・確かめる \"引用\" %PATH% & | <>\n" * 2000  # コマンドの行の上限（Windows は約 32,000 字）より長い
    assert len(text) > 40000
    for name, key in COMMANDS_READING_STANDARD_INPUT:
        args = {"name": "worker", "description": "説明", key: text, "module": "C:/work/Calc"}
        assert backend.standard_input(name, args) == text
        line = backend.command_line(name, args, ["yes"])
        assert line[2:] == ["-C", "C:/work/Calc", *name.split(), "--description", "説明", "--" + key, "-", "--json", "--", "worker"]
        assert text not in line  # 本文は、コマンドの行に置かない
    done = backend.run("agent registry set", {"name": "worker", "document": text}, {"run": None}, lambda event: None)
    assert done == {"ok": True, "result": {"argv": ["agent", "registry", "set", "--document", "-", "--json", "--", "worker"], "stdin": text}}
    # 共通の文（位置引数）も同じ道。空の文（消す）も、標準入力で空のまま渡る
    done = backend.run("agent rules set", {"common": "決まり1\n決まり2"}, {"run": None}, lambda event: None)
    assert done["result"] == {"argv": ["agent", "rules", "set", "--json", "--", "-"], "stdin": "決まり1\n決まり2"}
    done = backend.run("agent rules set", {"common": ""}, {"run": None}, lambda event: None)
    assert done["result"] == {"argv": ["agent", "rules", "set", "--json", "--", "-"], "stdin": ""}


def test_the_backend_uses_standard_input_only_for_those_texts(tmp_path):
    backend = echo_backend(tmp_path)
    # 本文を書いていない保存：標準入力は使わない（- も付けない）
    assert backend.standard_input("agent skill set", {"name": "pdf", "description": "説明"}) is None
    assert backend.command_line("agent skill set", {"name": "pdf", "description": "説明"}) == [
        *backend.argv, "agent", "skill", "set", "--description", "説明", "--json", "--", "pdf"]
    # ほかのコマンドの値は、今までどおり（鍵・トークンを標準入力へ流す道は作らない：画面に入れないので、ここへは来ない）
    assert backend.standard_input("config set", {"key": "operator_style", "value": "やさしく"}) is None
    assert backend.standard_input("agent token set", {"token": "fake-value"}) is None
    done = backend.run("config set", {"key": "owner", "value": "acme"}, {"run": None}, lambda event: None)
    assert done["result"] == {"argv": ["config", "set", "--value", "acme", "--json", "--", "owner"], "stdin": ""}


def test_help_screens_show_the_guide_inside_and_outside_a_module_window(relay):
    alone = opened(relay, "help-guide")
    assert nodes(relay, alone)["step1_title"]["props"]["text"].startswith("1.")
    assert nodes(relay, alone)["terms"]["props"]["data"]["task"].startswith("GitHub の Issue")
    assert [call for call in relay.backend.calls] == []  # 読むコマンドはない（決まった文だけ）
    window = opened(relay, "help", module="C:/work/Calc")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "help" and view["body:step6_title"]["props"]["text"].startswith("6.")
    assert notices(relay) == []
