"""eco_gui の入力の窓の描く所が1つであること（共有のコード lib.js の form）と、画面のつなぎの残り：
作業空間を同じ窓で開く・作業空間の「提出」で提出の窓・提出の窓の「入るコミット」「下書きを解除」・反映の文・後から届く候補。

ecobuild は呼ばない（偽のバックエンドで確かめる）。部品の JS は、ブラウザー（Chrome）があるときだけ、ページの中で動かして確かめる。
"""

import importlib
import inspect
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytest.importorskip("guiframework")

from guiframework import create_app  # noqa: E402
from test_eco_gui import answer, nodes  # noqa: E402
from test_eco_gui_forms import FakeForms, _spec, calls, opened  # noqa: E402

ECO_GUI = Path(__file__).resolve().parent.parent / "eco_gui"
PLACE = "C:/work/Calc/.ecobuild/w/12"  # タスクブランチの作業空間
FORM_PARTS = ("form", "task_form", "hub_add_form")


class FakeTidy(FakeForms):
    """提出に入るコミット（task status の commits）と、下書きの提出を返す、ecobuild の代わり。"""

    def _specs(self, text):
        return {**super()._specs(text), "module members": _spec("read")}

    def run(self, name, args, context, on_event):
        result = super().run(name, args, context, on_event)
        if name == "task status" and isinstance(result, dict) and result.get("ok"):
            result["result"]["commits"] = ["abc1234 ログイン画面を足す", "def5678 文言を直す"]
        return result


@pytest.fixture
def relay():
    eco_gui = importlib.import_module("eco_gui")
    app = create_app(eco_gui, backend=FakeTidy(), roles={"confirm": "confirm-box"})
    return app.relay(threaded=True)


def test_bindings_match_the_backend_commands(relay):
    relay.verify()


# --- 描く所は1つ ---------------------------------------------------------------------------------------
def test_the_form_is_drawn_in_one_place():
    """入力の窓を描くコードと見た目は lib.js の form だけ。部品 form・task-form・hub-add-form は、それを呼ぶ（自分の CSS・描くコードを持たない）。"""
    lib = (ECO_GUI / "lib.js").read_text(encoding="utf-8")
    assert "form: { render: formRender" in lib and "const FORM_CSS" in lib
    for name in FORM_PARTS:
        folder = ECO_GUI / "parts" / name
        code = (folder / "part.js").read_text(encoding="utf-8")
        assert "lib.form.render(" in code and not (folder / "part.css").exists(), name
        # 欄を描く要素（input・select・fieldset・form）を、自分では作らない
        assert not any(f"h('{tag}'" in code for tag in ("input", "select", "textarea", "fieldset", "form", "button")), name
    assert len((ECO_GUI / "parts" / "form" / "part.js").read_text(encoding="utf-8").splitlines()) < 10


# --- 作業空間を同じ窓で開く・作業空間の「提出」 -------------------------------------------------------------
def test_overview_opens_the_workspace_in_the_same_window(relay):
    window = opened(relay, "overview")
    relay.input(window, "open_here", "pressed", {}, human=True)  # 「この場所の作業空間を開く」
    relay.idle()
    tree = relay.display.tree(window)
    assert (tree["screen"], tree["args"]["module"], tree["args"]["space"]) == ("frame-workspace", "C:/work/Calc", "C:/work/Calc")
    assert [w["id"] for w in relay.display.windows()] == [window]  # 別の窓は開かない


@pytest.mark.parametrize("screen", ["tasks", "board", "schedule"])
def test_task_views_open_the_task_branch_in_the_same_window(relay, screen):
    module = importlib.import_module("eco_gui.screens.task_view").SCREEN
    row = next(row for row in module["bindings"] if row.get("on") == "view.workspace")
    assert row["open"] == "frame-workspace" and row["here"] is True and row["args"]["space"] == {"payload": "path"}
    window = opened(relay, screen)
    target = next(node["id"] for node in relay.display.tree(window)["nodes"] if node.get("part") in ("task-list", "board", "timeline"))
    relay.input(window, target, "workspace", {"path": PLACE}, human=True)
    relay.idle()
    tree = relay.display.tree(window)
    assert (tree["screen"], tree["args"]["module"], tree["args"]["space"]) == ("frame-workspace", "C:/work/Calc", PLACE)
    assert [w["id"] for w in relay.display.windows()] == [window]


