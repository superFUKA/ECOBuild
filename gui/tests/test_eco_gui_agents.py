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
            specs[f"{group} add"] = spec("confirm", ["name"], name=text, **extra, **(
                {"title": text, "human_start": {"type": "boolean"}, "no_owner_tools": {"type": "boolean"}} if group == "agent registry" else {}))
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
            "agent registry fit": spec("read", ["name"], name=text, tools=text),
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
            "help": spec("read", commands={"type": "array", "items": text}),
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
            return {"ok": True, "result": [{"name": "status", "mark": "read", "summary": "今の状態を表示します。", "area": "状態・履歴を見る"},
                                           {"name": "task_commit", "mark": "owner", "summary": "コミットします。", "area": "タスク"}]}
        if name == "agent registry fit":  # 本物と同じ形（数えるのは、偽のツール2つのうち名前の合うもの）
            found = next(r for r in self.registrations if r["name"] == args["name"])
            tools = [t for t in args["tools"].split(",") if t] if "tools" in args else found["tools"]
            given = [t for t in ("status", "task_commit") if "*" in tools or t in tools]
            return {"ok": True, "result": {"name": args["name"], "tools": tools, "count": len(given), "total": 2,
                                           "owner": sum(1 for t in given if t == "task_commit"), "limit": 30, "too_many": False,
                                           "stronger": [r["name"] for r in self.registrations
                                                        if r["name"] != args["name"] and "*" in r["tools"] and "*" not in tools],
                                           "parents": []}}
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
        if name == "help":
            return {"ok": True, "result": {
                "commands": [{"name": "status", "path": "status", "summary": "今の状態を表示します。", "help": "今の状態を表示します。",
                              "runnable": True, "effect": "read", "arguments": [], "options": []}],
                "types": {"python": {"description": "Python", "commands": [
                    {"name": "tests", "path": "tests", "summary": "流せるテストの一覧を表示します。", "help": "流せるテストの一覧を表示します。",
                     "runnable": True, "effect": "read", "arguments": [], "options": []}]}}}}
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


def inside(relay, window, screen):
    """window の中に重ねて開いた窓（入力の窓）。"""
    found = [w["id"] for w in relay.display.windows() if w.get("parent") == window and w["screen"] == screen]
    assert found, [(w["id"], w["screen"], w.get("parent")) for w in relay.display.windows()]
    return found[-1]


def notices(relay):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify"]


def test_every_binding_matches_the_backend_commands(relay):
    relay.verify()


def test_agents_screen_puts_the_list_and_the_chosen_one_in_one_editor(relay):
    window = opened(relay, "agents", module="C:/work/Calc")
    view = nodes(relay, window)
    editor = view["editor"]["props"]
    assert view["nav"]["props"]["current"] == "agents" and view["editor"]["part"] == "cfg-agent-editor"
    assert [row["name"] for row in editor["agents"]] == ["lead", "worker"]
    assert [row["name"] for row in editor["skills"]] == ["release-notes"]
    assert [(row["name"], row["area"]) for row in editor["tools"]] == [("status", "状態・履歴を見る"), ("task_commit", "タスク")]
    assert [row["name"] for row in editor["presets"]] == ["lead", "worker"]
    assert editor["rules"]["common"] == "決まり1" and editor["rules"]["in_force"] == "origin/main"  # 一番上は、全エージェント共通の文
    assert not [call for call in relay.backend.calls if call[0] in ("agent registry show", "agent registry fit", "agent skill show")]  # 選ぶまで読まない

    relay.input(window, "editor", "selected", {"kind": "role", "name": "worker"}, human=True)
    relay.idle()
    editor = nodes(relay, window)["editor"]["props"]
    assert (editor["registration"]["name"], editor["registration"]["tools"]) == ("worker", ["status", "diff"])
    assert editor["registration"]["document"] == "## あなたの役：作業役"
    # 選んだツールの確かめ（多すぎないか・この役より強い子）は、ecobuild agent registry fit が答える。初めは今の並びで
    assert ("agent registry fit", {"name": "worker"}) in relay.backend.calls
    assert (editor["fit"]["name"], editor["fit"]["stronger"], editor["fit"]["too_many"]) == ("worker", ["lead"], False)
    assert relay.backend.calls.count(("agent registry show", {"name": "worker"})) == 1
    assert relay.backend.modules[-1] == "C:/work/Calc"

    relay.input(window, "editor", "selected", {"kind": "skill", "name": "release-notes"}, human=True)
    relay.idle()
    assert nodes(relay, window)["editor"]["props"]["skill"]["document"].startswith("# 手順")
    relay.input(window, "editor", "selected", {"kind": "common", "name": ""}, human=True)
    relay.idle()
    assert notices(relay) == []


