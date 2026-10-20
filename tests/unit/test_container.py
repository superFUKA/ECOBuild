"""作業空間のコンテナ（ecobuild_bundle.container）。docker は偽物（コンテナの状態を持つ）。"""

import base64
from pathlib import Path

import pytest

from ecobuild import config
from ecobuild.errors import ErrorCode, WorkError
from ecobuild_bundle import container, docker


class FakeDocker:
    def __init__(self, monkeypatch, *, ready=True):
        self.ready, self.containers, self.images, self.calls = ready, {}, set(), []
        monkeypatch.setattr(docker.shutil, "which", lambda name: name if name == "docker" else None)

    def run(self, args):
        self.calls.append(args)
        command, rest = args[1], args[2:]
        if command == "version":
            return docker.Completed(tuple(args), 0 if self.ready else 1, "29.1.3" if self.ready else "")
        if command == "inspect":
            state = self.containers.get(rest[-1])
            return docker.Completed(tuple(args), 0 if state else 1, " ".join(state) if state else "No such object")
        if args[1:3] == ["image", "inspect"]:
            return docker.Completed(tuple(args), 0 if rest[-1] in self.images else 1, "")
        if args[1:3] == ["image", "ls"]:
            wanted = rest[1] if len(rest) > 1 and not rest[1].startswith("-") else ""   # 名前（リポジトリ）で絞る
            return docker.Completed(tuple(args), 0, "\n".join(f"{i}\t420MB\t2 hours ago" for i in sorted(self.images)
                                                               if not wanted or i.rsplit(":", 1)[0] == wanted))
        if args[1:3] == ["image", "rm"]:
            self.images.discard(rest[-1])
            return docker.Completed(tuple(args), 0, "")
        if command == "ps":
            return docker.Completed(tuple(args), 0, "\n".join(f"{c[1]}\tC:/ECO/{n}" for n, c in self.containers.items()))
        if command == "build":
            self.images.add(rest[rest.index("--tag") + 1])
        elif command == "run":
            labels = [rest[i + 1] for i, a in enumerate(rest) if a == "--label"]
            version = next((l.split("=", 1)[1] for l in labels if l.startswith(container.VERSION_LABEL + "=")), "")
            self.containers[rest[rest.index("--name") + 1]] = ["running", rest[-3], version]
        elif command in ("exec", "volume"):
            pass
        elif command == "start":
            self.containers[rest[-1]][0] = "running"
        elif command == "stop":
            self.containers[rest[-1]][0] = "exited"
        elif command == "rm":
            self.containers.pop(rest[-1])
        else:
            raise AssertionError(f"想定していないコマンド：{args}")
        return docker.Completed(tuple(args), 0, "")


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "My Calc"
    config.save(config.ModuleConfig.for_new_module("Calc", "generic"), path / config.FILE_NAME)
    return path


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_container_lifecycle(monkeypatch, root, tmp_path):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    assert code_of(lambda: container.start(root, fake.run)) == ErrorCode.CONTAINER_ERROR   # コンテナにしていない
    assert container.choose(root, True, fake.run).changed and container.enabled(root)
    assert container.show(root, fake.run).state == "none"

    started = container.start(root, fake.run, source=("https://example.com/ECOBuild", "abc123"))
    assert started.changed and started.state == "running" and started.name.startswith("ecobuild-my-calc-")
    assert started.built and started.image.startswith("ecobuild-calc:")                   # モジュールのイメージを作った
    built = (tmp_path / "home/containers" / started.image.replace(":", "-") / "Dockerfile").read_text(encoding="utf-8")
    assert '"git+https://example.com/ECOBuild@abc123"' in built and "safe.directory /work" in built
    assert built.startswith("# ECOBuild") and "FROM ecobuild-env-calc:" in built                # 環境の上に ECOBuild の層
    run = next(args for args in fake.calls if args[1] == "run")
    assert f"{root}:/work" in run and "1000:1000" in run and run[-3:] == [started.image, "sleep", "infinity"]
    assert f"{container.AGENT_VOLUME}:{container.AGENT_HOME}" in run                     # エージェントのログインは共有
    assert not container.start(root, fake.run).changed                                    # 動いていれば何もしない

    assert container.stop(root, fake.run).state == "exited"
    assert container.start(root, fake.run).state == "running"
    assert ["docker", "start", started.name] in fake.calls                                # 止めたものは作り直さない

    container.remove(root, fake.run)                                                      # 作り直しても、イメージは作り直さない
    again = container.start(root, fake.run, source=("https://example.com/ECOBuild", "abc123"))
    assert not again.built and again.image == started.image
    assert [args[1] for args in fake.calls].count("build") == 2                           # 環境と ECOBuild の層

    off = container.choose(root, False, fake.run)                                         # コンテナにしないならコンテナも消す
    assert off.changed and not off.container and off.state == "none" and not fake.containers
    assert "container" not in (root / config.LOCAL_FILE_NAME).read_text(encoding="utf-8")