def test_workspace_submit_opens_the_submit_window(relay):
    """作業空間の「提出」：すぐには提出せず、提出の窓（何が起きるか・題・下書き・見てもらう人・衝突の警告）を重ねて開く。"""
    workspace = opened(relay, "workspace", module=PLACE)
    relay.input(workspace, "tabs", "selected", {"tab": "submit"}, human=True)
    relay.input(workspace, "submit", "pressed", {}, human=True)
    relay.idle()
    window = next(w["id"] for w in relay.display.windows() if w["screen"] == "task-submit" and w.get("parent") == workspace)
    assert calls(relay, "task submit") == []
    props = nodes(relay, window)["form"]["props"]
    assert [row["label"] for row in props["outcome"]][:3] == ["PR", "PR", "取り込み"] and props["values"]["base_conflicts"] == ["src/app.py", "README.md"]


# --- 提出の窓・反映の窓の残り ------------------------------------------------------------------------------
def test_submit_window_lists_the_commits_and_makes_a_draft_ready(relay):
    window = opened(relay, "task-submit", module=PLACE)
    props = nodes(relay, window)["form"]["props"]
    commits = next(field for field in props["fields"] if field.get("list_as") == "commits")
    assert commits["list_from"] == "commits" and "{commits.length}件" in commits["label"] and "ありません" in commits["empty_text"]
    assert props["also"]["commits"] == ["abc1234 ログイン画面を足す", "def5678 文言を直す"]  # ecobuild task status（この作業空間のタスク）
    # 下書きの提出にだけ出る「下書きを解除」：ecobuild task submit --no-check
    assert props["actions"] == [{"name": "ready", "label": "下書きを解除", "hint": props["actions"][0]["hint"],
                                 "show_if": {"pull_request.state": "open", "pull_request.draft": True}}]
    assert props["values"]["pull_request"]["draft"] is True
    relay.input(window, "form", "action", {"name": "ready", "values": {"title": "打ちかけ"}}, human=True)
    assert answer(relay, window, True)["part"] == "confirm-box"
    relay.idle()
    assert calls(relay, "task submit") == [{"check": False}] and relay.backend.modules[-1] == PLACE
    assert window not in [w["id"] for w in relay.display.windows()]



def test_apply_window_says_the_open_submission_is_closed_and_lists_the_commits(relay):
    board = opened(relay, "board")
    window = opened(relay, "task-apply", inside=board, issue=12)
    props = nodes(relay, window)["form"]["props"]
    closing = next(row for row in props["outcome"] if row["label"] == "提出")
    assert closing == {"label": "提出", "text": "開いている提出は、取り込まずに閉じます", "show_if": {"pull_request.state": "open"}}
    assert {"label": "衝突したら", "text": "何もせずに止まります"} in props["outcome"]
    assert props["fields"][0]["list_as"] == "commits" and props["values"]["commits"][0].startswith("abc1234")


@pytest.mark.parametrize("screen", ["task-new", "task-assign"])
def test_assignee_candidates_include_the_members_read_from_github(relay, screen):
    """担当者の候補：GitHub のメンバー（ecobuild module members）も足す。遅い読みなので、ほかの窓の変更では読み直さない（lazy）。"""
    row = next(row for row in importlib.import_module(f"eco_gui.screens.{screen.replace('-', '_')}").SCREEN["bindings"] if row.get("read") == "module members")
    assert row["to"] == "form.members" and row["lazy"] is True
    tasks = opened(relay, "tasks")
    window = opened(relay, screen, inside=tasks, issue=12)
    assert nodes(relay, window)["form"]["props"]["members"] == relay.backend.members


