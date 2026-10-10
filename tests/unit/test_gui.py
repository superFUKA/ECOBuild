import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from helpers import git, write
from ecobuild_gui import app as gui


def _module(path):
    write(path / "ecobuild.toml", "format = 1\n")
    return path


def test_store_registers_modules_and_dedicated_clones(tmp_path):
    store = gui.Store(tmp_path / "home" / "gui.json")
    root = _module(tmp_path / "Calc")
    added = store.add_module(str(root / "src"))      # 中の場所を指定してもモジュールの場所で登録する
    assert added["name"] == "Calc"
    store.add_module(str(root))                       # 同じ場所は重ねない
    assert [m["name"] for m in store.modules()] == ["Calc"] and store.modules()[0]["exists"]
    with pytest.raises(gui.GuiError):
        store.add_module(str(tmp_path))               # ecobuild.toml がなければ断る

    clone = _module(tmp_path / "Calc-7")
    (clone / ".git").mkdir()
    assert store.add_workspace(str(root), str(clone)) == [clone.resolve().as_posix()]
    assert store.add_workspace(str(root), str(root)) == [clone.resolve().as_posix()]   # 元のcloneは足さない
    assert store.remove_workspace(str(root), str(clone)) == []
    store.remove_module(str(root))
    assert store.modules() == []


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


def test_cli_returns_the_json_document_and_the_command_line(tmp_path):
    # ecobuild の代わりに、引数をそのままJSONで返すコマンドを使う
    script = "import json, sys; print('進捗', file=sys.stderr); print(json.dumps({'ok': True, 'result': sys.argv[1:]}))"
    cli = gui.Cli([sys.executable, "-c", script])
    document = cli.run(str(tmp_path), ["task", "list", "--all"])
    assert document["ok"] and document["result"] == ["-C", str(tmp_path), "task", "list", "--all", "--json"]
    assert document["exit_code"] == 0 and "進捗" in document["stderr"]
    broken = gui.Cli([sys.executable, "-c", "print('not json')"]).run(None, ["status"])
    assert not broken["ok"] and broken["error"]["code"] == "gui_no_output"


def test_api_requires_the_token_and_the_local_host(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = server.server_address[1]
    app = gui.App(gui.Cli([sys.executable, "-c", "print('{}')"]), gui.Store(tmp_path / "gui.json"), "secret", port)
    server.RequestHandlerClass = gui.make_handler(app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def post(token, host=f"127.0.0.1:{port}"):
            request = urllib.request.Request(f"http://127.0.0.1:{port}/api/modules", data=b"{}", method="POST",
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