def test_without_docker_choice_works_but_start_fails(monkeypatch, root):
    fake = FakeDocker(monkeypatch, ready=False)
    chosen = container.choose(root, True, fake.run)
    assert chosen.container and not chosen.docker_ready and chosen.state == "unknown"
    assert code_of(lambda: container.start(root, fake.run)) == ErrorCode.CONTAINER_ERROR
    assert not container.discard(root, fake.run)


def test_names_and_wsl_paths(tmp_path):
    assert container.name(tmp_path / "a") != container.name(tmp_path / "b" / "a")        # 同じフォルダ名でも別の名前
    assert container.mount_path(Path(r"C:\ECO\Calc 1"), ("wsl", "-d", "ECOBuild", "-u", "root", "--", "docker")) \
        == "/mnt/c/ECO/Calc 1"
    assert container.mount_path(Path("/home/me/Calc"), ("docker",)) == str(Path("/home/me/Calc"))


def test_type_tools_go_into_the_template():
    from ecobuild_bundle import REGISTRY
    cpp, generic = REGISTRY.load("cpp").container_dockerfile(), REGISTRY.load("generic").container_dockerfile()
    assert "cmake ninja-build g++" in cpp and "g++" not in generic and generic.startswith("#") and "FROM ubuntu:24.04" in generic


def test_the_image_follows_the_module_recipe(monkeypatch, tmp_path):
    """イメージはモジュールごと：.ecobuild/container/ の中身（なければ型のひな型）で名前が決まり、変わると古い（outdated）と分かる。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    root = tmp_path / "Calc"
    config.save(config.ModuleConfig.for_new_module("Calc", "cpp"), root / config.FILE_NAME)
    source = ("https://example.com/ECOBuild", "abc")
    template = container.recipe(root, source)
    assert template.context is None and "cmake" in template.dockerfile and template.environment.startswith("ecobuild-env-calc:")
    folder = root / config.CONTAINER_DIRECTORY
    folder.mkdir(parents=True)
    (folder / "Dockerfile").write_bytes(template.dockerfile.encode())
    same = container.recipe(root, source)
    assert same.context == folder and same.image == template.image                    # 中身が同じなら同じ名前
    (folder / "Dockerfile").write_bytes(template.dockerfile.replace("\n", "\r\n").encode())
    assert container.recipe(root, source).image == template.image                     # 改行の違いは同じ（端末によらない）
    (folder / "tool.cfg").write_text("x", encoding="utf-8")
    assert container.recipe(root, source).environment != template.environment          # フォルダーの中のファイルも材料
    newer = ("https://example.com/ECOBuild", "def")
    assert container.recipe(root, newer).environment == container.recipe(root, source).environment
    assert container.recipe(root, newer).image != container.recipe(root, source).image

    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    started = container.start(root, fake.run, source=source)
    environment_build = next(args for args in fake.calls if args[1] == "build")
    assert environment_build[-1] == str(folder)                                        # 環境は .ecobuild/container から作る
    assert not container.show(root, fake.run, source=source).outdated
    (folder / "Dockerfile").write_text(template.dockerfile + "RUN echo more\n", encoding="utf-8")   # リポジトリの更新で変わった
    shown = container.show(root, fake.run, source=source)
    assert shown.outdated and shown.image == started.image and shown.recipe == config.CONTAINER_DOCKERFILE
    assert not container.show(root, fake.run).outdated                                 # 入れ元を渡さなければ調べない
    again = container.start(root, fake.run, source=source)
    assert again.built and again.image == shown.wanted_image and not container.show(root, fake.run, source=source).outdated


def test_old_containers_are_made_again(monkeypatch, root, tmp_path):
    """古い形（VERSION）のコンテナや、ECOBuild を更新して違うイメージになったコンテナは作り直す。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    first = container.start(root, fake.run, source=("https://example.com/ECOBuild", "abc123"))
    fake.containers[first.name][2] = "1"
    again = container.start(root, fake.run, source=("https://example.com/ECOBuild", "abc123"))
    assert again.changed and fake.containers[first.name][2] == container.VERSION
    assert ["docker", "rm", "--force", first.name] in fake.calls
    newer = container.start(root, fake.run, source=("https://example.com/ECOBuild", "def456"))
    assert newer.built and newer.image != first.image