# --- 部品の JS（ブラウザーがあるときだけ） -----------------------------------------------------------------
DRIVER = """
async ({part, props, steps}) => {
  const lib = (await import('/lib.js')).default;
  const mod = (await import('/parts/' + part + '/part.js')).default;
  const h = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) { if (key in node && key !== 'role') node[key] = value; else node.setAttribute(key, value); }
    node.append(...children);
    return node;
  };
  const root = document.createElement('div');
  document.body.replaceChildren(root);
  const emitted = [], state = {}, remembered = {};
  let now = props;
  const tools = { h, lib, state, emit: (name, payload) => emitted.push([name, payload]),
    memory: { get: (key, fallback = null) => (key in remembered ? remembered[key] : fallback), set: (key, value) => { remembered[key] = value; } },
    redraw: () => mod.render(root, now, tools) };
  mod.render(root, now, tools);
  const shown = (node) => { for (let at = node; at && at !== root; at = at.parentElement) if (at.hidden) return false; return true; };
  const field = (label) => {
    const box = [...root.querySelectorAll('label, fieldset')].filter(shown).find((node) => node.textContent.includes(label));
    if (!box) throw new Error('欄がありません：' + label);
    return box;
  };
  const out = {};
  for (const [what, a, b] of steps) {
    if (what === 'fill') { const input = field(a).querySelector('input, textarea'); input.value = b; input.dispatchEvent(new Event('input', { bubbles: true })); }
    else if (what === 'choose') { const select = field(a).querySelector('select'); select.value = b; select.dispatchEvent(new Event('change', { bubbles: true })); }
    else if (what === 'check') field(a).querySelector('input').click();
    else if (what === 'pick') [...field(a).querySelectorAll('label')].find((node) => node.textContent.includes(b)).querySelector('input').click();
    else if (what === 'press') [...root.querySelectorAll('button')].filter(shown).find((node) => node.textContent.includes(a)).click();
    else if (what === 'props') { now = { ...now, ...a }; mod.render(root, now, tools); }
    else if (what === 'value') out[b || a] = field(a).querySelector('input, textarea, select').value;
    else if (what === 'has') out[a] = [...root.querySelectorAll(a)].filter(shown).map((node) => node.textContent);
  }
  return { emitted, out, error: (root.querySelector('.error') || {}).textContent || '', styles: root.querySelectorAll('style').length,
    forms: root.querySelectorAll('form.eco-form').length,
    buttons: [...root.querySelectorAll('button')].filter(shown).map((node) => node.textContent) };
}
"""


@pytest.fixture(scope="module")
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except Exception as error:  # noqa: BLE001  ブラウザーがない所では、JS の試験を飛ばす
            pytest.skip(f"Chrome を起こせません：{error}")

        def serve(route):
            path = urlparse(route.request.url).path
            file = ECO_GUI / path.lstrip("/")
            if path == "/":
                route.fulfill(content_type="text/html", body="<!doctype html><meta charset='utf-8'><body></body>")
            elif file.suffix == ".js" and file.is_file() and ECO_GUI in file.resolve().parents:
                route.fulfill(content_type="text/javascript; charset=utf-8", body=file.read_text(encoding="utf-8"))
            else:
                route.fulfill(status=404, body="")

        tab = browser.new_page()
        tab.route("http://eco-gui.test/**", serve)
        tab.goto("http://eco-gui.test/")
        yield tab
        browser.close()


def sample(part, name):
    samples = importlib.import_module(f"eco_gui.parts.{part}.samples").SAMPLES
    return next(one["props"] for one in samples if one["name"].startswith(name))


def drive(page, part, props, *steps):
    spec = importlib.import_module(f"eco_gui.parts.{part}.part")
    defaults = {name: value.default for name, value in inspect.signature(spec.part).parameters.items()
                if value.default is not value.empty}  # 画面が渡さない要る情報は、宣言の既定値（本体と同じ）
    return page.evaluate(DRIVER, {"part": part, "props": {**defaults, **props}, "steps": [list(step) for step in steps]})