def test_agents_screen_asks_the_cli_what_a_choice_of_tools_comes_to(relay):
    window = opened(relay, "agents", module="C:/work/Calc")
    relay.input(window, "editor", "selected", {"kind": "role", "name": "lead"}, human=True)
    relay.idle()
    relay.input(window, "editor", "tools_changed", {"name": "lead", "text": "status"}, human=True)
    relay.idle()
    assert ("agent registry fit", {"name": "lead", "tools": "status"}) in relay.backend.calls
    fit = nodes(relay, window)["editor"]["props"]["fit"]
    assert (fit["tools"], fit["count"], fit["owner"], fit["stronger"]) == (["status"], 1, 0, [])
    relay.input(window, "editor", "tools_changed", {"name": "lead", "text": ","}, human=True)  # 1つも選ばない
    relay.idle()
    assert nodes(relay, window)["editor"]["props"]["fit"]["count"] == 0
    relay.input(window, "editor", "selected", {"kind": "role", "name": "worker"}, human=True)  # 選び直したら、前の役の並びは捨てる
    relay.idle()
    assert relay.display.values(window)["reg_fit_tools"] is None
    assert ("agent registry fit", {"name": "worker"}) in relay.backend.calls
    assert nodes(relay, window)["editor"]["props"]["fit"]["stronger"] == ["lead"]  # すべてのツールを持つ役は、この役より強い


def test_agents_screen_saves_only_what_was_changed_after_a_confirmation(relay):
    window = opened(relay, "agents", module="C:/work/Calc/.ecobuild/w/12")
    relay.input(window, "editor", "selected", {"kind": "role", "name": "worker"}, human=True)
    relay.idle()
    relay.input(window, "editor", "save", {"name": "worker", "title": "実装役", "human_start": False, "tools": "status,diff,task_*",
                                           "max_children": 2, "max_cost": 1.5, "document": "## あなたの役：実装役\n"}, human=True)
    assert answer(relay, window, True)["part"] == "confirm-box"  # 人がする（human）のコマンドは、確かめてから
    assert ("agent registry set", {"name": "worker", "title": "実装役", "human_start": False, "tools": "status,diff,task_*",
                                   "max_children": 2, "max_cost": 1.5, "document": "## あなたの役：実装役\n"}) in relay.backend.calls
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"
    assert nodes(relay, window)["editor"]["props"]["registration"]["title"] == "実装役"  # 変えたら読み直す
    assert "保存してコミットしました。提出して取り込まれると効きます。" in notices(relay)
    # 空にする値：並びは「,」、文字は空白1つ（空の文字は「変えない」と同じに扱われるので）
    relay.input(window, "editor", "save", {"name": "worker", "model": " ", "children": ",", "skills": ","}, human=True)
    answer(relay, window, True)
    assert ("agent registry set", {"name": "worker", "model": " ", "children": ",", "skills": ","}) in relay.backend.calls