def test_running_inside_passes_the_keys_by_name(monkeypatch, tmp_path):
    root = tmp_path / "Calc"
    command = container.exec_command(root, ("wsl", "-d", "ECOBuild", "--", "docker"), ["ecobuild", "build"],
                                     ("GH_TOKEN",), directory="/work/src", tty=False)
    assert command[:6] == ["wsl", "-d", "ECOBuild", "--", "docker", "exec"]
    assert command[6:10] == ["--env", "GH_TOKEN", "--workdir", "/work/src"] and "secret" not in command
    monkeypatch.setenv("WSLENV", "USERPROFILE/p")
    env = container.environment(("wsl",), {"GH_TOKEN": "secret"})
    assert env["GH_TOKEN"] == "secret" and env["WSLENV"] == "USERPROFILE/p:GH_TOKEN"
    assert container.inside_path(root, root / "src" / "a") == "/work/src/a"
    assert container.inside_path(root, tmp_path) == "/work"


def test_a_terminal_inside_stops_what_it_started_when_it_ends(tmp_path):
    # docker exec は、こちらが終わっても中のプロセスを止めない：端末で動かすものは印を付け、包む sh が終わりに止める
    root = tmp_path / "Calc"
    command = container.exec_command(root, ("wsl", "-d", "ECOBuild", "--", "docker"), ["claude"], tty=True)
    assert command[:6] == ["wsl", "-d", "ECOBuild", "--", "sh", "-c"] and '"' not in command[6]
    tag, box = command[8], command[9]
    assert command[7] == "sh" and box == container.name(root)
    assert command[10:14] == ["docker", "exec", "--env", f"{container.EXEC_TAG}={tag}"] and command[-1] == "claude"
    encoded = command[6].split("echo ")[1].split(" |")[0]
    assert base64.b64decode(encoded).decode("utf-8") == container.STOP_WRAPPER
    other = container.exec_command(root, ("wsl", "-d", "ECOBuild", "--", "docker"), ["claude"], tty=True)
    assert other[8] != tag   # 起動ごとに別の印（閉じたタブの分だけを止める）


def test_agent_starts_inside_without_prompts(monkeypatch, root, tmp_path):
    import ecoagent
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    monkeypatch.setattr(container, "_docker", lambda runner, command: ("docker",))
    monkeypatch.setattr(container.docker, "run", fake.run)
    monkeypatch.setattr(container, "credentials", lambda root=None: {"GH_TOKEN": "secret"})
    container.save_token("sk-ant-oat01-abc")
    started = []
    monkeypatch.setattr(ecoagent, "start", lambda directory, command, env=None: started.append((command, env))
                        or ecoagent.Session(1, tuple(command), Path(directory)))
    container.choose(root, True, fake.run)
    container.start_agent(root, ("claude",), deny=("WebFetch",))
    written = next(args for args in fake.calls if args[1] == "exec")
    assert written[2:4] == ["--user", "0"] and container.MANAGED_SETTINGS in written[-1]
    assert container.write_settings(("WebFetch",)) == written[-1] and '"' not in written[-1]
    command, env = started[0]
    assert command[-2:] == ["claude", "--dangerously-skip-permissions"] and "--tty" in command
    assert env["GH_TOKEN"] == "secret" and "secret" not in command
    assert env[container.TOKEN_VARIABLE] == "sk-ant-oat01-abc" and "sk-ant-oat01-abc" not in command
    assert "TERM=xterm-256color" in command and "COLORTERM=truecolor" in command          # Claude のオレンジが赤にならない
    assert any(args[-3:-1] == ["python3", "-c"] for args in fake.calls)                  # 初めての質問に先に答える


