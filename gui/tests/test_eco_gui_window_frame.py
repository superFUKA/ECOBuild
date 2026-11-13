"""eco_gui のハブとモジュールの窓の枠（前の GUI と同じ振る舞いに戻したもの）：アカウントの窓・ログインと権限の端末・
Visual Studio で開く（ソリューションがなければビルドしてから）・ハブのカードのメニュー・フォルダを開く・環境チェックの直すボタン・
更新（新しい版があるときだけ。入れ直したら起動し直す）・この GUI・参照…・登録したフォルダがモジュールでないとき・窓の大きさ・
タスクバーのモジュールごとのアプリ（Electron に渡すもの）。

ecobuild は呼ばない（偽のバックエンドで確かめる）。窓の外（端末・フォルダを選ぶ窓・ショートカット）も開かない。
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("guiframework")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guiframework import create_app  # noqa: E402

from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402
from test_eco_gui_frame import MODULE, PLACE, FrameEcobuild  # noqa: E402
from test_eco_gui_hub import CHECK, FakeHub, emit, inside  # noqa: E402
from test_eco_gui_polish import notices, spec  # noqa: E402
from test_eco_gui_settings import opened  # noqa: E402

GUI = Path(__file__).resolve().parent.parent
SCREENS = GUI / "eco_gui" / "screens"


class WindowCommands(FakeEcobuild):
    """足したコマンドの形（ecobuild gui の拡張コマンド：next_commands.COMMANDS と、open --solution・build）。"""

    def _specs(self, text):
        flag = {"type": "boolean"}
        return {
            "gui login": spec("change", switch=flag),
            "gui scope": spec("change", ["scope"], scope=text),
            "gui pick-folder": spec("read", title=text, initial=text),
            "gui shortcut": spec("change", module=text, place=text, pick=flag),
            "gui quit": spec("confirm"),
            "gui update": spec("confirm", ref=text),
            "open": {**spec("change", path={"type": "array", "items": text}, app=text, vs_version=text, line={"type": "integer"}, solution=flag), "can": True},
            "build": spec("change", configuration=text, project=text),
            "container image build": spec("change", workspace=text),
            "container image prune": spec("change"),
        }


class WindowHub(FakeHub):
    """ハブ：足したコマンドの答え。"""

    def __init__(self):
        super().__init__()
        self.check = dict(CHECK)
        self.no_solution = True

    def run(self, name, args, context, on_event):
        plain = {key: value for key, value in args.items() if key != "module"}
        if name in ("open", "gui shortcut", "build"):
            self.__dict__.setdefault("done", []).append((name, plain, args.get("module")))
        if name == "installer check":
            self.calls.append((name, plain))
            return {"ok": True, "result": self.check} if self.check else {"ok": False, "error": {"code": "not_supported", "message": "手元のソースから入れています。"}}
        if name == "gui pick-folder":
            self.calls.append((name, plain))
            return {"ok": True, "result": {"path": "C:/picked/Folder"}}
        if name in ("gui shortcut", "gui update"):
            self.modules.append(args.get("module"))
            self.calls.append((name, plain))
            return {"ok": True, "result": {"message": "ショートカットを作りました：x.lnk" if name == "gui shortcut" else "更新を始めました。"}}
        if name == "open" and plain.get("solution") and self.no_solution:
            self.modules.append(args.get("module"))
            self.calls.append((name, plain))
            return {"ok": False, "error": {"code": "no_solution", "message": "ソリューション（.sln／.slnx）がまだありません。"}}
        if name == "open" and plain.get("app") == "vs":
            self.modules.append(args.get("module"))
            self.calls.append((name, plain))
            return {"ok": True, "result": {"app": "vs", "version": "2026", "opened": "solution", "name": "Game.slnx"}}
        if name == "workspace add" and plain.get("path") == "C:/plain":
            self.calls.append((name, plain))
            return {"ok": False, "error": {"code": "not_in_module", "message": "C:/plain はECOBuildのモジュールの中ではありません。"}}
        if name == "container image build":
            self.calls.append((name, plain))
            return {"ok": True, "result": {"built": ["ecobuild-calc:1", "ecobuild-game:2"]}}
        return super().run(name, args, context, on_event)


class WindowFrame(FrameEcobuild):
    """モジュールの窓：Visual Studio で開く（ソリューションがまだない）。"""

    def run(self, name, args, context, on_event):
        plain = {key: value for key, value in args.items() if key != "module"}
        if name in ("open", "build"):
            self.__dict__.setdefault("done", []).append((name, plain, args.get("module")))
        if name == "open" and plain.get("solution"):
            self.modules.append(args.get("module"))
            self.calls.append((name, plain))
            if getattr(self, "built", False):
                return {"ok": True, "result": {"app": "vs", "version": "2026", "opened": "solution", "name": "Calc.slnx"}}
            return {"ok": False, "error": {"code": "no_solution", "message": "ソリューション（.sln／.slnx）がまだありません。"}}
        return super().run(name, args, context, on_event)


def make(backend):
    app = create_app(importlib.import_module("eco_gui"), backend=backend, roles={"confirm": "confirm-box"})
    relay = app.relay(threaded=True)
    relay.verify()  # どの画面のつなぎも、バックエンドのコマンドと合っている
    return relay


@pytest.fixture
def hub():
    return make(WindowHub())


@pytest.fixture
def frame():
    return make(WindowFrame())


def screen_data(name):
    """画面の定義（実行せずに読む：GUIFrameWork と同じ）。"""
    import ast

    tree = ast.parse((SCREENS / f"{name}.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "SCREEN")


# モジュールの窓 --------------------------------------------------------------------------------------------------------
def test_the_account_at_the_bottom_left_of_a_module_window_opens_the_account_window(frame):
    window = opened(frame, "overview", module=MODULE)
    emit(frame, window, "nav", "account")
    account = inside(frame, "hub-account")
    assert frame.display.tree(account)["args"]["module"] == MODULE   # そのモジュールでの役割も読む
    # ログイン・切り替え・権限の追加は、端末の窓で（ecobuild gui login [--switch]・gui scope <権限>）
    emit(frame, account, "account", "login", switch=True)
    emit(frame, account, "account", "scope", scope="workflow")
    calls = [call for call in frame.backend.calls if call[0] in ("gui login", "gui scope")]
    assert calls == [("gui login", {"switch": True}), ("gui scope", {"scope": "workflow"})]
    assert "ターミナルで続けてください。終わったら「読み直す」を押してください。" in notices(frame)


def test_visual_studio_from_a_tab_offers_to_build_when_there_is_no_solution(frame):
    window = opened(frame, "frame-workspace", module=MODULE, space=PLACE)
    emit(frame, window, "bar:tabs", "action", name="vs", path=PLACE, version="2026")
    assert ("open", {"app": "vs", "vs_version": "2026", "solution": True}) in frame.backend.calls
    build = inside(frame, "frame-vs-build")   # 「ビルドしてから開きますか？」
    assert frame.display.tree(build)["args"] == {"module": PLACE, "version": "2026"}
    assert [n for n, v in nodes(frame, build).items() if (v.get("wrap") or {}).get("kind") == "hidden"] == ["built", "open"]
    frame.backend.built = True   # ビルドするとソリューションができる
    emit(frame, build, "build", "pressed")
    # 1回の押下で：その作業空間でビルドし、うまくいったら続けて開く（ecobuild open --app vs --solution）
    done = [(name, args, module) for name, args, module in frame.backend.done if name in ("build", "open")]
    assert done[-2:] == [("build", {}, PLACE), ("open", {"app": "vs", "vs_version": "2026", "solution": True}, PLACE)]
    assert "Visual Studio 2026 で開きます：Calc.slnx" in notices(frame)
    view = nodes(frame, build)
    assert view["out"]["props"]["lines"] and not view["open"]["wrap"]   # 開き直すボタンも出る


def test_the_tab_menu_has_one_visual_studio_the_version_chosen_on_this_pc(frame):
    window = opened(frame, "frame-workspace", module=MODULE, space=PLACE)
    tabs = nodes(frame, window)["bar:tabs"]["props"]
    assert tabs["module"] == MODULE and "vs_version" in tabs
    js = (GUI / "eco_gui" / "parts" / "frame_tabs" / "part.js").read_text(encoding="utf-8")
    assert "memory.shared.get('vs', '2026')" in js and "studio('2022'" not in js


def test_closed_tabs_stay_closed_while_the_window_is_open():
    """閉じたタブは、左のメニューで別のページへ行って戻っても閉じたまま（窓のページの入れ物に、モジュールごとに覚える）。"""
    js = (GUI / "eco_gui" / "parts" / "frame_tabs" / "part.js").read_text(encoding="utf-8")
    assert "memory.session" in js and "session.get(closedKey" in js and "session.set(closedKey" in js
    assert "closed.delete(current)" in js   # 出すよう頼まれた作業空間は、また出す


def test_the_module_window_is_as_large_as_before_and_rereads_the_tabs_every_20_seconds(frame):
    for name in ("frame_workspace", "frame_workspaces", "overview", "board", "settings"):
        window = screen_data(name)["window"]
        assert (window["width"], window["height"]) == (1360, 880), name
    # タブの状態（手元の module show）だけを 20 秒ごとに。GitHub に聞く task list は、その間隔では読まない
    reads = [row for row in screen_data("frame_bar")["bindings"] if "read" in row]
    assert [row["read"] for row in reads if row.get("every") == 20] == ["module show"]
    window = opened(frame, "frame-workspace", module=MODULE, space=PLACE)
    assert 20 in frame.display.tree(window)["refresh"]["reads"]


# ハブ ------------------------------------------------------------------------------------------------------------------
def test_the_card_menu_opens_the_folder_visual_studio_and_makes_a_shortcut(hub):
    window = opened(hub, "hub")
    emit(hub, window, "modules", "action", id="C:/work/Game", action="explorer", name="Game")
    emit(hub, window, "modules", "action", id="C:/work/Game", action="shortcut", name="Game")
    emit(hub, window, "modules", "action", id="C:/work/Game", action="vs", name="Game")
    assert hub.backend.done == [("open", {"app": "explorer"}, "C:/work/Game"), ("gui shortcut", {"pick": True}, "C:/work/Game"),
                                ("open", {"app": "vs", "solution": True}, "C:/work/Game")]
    assert "ショートカットを作りました：x.lnk" in notices(hub)
    assert inside(hub, "frame-vs-build")   # ソリューションがない：ビルドしてから
    hub.backend.no_solution = False
    emit(hub, window, "modules", "action", id="C:/work/Game", action="vs", name="Game")
    assert "Visual Studio 2026 で開きます：Game.slnx" in notices(hub)


def test_folders_open_from_the_archived_the_former_workspaces_and_an_unusable_module(hub):
    window = opened(hub, "hub")
    emit(hub, window, "modules", "archived", repository="acme/Old", action="folder", local="C:/work/Old", folder="C:/work/Old")
    emit(hub, window, "modules", "legacy", path="C:/work/Calc-2", action="folder")
    emit(hub, window, "modules", "action", id="C:/work/NotClone", action="unusable", name="NotClone", reason="git の clone ではなくなっています")
    unusable = inside(hub, "hub-unusable")
    emit(hub, unusable, "folder", "pressed")
    assert hub.backend.done == [("open", {"app": "explorer"}, folder) for folder in ("C:/work/Old", "C:/work/Calc-2", "C:/work/NotClone")]


def test_the_environment_check_fixes_the_login_and_the_permission(hub):
    window = opened(hub, "hub-settings")
    emit(hub, window, "doctor", "fix", fix="login", scope="")
    emit(hub, window, "doctor", "fix", fix="scope", scope="project")
    assert [call for call in hub.backend.calls if call[0].startswith("gui ")] == [("gui login", {}), ("gui scope", {"scope": "project"})]
    js = (GUI / "eco_gui" / "parts" / "hub_doctor" / "part.js").read_text(encoding="utf-8")
    assert "ログイン" in js and "権限を追加" in js


def test_update_is_offered_only_when_newer_and_relaunches_the_gui(hub):
    window = opened(hub, "hub-settings")
    view = nodes(hub, window)
    assert not view["update"]["wrap"] and not view["pick_card"]["wrap"]   # 新しい版がある
    press_and_confirm(hub, window, "update")
    assert ("gui update", {}) in hub.backend.calls and "更新を始めました。" in notices(hub)
    hub.backend.check = {**CHECK, "up_to_date": True}
    emit(hub, window, "reload", "pressed")
    assert (nodes(hub, window)["update"]["wrap"] or {}).get("kind") == "hidden" and not nodes(hub, window)["pick_card"]["wrap"]


def test_versions_are_not_offered_when_this_install_cannot_be_updated():
    backend = WindowHub()
    backend.check = None   # 手元のソースから入れた等：確かめられない
    relay = make(backend)
    window = opened(relay, "hub-settings")
    assert [(nodes(relay, window)[n]["wrap"] or {}).get("kind") for n in ("update", "pick_card")] == ["hidden", "hidden"]


def press_and_confirm(relay, window, node):
    relay.input(window, node, "pressed", {}, human=True)
    answer(relay, window, True)
    relay.idle()


def test_settings_remember_the_tab_and_tell_how_many_images_were_made(hub):
    window = opened(hub, "hub-settings")
    assert nodes(hub, window)["tabs"]["layout"] == "tabs"   # 最後に見ていたタブは、配置 tabs が覚える
    emit(hub, window, "images_build", "pressed")
    assert nodes(hub, window)["images"]["props"]["done"] == {"built": ["ecobuild-calc:1", "ecobuild-game:2"]}
    js = (GUI / "eco_gui" / "parts" / "hub_images" / "part.js").read_text(encoding="utf-8")
    assert "個のイメージを作りました" in js and "個のイメージを消しました" in js


def test_this_gui_makes_shortcuts_and_quits(hub):
    window = opened(hub, "hub-settings")
    emit(hub, window, "make_shortcut", "pressed")
    press_and_confirm(hub, window, "quit_gui")
    assert ("gui shortcut", {}) in hub.backend.calls and ("gui quit", {}) in hub.backend.calls


def test_browse_picks_a_folder_and_a_plain_folder_is_offered_to_become_a_module(hub):
    window = opened(hub, "hub")
    emit(hub, window, "add", "pressed")
    add = inside(hub, "hub-add")
    emit(hub, add, "form", "browse", field="folder", initial="C:/work")
    assert ("gui pick-folder", {"title": "フォルダを選ぶ", "initial": "C:/work"}) in hub.backend.calls
    props = nodes(hub, add)["form"]["props"]
    assert (props["picked"], props["picked_for"]) == ("C:/picked/Folder", "folder")
    emit(hub, add, "form", "changed", method="register", folder="C:/plain")
    emit(hub, add, "register", "pressed")
    assert nodes(hub, add)["form"]["props"]["failed"] == "not_in_module"   # 入力の窓が「モジュールにする」を勧める


# 窓の外（ecobuild gui の拡張コマンド・Electron に渡すもの・ショートカット） ---------------------------------------------
def test_the_extension_commands_are_listed_and_read_their_words():
    import next_commands

    names = [c["path"] for c in next_commands.COMMANDS]
    assert names == ["gui login", "gui scope", "gui pick-folder", "gui shortcut", "gui quit", "gui update"]
    assert next_commands.parse("shortcut", ["--module", "C:/w/Calc", "--pick"]) == {"module": "C:/w/Calc", "pick": True}
    assert next_commands.parse("scope", ["--", "project"]) == {"scope": "project"}
    with pytest.raises(next_commands.Failure):
        next_commands.scope("admin:org")
    with pytest.raises(next_commands.Failure):
        next_commands.parse("login", ["--nope"])
    import ecobuild_gui

    assert {c["path"] for c in next_commands.COMMANDS} <= {c["path"] for c in ecobuild_gui.COMMANDS}


def test_a_module_window_is_its_own_app_on_the_taskbar(monkeypatch):
    """モジュールの窓の AppUserModelID は、ショートカット・今までの GUI と同じ作り方（ピン留めでそのモジュールが開く）。"""
    import next_commands

    root = "C:/ECO/Calc"
    assert next_commands.module_app_id(root) == next_commands.module_app_id("c:\\eco\\calc\\")
    try:
        import app as classic

        assert next_commands.module_app_id(root) == classic.module_app_id(root)
    except ImportError:
        pass
    main = (GUI / "eco_gui" / "electron" / "main.js").read_text(encoding="utf-8")
    assert "'ECOBuild.Module.' + crypto.createHash('sha1')" in main and "'--module', root" in main and "setAppDetails" in main


def test_electron_gets_how_to_reopen_a_module_and_the_type_icons(monkeypatch, tmp_path):
    from eco_gui import shell

    monkeypatch.setattr(shell, "type_icons", lambda: {"cpp": "C:/icons/cpp.ico"})
    command = shell.electron_command("electron.exe", "http://127.0.0.1:5000/w/w1#t.s", "ECOBuild", [1360, 880])
    words = dict(word[2:].split("=", 1) for word in command[2:])
    assert words["size"] == "1360x880" and json.loads(words["type-icons"]) == {"cpp": "C:/icons/cpp.ico"}
    launch = json.loads(words["launch"])
    assert launch[-1].endswith("ECOBuildGUINext.pyw") and words["module-icon"].endswith("module.ico")


def test_the_start_script_opens_a_module_window_with_module():
    text = (GUI / "ECOBuildGUINext.pyw").read_text(encoding="utf-8")
    assert '"--module"' in text and '"--keep"' in text and '"frame-workspaces"' in text   # 表示の CLI の open --keep


def test_a_module_shortcut_opens_its_window_with_its_app_id(tmp_path):
    if sys.platform != "win32":
        pytest.skip("ショートカットは Windows だけ")
    import subprocess

    import eco_gui_setup
    import next_commands

    root = tmp_path / "Calc"
    root.mkdir()
    link = eco_gui_setup.make_module_shortcut(root, tmp_path, tmp_path / "venv", str(GUI / "module.ico"), next_commands.module_app_id(root))
    assert link == tmp_path / "Calc - ECOBuild.lnk"
    read = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                           "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:EG_LINK); $s.Arguments; "
                           "(New-Object -ComObject Shell.Application).NameSpace($env:EG_DIR).ParseName('Calc - ECOBuild.lnk')"
                           ".ExtendedProperty('System.AppUserModel.ID')"],
                          env={**__import__("os").environ, "EG_LINK": str(link), "EG_DIR": str(tmp_path)}, capture_output=True, text=True)
    arguments, app_id = read.stdout.strip().splitlines()[-2:]
    assert "--module" in arguments and str(root) in arguments and app_id == next_commands.module_app_id(root)