def test_agents_screen_removes_and_opens_the_forms_inside_the_window(relay):
    window = opened(relay, "agents", module="C:/work/Calc/.ecobuild/w/12")
    relay.input(window, "editor", "selected", {"kind": "role", "name": "worker"}, human=True)
    relay.idle()
    relay.input(window, "editor", "remove", {"name": "worker"}, human=True)
    answer(relay, window, False)  # いいえ：実行しない
    assert ("agent registry remove", {"name": "worker"}) not in relay.backend.calls
    relay.input(window, "editor", "remove", {"name": "worker"}, human=True)
    answer(relay, window, True)
    assert ("agent registry remove", {"name": "worker"}) in relay.backend.calls
    assert relay.display.values(window)["registration"] is None  # 消したら、選択を空に

    # 追加：入力の窓を、この窓の中に重ねて開く。決めると ecobuild agent registry add … を実行して閉じる
    relay.input(window, "editor", "add", {}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-agent-add")
    assert [row["name"] for row in nodes(relay, form)["form"]["props"]["rows"]] == ["lead", "worker"]  # 元にするプリセットは、読んだ一覧から
    relay.input(form, "form", "submitted", {"values": {"how": "preset", "from_preset": "worker", "name": "reviewer", "human_start": True,
                                                        "no_owner_tools": True}}, human=True)
    answer(relay, form, True)
    assert ("agent registry add", {"name": "reviewer", "from_preset": "worker", "human_start": True, "no_owner_tools": True}) in relay.backend.calls
    assert form not in [w["id"] for w in relay.display.windows()]  # うまくいったら閉じる
    relay.input(window, "editor", "add", {}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-agent-add")
    relay.input(form, "form", "submitted", {"values": {"how": "new", "name": "checker", "title": "確かめ役", "human_start": False,
                                                        "no_owner_tools": False}}, human=True)
    answer(relay, form, True)
    assert ("agent registry add", {"name": "checker", "title": "確かめ役", "human_start": False, "no_owner_tools": False}) in relay.backend.calls
    relay.input(window, "editor", "add", {}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-agent-add")
    relay.input(form, "form", "cancelled", {}, human=True)  # キャンセル：何もせずに閉じる
    relay.idle()
    assert form not in [w["id"] for w in relay.display.windows()]

    # プリセットにする：名前を決める窓（初めは役の名前）
    relay.input(window, "editor", "to_preset", {"name": "lead"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-agent-to-preset")
    assert nodes(relay, form)["form"]["props"]["values"] == {"name": "lead"}
    relay.input(form, "form", "submitted", {"values": {"name": "my-lead"}}, human=True)
    answer(relay, form, True)
    assert ("agent preset add", {"name": "my-lead", "from_module": "lead"}) in relay.backend.calls


def test_agents_screen_edits_adds_and_removes_skills(relay):
    window = opened(relay, "agents", module="C:/work/Calc/.ecobuild/w/12")
    relay.input(window, "editor", "selected", {"kind": "skill", "name": "release-notes"}, human=True)
    relay.idle()
    relay.input(window, "editor", "save_skill", {"name": "release-notes", "description": "リリースノートを書く手順。\nリリースの前に使う。"}, human=True)
    answer(relay, window, True)
    assert ("agent skill set", {"name": "release-notes", "description": "リリースノートを書く手順。\nリリースの前に使う。"}) in relay.backend.calls
    relay.input(window, "editor", "save_skill", {"name": "release-notes", "document": "# 手順\n1. 変更を集める\n2. 書く\n"}, human=True)
    answer(relay, window, True)
    assert ("agent skill set", {"name": "release-notes", "document": "# 手順\n1. 変更を集める\n2. 書く\n"}) in relay.backend.calls

    relay.input(window, "editor", "add_skill", {}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-skill-add")
    relay.input(form, "form", "submitted", {"values": {"how": "new", "name": "notes", "description": "メモの書き方"}}, human=True)
    answer(relay, form, True)
    assert ("agent skill add", {"name": "notes", "description": "メモの書き方"}) in relay.backend.calls
    relay.input(window, "editor", "add_skill", {}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-skill-add")
    relay.input(form, "form", "submitted", {"values": {"how": "dir", "name": "pdf", "from_dir": "C:/skills/pdf"}}, human=True)
    answer(relay, form, True)
    assert ("agent skill add", {"name": "pdf", "from_dir": "C:/skills/pdf"}) in relay.backend.calls

    relay.input(window, "editor", "skill_to_preset", {"name": "release-notes"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-skill-to-preset")
    relay.input(form, "form", "submitted", {"values": {"name": "release-notes"}}, human=True)
    answer(relay, form, True)
    assert ("agent skill preset add", {"name": "release-notes", "from_module": "release-notes"}) in relay.backend.calls
    relay.input(window, "editor", "remove_skill", {"name": "release-notes"}, human=True)
    answer(relay, window, True)
    assert ("agent skill remove", {"name": "release-notes"}) in relay.backend.calls
    assert relay.display.values(window)["skill"] is None  # 消したら、選択を空に


def test_agents_screen_saves_the_text_for_every_agent(relay):
    window = opened(relay, "agents", module="C:/work/Calc/.ecobuild/w/12")
    relay.input(window, "editor", "save_rules", {"common": "決まり1\n決まり2"}, human=True)
    answer(relay, window, True)
    assert ("agent rules set", {"common": "決まり1\n決まり2"}) in relay.backend.calls
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"
    assert nodes(relay, window)["editor"]["props"]["rules"]["common"] == "決まり1\n決まり2"  # 変えたら読み直す
    relay.input(window, "editor", "save_rules", {"common": ""}, human=True)  # 空にして保存すると、消す
    answer(relay, window, True)
    assert ("agent rules set", {"common": ""}) in relay.backend.calls


def test_the_agents_screen_goes_to_this_pcs_presets_and_back_in_the_same_window(relay):
    window = opened(relay, "agents", module="C:/work/Calc")
    relay.input(window, "presets", "pressed", {}, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == "agent-presets" and relay.display.tree(window)["args"] == {"module": "C:/work/Calc"}
    relay.input(window, "back", "pressed", {}, human=True)
    relay.idle()
    assert relay.display.tree(window)["screen"] == "agents"
    assert [w["id"] for w in relay.display.windows()] == [window]  # 窓は増えない
    assert notices(relay) == []


def test_the_form_and_the_editor_have_samples_for_what_they_show(relay):
    parts = relay.parts
    assert {"cfg-agent-editor", "cfg-form"} <= set(parts)
    editor = {sample["name"]: sample["props"] for sample in parts["cfg-agent-editor"].samples}
    assert editor["役（選んだツール・強い子の警告）"]["fit"]["stronger"] == ["lead", "manager"]
    assert any(sample["props"].get("error") for sample in parts["cfg-form"].samples)


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
    assert view["nav"]["props"]["current"] == "agents" and view["back"]["props"]["label"].startswith("←")
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
    assert [call for call in relay.backend.calls] == [("help", {})]  # 読むのは、コマンドの一覧（ecobuild help）だけ
    catalog = nodes(relay, alone)["commands"]["props"]["catalog"]
    assert [c["path"] for c in catalog["commands"]] == ["status"] and list(catalog["types"]) == ["python"]
    window = opened(relay, "help", module="C:/work/Calc")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "help" and view["body:step6_title"]["props"]["text"].startswith("6.")
    assert view["body:commands"]["props"]["catalog"]["commands"][0]["path"] == "status"
    assert notices(relay) == []