def test_the_microphone_reaches_the_container(monkeypatch, tmp_path):
    """Windows（WSL の docker）は WSLg の PulseAudio を、Linux はそのユーザーの PulseAudio を見せる。なければ何もしない。"""
    assert container.sound(("wsl", "-d", "ECOBuild", "--exec", "docker"))[:2] == ["--volume", "/mnt/wslg:/mnt/wslg"]
    assert "PULSE_SERVER=unix:/mnt/wslg/PulseServer" in container.sound(("wsl",))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert container.sound(("docker",)) == []
    (tmp_path / "pulse").mkdir(); (tmp_path / "pulse" / "native").write_text("")
    assert "PULSE_SERVER=unix:/run/ecobuild-pulse/native" in container.sound(("docker",))
    assert "sox libsox-fmt-pulse" in container.layer("ecobuild-env-calc:1")


def test_the_ecobuild_layer_has_the_agent():
    text = container.layer("ecobuild-env-calc:123")
    assert text.splitlines()[1] == "FROM ecobuild-env-calc:123" and "USER root" in text and "useradd" in text
    assert "claude.ai/install.sh" in text and f"CLAUDE_CONFIG_DIR={container.AGENT_HOME}" in text
    assert "gh auth git-credential" in text and f"{container.INSIDE}=1" in text


def test_images_are_per_module_and_old_ones_can_be_pruned(monkeypatch, root, tmp_path):
    from ecobuild import workspaces
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    old_source, source = ("https://example.com/ECOBuild", "old"), ("https://example.com/ECOBuild", "new")
    workspaces.record(root)
    container.choose(root, True, fake.run)
    used = container.start(root, fake.run, source=old_source).image          # 古い版のイメージを使うコンテナ
    environment = container.recipe(root, source).environment                  # 環境は ECOBuild の版によらない
    fake.images.add("ecobuild-cpp:000000000000")                            # 以前の型ごとのイメージ。どれも使っていない
    listed = container.images(source, fake.run)
    assert {i.name for i in listed.images} == {used, environment, "ecobuild-cpp:000000000000"}
    assert [i.name for i in listed.images if i.current] == [environment]
    assert next(i for i in listed.images if i.name == environment).environment and listed.missing == (str(root),)
    mine = next(i for i in listed.images if i.name == used)
    assert mine.used_by and mine.module == "calc" and not mine.environment
    built = container.build_images((), source, fake.run)
    assert len(built.built) == 1 and not built.missing
    pruned = container.prune_images(source, fake.run)
    assert pruned.removed == ("ecobuild-cpp:000000000000",) and used in fake.images   # 使っているものは消さない
    assert not container.images(source, lambda args: docker.Completed(tuple(args), 1, "")).docker_ready


def test_settings_of_one_container(monkeypatch, root):
    fake = FakeDocker(monkeypatch)
    set_ = container.configure(root, deny=("WebFetch", "Bash(rm:*)"), image="my/image:1", runner=fake.run)
    assert set_.changed and set_.deny == ("WebFetch", "Bash(rm:*)") and set_.custom_image == "my/image:1"
    assert not container.configure(root, deny=("WebFetch", "Bash(rm:*)"), runner=fake.run).changed
    cleared = container.configure(root, deny=(), image="", runner=fake.run)
    assert cleared.deny == () and cleared.custom_image == ""
    assert container.split_rules(" a ; ;b") == ("a", "b")


def test_the_token_is_kept_without_spaces(monkeypatch, tmp_path):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    assert container.load_token() == "" and not container.forget_token()
    container.save_token("  sk-ant-oat01-xyz\n")
    assert container.load_token() == "sk-ant-oat01-xyz"
    with pytest.raises(WorkError):
        container.save_token("sk-ant oat")
    assert container.forget_token() and container.load_token() == ""
    (tmp_path / "repo" / ".git").mkdir(parents=True)                       # リポジトリの中には置かない
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "repo" / "home"))
    with pytest.raises(WorkError) as raised:
        container.save_token("sk-ant-oat01-xyz")
    assert "リポジトリ" in raised.value.message and not container.token_path().exists()