def test_js_new_task_builds_the_fields_and_emits_only_what_was_entered(page):
    props = sample("task_form", "新しいタスク")
    got = drive(page, "task_form", props, ("press", "作成"))
    assert got["error"] == "題名を入力してください。" and got["emitted"] == [] and (got["forms"], got["styles"]) == (1, 1)
    got = drive(page, "task_form", props, ("fill", "題名", "ログ を/残す"), ("check", "作成したら、作業空間を作って"),
                ("value", "タスクブランチの名前"), ("pick", "担当者", "hubot"), ("fill", "GitHubのアカウント", "mona, hubot"), ("press", "作成"))
    assert got["out"]["タスクブランチの名前"] == "ログ-を-残す"  # 手で変えるまで、題名に合わせる
    assert got["emitted"] == [["new", {"title": "ログ を/残す", "assignee": "hubot,mona", "parent": "12", "start": True, "name": "ログ-を-残す"}]]
    got = drive(page, "task_form", props, ("fill", "題名", "検索"), ("check", "作成したら、作業空間を作って"), ("fill", "タスクブランチの名前", "a b"), ("press", "作成"))
    assert "使えない文字" in got["error"] and got["emitted"] == []
    got = drive(page, "task_form", props, ("fill", "題名", "検索"), ("pick", "段階", "計画中"), ("choose", "優先度", "High"), ("fill", "見積もり", "2.5"), ("press", "作成"))
    assert got["emitted"] == [["new", {"title": "検索", "stage": "planned", "priority": "High", "estimate": "2.5", "parent": "12"}]]


def test_js_start_edit_and_assign_emit_the_same_payloads_as_before(page):
    start = sample("task_form", "作業を開始")
    got = drive(page, "task_form", start, ("press", "開始"))
    assert got["error"].startswith("hubot が担当しています") and got["emitted"] == []
    got = drive(page, "task_form", start, ("check", "から引き継ぐ"), ("check", "先に終わるべきタスクが開いていても始める"), ("choose", "作成元のブランチ", "dev"), ("press", "開始"))
    assert got["emitted"] == [["start", {"id": "13", "name": "ログを残す", "base": "dev", "ignore_blocked": True, "take_over": True}]]
    got = drive(page, "task_form", start, ("check", "から引き継ぐ"), ("pick", "作業の場所", "タスクブランチを作らない"), ("press", "開始"))
    assert got["emitted"] == [["start", {"id": "13", "no_branch": True, "take_over": True}]]
    waiting = drive(page, "task_form", sample("task_form", "読み込み中"))
    assert waiting["buttons"] == ["キャンセル"]  # タスクの状態が届くまで、決めるボタンは出さない

    edit = sample("task_form", "編集")
    got = drive(page, "task_form", edit, ("press", "保存"))
    assert got["error"] == "変更する内容がありません。" and got["emitted"] == []
    got = drive(page, "task_form", edit, ("fill", "題名", "新しい題"), ("choose", "親タスク", ""), ("fill", "先に終わるべきタスクを追加", "7,8"), ("press", "保存"))
    assert got["emitted"] == [["edit", {"id": "13", "title": "新しい題", "clear_parent": True, "add_blocked_by": "7,8"}]]
    got = drive(page, "task_form", edit, ("press", "キャンセル"))
    assert got["emitted"] == [["cancel", {}]]

    got = drive(page, "task_form", sample("task_form", "GitHub のメンバーが届いた"), ("has", "fieldset.checks label"), ("pick", "担当者", "mona"),
                ("fill", "候補にいない担当者", "a, b"), ("press", "追加"))
    assert got["out"]["fieldset.checks label"] == ["octocat（自分）", "mona"]  # 担当済みの hubot は出さない。mona は GitHub のメンバーから
    assert got["emitted"] == [["edit", {"id": "12", "add_assignee": "mona,a,b"}]]
    late = drive(page, "task_form", sample("task_form", "候補を読み込み中"), ("has", "fieldset.more"), ("press", "追加"))
    assert len(late["out"]["fieldset.more"]) == 1 and late["error"] == "担当者を選んでください。"  # 窓は待たせず、欄に「候補を読み込んでいます…」


