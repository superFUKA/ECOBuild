"""eco_gui の入力の窓（共通の部品 form）と、下見（--dry-run）を使った事前確認：
どの入力の窓も部品 form 1つで描き、決めた値で、人が打つのと同じ ecobuild のコマンドを呼ぶこと。

ecobuild は呼ばない（偽のバックエンドで確かめる）。
"""

import importlib

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from test_eco_gui import FakeEcobuild, answer, nodes  # noqa: E402

PLACE = "C:/work/Calc/.ecobuild/w/12"  # タスクブランチの作業空間


def _spec(weight, required=(), **properties):
    return {"description": "", "weight": weight, "args": {"type": "object", "required": list(required), "properties": properties}}


class FakeForms(FakeEcobuild):
    """入力の窓が呼ぶコマンドと、下見（--dry-run --json の結果）を足した、ecobuild の代わり。"""

    def __init__(self):
        super().__init__()
        self.plans = []  # 下見を読んだコマンド
        self.partial = False  # 出している提出が、中間提出か
        self.clashes = ["src/app.py", "README.md"]  # 作成元の最新を取り込むと衝突するファイル
        self.conflicting = False  # 提出が作成元と衝突している（取り込み・承認・反映が、何も変えずに止まる）

    def _specs(self, text):
        number, flag = {"type": "integer"}, {"type": "boolean"}
        return {
            **super()._specs(text),
            "status": _spec("read", fetch=flag),
            "task status": _spec("read", number=number, issue=number, body=flag),
            "task finish": _spec("confirm", number=number, task=number, subject=text, ignore_checks=flag, complete=flag, partial=flag),
            "task approve": _spec("confirm", ["task"], task=number, message=text, subject=text, ignore_checks=flag),
            "task reject": _spec("confirm", ["task"], task=number, message=text),
            "task comment": _spec("change", number=number, issue=number, message=text),
            "task apply": _spec("confirm", number=number, task=number, subject=text, partial=flag),
            "task drop": _spec("confirm", number=number, close=flag),
            "task close": _spec("confirm", ["issue"], issue=number, not_planned=flag),
            "task reopen": _spec("change", ["issue"], issue=number, stage=text),
            "task prune": {**_spec("change", number=number), "dry_run": True},
            "task edit": _spec("change", ["issue"], issue=number, add_label=text),
            "task submit": _spec("confirm", title=text, draft=flag, reviewer=text, partial=flag, complete=flag, check=flag),
            "branch merge": {**_spec("confirm", ["name"], name=text, into=text, ignore_checks=flag), "dry_run": True},
            "module upgrade": {**_spec("change", branch=text), "dry_run": True},
        }

    def run(self, name, args, context, on_event):
        given = {key: value for key, value in args.items() if key != "module"}
        if name == "task status":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"number": given.get("number"), "title": "ログイン画面", "base": "main", "branch": "task/12-login",
                                           "pull_request": {"number": 13, "state": "open", "draft": False, "partial": self.partial}}}
        if self.conflicting and name in ("task finish", "task approve", "task apply"):
            super().run(name, args, context, on_event)
            code = "merge_conflict" if name == "task apply" else "pull_request_conflict"
            return {"ok": False, "error": {"code": code, "message": "作成元と衝突しています。", "details": list(self.clashes)}}
        if name == "task start":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"branch": "task/12-login", "base": "main", "workspace": PLACE}}
        if name == "status":
            super().run(name, args, context, on_event)
            return {"ok": True, "result": {"branch": "task/12-login", "task": 12, "base": "main", "ahead": 0, "behind": 0, "staged": [], "unstaged": [],
                                           "untracked": [], "pull_request": {"number": 13, "state": "open", "draft": True, "partial": True},
                                           "base_conflicts": list(self.clashes) if given.get("fetch") else []}}
        return super().run(name, args, context, on_event)

    def preview(self, name, args):
        self.plans.append((name, {key: value for key, value in args.items() if key != "module"}))
        if name == "module upgrade":
            return {"ok": True, "result": {"format": 4, "latest_format": 5, "paths": ["ecobuild.toml", ".ecobuild/README.md"], "skipped": [], "dry_run": True}}
        return {"ok": False, "error": {"code": "not_found", "message": f"{name} の下見はできません"}}


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeForms(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def opened(relay, screen, inside=None, **args):
    command = {"command": "open", "screen": screen, "args": {"module": "C:/work/Calc", **args}}
    window = relay.execute({**command, "inside": inside} if inside else command)["window"]
    relay.idle()
    return window


def calls(relay, name):
    return [args for called, args in relay.backend.calls if called == name]


def decide(relay, window, yes=None, **values):
    """入力の窓で決める（欄の値をまとめて出す）。yes を渡すと、出てきた確認に答える。"""
    relay.input(window, "form", "submitted", {"values": values}, human=True)
    if yes is not None:
        assert answer(relay, window, yes)["part"] == "confirm-box"
    relay.idle()


def test_bindings_match_the_backend_commands(relay):
    relay.verify()


def test_every_input_window_is_drawn_by_the_one_form_part(relay):
    """入力の窓の部品は form と、欄を読んだ情報から組む task-form・hub-add-form だけ（範囲ごとの部品は、もうない）。"""
    parts = relay.parts
    assert "form" in parts and not {"review-form", "mod-form", "cfg-form"} & set(parts)
    samples = {sample["name"]: sample["props"] for sample in parts["form"].samples}
    assert any(props.get("loading") for props in samples.values()) and any(props.get("error") for props in samples.values())
    assert any(props.get("outcome") for props in samples.values()) and any(props.get("problem") for props in samples.values())
    kinds = {field.get("type", "text") for props in samples.values() for field in props["fields"]}
    assert {"text", "number", "date", "textarea", "select", "radio", "checkbox", "checks", "section", "note"} <= kinds  # 欄の種類が、見本にそろっている
    forms = sorted(name for name, screen in relay.screens.items() if any(node.get("part") == "form" for node in screen.data["nodes"]))
    assert len(forms) >= 30 and {"task-finish", "task-submit", "mod-upgrade", "mod-branch-new", "cfg-agent-add", "review-merge"} <= set(forms)
    assert parts["task-form"].inputs["properties"]["kind"]["enum"] == ["new", "start", "edit", "assign"]


@pytest.mark.parametrize("screen, values, command, expected, confirm", [
    ("task-finish", {"subject": "件名", "ignore_checks": False, "complete": False, "partial": True},
     "task finish", {"number": 12, "subject": "件名", "ignore_checks": False, "complete": False, "partial": True}, True),
    ("task-complete", {"ignore_checks": True}, "task finish", {"number": 12, "ignore_checks": True, "complete": True}, True),
    ("task-approve", {"message": "よいです", "subject": "", "ignore_checks": True}, "task approve", {"task": 12, "message": "よいです", "ignore_checks": True}, True),
    ("task-reject", {"message": "直してください"}, "task reject", {"task": 12, "message": "直してください"}, True),
    ("task-comment", {"message": "あとで見ます"}, "task comment", {"issue": 12, "message": "あとで見ます"}, False),
    ("task-apply", {"subject": "", "complete": True, "partial": False}, "task apply", {"task": 12, "partial": False}, True),
    ("task-drop", {"close": True}, "task drop", {"number": 12, "close": True}, True),
    ("task-prune", {}, "task prune", {"number": 12}, False),
    ("task-label", {"label": "bug,ui"}, "task edit", {"issue": 12, "add_label": "bug,ui"}, False),
])
def test_each_task_window_runs_its_command_with_what_was_entered(relay, screen, values, command, expected, confirm):
    board = opened(relay, "board")
    window = opened(relay, screen, inside=board, issue=12)
    assert nodes(relay, window)["form"]["part"] == "form"
    decide(relay, window, **values)  # 入力の窓が確認を兼ねる（重いコマンドでも、もう一度は確かめない）
    assert calls(relay, command) == [expected]
    assert [w["id"] for w in relay.display.windows()] == [board]  # うまくいったら閉じる
    assert [event for event in relay.display.events_after(0) if event["command"] == "notify" and event.get("level") == "error"] == []


def test_required_fields_are_marked_and_cancel_closes_without_running(relay):
    board = opened(relay, "board")
    for screen, command, name in (("task-reject", "task reject", "message"), ("task-comment", "task comment", "message"), ("task-label", "task edit", "label")):
        window = opened(relay, screen, inside=board, issue=12)
        field = next(field for field in nodes(relay, window)["form"]["props"]["fields"] if field.get("name") == name)
        assert field["required"] is True  # 空では決められない欄（部品が * を付け、空なら窓の中に誤りを出す）
        relay.input(window, "form", "cancelled", {}, human=True)  # キャンセル：何もせずに閉じる
        relay.idle()
        assert calls(relay, command) == [] and [w["id"] for w in relay.display.windows()] == [board]
    with pytest.raises(Exception):
        relay.input(opened(relay, "task-reject", inside=board, issue=12), "form", "submitted", {"message": "直して"}, human=True)  # 値は values にまとめて出す


def test_what_happens_follows_the_task_that_was_read(relay):
    """「何が起きるか」の表と初めの値は、読んだタスクの状態から（作成元・提出しているか・中間提出か）。"""
    relay.backend.partial = True
    board = opened(relay, "board")
    window = opened(relay, "task-finish", inside=board, issue=12)
    props = nodes(relay, window)["form"]["props"]
    assert props["vars"] == {"issue": 12} and props["values"]["base"] == "main" and props["values"]["pull_request"]["partial"] is True
    assert calls(relay, "task status") == [{"number": 12}]
    complete = next(field for field in props["fields"] if field["name"] == "complete")
    assert (complete["value_from"], complete["off_value"], complete["inverse"]) == ("pull_request.partial", True, "partial")  # 中間提出なら、初めは外れている
    assert [row.get("show_if") for row in props["outcome"]] == [None, {"complete": True}, {"complete": False}]  # 印で、タスクの行が変わる

    done = opened(relay, "task-complete", inside=board, issue=12)
    rows = nodes(relay, done)["form"]["props"]["outcome"]
    assert rows[0]["show_if"] == {"pull_request.state": "open"} and rows[1]["hide_if"] == {"pull_request.state": "open"}


def test_submit_window_warns_about_conflicts_with_the_base_before_submitting(relay):
    """提出の窓：GitHub の最新を見て（status --fetch）、作成元と衝突するファイルを赤い帯で知らせる。提出は、その作業空間で。"""
    workspace = opened(relay, "workspace", module=PLACE)
    relay.input(workspace, "tabs", "selected", {"tab": "submit"}, human=True)  # 「提出」のタブの「提出」
    relay.input(workspace, "submit", "pressed", {}, human=True)
    relay.idle()
    window = next(w["id"] for w in relay.display.windows() if w["screen"] == "task-submit" and w.get("parent") == workspace)
    props = nodes(relay, window)["form"]["props"]
    assert {"fetch": True} in calls(relay, "status") and props["values"]["base_conflicts"] == ["src/app.py", "README.md"]
    warning = props["fields"][0]
    assert (warning["type"], warning["tone"], warning["list_from"]) == ("note", "bad", "base_conflicts") and "衝突するファイル" in warning["label"]
    # 提出の窓で「提出」を押したら、それが確認を兼ねる（もう一度は確かめない）
    decide(relay, window, title="ログイン画面", draft=True, reviewer="octocat", complete=False, partial=True, check=False)
    assert calls(relay, "task submit") == [{"title": "ログイン画面", "draft": True, "reviewer": "octocat", "partial": True, "complete": False, "check": False}]
    assert relay.backend.modules[-1] == PLACE and window not in [w["id"] for w in relay.display.windows()]


def test_upgrade_window_shows_the_files_it_would_change_before_running(relay):
    """最新の仕様にする：下見（module upgrade --dry-run）で、変えるファイルを先に見せる。下見は何も変えない。"""
    branches = opened(relay, "branches")
    relay.input(branches, "detail", "action", {"action": "upgrade", "name": "dev"}, human=True)
    relay.idle()
    window = next(w["id"] for w in relay.display.windows() if w["screen"] == "mod-upgrade" and w.get("parent") == branches)
    props = nodes(relay, window)["form"]["props"]
    assert relay.backend.plans == [("module upgrade", {"branch": "dev"})] and calls(relay, "module upgrade") == []
    assert props["subject"] == "dev" and props["values"]["paths"] == ["ecobuild.toml", ".ecobuild/README.md"] and props["values"]["latest_format"] == 5
    assert [field.get("list_from") for field in props["fields"]] == [None, None, "paths", "skipped"]
    decide(relay, window)
    assert calls(relay, "module upgrade") == [{"branch": "dev"}] and [w["id"] for w in relay.display.windows()] == [branches]


def test_a_preview_that_fails_is_shown_in_the_window(relay):
    relay.backend.preview = lambda name, args: {"ok": False, "error": {"code": "dirty", "message": "未コミットの変更があります。"}}
    window = opened(relay, "mod-upgrade", branch="")
    assert "未コミットの変更があります。" in nodes(relay, window)["form"]["props"]["error"]


def test_backend_reads_a_preview_as_the_json_of_dry_run():
    """下見は、人が打つ <コマンド> --dry-run --json の結果そのもの（確認に出す dry_run は人向けの文。こちらは部品が描く情報）。"""
    from eco_gui.backend import EcobuildBackend

    asked = []
    catalog = {"ok": True, "result": {"type": None, "commands": [
        {"name": "merge", "path": "branch merge", "summary": "取り込みます", "runnable": True, "effect": "human",
         "arguments": [{"param": "name", "type": "str", "required": True}],
         "options": [{"names": ["--into"], "param": "into", "type": "str"}, {"names": ["--dry-run"], "param": "dry_run", "flag": True, "type": "bool"},
                     {"names": ["--yes"], "param": "yes", "flag": True, "type": "bool"}]}]}}
    plan = {"ok": True, "command": "branch merge", "result": {"name": "dev", "into": "main", "method": "fast-forward", "commit_count": 2, "conflicts": []}}

    def ask(argv):
        asked.append(list(argv))
        return catalog if list(argv) == ["--help", "--json"] else plan

    backend = EcobuildBackend(["ecobuild"])
    backend.ask = ask
    assert backend.commands()["branch merge"]["dry_run"] is True
    assert backend.preview("branch merge", {"module": "C:/work/Calc", "name": "dev", "into": "main"}) == plan
    assert asked[-1] == ["-C", "C:/work/Calc", "branch", "merge", "--into", "main", "--dry-run", "--json", "--", "dev"]  # --yes は付けない（何も変えない）

    def broken(argv):
        from guiframework.backend import BackendError
        raise BackendError("ecobuild を起動できません")

    backend.ask = broken
    failed = backend.preview("branch merge", {"name": "dev", "into": "main"})
    assert failed["ok"] is False and "起動できません" in failed["error"]["message"]


# --- 衝突で止まったとき・削除・開き直す（前の GUI と同じ案内） ------------------------------------------

@pytest.mark.parametrize("screen, values, command, guide", [
    ("task-finish", {"complete": True}, "task finish", "task-conflict-fix"),     # 自分の提出：取り込んで直す
    ("task-complete", {}, "task finish", "task-conflict-fix"),
    ("task-apply", {"complete": True}, "task apply", "task-conflict-fix"),       # 反映も同じ（作成元の最新を取り込んで直す）
    ("task-approve", {"message": ""}, "task approve", "task-conflict-reject"),  # ほかの人の提出：差し戻す
])
def test_a_conflict_with_the_base_turns_the_window_into_the_guide(relay, screen, values, command, guide):
    relay.backend.conflicting = True
    board = opened(relay, "board")
    window = opened(relay, screen, inside=board, issue=12)
    decide(relay, window, **values)
    assert len(calls(relay, command)) == 1
    found = [w for w in relay.display.windows() if w.get("parent") == board]
    assert [w["screen"] for w in found] == [guide] and found[0]["id"] == window  # 同じ窓が、案内に替わる（失敗の知らせは出さない）
    assert [e for e in relay.display.events_after(0) if e["command"] == "notify" and e.get("level") == "error"] == []
    props = nodes(relay, window)["form"]["props"]
    assert "衝突" in props["intro"] and props["vars"]["issue"] == 12
    if guide == "task-conflict-fix":
        assert props["ok"] == "取り込んで直す" and props["vars"]["title"] == ("反映できません" if command == "task apply" else "取り込めません")
        decide(relay, window)  # タスクブランチの作業空間を開く（手元になければ GitHub から取り出す）
        assert calls(relay, "task start") == [{"issue": 12}]
        assert relay.display.tree(board)["screen"] == "frame-workspace" and relay.display.tree(board)["args"]["space"] == PLACE
    else:
        assert props["ok"] == "差し戻す" and "作成元の最新を取り込んで直して" in props["initial"]["message"]
        decide(relay, window, message="直してください")  # 入力の窓が確認を兼ねる
        assert calls(relay, "task reject") == [{"task": 12, "message": "直してください"}]
        assert [w["id"] for w in relay.display.windows()] == [board]


def test_delete_window_says_the_task_can_be_restored_and_warns_about_the_work(relay):
    board = opened(relay, "board")
    window = opened(relay, "task-delete", inside=board, issue=12)
    props = nodes(relay, window)["form"]["props"]
    assert props["title"] == "#{issue} を削除" and props["danger"] is True and "あとで「元に戻す」で戻せます" in props["intro"]
    assert [field["tone"] for field in props["fields"]] == ["bad", "bad"]  # タスクブランチ（手元か GitHub）があるときの赤い警告
    assert "作業は戻せません" in props["fields"][0]["label"]
    decide(relay, window)  # 入力の窓が確認を兼ねる
    assert calls(relay, "task close") == [{"issue": 12, "not_planned": True}] and [w["id"] for w in relay.display.windows()] == [board]


@pytest.mark.parametrize("stage", ["planned", "todo"])
def test_reopen_window_reopens_into_the_column_it_was_dropped_on(relay, stage):
    board = opened(relay, "board")
    window = opened(relay, "task-reopen", inside=board, issue=9, text=stage)
    props = nodes(relay, window)["form"]["props"]
    assert props["vars"] == {"issue": 9, "stage": stage} and props["ok"] == "開き直す"
    decide(relay, window)
    assert calls(relay, "task reopen") == [{"issue": 9, "stage": stage}]  # 開き直して、落とした列（計画中・未着手）に
