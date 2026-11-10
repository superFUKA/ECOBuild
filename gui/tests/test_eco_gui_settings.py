"""eco_gui の設定の画面（settings・container・hub_settings・hub_archive）：正しいコマンドと引数で ecobuild を呼ぶこと。

GUIFrameWork が入っていない Python では飛ばす。ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from guiframework.errors import RelayError  # noqa: E402

from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402


def spec(weight, required=(), **properties):
    return {"description": "設定", "weight": weight, "args": {"type": "object", "required": list(required), "properties": properties}}


class FakeSettings(FakeEcobuild):
    """設定の画面が使うコマンドを足した、ecobuild の代わり。片付け・コンテナ・トークンの状態は、コマンドで変わる。"""

    def __init__(self):
        super().__init__()
        self.archived = {"acme/Calc": False, "acme/Old": True}
        self.container = {"container": True, "state": "exited"}
        self.token = False

    def _specs(self, text):
        flag, number, many = {"type": "boolean"}, {"type": "integer"}, {"type": "array", "items": text}
        return {
            **super()._specs(text),
            **{name: spec("read") for name in (
                "profile list", "track", "release list", "container status", "container recipe", "agent version status",
                "account list", "config list", "agent token status", "container image list", "installer show")},
            "agent version list": spec("read", limit=number),
            "installer versions": spec("read", ref=text, count=number),
            "module list": spec("read", owner=text, archived=flag, all=flag),
            "module upgrade": spec("change", branch=text),
            "module protect": spec("confirm", approvals=number, require_ci=flag, show=flag, off=flag),
            "module archive": spec("confirm", ["name"], name=text, owner=text),
            "module unarchive": spec("confirm", ["name"], name=text, owner=text),
            "module delete": spec("confirm", ["name"], name=text, owner=text, confirm=text, remove_workspaces=flag, discard_local=flag),
            "profile use": spec("change", ["name"], name=text),
            "profile remove": spec("change", ["name"], name=text),
            "profile add": spec("change", ["name"], name=text, configuration=text, parallel=number),
            "track add": spec("change", patterns=many),
            "track remove": spec("change", patterns=many),
            "ignore": spec("change", patterns=many),
            "release create": spec("confirm", ["tag"], tag=text, title=text, notes=text, target=text),
            "account use": spec("change", account=text, clear=flag),
            **{name: spec(weight) for name, weight in (
                ("container on", "change"), ("container off", "confirm"), ("container start", "change"), ("container stop", "change"),
                ("container remove", "confirm"), ("container image prune", "confirm"),
                ("agent token login", "confirm"), ("agent token remove", "confirm"))},
            "container set": spec("change", image=text, default_image=flag, deny=text, no_deny=flag),
            "container image build": spec("change", workspace=text),
            "config set": spec("change", ["key", "value"], key=text, value=text),
            "config unset": spec("change", ["key"], key=text),
            "setup": spec("confirm", name=text, email=text, install=flag, docker=flag),
            "installer update": spec("confirm", check=flag, ref=text),
        }

    def run(self, name, args, context, on_event):
        plain = {key: value for key, value in args.items() if key != "module"}
        if name in ("module archive", "module unarchive"):
            self.archived[plain["name"]] = name == "module archive"
        changes = {"container on": {"container": True}, "container off": {"container": False}, "container start": {"state": "running"},
                   "container stop": {"state": "exited"}, "container remove": {"state": "none"}}
        self.container.update(changes.get(name, {}))
        if name in ("agent token login", "agent token remove"):
            self.token = name == "agent token login"
        answers = {
            "module show": {"name": "Calc", "type": "python", "private": True, "repository": "acme/Calc",
                            "archived": self.archived["acme/Calc"], "workspaces": []},
            "profile list": {"profiles": {"release": {"configuration": "Release", "parallel": 8, "shared": False}}, "selected": "release"},
            "track": {"patterns": [{"pattern": "*.md", "source": "type", "excluded": False},
                                   {"pattern": "data/**", "source": "module", "excluded": False}], "exclude": []},
            "release list": [{"tag": "v1.0.0", "name": "最初の版", "url": "https://example.invalid/r/v1.0.0", "latest": True}],
            "container status": {"path": "C:/work/Calc", **self.container, "outdated": True,
                                 "custom_image": "", "deny": ["WebFetch"], "docker_ready": True},
            "container recipe": {"module": "calc", "environment": "ecobuild-env-calc:aaa", "image": "ecobuild-calc:bbb",
                                 "context": "", "dockerfile": "FROM ubuntu:24.04\n", "layer": "RUN echo layer\n"},
            "agent version status": {"setting": "stable", "installed": None, "reason": "コンテナが動いていません"},
            "agent version list": {"channels": {"stable": "2.1.1", "latest": "2.1.9"}, "versions": ["2.1.9", "2.1.1"]},
            "account list": [{"login": "octocat", "active": True}, {"login": "hubot", "active": False}],
            "config list": {"owner": "acme"},
            "agent token status": {"saved": self.token, "path": "C:/home/ecobuild/agents/container-token"},
            "container image list": {"docker_ready": True, "docker_detail": "Docker 29", "missing": [], "images": [
                {"name": "ecobuild-calc:bbb", "module": "calc", "size": "1GB", "created": "2 days ago", "current": True,
                 "used_by": [], "environment": False}]},
            "installer show": {"version": "0.1.0", "ref": "main", "commit": "abc", "editable": False},
            "installer versions": {"ref": plain.get("ref", "main"), "branches": ["main", "dev"], "commits": [
                {"sha": "abc", "date": "2026-11-01", "subject": "今の版", "current": True, "latest": True},
                {"sha": "def", "date": "2026-10-01", "subject": "前の版", "current": False, "latest": False}]},
            "module list": [{"repository": "acme/Calc", "type": "python", "private": True, "archived": self.archived["acme/Calc"], "description": ""},
                            {"repository": "acme/Old", "type": "cpp", "private": True, "archived": self.archived["acme/Old"], "description": "古い"}],
        }
        if name in answers:
            self.modules.append(args.get("module"))
            self.calls.append((name, plain))
            return {"ok": True, "result": answers[name]}
        if name == "container image build":
            on_event({"event": "output", "message": "イメージを作っています…\n"})
        return super().run(name, args, context, on_event)


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeSettings(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def opened(relay, screen, **args):
    window = relay.execute({"command": "open", "screen": screen, "args": args})["window"]
    relay.idle()
    return window


def press(relay, window, node, confirm=None):
    relay.input(window, node, "pressed", {}, human=True)
    if confirm is not None:
        answer(relay, window, confirm)
    relay.idle()


def wraps(relay, window, *ids):
    """部品の包み（None＝出ていて押せる／unavailable＝灰色／hidden＝出していない）。"""
    view = nodes(relay, window)
    return [(view[node]["wrap"] or {}).get("kind") for node in ids]


def typed(relay, window, **texts):
    for node, text in texts.items():
        relay.input(window, node, "changed", {"text": text}, human=True)
    relay.idle()


def test_every_binding_matches_the_backend_commands(relay):
    relay.verify()


def test_settings_shows_the_module_and_upgrades_it(relay):
    window = opened(relay, "settings", module="C:/work/Calc")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "settings"
    assert view["info"]["props"]["data"]["name"] == "Calc"
    assert relay.backend.modules[-1] == "C:/work/Calc"  # そのモジュールで読む
    press(relay, window, "upgrade")
    assert ("module upgrade", {}) in relay.backend.calls  # ブランチ（任意）は、決めなければ渡さない
    typed(relay, window, upgrade_branch="main")
    press(relay, window, "upgrade")
    assert ("module upgrade", {"branch": "main"}) in relay.backend.calls


def test_settings_build_profiles_are_listed_by_name_and_used_added_removed(relay):
    window = opened(relay, "settings", module="C:/work/Calc")
    view = nodes(relay, window)
    assert view["profile_selected"]["props"]["data"]["selected"] == "release"
    assert list(view["profile_list"]["props"]["data"]) == ["release"]
    assert relay.backend.calls.count(("profile list", {})) == 1  # 2つの部品へ出しても、読むのは1回
    relay.input(window, "profile_list", "action", {"id": "release", "action": "use"}, human=True)
    relay.idle()
    assert ("profile use", {"name": "release"}) in relay.backend.calls
    assert ("profile remove", {"name": "release"}) not in relay.backend.calls  # 押したボタンのコマンドだけ
    relay.input(window, "profile_list", "action", {"id": "release", "action": "remove"}, human=True)
    relay.idle()
    assert ("profile remove", {"name": "release"}) in relay.backend.calls
    press(relay, window, "profile_none")
    assert ("profile use", {"name": "none"}) in relay.backend.calls
    assert view["profile_add"]["wrap"]["kind"] == "unavailable"  # 名前がまだ
    typed(relay, window, profile_name="debug", profile_configuration="Debug", profile_parallel="4")
    press(relay, window, "profile_add")
    assert ("profile add", {"name": "debug", "configuration": "Debug", "parallel": 4}) in relay.backend.calls  # 数は数で渡る


def test_settings_protects_the_base_branch_after_asking(relay):
    window = opened(relay, "settings", module="C:/work/Calc")
    press(relay, window, "do_protect", confirm=False)  # いいえ：実行しない
    assert not [call for call in relay.backend.calls if call[0] == "module protect"]
    press(relay, window, "do_protect", confirm=True)
    assert ("module protect", {}) in relay.backend.calls  # 決めていないものは渡さない（ecobuild の既定）
    typed(relay, window, approvals="2")
    relay.input(window, "require_ci", "changed", {"value": "true"}, human=True)
    relay.idle()
    press(relay, window, "do_protect", confirm=True)
    assert ("module protect", {"approvals": 2, "require_ci": True}) in relay.backend.calls
    press(relay, window, "unprotect", confirm=True)
    assert ("module protect", {"off": True}) in relay.backend.calls


def test_settings_tracked_patterns_and_gitignore(relay):
    window = opened(relay, "settings", module="C:/work/Calc")
    view = nodes(relay, window)
    assert [row["pattern"] for row in view["patterns"]["props"]["rows"]] == ["*.md", "data/**"]
    assert view["track_add"]["wrap"]["kind"] == "unavailable" and view["ignore_add"]["wrap"]["kind"] == "unavailable"
    typed(relay, window, pattern="*.txt")
    press(relay, window, "track_add")
    press(relay, window, "ignore_add")
    relay.input(window, "patterns", "action", {"id": "data/**", "action": "remove"}, human=True)
    relay.idle()
    for call in [("track add", {"patterns": ["*.txt"]}), ("ignore", {"patterns": ["*.txt"]}), ("track remove", {"patterns": ["data/**"]})]:
        assert call in relay.backend.calls


def test_settings_releases_and_the_account_of_the_workspace(relay):
    window = opened(relay, "settings", module="C:/work/Calc")
    view = nodes(relay, window)
    assert view["release_list"]["props"]["rows"][0]["tag"] == "v1.0.0"
    assert view["me"]["props"]["data"]["login"] == "superFUKA"
    assert view["release_create"]["wrap"]["kind"] == "unavailable"  # タグがまだ
    typed(relay, window, release_tag="v1.1.0", release_notes="直した")
    press(relay, window, "release_create", confirm=True)
    assert ("release create", {"tag": "v1.1.0", "notes": "直した"}) in relay.backend.calls
    typed(relay, window, account_name="hubot")
    press(relay, window, "account_use")
    press(relay, window, "account_clear")
    assert ("account use", {"account": "hubot"}) in relay.backend.calls and ("account use", {"clear": True}) in relay.backend.calls


def test_settings_puts_the_module_away_without_typing_its_name(relay):
    window = opened(relay, "settings", module="C:/work/Calc")
    assert nodes(relay, window)["away_now"]["props"]["data"]["repository"] == "acme/Calc"
    assert relay.backend.calls.count(("module show", {})) == 1  # 表示にも共有の値にも使うが、読むのは1回
    # アーカイブしていない：出るのは「アーカイブする」だけ（解除・削除は出さない）
    assert wraps(relay, window, "archive", "unarchive", "delete_confirm", "remove_workspaces", "delete") == [None] + ["hidden"] * 4
    with pytest.raises(RelayError):  # 隠した部品は、入力も受けない
        relay.input(window, "delete", "pressed", {}, human=True)
    press(relay, window, "archive", confirm=True)
    assert ("module archive", {"name": "acme/Calc"}) in relay.backend.calls  # 名前は、module show のリポジトリ（人は打たない）
    # アーカイブ済み：解除と、削除の欄が出る。削除は、確かめの名前を打つまで押せない
    assert wraps(relay, window, "archive", "unarchive", "delete_confirm", "remove_workspaces", "delete") == ["hidden", None, None, None, "unavailable"]
    press(relay, window, "unarchive", confirm=True)
    assert ("module unarchive", {"name": "acme/Calc"}) in relay.backend.calls
    assert wraps(relay, window, "archive", "unarchive", "delete") == [None, "hidden", "hidden"]
    press(relay, window, "archive", confirm=True)
    typed(relay, window, delete_confirm="acme/Calc")
    assert wraps(relay, window, "delete") == [None]
    press(relay, window, "delete", confirm=False)
    assert not [call for call in relay.backend.calls if call[0] == "module delete"]
    relay.input(window, "remove_workspaces", "changed", {"value": "true"}, human=True)
    relay.idle()
    press(relay, window, "delete", confirm=True)
    assert ("module delete", {"name": "acme/Calc", "confirm": "acme/Calc", "remove_workspaces": True}) in relay.backend.calls


def test_container_screen_shows_the_state_and_only_the_buttons_that_fit_it(relay):
    window = opened(relay, "container", module="C:/work/Calc/.ecobuild/w/12")
    view = nodes(relay, window)
    assert view["nav"]["props"]["current"] == "container"
    assert view["status"]["props"]["data"]["state"] == "exited" and view["own_now"]["props"]["data"]["deny"] == ["WebFetch"]
    assert relay.backend.calls.count(("container status", {})) == 1
    assert view["claude"]["props"]["data"]["setting"] == "stable"
    assert view["dockerfile"]["props"]["text"].startswith("FROM ubuntu") and view["layer"]["props"]["text"].startswith("RUN echo")
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"
    buttons = ("on", "off", "start", "stop", "remove")
    assert wraps(relay, window, *buttons) == ["hidden", None, None, "hidden", None]  # コンテナにしてある・止まっている
    press(relay, window, "start")
    assert wraps(relay, window, *buttons) == ["hidden", None, "hidden", None, None]  # 動いている
    press(relay, window, "stop")
    press(relay, window, "remove", confirm=True)
    assert wraps(relay, window, *buttons) == ["hidden", None, None, "hidden", "hidden"]  # まだない：消すものがない
    press(relay, window, "off", confirm=True)
    assert wraps(relay, window, *buttons) == [None, "hidden", "hidden", "hidden", "hidden"]  # コンテナにしない
    press(relay, window, "on")
    for call in [("container start", {}), ("container stop", {}), ("container remove", {}), ("container off", {}), ("container on", {})]:
        assert call in relay.backend.calls


def test_container_screen_sets_the_image_and_what_agents_may_not_use(relay):
    window = opened(relay, "container", module="C:/work/Calc/.ecobuild/w/12")
    view = nodes(relay, window)
    assert view["image"]["props"]["text"] == "" and view["deny"]["props"]["items"] == ["WebFetch"]  # 今の値が欄に入っている
    assert wraps(relay, window, "image_set", "deny_set") == ["unavailable", "unavailable"]  # 書き直すまで押せない
    for node in ("image_default", "deny_clear"):
        press(relay, window, node)
    typed(relay, window, image="ubuntu:24.04", deny="WebFetch;Bash(curl:*)")
    press(relay, window, "image_set")
    press(relay, window, "deny_set")
    press(relay, window, "build")
    for call in [("container set", {"default_image": True}), ("container set", {"no_deny": True}),
                 ("container set", {"image": "ubuntu:24.04"}), ("container set", {"deny": "WebFetch;Bash(curl:*)"}),
                 ("container image build", {"workspace": "C:/work/Calc/.ecobuild/w/12"})]:
        assert call in relay.backend.calls
    assert nodes(relay, window)["out"]["props"]["lines"] == ["イメージを作っています…"]


def test_hub_opens_the_settings_and_the_put_away_screens(relay):
    hub = opened(relay, "hub")
    press(relay, hub, "settings")
    press(relay, hub, "archive")
    assert {w["screen"] for w in relay.display.windows()} == {"hub", "hub-settings", "hub-archive"}


def test_hub_settings_reads_this_pc_and_changes_the_tool_settings(relay):
    window = opened(relay, "hub-settings")
    view = nodes(relay, window)
    assert [row["login"] for row in view["accounts"]["props"]["rows"]] == ["octocat", "hubot"]
    assert view["config"]["props"]["data"] == {"owner": "acme"}
    assert view["token"]["props"]["data"]["saved"] is False
    assert view["channels"]["props"]["data"] == {"stable": "2.1.1", "latest": "2.1.9"}
    assert view["images"]["props"]["rows"][0]["name"] == "ecobuild-calc:bbb" and view["docker"]["props"]["data"]["docker_ready"] is True
    assert view["installed"]["props"]["data"]["ref"] == "main"
    assert [row["sha"] for row in view["versions"]["props"]["rows"]] == ["abc", "def"]
    assert set(relay.backend.modules) == {None}  # モジュールの外：-C を付けない
    assert view["config_set"]["wrap"]["kind"] == "unavailable"  # 項目と値がまだ

    relay.input(window, "config_key", "changed", {"value": "owner"}, human=True)
    typed(relay, window, config_value="octo-org")
    press(relay, window, "config_set")
    press(relay, window, "config_unset")
    typed(relay, window, claude_version="stable")
    assert nodes(relay, window)["version_now"]["props"]["text"] == "stable"
    press(relay, window, "version_set")
    press(relay, window, "version_unset")
    # 版は、読んだ一覧から選んでも決められる
    assert nodes(relay, window)["version_pick"]["props"]["options"] == ["2.1.9", "2.1.1"]
    relay.input(window, "version_pick", "changed", {"value": "2.1.1"}, human=True)
    relay.idle()
    press(relay, window, "version_set")
    assert ("config set", {"key": "agent_claude_version", "value": "2.1.1"}) in relay.backend.calls
    for call in [("config set", {"key": "owner", "value": "octo-org"}), ("config unset", {"key": "owner"}),
                 ("config set", {"key": "agent_claude_version", "value": "stable"}), ("config unset", {"key": "agent_claude_version"})]:
        assert call in relay.backend.calls
    typed(relay, window, setup_name="Octo Cat")
    press(relay, window, "setup", confirm=True)
    assert ("setup", {"name": "Octo Cat"}) in relay.backend.calls
    press(relay, window, "doctor")
    assert "doctor" in {w["screen"] for w in relay.display.windows()}


def test_hub_settings_token_images_and_update_ask_before_they_run(relay):
    window = opened(relay, "hub-settings")
    assert wraps(relay, window, "token_login", "token_remove") == [None, "hidden"]  # トークンがない：消すボタンは出さない
    press(relay, window, "token_login", confirm=True)
    assert wraps(relay, window, "token_remove") == [None]
    press(relay, window, "token_remove", confirm=False)
    assert ("agent token login", {}) in relay.backend.calls and ("agent token remove", {}) not in relay.backend.calls
    assert not [name for name, _ in relay.backend.calls if name == "agent token set"]  # 値を入れる口は、画面にない
    press(relay, window, "images_build")
    assert ("container image build", {}) in relay.backend.calls
    assert nodes(relay, window)["images_out"]["props"]["lines"] == ["イメージを作っています…"]
    press(relay, window, "images_prune", confirm=True)
    assert ("container image prune", {}) in relay.backend.calls

    press(relay, window, "update", confirm=False)
    assert not [call for call in relay.backend.calls if call[0] == "installer update"]
    press(relay, window, "update", confirm=True)
    assert ("installer update", {}) in relay.backend.calls
    assert wraps(relay, window, "update_ref", "update_branch") == ["unavailable", "unavailable"]  # 版・ブランチを決めるまで押せない
    typed(relay, window, ref="main")
    press(relay, window, "update_ref", confirm=True)
    relay.input(window, "versions", "action", {"id": "def", "action": "install"}, human=True)
    answer(relay, window, True)
    assert ("installer update", {"ref": "main"}) in relay.backend.calls and ("installer update", {"ref": "def"}) in relay.backend.calls


def test_hub_settings_picks_a_branch_from_the_list_and_reads_its_versions(relay):
    window = opened(relay, "hub-settings")
    assert nodes(relay, window)["branch"]["props"]["options"] == ["main", "dev"]
    assert relay.backend.calls.count(("installer versions", {})) == 1  # 選ぶ前：入れたときのブランチ
    relay.input(window, "branch", "changed", {"value": "dev"}, human=True)
    relay.idle()
    assert ("installer versions", {"ref": "dev"}) in relay.backend.calls  # 選んだブランチの版を読む
    assert nodes(relay, window)["branch"]["props"]["value"] == "dev"
    press(relay, window, "update_branch", confirm=True)
    assert ("installer update", {"ref": "dev"}) in relay.backend.calls


def test_hub_archive_shows_only_the_buttons_that_fit_the_chosen_module(relay):
    window = opened(relay, "hub-archive")
    assert [row["repository"] for row in nodes(relay, window)["modules"]["props"]["rows"]] == ["acme/Calc", "acme/Old"]
    assert ("module list", {"all": True}) in relay.backend.calls
    buttons = ("archive", "unarchive", "confirm", "remove_workspaces", "delete")
    assert wraps(relay, window, *buttons) == ["hidden"] * 5  # 選ぶまで、どれも出ない
    relay.input(window, "modules", "selected", {"id": "acme/Calc", "row": {"repository": "acme/Calc", "archived": False}}, human=True)
    relay.idle()
    view = nodes(relay, window)
    assert view["modules"]["props"]["selected"] == "acme/Calc" and view["chosen"]["props"]["text"] == "acme/Calc"
    assert wraps(relay, window, *buttons) == [None, "hidden", "hidden", "hidden", "hidden"]  # アーカイブしていない
    press(relay, window, "archive", confirm=True)
    assert ("module archive", {"name": "acme/Calc"}) in relay.backend.calls
    assert wraps(relay, window, *buttons) == ["hidden", None, None, None, "unavailable"]  # アーカイブした：解除と削除の欄に入れ替わる
    press(relay, window, "unarchive", confirm=True)
    assert ("module unarchive", {"name": "acme/Calc"}) in relay.backend.calls
    assert wraps(relay, window, "archive", "unarchive") == [None, "hidden"]

    relay.input(window, "modules", "selected", {"id": "acme/Old", "row": {"repository": "acme/Old", "archived": True}}, human=True)
    relay.idle()
    assert wraps(relay, window, *buttons) == ["hidden", None, None, None, "unavailable"]  # 削除は、確かめの名前を打つまで押せない
    typed(relay, window, confirm="acme/Old")
    press(relay, window, "delete", confirm=False)
    assert not [call for call in relay.backend.calls if call[0] == "module delete"]
    press(relay, window, "delete", confirm=True)
    assert ("module delete", {"name": "acme/Old", "confirm": "acme/Old"}) in relay.backend.calls
    assert relay.display.values(window)["away_module"] is None  # 消したら、選択を空に
    assert wraps(relay, window, *buttons) == ["hidden"] * 5
