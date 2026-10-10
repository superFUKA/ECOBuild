"""GUIのサーバーの試験（ECOBuildの試験とは別。実行：python -m pytest gui/tests）。"""

import json
import os
import subprocess
import sys
import threading
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


def test_module_list_order_defaults_and_solution(tmp_path):
    store = gui.Store(tmp_path / "gui.json")
    a, b = _module(tmp_path / "A"), _module(tmp_path / "B")
    store.add_module(str(a)); store.add_module(str(b))
    store.order_modules([str(b), str(a)])
    assert [m["name"] for m in store.modules()] == ["B", "A"]

    write(a / "ecobuild.toml", '[branches]\ndefault_base = "develop"\n')
    assert gui.module_defaults(str(a)) == {"default_base": "develop"}
    assert gui.module_defaults(str(tmp_path)) == {}            # モジュールでなければ空

    assert gui.find_solution(str(a)) is None
    write(a / "build" / "1234" / "A.sln", "")
    assert gui.find_solution(str(a)).name == "A.sln"
    assert gui.open_in_visual_studio(str(b)) == {"solution": None}