def test_first_run_answers_are_added_without_changing_the_rest(tmp_path, monkeypatch):
    import json
    import subprocess
    import sys
    (tmp_path / ".claude.json").write_text(json.dumps({"numStartups": 3, "projects": {"/work": {"allowedTools": ["x"]}}}))
    (tmp_path / "settings.json").write_text(json.dumps({"theme": "light"}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    subprocess.run([sys.executable, "-c", container.first_run_script()], check=True)
    state = json.loads((tmp_path / ".claude.json").read_text())
    assert state["numStartups"] == 3 and state["hasCompletedOnboarding"] is True
    assert state["projects"]["/work"] == {"allowedTools": ["x"], "hasTrustDialogAccepted": True}
    assert json.loads((tmp_path / "settings.json").read_text()) == {"theme": "light", "skipDangerousModePermissionPrompt": True}


def test_the_token_is_caught_from_the_screen(monkeypatch, tmp_path):
    import ecoagent
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = "sk-ant-oat01-" + "Ab3_-" * 20
    ran = []
    monkeypatch.setattr(container.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(container.subprocess, "run", lambda args, **kw: ran.append(args))
    monkeypatch.setattr(ecoagent.console, "screen_text", lambda: f"Your OAuth token:\n\n{fake}\n\nStore this token securely.\n")
    assert container.capture_token() == fake and container.load_token() == fake
    assert ran == [["/bin/claude", "setup-token"]]
    monkeypatch.setattr(ecoagent.console, "screen_text", lambda: "Login failed\n")
    container.forget_token()
    assert container.capture_token() == "" and container.load_token() == ""
    assert container.find_token("old sk-ant-oat01-" + "a" * 30 + " new sk-ant-oat01-" + "b" * 30).endswith("b" * 30)


def test_type_caches_live_in_the_container(monkeypatch, tmp_path):
    """型のキャッシュ（cpp の build）は作業空間ではなくコンテナの側のボリューム。中の一般ユーザーのものにし、コンテナと一緒に消す。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    root = tmp_path / "Calc"
    config.save(config.ModuleConfig.for_new_module("Calc", "cpp"), root / config.FILE_NAME)
    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    started = container.start(root, fake.run, source=("https://example.com/ECOBuild", "abc"))
    run = next(args for args in fake.calls if args[1] == "run")
    assert f"{started.name}-build:/work/build" in run
    assert any(args[1:4] == ["exec", "--user", "0"] and args[-2:] == ["1000:1000", "/work/build"] for args in fake.calls)
    container.remove(root, fake.run)
    assert ["docker", "volume", "rm", "--force", f"{started.name}-build"] in fake.calls
    generic = tmp_path / "Box"
    config.save(config.ModuleConfig.for_new_module("Box", "generic"), generic / config.FILE_NAME)
    assert container.caches(generic) == []


def test_old_images_are_removed_when_the_container_is_rebuilt(root, monkeypatch, tmp_path):
    """ECOBuild を更新するとイメージの名前が変わる。作り直したら、どのコンテナも使っていない前の版は消す（増え続けない）。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    container.start(root, fake.run, source=("https://example.com/ECOBuild", "v1"))
    old = next(i for i in fake.images if not i.startswith(container.ENVIRONMENT_PREFIX))
    fake.images.add("ecobuild-other:someother")        # 別のモジュールのイメージは消さない
    container.start(root, fake.run, source=("https://example.com/ECOBuild", "v2"))
    assert old not in fake.images and "ecobuild-other:someother" in fake.images and len(fake.images) == 3   # 環境は同じものを使う


def test_conversations_inside_are_read_with_the_python_inside(monkeypatch, root, tmp_path):
    """中の会話は、ecoagent.history を中の python3 で動かして読む（今のブランチのものだけ）。止まっていれば読まない。"""
    import json
    import os
    import subprocess
    import sys
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    assert container.agent_conversations(root, "task/1", runner=fake.run)[1].startswith("コンテナが動いていない")
    container.start(root, fake.run)
    folder = tmp_path / "agent" / "projects" / "-work"
    folder.mkdir(parents=True)
    for id, branch in (("a", "task/1"), ("b", "task/2")):
        (folder / f"{id}.jsonl").write_text(json.dumps({"type": "user", "message": {"content": "hi"}, "gitBranch": branch}) + "\n",
                                            encoding="utf-8")

    def inside(args):
        if args[1] == "exec" and "python3" in args and "-c" in args:
            script = args[args.index("-c") + 1]
            done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, encoding="utf-8",
                                  env={**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path / "agent")})
            return docker.Completed(tuple(args), done.returncode, done.stdout + done.stderr)
        return fake.run(args)

    found, note = container.agent_conversations(root, "task/1", runner=inside)
    assert [c.id for c in found] == ["a"] and note == ""
