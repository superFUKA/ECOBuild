"""eco_gui の設定の画面（settings・container・hub_settings）：正しいコマンドと引数で ecobuild を呼ぶこと。

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
        self.kind = "python"

    def _specs(self, text):
        return {**self._specs_before_protection(text), "module protection": {
            "description": "保護の状態", "weight": "read", "args": {"type": "object", "required": [], "properties": {}}}}

    def _specs_before_protection(self, text):
        flag, number, many = {"type": "boolean"}, {"type": "integer"}, {"type": "array", "items": text}
        return {
            **super()._specs(text),
            **{name: spec("read") for name in (
                "profile list", "track", "release list", "container status", "container recipe", "agent version status",
                "account list", "config list", "agent token status", "container image list", "installer show")},
            "container dockerfile": spec("read", write=text),
            "agent version list": spec("read", limit=number),
            "installer versions": spec("read", ref=text, count=number),
            "module list": spec("read", owner=text, archived=flag, all=flag),
            "module upgrade": {**spec("change", branch=text), "dry_run": True},
            "module protect": spec("confirm", approvals=number, require_ci=flag, show=flag, off=flag),
            "module archive": spec("confirm", ["name"], name=text, owner=text),
            "module unarchive": spec("confirm", ["name"], name=text, owner=text),
            "module delete": spec("confirm", ["name"], name=text, owner=text, confirm=text, remove_workspaces=flag, discard_local=flag),
            "profile use": spec("change", ["name"], name=text),
            "profile remove": spec("change", ["name"], name=text),
            "profile add": spec("change", ["name"], name=text, configuration=text, parallel=number, shared=flag, architecture=text,
                                cpp_standard=number, generator=text, toolset=text, c_compiler=text, cxx_compiler=text, toolchain_file=text,
                                windows_sdk=text, test_parallel=number, stop_on_test_failure=flag, googletest_archive=text, no_fetch=flag),
            "profile project": spec("change", ["name", "project"], name=text, project=text, type=text, cpp_standard=number,
                                    artifact_directory=text, test_parallel=number, googletest_archive=text, clear=flag),
            "project list": spec("read"),
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
            "module show": {"name": "Calc", "type": self.kind, "private": True, "repository": "acme/Calc",
                            "archived": self.archived["acme/Calc"], "workspaces": []},
            "profile list": {"profiles": {"release": {"configuration": "Release", "parallel": 8, "shared": False,
                                                      "options": {"cpp_standard": 23, "fetch_git": False},
                                                      "projects": {"Core": {"type": "static"}}}}, "selected": "release"},
            "project list": [{"name": "Core", "kind": "static_library"}, {"name": "App", "kind": "executable"}],
            "profile use": {"profiles": {}, "selected": None if plain.get("name") == "none" else plain.get("name")},
            "track": {"patterns": [{"pattern": "*.md", "source": "type", "excluded": False},
                                   {"pattern": "data/**", "source": "module", "excluded": False}], "exclude": []},
            "release list": [{"tag": "v1.0.0", "name": "最初の版", "url": "https://example.invalid/r/v1.0.0", "latest": True}],
            "container status": {"path": "C:/work/Calc", **self.container, "outdated": True,
                                 "custom_image": "", "deny": ["WebFetch"], "docker_ready": True},
            "container recipe": {"module": "calc", "environment": "ecobuild-env-calc:aaa", "image": "ecobuild-calc:bbb",
                                 "context": "", "dockerfile": "FROM ubuntu:24.04\n", "layer": "RUN echo layer\n"},
            "container dockerfile": {"text": plain.get("write", "FROM ubuntu:24.04\n"), "exists": True, "hash": "aaa", "image": "ecobuild-env-calc:aaa",
                                     "image_ready": False, "outdated": False, "container_image": "", "editable": True, "reason": "",
                                     "docker_ready": True, "docker_detail": "", **({"changed": True} if "write" in plain else {})},
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


def notices(relay):
    return [event["message"] for event in relay.display.events_after(0) if event["command"] == "notify"]


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
    # 今の仕様に合わせる：入力の窓が、下見（変えるファイル）を見せてから実行する
    relay.backend.preview = lambda name, args: {"ok": True, "result": {"format": 4, "latest_format": 5, "paths": ["ecobuild.toml"], "skipped": []}}
    press(relay, window, "upgrade")
    form = inside(relay, window, "mod-upgrade")
    assert nodes(relay, form)["form"]["props"]["values"]["paths"] == ["ecobuild.toml"]
    relay.input(form, "form", "submitted", {"values": {}}, human=True)
    relay.idle()
    assert ("module upgrade", {"branch": ""}) in relay.backend.calls  # ブランチを決めなければ空（今いるブランチ）
    typed(relay, window, upgrade_branch="main")
    press(relay, window, "upgrade")
    form = inside(relay, window, "mod-upgrade")
    assert nodes(relay, form)["form"]["props"]["subject"] == "main"
    relay.input(form, "form", "submitted", {"values": {}}, human=True)
    relay.idle()
    assert ("module upgrade", {"branch": "main"}) in relay.backend.calls


def inside(relay, window, screen):
    """window の中に重ねて開いた窓（入力の窓）。"""
    found = [w["id"] for w in relay.display.windows() if w.get("parent") == window and w["screen"] == screen]
    assert found, [(w["id"], w["screen"], w.get("parent")) for w in relay.display.windows()]
    return found[-1]


def test_settings_build_profiles_are_a_table_with_the_one_used_on_this_pc(relay):
    window = opened(relay, "settings", module="C:/work/Calc")
    table = nodes(relay, window)["profile_table"]
    assert table["part"] == "cfg-profiles" and table["props"]["kind"] == "python"  # 列は、モジュールの型で変わる
    assert table["props"]["data"]["selected"] == "release" and list(table["props"]["data"]["profiles"]) == ["release"]
    assert relay.backend.calls.count(("profile list", {})) == 1
    place = "C:/work/Calc/.ecobuild/w/12"  # 変える操作は、窓の中で選んだタスクブランチの作業空間で
    assert table["props"]["workspaces"] == []  # 作業空間がない：部品が変える操作を灰色にし、「今は見るだけ」の帯を出す
    relay.input(window, "profile_table", "use", {"name": "release", "stop": False}, human=True)  # ラジオで選ぶ
    relay.idle()
    assert notices(relay)[-1] == "このPCではビルド設定 release を使います。"
    relay.input(window, "profile_table", "use", {"name": "none", "stop": True}, human=True)     # 使わない
    relay.idle()
    assert notices(relay)[-1] == "ビルド設定の使用をやめました。"
    assert ("profile use", {"name": "release"}) in relay.backend.calls and ("profile use", {"name": "none"}) in relay.backend.calls
    relay.input(window, "profile_table", "remove", {"name": "release"}, human=True)  # 削除：場所を選ぶ窓（危険の色）
    relay.idle()
    form = inside(relay, window, "cfg-profile-remove")
    assert nodes(relay, form)["form"]["props"]["danger"] is True
    relay.input(form, "form", "submitted", {"values": {"place": place}}, human=True)
    relay.idle()
    call = ("profile remove", {"name": "release"})
    assert relay.backend.modules[relay.backend.calls.index(call)] == place
    relay.input(window, "profile_table", "open_tasks", {}, human=True)  # 「タスク管理を開く」
    relay.idle()
    assert relay.display.tree(window)["screen"] == "tasks"
    window = opened(relay, "settings", module="C:/work/Calc")

    # 追加・編集：型に合う入力の窓を、この窓の中に重ねて開く（Python は 名前・構成・並列の数）
    relay.input(window, "profile_table", "add", {"kind": "python"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-profile-edit-python")
    assert relay.display.tree(form)["args"] == {"module": "C:/work/Calc", "name": ""}
    relay.input(form, "form", "submitted", {"values": {"name": "debug", "configuration": "Debug", "parallel": 4, "place": place}}, human=True)
    relay.idle()
    call = ("profile add", {"name": "debug", "configuration": "Debug", "parallel": 4})
    assert relay.backend.modules[relay.backend.calls.index(call)] == place
    assert form not in [w["id"] for w in relay.display.windows()]  # うまくいったら閉じる
    relay.input(window, "profile_table", "edit", {"name": "release", "kind": "python"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-profile-edit-python")
    props = nodes(relay, form)["form"]["props"]
    assert props["at"] == ["release"] and props["values"]["release"]["configuration"] == "Release"  # 今の値が入っている
    assert props["fields"][0]["value"] == "release"
    relay.input(form, "form", "cancelled", {}, human=True)
    relay.idle()
    relay.input(window, "profile_table", "add", {"kind": "generic"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-profile-edit")
    relay.input(form, "form", "submitted", {"values": {"name": "ci", "configuration": "Release", "place": place}}, human=True)
    relay.idle()
    assert ("profile add", {"name": "ci", "configuration": "Release"}) in relay.backend.calls
    assert notices(relay)[-1] == "ビルド設定を保存しました。"


def test_settings_cpp_build_profiles_have_options_and_overrides_for_projects(relay):
    relay.backend.kind = "cpp"
    window = opened(relay, "settings", module="C:/work/Calc")
    assert nodes(relay, window)["profile_table"]["props"]["kind"] == "cpp"
    relay.input(window, "profile_table", "edit", {"name": "release", "kind": "cpp"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-profile-edit-cpp")
    labels = [field.get("label") for field in nodes(relay, form)["form"]["props"]["fields"] if field.get("type") == "section"]
    assert labels == ["C++・コンパイラ（空なら既定）", "テスト・依存先（空なら既定）"]  # 畳める節
    relay.input(form, "form", "submitted", {"values": {
        "name": "release", "configuration": "Release", "parallel": 8, "shared": True, "cpp_standard": "23", "architecture": "",
        "generator": "Ninja Multi-Config", "toolset": "", "c_compiler": "", "cxx_compiler": "", "toolchain_file": "", "windows_sdk": "",
        "test_parallel": "", "stop_on_test_failure": False, "googletest_archive": "", "no_fetch": True, "place": "C:/work/Calc/.ecobuild/w/12"}}, human=True)
    relay.idle()
    # 空の欄は渡さない（既定）。数は数で渡る
    assert ("profile add", {"name": "release", "configuration": "Release", "parallel": 8, "shared": True, "cpp_standard": 23,
                            "generator": "Ninja Multi-Config", "stop_on_test_failure": False, "no_fetch": True}) in relay.backend.calls

    # Project ごとの上書き：変える・足す（Project は読んだ一覧から選ぶ）・外す
    relay.input(window, "profile_table", "project", {"name": "release", "project": "Core"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-profile-project")
    props = nodes(relay, form)["form"]["props"]
    assert props["at"] == ["release", "projects", "Core"] and [row["name"] for row in props["rows"]] == ["Core", "App"]
    relay.input(form, "form", "submitted", {"values": {"project": "Core", "type": "shared", "cpp_standard": "", "artifact_directory": "",
                                                        "test_parallel": "", "googletest_archive": "", "place": "C:/work/Calc/.ecobuild/w/12"}}, human=True)
    relay.idle()
    assert ("profile project", {"name": "release", "project": "Core", "type": "shared"}) in relay.backend.calls
    relay.input(window, "profile_table", "project_clear", {"name": "release", "project": "Core"}, human=True)
    relay.idle()
    form = inside(relay, window, "cfg-profile-project-clear")
    relay.input(form, "form", "submitted", {"values": {"place": "C:/work/Calc/.ecobuild/w/12"}}, human=True)
    relay.idle()
    assert ("profile project", {"name": "release", "project": "Core", "clear": True}) in relay.backend.calls


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
    assert view["nav"]["props"]["current"] == "settings"  # 左の印は「設定」
    assert view["body:status"]["props"]["data"]["state"] == "exited" and view["body:own_now"]["props"]["data"]["deny"] == ["WebFetch"]
    assert relay.backend.calls.count(("container status", {})) == 1
    assert view["body:claude"]["props"]["data"]["setting"] == "stable"
    # 上の要約：作り方・この作業空間のコンテナ（古い／今の作り方の印は、読んだ outdated から）・この PC のイメージ
    summary = view["body:summary"]["props"]
    assert view["body:summary"]["part"] == "cfg-container" and summary["recipe"]["image"] == "ecobuild-calc:bbb"
    assert summary["status"]["outdated"] is True and summary["images"]["images"][0]["current"] is True
    assert view["body:dockerfile"]["props"]["text"].startswith("FROM ubuntu") and view["body:layer"]["props"]["text"].startswith("RUN echo")
    assert relay.backend.modules[-1] == "C:/work/Calc/.ecobuild/w/12"
    buttons = ("body:on", "body:off", "body:start", "body:stop", "body:remove")
    assert wraps(relay, window, *buttons) == ["hidden", None, None, "hidden", None]  # コンテナにしてある・止まっている
    press(relay, window, "body:start")
    assert wraps(relay, window, *buttons) == ["hidden", None, "hidden", None, None]  # 動いている
    press(relay, window, "body:stop")
    press(relay, window, "body:remove", confirm=True)
    assert wraps(relay, window, *buttons) == ["hidden", None, None, "hidden", "hidden"]  # まだない：消すものがない
    press(relay, window, "body:off", confirm=True)
    assert wraps(relay, window, *buttons) == [None, "hidden", "hidden", "hidden", "hidden"]  # コンテナにしない
    press(relay, window, "body:on")
    for call in [("container start", {}), ("container stop", {}), ("container remove", {}), ("container off", {}), ("container on", {})]:
        assert call in relay.backend.calls


def test_container_summary_edits_the_dockerfile_opens_its_place_and_puts_the_template_in_the_repository(relay):
    window = opened(relay, "container", module="C:/work/Calc/.ecobuild/w/12")
    relay.input(window, "body:summary", "action", {"name": "edit"}, human=True)  # 作業空間で編集：Dockerfile のエディター
    relay.idle()
    editor = inside(relay, window, "container-dockerfile")
    props = nodes(relay, editor)["editor"]["props"]
    assert props["data"]["editable"] is True and props["layer"].startswith("RUN echo")
    relay.input(editor, "editor", "save", {"text": "FROM ubuntu:24.04\nRUN true\n"}, human=True)  # 保存（中身は標準入力で）
    relay.idle()
    call = ("container dockerfile", {"write": "FROM ubuntu:24.04\nRUN true\n"})
    assert call in relay.backend.calls and relay.backend.modules[relay.backend.calls.index(call)] == "C:/work/Calc/.ecobuild/w/12"
    assert nodes(relay, editor)["editor"]["props"]["saved"]["changed"] is True and "保存しました" in notices(relay)[-1]
    relay.input(editor, "editor", "build", {}, human=True)  # 試しに作る
    relay.idle()
    assert ("container image build", {"workspace": "C:/work/Calc/.ecobuild/w/12"}) in relay.backend.calls
    relay.input(editor, "editor", "close", {}, human=True)
    relay.idle()
    assert editor not in [w["id"] for w in relay.display.windows()]
    relay.input(window, "body:summary", "action", {"name": "reveal"}, human=True)  # 場所を開く：エクスプローラーで Dockerfile を選んで
    relay.idle()
    assert ("open", {"path": [".ecobuild/container/Dockerfile"], "app": "explorer"}) in relay.backend.calls
    relay.input(window, "body:summary", "action", {"name": "place"}, human=True)  # リポジトリに置く：下見で確かめてから module upgrade
    relay.idle()
    inside(relay, window, "mod-upgrade")


def test_container_screen_sets_the_image_and_what_agents_may_not_use(relay):
    window = opened(relay, "container", module="C:/work/Calc/.ecobuild/w/12")
    view = nodes(relay, window)
    assert view["body:image"]["props"]["text"] == "" and view["body:deny"]["props"]["items"] == ["WebFetch"]  # 今の値が欄に入っている
    assert wraps(relay, window, "body:image_set", "body:deny_set") == ["unavailable", "unavailable"]  # 書き直すまで押せない
    for node in ("body:image_default", "body:deny_clear"):
        press(relay, window, node)
    typed(relay, window, **{"body:image": "ubuntu:24.04", "body:deny": "WebFetch;Bash(curl:*)"})
    press(relay, window, "body:image_set")
    press(relay, window, "body:deny_set")
    press(relay, window, "body:build")
    for call in [("container set", {"default_image": True}), ("container set", {"no_deny": True}),
                 ("container set", {"image": "ubuntu:24.04"}), ("container set", {"deny": "WebFetch;Bash(curl:*)"}),
                 ("container image build", {"workspace": "C:/work/Calc/.ecobuild/w/12"})]:
        assert call in relay.backend.calls
    assert nodes(relay, window)["body:out"]["props"]["lines"] == ["イメージを作っています…"]


def test_hub_opens_the_settings_from_the_menu_in_the_same_window(relay):
    hub = opened(relay, "hub")
    relay.input(hub, "nav", "selected", {"id": "hub-settings"}, human=True)  # 左のメニューの「設定」
    relay.idle()
    assert {w["screen"] for w in relay.display.windows()} == {"hub-settings"}


def test_hub_settings_reads_this_pc_and_changes_the_tool_settings(relay):
    window = opened(relay, "hub-settings")
    view = nodes(relay, window)
    assert [row["login"] for row in view["accounts"]["props"]["rows"]] == ["octocat", "hubot"]
    assert view["config"]["props"]["data"] == {"owner": "acme"}
    assert view["token"]["props"]["data"]["saved"] is False
    assert view["channels"]["props"]["data"] == {"stable": "2.1.1", "latest": "2.1.9"}
    images = view["images"]["props"]["data"]  # モジュールごとにまとめるのは、部品（hub-images）
    assert images["images"][0]["name"] == "ecobuild-calc:bbb" and images["docker_ready"] is True
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
    relay.input(window, "setup_fields", "changed", {"name": "Octo Cat", "email": "", "install": False}, human=True)
    relay.idle()
    press(relay, window, "setup", confirm=True)
    assert ("setup", {"name": "Octo Cat", "install": False}) in relay.backend.calls
    assert nodes(relay, window)["doctor"]["props"]["items"][0]["name"] == "git"  # 環境チェックは、設定の中に出す


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


