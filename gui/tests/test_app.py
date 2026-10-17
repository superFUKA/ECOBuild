"""GUIのサーバーの試験（ECOBuildの試験とは別。実行：python -m pytest gui/tests）。"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as gui  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "GUI Test", "GIT_AUTHOR_EMAIL": "test@example.com",
           "GIT_COMMITTER_NAME": "GUI Test", "GIT_COMMITTER_EMAIL": "test@example.com"}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, **GIT_ENV}).stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _module(path):
    write(path / ".ecobuild" / "ecobuild.toml", "format = 1\n")
    return path


def test_gui_json_keeps_only_the_order(tmp_path):
    store = gui.Store(tmp_path / "home" / "gui.json")
    assert store.order() == []
    store.set_order(["C:\\work\\B", "C:/work/A"])
    assert store.order() == ["C:/work/B", "C:/work/A"]
    assert json.loads((tmp_path / "home" / "gui.json").read_text(encoding="utf-8")) == {"order": ["C:/work/B", "C:/work/A"]}


def test_older_gui_json_moves_to_the_clone_record(tmp_path):
    """以前の gui.json の一覧・専用のcloneは、ecobuild の作業空間の記録（workspace add）へ一度だけ移し、並びは残す。"""
    calc, gone, ws = _module(tmp_path / "Calc"), tmp_path / "Gone", _module(tmp_path / "Calc-7")
    (tmp_path / "gui.json").write_text(json.dumps({
        "modules": [{"path": calc.as_posix(), "name": "Calc"}, {"path": gone.as_posix()}],
        "workspaces": {calc.as_posix().lower(): [ws.as_posix()]}}), encoding="utf-8")
    calls = []

    class Recorder(gui.Cli):
        def run(self, directory, args, stdin=None):
            calls.append((directory, args))
            return {"ok": True}

    app = gui.App(Recorder(["ecobuild"]), gui.Store(tmp_path / "gui.json"), "t", 1)
    app.move_legacy()
    assert calls == [(None, ["workspace", "add", calc.as_posix()]),           # なくなったフォルダは入れない
                     (None, ["workspace", "add", ws.as_posix()])]
    assert json.loads((tmp_path / "gui.json").read_text(encoding="utf-8")) == {"order": [calc.as_posix(), gone.as_posix()]}
    calls.clear()
    app.move_legacy()
    assert calls == []


def test_list_files_uses_git_and_keeps_empty_folders(tmp_path):
    root = tmp_path / "work"
    git(tmp_path, "init", "--quiet", str(root))
    write(root / ".gitignore", "build/\n")
    write(root / "src" / "a.cpp", "a\n")
    write(root / "build" / "out.obj", "x\n")
    (root / "docs" / "empty").mkdir(parents=True)
    git(root, "add", "src/a.cpp", ".gitignore")
    git(root, "commit", "--quiet", "-m", "init")
    (root / "src" / "a.cpp").unlink()
    write(root / "new.txt", "n\n")

    listed = gui.list_files(str(root))
    assert listed["files"] == [".gitignore", "new.txt", "src/a.cpp"]
    assert listed["missing"] == ["src/a.cpp"]
    assert "build" not in listed["dirs"] and {"docs", "docs/empty", "src"} <= set(listed["dirs"])


def test_local_operations_stay_inside_the_place(tmp_path):
    assert gui.make_directory(str(tmp_path), "a/b") == {"path": "a/b"}
    assert gui.make_file(str(tmp_path), "a/b/c.txt") == {"path": "a/b/c.txt"}
    for bad in ("../x", "a/../../x"):
        with pytest.raises(gui.GuiError):
            gui.make_directory(str(tmp_path), bad)
    with pytest.raises(gui.GuiError):
        gui.make_file(str(tmp_path), "a/b/c.txt")      # 既にある
    assert gui.read_text(str(tmp_path), "a/b/c.txt")["text"] == ""

    # 型が file move・file remove を持たないとき（generic）の代わり
    assert gui.move_file(str(tmp_path), "a/b/c.txt", "d/c2.txt") == {"paths": ["d/c2.txt"]}
    assert not (tmp_path / "a/b/c.txt").exists() and (tmp_path / "d/c2.txt").is_file()
    gui.make_file(str(tmp_path), "e.txt")
    for source, destination in (("d/c2.txt", "e.txt"), ("d/c2.txt", "../x.txt"), ("nothing.txt", "y.txt")):
        with pytest.raises(gui.GuiError):
            gui.move_file(str(tmp_path), source, destination)
    assert gui.remove_file(str(tmp_path), "d/c2.txt") == {"paths": ["d/c2.txt"]}
    assert not (tmp_path / "d/c2.txt").exists()
    for bad in ("d/c2.txt", "d", "../x.txt"):
        with pytest.raises(gui.GuiError):
            gui.remove_file(str(tmp_path), bad)


def test_reads_are_cached_and_marked_stale_after_a_change(tmp_path):
    """読むだけのコマンドの結果を覚える（stale-while-revalidate）。変える操作の後は「古い」になる。起動し直しても残る。"""
    counter = tmp_path / "count.txt"
    script = ("import json, sys, pathlib; p = pathlib.Path(sys.argv[1]); n = int(p.read_text()) + 1 if p.exists() else 1; "
              "p.write_text(str(n)); print(json.dumps({'ok': True, 'result': n}))")
    store = gui.Store(tmp_path / "gui.json")
    app = gui.App(gui.Cli([sys.executable, "-c", script, str(counter)]), store, "t", 1)
    assert app.api("query", {"args": ["task", "list"], "mode": "cache"}) is None
    first = app.api("query", {"args": ["task", "list"], "mode": "fresh"})
    assert first["doc"]["result"] == 1
    kept = app.api("query", {"args": ["task", "list"], "mode": "cache"})
    assert kept["doc"]["result"] == 1 and not kept.get("stale")
    app.api("cli", {"args": ["task", "new", "x"]})                       # 変える操作
    assert app.api("query", {"args": ["task", "list"], "mode": "cache"})["stale"]
    assert app.api("query", {"args": ["task", "list"], "mode": "fresh"})["doc"]["result"] == 3
    again = gui.App(gui.Cli([sys.executable, "-c", script, str(counter)]), gui.Store(tmp_path / "gui.json"), "t", 1)
    assert again.api("query", {"args": ["task", "list"], "mode": "cache"})["doc"]["result"] == 3   # cache.json に残る
    with pytest.raises(gui.GuiError):
        app.api("query", {"args": ["task", "new", "x"], "mode": "fresh"})   # 変える操作は覚えない
    assert app.api("prefetch", {"queries": [["module", "show"], ["branch", "list"], ["build"]]}) == {"read": 2, "of": 2}


def test_the_same_read_at_the_same_time_runs_once(tmp_path):
    counter = tmp_path / "count.txt"
    script = ("import json, sys, time, pathlib; p = pathlib.Path(sys.argv[1]); "
              "p.write_text(p.read_text() + 'x' if p.exists() else 'x'); time.sleep(1); print(json.dumps({'ok': True, 'result': 1}))")
    app = gui.App(gui.Cli([sys.executable, "-c", script, str(counter)]), gui.Store(tmp_path / "gui.json"), "t", 1)
    threads = [threading.Thread(target=app.api, args=("query", {"args": ["task", "list"], "mode": "fresh"})) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert counter.read_text() == "x"


def test_dropped_files_are_copied_into_the_folder_without_overwriting(tmp_path):
    """エクスプローラーに落としたファイル・フォルダ（中身は base64）を、落とした先のフォルダに置く。"""
    import base64
    (tmp_path / "src").mkdir()
    encoded = lambda text: base64.b64encode(text.encode("utf-8")).decode("ascii")  # noqa: E731
    files = [{"path": "lib/a.h", "data": encoded("// a")}, {"path": "lib/sub/b.cpp", "data": encoded("// b")},
             {"path": "lib/empty"}]
    assert gui.import_files(str(tmp_path), "src", files) == {"files": ["src/lib/a.h", "src/lib/sub/b.cpp"]}
    assert (tmp_path / "src/lib/sub/b.cpp").read_text(encoding="utf-8") == "// b" and (tmp_path / "src/lib/empty").is_dir()
    with pytest.raises(gui.GuiError, match="src/lib/a.h"):        # 既にある：何も置かない
        gui.import_files(str(tmp_path), "src", [{"path": "lib/new.h", "data": encoded("x")}, files[0]])
    assert not (tmp_path / "src/lib/new.h").exists()
    with pytest.raises(gui.GuiError):                             # 場所の外には置かない
        gui.import_files(str(tmp_path), "", [{"path": "../outside.txt", "data": encoded("x")}])


def test_cli_returns_the_json_document_and_the_command_line(tmp_path):
    # ecobuild の代わりに、引数をそのままJSONで返すコマンドを使う
    script = "import json, sys; print('進捗', file=sys.stderr); print(json.dumps({'ok': True, 'result': sys.argv[1:]}))"
    cli = gui.Cli([sys.executable, "-c", script])
    document = cli.run(str(tmp_path), ["task", "list", "--all"])
    assert document["ok"] and document["result"] == ["-C", str(tmp_path), "task", "list", "--all", "--json"]
    assert document["exit_code"] == 0 and "進捗" in document["stderr"]
    broken = gui.Cli([sys.executable, "-c", "print('not json')"]).run(None, ["status"])
    assert not broken["ok"] and broken["error"]["code"] == "gui_no_output"


def test_cli_reports_progress_while_it_runs(tmp_path):
    """progress を渡すと、標準エラーの行（経過）が終わる前から読める。画面は progress で番号ごとに読みに来る。"""
    script = ("import json, sys, time; print('作成中…', file=sys.stderr, flush=True); time.sleep(1.5); "
              "print('push中…', file=sys.stderr); print(json.dumps({'ok': True, 'result': 1}))")
    app = gui.App(gui.Cli([sys.executable, "-c", script]), gui.Store(tmp_path / "gui.json"), "t", 1)
    done = {}
    worker = threading.Thread(target=lambda: done.update(app.api("cli", {"args": ["module", "new", "M"], "progress": "p1"})))
    worker.start()
    deadline = time.monotonic() + 10
    while not app.api("progress", {"id": "p1"})["lines"] and time.monotonic() < deadline:
        time.sleep(0.05)
    assert app.api("progress", {"id": "p1"})["lines"] == ["作成中…"] and not done
    worker.join()
    assert done["ok"] and "push中…" in done["stderr"]
    assert app.api("progress", {"id": "p1"}) == {"lines": []}      # 終わったら片付ける


def test_api_requires_the_token_and_the_local_host(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = server.server_address[1]
    app = gui.App(gui.Cli([sys.executable, "-c", "print('{}')"]), gui.Store(tmp_path / "gui.json"), "secret", port)
    server.RequestHandlerClass = gui.make_handler(app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def post(token, host=f"127.0.0.1:{port}"):
            request = urllib.request.Request(f"http://127.0.0.1:{port}/api/modules/order", data=b"{}", method="POST",
                                             headers={"X-ECOBuild-Token": token, "Host": host})
            try:
                with urllib.request.urlopen(request) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, None

        assert post("secret") == (200, {"value": []})
        assert post("wrong")[0] == 403
        assert post("secret", host="evil.example:80")[0] == 403
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            assert response.headers["Content-Type"].startswith("text/html") and b"ECOBuild" in response.read()
    finally:
        server.shutdown()
        server.server_close()


def test_ecobuild_is_found_on_path_first(tmp_path, monkeypatch):
    # インストール後は PATH の ecobuild を使う（どこから起動しても同じ）
    tool = tmp_path / ("ecobuild.exe" if os.name == "nt" else "ecobuild")
    tool.write_bytes(b"")
    tool.chmod(0o755)
    monkeypatch.delenv("ECOBUILD_GUI_CLI", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert gui.default_cli() == [str(tool)] or Path(gui.default_cli()[0]).resolve() == tool.resolve()
    assert gui.default_cli("C:/other/ecobuild.exe") == ["C:/other/ecobuild.exe"]


def test_warns_about_batch_wrappers():
    if os.name != "nt":
        pytest.skip("Windows だけ")
    assert gui.cli_warning(["C:/tools/ecobuild.cmd"]) and gui.cli_warning(["C:/tools/ecobuild.BAT"])
    assert gui.cli_warning(["C:/tools/ecobuild.exe"]) == ""


def test_server_does_not_share_a_port_in_use():
    first = gui.Server(("127.0.0.1", 0), None)
    try:
        with pytest.raises(OSError):
            gui.Server(("127.0.0.1", first.server_address[1]), None)
    finally:
        first.server_close()


def test_module_defaults_and_solution(tmp_path):
    a, b = _module(tmp_path / "A"), _module(tmp_path / "B")
    write(a / ".ecobuild" / "ecobuild.toml", '[branches]\ndefault_base = "develop"\n')
    assert gui.module_defaults(str(a)) == {"default_base": "develop"}
    write(a / ".ecobuild" / "ecobuild.toml", '[module]\nname = "A"\ntype = "python"\n[branches]\ndefault_base = "develop"\n')
    assert gui.module_defaults(str(a)) == {"type": "python", "default_base": "develop"}
    assert gui.module_defaults(str(tmp_path)) == {}            # モジュールでなければ空

    assert gui.find_solution(str(a)) is None
    write(a / "build" / "1234" / "A.sln", "")
    assert gui.find_solution(str(a)).name == "A.sln"
    write(a / "build" / "5678" / "A.slnx", "")                 # VS 2026 のジェネレーターが作るもの
    os.utime(a / "build" / "5678" / "A.slnx", (time.time() + 10,) * 2)
    assert gui.find_solution(str(a)).name == "A.slnx"
    assert gui.open_in_visual_studio(str(b)) == {"solution": None}


def test_stale_server_is_reported(monkeypatch, tmp_path):
    app = gui.App(gui.Cli(["ecobuild"]), gui.Store(tmp_path / "gui.json"), "t", 1)
    monkeypatch.setattr(gui, "who_am_i", lambda: "me")
    assert app.api("info", {})["stale"] == ""
    monkeypatch.setattr(gui, "STARTED_WITH", 0)              # 起動した後で app.py が変わった
    assert "切り替わります" in app.api("info", {})["stale"]
    with pytest.raises(gui.GuiError, match="切り替わります"):
        app.api("no-such-operation", {})


def test_ping_and_shutdown(tmp_path):
    app = gui.App(gui.Cli(["ecobuild"]), gui.Store(tmp_path / "gui.json"), "t", 1)
    assert app.api("ping", {})["pid"] == os.getpid()

    class FakeServer:
        stopped = threading.Event()

        def shutdown(self):
            self.stopped.set()
    app.server = FakeServer()
    app.api("shutdown", {})
    assert app.server.stopped.wait(2)


def test_open_window_only_for_gui_pages(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(gui, "open_window", opened.append)
    app = gui.App(gui.Cli(["ecobuild"]), gui.Store(tmp_path / "gui.json"), "tok", 8765)
    app.api("open-window", {"page": "module.html?path=C%3A%2FECO%2FCalc"})
    assert opened == ["http://127.0.0.1:8765/module.html?path=C%3A%2FECO%2FCalc&t=tok"]
    for bad in ("https://example.com/", "//evil/module.html?", "../app.py", "module.html"):
        with pytest.raises(gui.GuiError):
            app.api("open-window", {"page": bad})


def test_visual_studio_version_is_checked(tmp_path, monkeypatch):
    root = _module(tmp_path / "A")
    write(root / "build" / "x" / "A.sln", "")
    with pytest.raises(gui.GuiError, match="対応していない"):
        gui.open_in_visual_studio(str(root), "2019")
    monkeypatch.setattr(gui, "_visual_studio", lambda version: None)   # その版がないPC
    with pytest.raises(gui.GuiError, match="Visual Studio 2026 が見つかりません"):
        gui.open_in_visual_studio(str(root), "2026")


@pytest.mark.skipif(os.name != "nt", reason="ショートカットは Windows だけ")
def test_shortcut_has_the_icon(tmp_path):
    place = tmp_path / "デスクトップ"
    place.mkdir()
    made = gui.make_shortcuts([place, tmp_path / "ない"])
    assert made == [str(place / "ECOBuild GUI.lnk")]
    assert (Path(gui.__file__).with_name("icon.ico")).is_file()
    assert (gui.STATIC / "icon.svg").is_file()


def test_delete_runs_outside_the_clone_and_repository_name(tmp_path):
    root = tmp_path / "Calc"
    root.mkdir()
    assert gui._working_directory(str(root), ["module", "delete", "Calc", "--remove-workspaces"]) == str(tmp_path)
    assert gui._working_directory(str(root), ["status"]) == str(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for url, expected in (("https://github.com/owner/Calc.git", "owner/Calc"), ("git@github.com:owner/Calc", "owner/Calc"),
                          ("C:/fake/gh/Calc.git", "Calc")):
        subprocess.run(["git", "-C", str(root), "remote", "remove", "origin"], capture_output=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", url], check=True)
        assert gui.module_repository(str(root)) == expected


def test_commands_that_fetch_wait_for_the_others():
    assert gui._read_only(["status"]) and gui._read_only(["task", "list"]) and gui._read_only(["deps", "list", "--fetch"])
    # task next 等は読む前に git fetch して段階のずれを直す。status --fetch は origin も合わせる
    for args in (["status", "--fetch"], ["task", "next", "--count", "5"], ["task", "overdue"], ["task", "workload"],
                 ["sprint", "status"], ["milestone", "status"], ["build"]):
        assert not gui._read_only(args), args


def test_a_file_opens_in_the_visual_studio_that_has_the_solution(tmp_path, monkeypatch):
    """ソリューションを開いた Visual Studio があればそこで（/edit）、なければソリューションごと起動して開く。"""
    root = _module(tmp_path / "Calc")
    write(root / "src" / "Calc.cpp", "")
    write(root / "build" / "Calc.slnx", "")
    started = []
    monkeypatch.setattr(gui, "_visual_studio", lambda version: "devenv.exe")
    monkeypatch.setattr(gui.subprocess, "Popen", lambda args, **kw: started.append(args))
    titles = []

    class Done:
        def __init__(self):
            self.stdout = "\n".join(f'"devenv.exe","1","Console","1","1 K","Running","me","0:00:01","{t}"' for t in titles)

    monkeypatch.setattr(gui.subprocess, "run", lambda *a, **kw: Done())
    monkeypatch.setattr(gui.os, "name", "nt")
    waits = []
    monkeypatch.setattr(gui.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: waits.append(args)})())
    target = (root / "src" / "Calc.cpp").resolve()
    solution = (root / "build" / "Calc.slnx").resolve()
    assert gui.open_file_in_visual_studio(str(root), "src/Calc.cpp")["started"]
    assert started[-1][1:] == [str(solution)]                           # 起動にはファイルを渡さない（/command は使わない）
    assert waits[-1] == ("devenv.exe", solution, target)                 # ウィンドウが出てから /edit で開く
    assert not gui._edit_when_open("devenv.exe", solution, target, timeout=0)
    titles.append("Other - Microsoft Visual Studio")
    gui.open_file_in_visual_studio(str(root), "src/Calc.cpp")
    assert started[-1][1] != "/edit"                                     # 別のソリューションの Visual Studio では開かない
    titles.append("Calc - Microsoft Visual Studio")
    assert gui._edit_when_open("devenv.exe", solution, target)
    assert started[-1][1:] == ["/edit", str(target)]
    assert not gui.open_file_in_visual_studio(str(root), "src/Calc.cpp")["started"]
    assert started[-1][1:] == ["/edit", str(target)]
    with pytest.raises(gui.GuiError):
        gui.open_file_in_visual_studio(str(root), "../outside.cpp")


def test_generated_files_are_marked(tmp_path):
    """ツールが作り直すファイル（先頭に Generated by … Do not edit）は generated に入れる（エクスプローラーで隠す）。"""
    root = tmp_path / "work"
    git(tmp_path, "init", "--quiet", str(root))
    write(root / "Calc" / "CMakeLists.txt", "# Generated by CppBuild from .cppbuild/project.json. Do not edit: CppBuild rewrites this file.\n")
    write(root / "Calc" / "notes.txt", "Do not edit this list by hand\n")
    write(root / "Calc" / "src" / "Calc.cpp", "// Generated by hand. Do not edit.\n")
    assert gui.list_files(str(root))["generated"] == ["Calc/CMakeLists.txt"]
