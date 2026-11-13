"""eco_gui のハブの窓（hub・hub_add・hub_forget・hub_delete・hub_account・hub_settings・hub_help・doctor・operator）：
左のメニューで画面が切り替わること、カード・帯・入力の窓が、正しいコマンドと引数で ecobuild を呼ぶこと。

GUIFrameWork が入っていない Python では飛ばす。ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402

from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402
from test_eco_gui_settings import FakeSettings, opened, press, spec, typed, wraps  # noqa: E402

MODULES = [
    {"path": "C:/work/Calc", "exists": True, "repository": "acme/Calc", "url": "https://github.com/acme/Calc.git", "type": "python"},
    {"path": "C:/work/Game", "exists": True, "repository": "acme/Game", "url": "https://github.com/acme/Game.git", "type": "cpp"},
    {"path": "C:/work/Gone", "exists": False, "repository": "acme/Gone", "url": "https://github.com/acme/Gone.git", "type": "cpp"},
]
LEGACY = [{"path": "C:/work/Calc-2", "exists": True, "repository": "acme/Calc", "url": "https://github.com/acme/Calc.git", "branch": "task/3-x", "task": 3}]
DOCTOR = [
    {"id": "git", "name": "git", "ok": True, "required": True, "detail": "2.55", "hint": "", "fix": ""},
    {"id": "gh_auth", "name": "gh の認証", "ok": False, "required": True, "detail": "", "hint": "gh auth login を実行してください。", "fix": "login"},
    {"id": "git_identity", "name": "git の名前・メール", "ok": True, "required": True, "detail": "Octo Cat <octo@example.com>", "hint": "", "fix": "identity"},
    {"id": "docker", "name": "docker", "ok": False, "required": False, "detail": "", "hint": "ecobuild setup --docker", "fix": "docker"},
]
CHECK = {"url": "https://example.invalid/ECOBuild", "ref": "main", "current": "aaaaaaa1", "latest": "bbbbbbb2", "up_to_date": False, "gui": True}
TYPES = [{"name": "cpp", "new_kinds": ["app", "library", "shared", "none"], "default_new_kind": "app"},
         {"name": "python", "new_kinds": ["app", "library", "none"], "default_new_kind": "app"},
         {"name": "generic", "new_kinds": [], "default_new_kind": None}]


def hub_specs(text):
    flag = {"type": "boolean"}
    return {
        "installer check": spec("read", ref=text),
        "module types": spec("read"),
        "workspace close": spec("confirm", path=text, at=text, discard_local=flag, dry_run=flag),
        "module adopt": spec("confirm", type=text, dry_run=flag),
        "module new": spec("change", ["name"], name=text, type=text, kind=text, project=text, test=flag, description=text, owner=text, public=flag),
        # オペレーターとの会話（拡張コマンド ecobuild gui）
        "gui conversation": spec("read"),
        "gui ask": spec("change", text=text, session=text, agent=text, **{"continue": flag}),
        "gui conversation-new": spec("change"),
    }


class HubCommands(FakeEcobuild):
    """ハブの画面が使うコマンドの形だけ（FakeEcobuild.commands() が、じかの子クラスの _specs を集めるので、ここに置く）。"""

    def _specs(self, text):
        return hub_specs(text)


class FakeHub(FakeSettings):
    """ハブの画面が使うコマンドを足した、ecobuild の代わり。"""

    def _specs(self, text):
        return {**super()._specs(text), **hub_specs(text)}

    def run(self, name, args, context, on_event):
        plain = {key: value for key, value in args.items() if key != "module"}
        talk = self.__dict__.setdefault("talk", [])  # オペレーターとの会話の記録
        if name == "gui conversation":
            self.calls.append((name, plain))
            return {"ok": True, "result": {"session": "s1" if talk else None, "messages": list(talk), "state": "idle", "doing": None}}
        if name == "gui conversation-new":
            self.calls.append((name, plain))
            talk.clear()
            return {"ok": True, "result": {"session": None, "messages": [], "state": "idle", "doing": None}}
        if name == "gui ask":
            self.calls.append((name, plain))
            if plain["text"] == "つながらない":   # 記録に何も残らない失敗（ecobuild gui が入っていない等）
                return {"ok": False, "error": {"code": "usage_error", "message": "gui というコマンドはありません。"}}
            talk.append({"role": "user", "text": plain["text"], "at": len(talk)})
            on_event({"event": "output", "message": "ecobuild workspace list"})
            on_event({"event": "output", "message": "ecobuild gui open --page tasks"})
            talk.append({"role": "agent", "ok": True, "text": "開きました", "at": len(talk),
                         "actions": [{"command": "ecobuild workspace list", "ok": True}, {"command": "ecobuild gui open --page tasks", "ok": True}]})
            return {"ok": True, "result": {"session": "s1", "text": "開きました", "ok": True, "actions": []}}
        answers = {
            "workspace list": {"modules": MODULES, "legacy": LEGACY},
            "doctor": {"items": DOCTOR},
            "installer check": CHECK,
            "module types": TYPES,
            "account show": {"login": "octocat", "role": None, "scopes": ["project", "repo"]},
        }
        if name in answers:
            self.modules.append(args.get("module"))
            self.calls.append((name, plain))
            return {"ok": True, "result": answers[name]}
        if name == "module new" and plain.get("name") == "Taken":
            self.calls.append((name, plain))
            return {"ok": False, "error": {"code": "repository_exists", "message": "GitHub に acme/Taken は既にあります。"}}
        if name == "module delete" and plain.get("confirm") == "acme/NoScope":
            self.calls.append((name, plain))
            return {"ok": False, "error": {"code": "github_permission", "message": "リポジトリを削除する権限（delete_repo）がありません。"}}
        if name == "module delete" and not plain.get("confirm"):
            self.calls.append((name, plain))
            return {"ok": False, "error": {"code": "confirmation_required", "message": "確認が必要です：開いている Issue が 2 件あります。"}}
        if name == "setup":
            self.modules.append(args.get("module"))
            self.calls.append((name, plain))
            return {"ok": True, "result": {"done": ["git が gh の認証を使うようにしました"], "remaining": [], "commands": []}}
        return super().run(name, args, context, on_event)


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeHub(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def inside(relay, screen):
    """窓の中に重ねて開いた画面の窓。"""
    found = [w for w in relay.display.windows() if w["screen"] == screen]
    assert len(found) == 1 and found[0].get("parent"), f"{screen} が、窓の中に開いていません"
    return found[0]["id"]


def screens(relay):
    return sorted(w["screen"] for w in relay.display.windows())


def emit(relay, window, node, output, **payload):
    relay.input(window, node, output, payload, human=True)
    relay.idle()


def test_every_binding_matches_the_backend_commands(relay):
    relay.verify()


def test_hub_shows_the_menu_the_cards_and_the_banners(relay):
    hub = opened(relay, "hub")
    view = nodes(relay, hub)
    assert view["page"]["look"] == "shell" and view["main"]["look"] == "page"
    menu = view["nav"]["props"]
    assert menu["current"] == "hub" and [item["id"] for item in menu["items"]] == ["hub", "operator", "hub-settings", "hub-help"]
    assert menu["account"]["login"] == "octocat"  # 下のアカウント
    cards = view["modules"]["props"]
    assert [row["path"] for row in cards["rows"]] == ["C:/work/Calc", "C:/work/Game", "C:/work/Gone"]
    assert [row["path"] for row in cards["legacy"]] == ["C:/work/Calc-2"]
    assert [row["repository"] for row in cards["known"]] == ["acme/Calc", "acme/Old"]  # アーカイブ済みかは GitHub の一覧から
    assert ("module list", {"all": True}) in relay.backend.calls
    assert [item["name"] for item in view["setup"]["props"]["items"] if not item["ok"] and item["required"]] == ["gh の認証"]
    assert view["update"]["props"]["check"]["up_to_date"] is False
    assert set(relay.backend.modules) == {None}  # モジュールの外：-C を付けない


def test_hub_asks_github_only_when_opened_changed_or_asked(relay):
    """GitHub に聞く読み（module list --all・installer check）は、窓が前に来るたびには読み直さない。「読み直す」で読む。"""
    hub = opened(relay, "hub")
    assert importlib.import_module("eco_gui.screens.hub").SCREEN["window"]["refresh"] == {"focus": True}  # 戻ってきたら一覧を読み直す
    assert all(row.get("lazy") for row in importlib.import_module("eco_gui.screens.hub").SCREEN["bindings"]
               if row.get("read") in ("module list", "installer check", "doctor"))  # 遅い・GitHub に聞く読みは、そのたびには読まない
    asked = lambda: [name for name, _ in relay.backend.calls if name in ("module list", "installer check")]  # noqa: E731
    assert sorted(asked()) == ["installer check", "module list"]
    press(relay, hub, "reload")
    assert sorted(asked()) == ["installer check", "installer check", "module list", "module list"]


def test_hub_menu_switches_the_screen_in_the_same_window(relay):
    hub = opened(relay, "hub")
    for screen in ("operator", "hub-settings", "hub-help", "hub"):
        emit(relay, hub, "nav", "selected", id=screen)
        assert screens(relay) == [screen]  # 窓は増えない
        assert nodes(relay, hub)["nav"]["props"]["current"] == screen
    emit(relay, hub, "setup", "pressed")  # 帯の「準備する」は、設定へ
    assert screens(relay) == ["hub-settings"]


def test_hub_cards_open_forget_and_put_away(relay):
    hub = opened(relay, "hub")
    emit(relay, hub, "modules", "action", id="C:/work/Game", action="open", name="Game", repository="acme/Game")
    assert [w["args"] for w in relay.display.windows() if w["screen"] == "frame-workspaces"] == [{"module": "C:/work/Game"}]
    # 開けないモジュール：理由と一緒に「一覧から外す」の窓が、ハブの中に開く
    emit(relay, hub, "modules", "action", id="C:/work/Gone", action="forget", name="Gone", repository="acme/Gone", reason="フォルダが見つかりません")
    forget = inside(relay, "hub-forget")
    view = nodes(relay, forget)
    assert view["title"]["props"]["text"] == "Gone" and view["reason"]["props"]["text"] == "フォルダが見つかりません"
    assert ("workspace forget", {"path": "C:/work/Gone"}) not in relay.backend.calls  # 押すまで外さない
    press(relay, forget, "forget")
    assert ("workspace forget", {"path": "C:/work/Gone"}) in relay.backend.calls
    assert "hub-forget" not in screens(relay)  # できたら閉じる
    # 片付ける：アーカイブ（確かめてから）
    relay.input(hub, "modules", "action", {"id": "C:/work/Calc", "action": "away", "name": "Calc", "repository": "acme/Calc"}, human=True)
    answer(relay, hub, True)
    assert ("module archive", {"name": "acme/Calc"}) in relay.backend.calls


def test_hub_archived_modules_are_unarchived_or_deleted_by_name(relay):
    hub = opened(relay, "hub")
    relay.input(hub, "modules", "archived", {"repository": "acme/Old", "action": "unarchive"}, human=True)
    answer(relay, hub, True)
    assert ("module unarchive", {"name": "acme/Old"}) in relay.backend.calls
    emit(relay, hub, "modules", "archived", repository="acme/Old", action="delete", local="C:/work/Old")
    window = inside(relay, "hub-delete")
    view = nodes(relay, window)
    assert view["title"]["props"]["text"] == "acme/Old" and view["local"]["props"]["text"] == "C:/work/Old"
    assert wraps(relay, window, "discard_local") == ["hidden"]  # clone を消すときだけ出す
    # 名前を打たずに押す：ecobuild は消さず、開いている Issue の数を答える。それを窓の中に出す
    press(relay, window, "delete", confirm=True)
    assert nodes(relay, window)["problem"]["props"]["text"] == "確認が必要です：開いている Issue が 2 件あります。"
    assert wraps(relay, window, "permission") == ["hidden"]
    typed(relay, window, confirm="acme/NoScope")  # 権限（delete_repo）が足りない：足し方の案内を出す
    press(relay, window, "delete", confirm=True)
    assert wraps(relay, window, "permission") == [None] and "delete_repo" in nodes(relay, window)["permission"]["props"]["text"]
    emit(relay, window, "remove_workspaces", "changed", on=True)
    assert wraps(relay, window, "discard_local") == [None]
    emit(relay, window, "discard_local", "changed", on=True)
    typed(relay, window, confirm="acme/Old")
    press(relay, window, "delete", confirm=True)
    assert ("module delete", {"name": "acme/Old", "confirm": "acme/Old", "remove_workspaces": True, "discard_local": True}) in relay.backend.calls
    assert "hub-delete" not in screens(relay)


def test_hub_closes_or_forgets_the_workspaces_of_the_previous_version(relay):
    hub = opened(relay, "hub")
    relay.input(hub, "modules", "legacy", {"path": "C:/work/Calc-2", "action": "close"}, human=True)
    answer(relay, hub, True)
    emit(relay, hub, "modules", "legacy", path="C:/work/Lost", action="forget")
    assert ("workspace close", {"path": "C:/work/Calc-2"}) in relay.backend.calls
    assert ("workspace forget", {"path": "C:/work/Lost"}) in relay.backend.calls


def test_hub_update_banner_updates_after_asking(relay):
    hub = opened(relay, "hub")
    press(relay, hub, "update", confirm=False)
    assert not [call for call in relay.backend.calls if call[0] == "gui update"]
    press(relay, hub, "update", confirm=True)
    assert ("gui update", {}) in relay.backend.calls  # installer update の後、GUI を起動し直す（ecobuild gui update）


FORM = {"method": "new", "directory": "C:/work", "name": "", "type": "cpp", "kind": "app", "project": "", "test": None, "description": "",
        "owner": "", "public": None, "repository": "", "folder": "", "adopt_folder": "", "adopt_type": "cpp"}


def test_add_window_creates_a_module_in_the_parent_folder(relay):
    hub = opened(relay, "hub")
    press(relay, hub, "add")
    window = inside(relay, "hub-add")
    view = nodes(relay, window)
    assert [kind["name"] for kind in view["form"]["props"]["types"]] == ["cpp", "python", "generic"]
    assert [row["repository"] for row in view["form"]["props"]["candidates"]] == ["acme/Calc", "acme/Old"]
    assert view["form"]["props"]["owner"] == "acme"
    assert wraps(relay, window, "create", "clone", "register", "adopt") == ["unavailable", "hidden", "hidden", "hidden"]  # 名前がまだ
    emit(relay, window, "form", "changed", **{**FORM, "name": "Taken"})
    press(relay, window, "create")
    assert nodes(relay, window)["form"]["props"]["problem"] == "GitHub に acme/Taken は既にあります。"  # 誤りは窓の中に。窓は閉じない
    emit(relay, window, "form", "changed", **{**FORM, "name": "MathCore", "type": "cpp", "kind": "library", "project": "Core", "test": False,
                                               "description": "計算", "owner": "octo-org", "public": True})
    press(relay, window, "create")
    assert ("module new", {"name": "MathCore", "type": "cpp", "kind": "library", "project": "Core", "test": False,
                           "description": "計算", "owner": "octo-org", "public": True}) in relay.backend.calls
    assert "C:/work" in relay.backend.modules  # 保存先の親フォルダで実行する（ecobuild -C <親フォルダ>）
    assert "hub-add" not in screens(relay)


def test_add_window_omits_what_was_left_empty(relay):
    window = opened(relay, "hub-add")
    emit(relay, window, "form", "changed", **{**FORM, "name": "Tool", "type": "generic", "kind": ""})
    press(relay, window, "create")
    assert ("module new", {"name": "Tool", "type": "generic"}) in relay.backend.calls  # 型にないもの・空の欄は渡さない
    window = opened(relay, "hub-add")
    emit(relay, window, "form", "changed", **{**FORM, "directory": "", "name": "Tool"})
    assert wraps(relay, window, "create") == ["unavailable"]  # 保存先を決めるまで押せない（今いる場所に作らない）


def test_add_window_clones_registers_and_adopts(relay):
    window = opened(relay, "hub-add")
    emit(relay, window, "form", "changed", **{**FORM, "method": "clone", "repository": "acme/Old"})
    assert wraps(relay, window, "create", "clone", "register", "adopt") == ["hidden", None, "hidden", "hidden"]
    press(relay, window, "clone")
    assert ("module clone", {"repository": "acme/Old"}) in relay.backend.calls and "C:/work" in relay.backend.modules

    window = opened(relay, "hub-add")
    emit(relay, window, "form", "changed", **{**FORM, "method": "register", "folder": "C:/work/New"})
    press(relay, window, "register")
    assert ("workspace add", {"path": "C:/work/New"}) in relay.backend.calls

    window = opened(relay, "hub-add")
    emit(relay, window, "form", "changed", **{**FORM, "method": "adopt", "adopt_folder": "C:/work/Repo", "adopt_type": "python"})
    relay.input(window, "adopt", "pressed", {}, human=True)
    answer(relay, window, True)  # 置くファイルと push 先は、実行する前の確かめに出る
    assert ("module adopt", {"type": "python"}) in relay.backend.calls and "C:/work/Repo" in relay.backend.modules


def test_account_window_shows_the_login_and_saves_the_author_and_the_owner(relay):
    hub = opened(relay, "hub")
    emit(relay, hub, "nav", "account")
    window = inside(relay, "hub-account")
    props = nodes(relay, window)["account"]["props"]
    assert props["account"]["login"] == "octocat" and props["account"]["scopes"] == ["project", "repo"]
    assert props["config"] == {"owner": "acme"}
    assert next(item for item in props["doctor"] if item["id"] == "git_identity")["detail"] == "Octo Cat <octo@example.com>"
    relay.input(window, "account", "author", {"name": "Octo Cat", "email": "cat@example.com"}, human=True)
    answer(relay, window, True)
    emit(relay, window, "account", "owner", owner="octo-org")
    emit(relay, window, "account", "owner_reset")
    for call in [("setup", {"name": "Octo Cat", "email": "cat@example.com"}), ("config set", {"key": "owner", "value": "octo-org"}),
                 ("config unset", {"key": "owner"})]:
        assert call in relay.backend.calls
    press(relay, window, "close")
    assert "hub-account" not in screens(relay)


def test_hub_settings_shows_the_cards_of_each_tab(relay):
    window = opened(relay, "hub-settings")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "hub-settings"
    assert view["tabs"]["props"]["labels"] == ["全般", "AI", "エージェント", "コンテナ", "ECOBuild"]
    assert view["owner"]["props"]["text"] == "acme"  # 今の値が欄に入っている
    assert [item["id"] for item in view["doctor"]["props"]["items"]] == ["git", "gh_auth", "git_identity", "docker"]
    assert view["images"]["props"]["data"]["images"][0]["name"] == "ecobuild-calc:bbb"
    assert view["update_status"]["props"]["look"] == "status" and view["update_status"]["props"]["check"]["latest"] == "bbbbbbb2"
    typed(relay, window, owner="octo-org")
    press(relay, window, "owner_save")
    press(relay, window, "owner_reset")
    assert ("config set", {"key": "owner", "value": "octo-org"}) in relay.backend.calls and ("config unset", {"key": "owner"}) in relay.backend.calls
    # 環境の準備：欄には今の名前・メールを薄く出す（環境チェックの項目を渡す）。結果は、したこと・足りないもの・コマンド
    assert [item["id"] for item in view["setup_fields"]["props"]["items"]][2] == "git_identity" and view["setup_fields"]["props"]["result"] is None
    emit(relay, window, "setup_fields", "changed", name="", email="", install=True)
    press(relay, window, "setup", confirm=True)
    assert ("setup", {"install": True}) in relay.backend.calls
    assert nodes(relay, window)["setup_fields"]["props"]["result"] == {
        "done": ["git が gh の認証を使うようにしました"], "remaining": [], "commands": []}
    press(relay, window, "update_status", confirm=True)
    assert ("gui update", {}) in relay.backend.calls


def test_doctor_operator_and_help_screens(relay):
    doctor = opened(relay, "doctor")
    assert [item["name"] for item in nodes(relay, doctor)["items"]["props"]["items"]][:2] == ["git", "gh の認証"]
    assert nodes(relay, opened(relay, "operator"))["nav"]["props"]["current"] == "operator"
    view = nodes(relay, opened(relay, "hub-help"))
    # モジュールの窓のヘルプと同じ部品（cfg-help）・同じ中身
    assert view["nav"]["props"]["current"] == "hub-help" and view["main"]["look"] == "cfg-fill-page"
    guide = view["guide"]
    assert guide["part"] == "cfg-help" and guide["look"] == "cfg-fill" and ("help", {}) in relay.backend.calls
    assert [step["title"] for step in guide["props"]["steps"]][:2] == ["モジュールを用意する", "タスクを作る"]
    module_help = importlib.import_module("eco_gui.screens.help").SCREEN["nodes"]
    same = next(node for node in module_help if node.get("part") == "cfg-help")["props"]
    assert {key: guide["props"][key] for key in same} == same


def test_operator_talks_through_the_conversation_commands(relay):
    """会話：ecobuild gui conversation で読み、送ると gui ask --continue（文と「続き」）。途中の道具は会話へ続けて届く。"""
    window = opened(relay, "operator")
    view = nodes(relay, window)
    assert view["main"]["look"] == "hub-fill-page" and view["tabs"]["props"]["labels"] == ["会話", "エージェント", "話し方"]
    assert view["chat"]["props"]["conversation"]["messages"] == [] and view["chat"]["props"]["intro"].startswith("AI はコードを書かず")
    assert ("gui conversation", {}) in relay.backend.calls
    emit(relay, window, "input", "sent", text="タスクを見せて\n2行目")
    assert ("gui ask", {"text": "タスクを見せて\n2行目", "continue": True}) in relay.backend.calls
    chat = nodes(relay, window)["chat"]["props"]
    assert [(m["role"], m["text"]) for m in chat["conversation"]["messages"]] == [("user", "タスクを見せて\n2行目"), ("agent", "開きました")]
    assert chat["doing"] == ["ecobuild workspace list", "ecobuild gui open --page tasks"]  # 続いて届いた、実行中のコマンド
    assert chat["asked"] is None and chat["failed"] is None  # 返答が記録に入ったら、待っている文は消える
    with pytest.raises(Exception):  # 空の文は送れない（部品が断る）
        relay.input(window, "input", "sent", {"text": "  "}, human=True)
    # 新しい会話
    press(relay, window, "new")
    assert ("gui conversation-new", {}) in relay.backend.calls
    assert nodes(relay, window)["chat"]["props"]["conversation"]["messages"] == []


def test_operator_shows_why_a_message_could_not_be_sent(relay):
    window = opened(relay, "operator")
    emit(relay, window, "input", "sent", text="つながらない")
    chat = nodes(relay, window)["chat"]["props"]
    assert chat["asked"] is None and chat["failed"] == "gui というコマンドはありません。"
    emit(relay, window, "input", "sent", text="もう一度")  # 次に送ると、前の失敗は消える
    assert nodes(relay, window)["chat"]["props"]["failed"] is None


def test_operator_chat_parts_have_every_state_sample():
    samples = importlib.import_module("eco_gui.parts.hub_operator_chat.samples").SAMPLES
    states = {sample["props"].get("conversation", {}).get("state") for sample in samples}
    assert {"idle", "starting", "waiting", "choice", "exited"} <= states
    assert any(sample["props"].get("asked") for sample in samples) and any(sample["props"].get("failed") for sample in samples)
    part = importlib.import_module("eco_gui.parts.hub_operator_input.part")
    part.on_sent("頼む")
    with pytest.raises(ValueError):
        part.on_sent(" ")