def test_js_hub_add_form_emits_the_current_values_and_has_no_buttons_of_its_own(page):
    props = sample("hub_add_form", "ふつう")
    got = drive(page, "hub_add_form", props)
    first = {"method": "new", "directory": "C:/work", "name": "", "type": "cpp", "kind": "app", "project": "", "test": None, "description": "", "owner": "",
             "public": None, "repository": "", "folder": "", "adopt_folder": "", "adopt_type": "cpp"}
    assert got["emitted"] == [["changed", first]] and got["buttons"] == [] and (got["forms"], got["styles"]) == (1, 1)
    got = drive(page, "hub_add_form", props, ("fill", "モジュール名", "MathCore"), ("choose", "型", "python"), ("choose", "最初に作るもの", "library"),
                ("has", "label.check"), ("has", "div.intro"), ("check", "テスト（tests/）も作る"), ("fill", "保存先の親フォルダ", "D:/src/"))
    assert got["out"]["label.check"][0] == "テスト（tests/）も作る" and "作成先：C:/work/MathCore" in got["out"]["div.intro"]
    assert got["emitted"][-1][1] == {**first, "name": "MathCore", "type": "python", "kind": "library", "test": False, "directory": "D:/src"}
    got = drive(page, "hub_add_form", props, ("choose", "型", "generic"), ("pick", "追加方法", "GitHubから取得"), ("has", ".candidates button strong"),
                ("press", "acme/Calc"), ("value", "GitHubリポジトリ"), ("has", "div.intro"))
    assert got["out"][".candidates button strong"] == ["acme/Calc"]  # 登録済み（Game）・アーカイブ済み（Old）は出さない
    assert got["out"]["GitHubリポジトリ"] == "acme/Calc" and "作成先：C:/work/Calc" in got["out"]["div.intro"]
    assert got["emitted"][-1][1] == {**first, "method": "clone", "type": "generic", "kind": "", "repository": "acme/Calc"}
    waiting = drive(page, "hub_add_form", sample("hub_add_form", "型・候補を読み込み中"), ("pick", "追加方法", "GitHubから取得"), ("has", ".candidates p"))
    assert "読み込んでいます" in waiting["out"][".candidates p"][0]
    failed = drive(page, "hub_add_form", sample("hub_add_form", "実行できなかった"))
    assert failed["error"].startswith("GitHub に acme/Calc は既にあります。")


def test_js_form_shows_the_commits_the_draft_button_and_late_candidates(page):
    screen = importlib.import_module("eco_gui.screens.task_submit").SCREEN
    props = next(node["props"] for node in screen["nodes"] if node.get("part") == "form")
    status = {"task": 12, "base": "main", "base_conflicts": [], "pull_request": {"number": 13, "state": "open", "draft": True, "partial": False}}
    got = drive(page, "form", {**props, "values": status, "also": {"commits": ["abc1234 ログイン画面を足す", "def5678 文言を直す"]}},
                ("has", ".commits > div"), ("has", ".commits code"), ("fill", "題名", "打ちかけ"), ("press", "下書きを解除"))
    assert got["out"][".commits > div"] == ["提出に入るコミット（2件、新しい順）"] and got["out"][".commits code"] == ["abc1234", "def5678"]
    assert got["buttons"] == ["下書きを解除", "キャンセル", "提出"]
    assert got["emitted"] == [["action", {"name": "ready", "values": {"complete": True, "partial": False, "title": "打ちかけ", "draft": True, "reviewer": "", "check": True}}]]
    ready = drive(page, "form", {**props, "values": {**status, "pull_request": {**status["pull_request"], "draft": False}}, "also": {"commits": []}}, ("has", ".commits-none"))
    assert ready["buttons"] == ["キャンセル", "提出"] and ready["out"][".commits-none"] == ["提出に入るコミットはありません（作成元と同じです）。"]
    old = drive(page, "form", {**props, "values": status, "also": {}}, ("has", ".commits"), ("has", ".commits-none"))
    assert old["out"] == {".commits": [], ".commits-none": []}  # commits を返さない ecobuild：何も出さない

    # 後から届く候補：届くまで欄の下に知らせ、届いたら選べる（打った値は残る）
    fields = [{"name": "repository", "label": "リポジトリ", "suggestions_from": {"source": "rows", "value": "repository", "label": "repository", "note": "type"}},
              {"name": "branch", "label": "ブランチ", "type": "select", "none_label": "既定", "options_from": {"source": "more"}}]
    got = drive(page, "form", {"fields": fields, "loading": True}, ("has", "label.more"), ("fill", "リポジトリ", "acme/"),
                ("props", {"loading": False, "rows": [{"repository": "acme/Calc", "type": "cpp"}], "more": [{"name": "dev"}]}),
                ("has", "datalist option"), ("value", "リポジトリ"), ("choose", "ブランチ", "dev"), ("press", "OK"))
    assert len(got["out"]["label.more"]) == 2 and got["out"]["リポジトリ"] == "acme/"
    assert got["emitted"] == [["submitted", {"values": {"repository": "acme/", "branch": "dev"}}]]
