"""作業空間のコンテナ（ecobuild_bundle.container）。docker は偽物（コンテナの状態を持つ）。"""

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
            return docker.Completed(tuple(args), 0, "\n".join(f"{i}\t420MB\t2 hours ago" for i in sorted(self.images)))
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
        elif command == "exec":
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
    assert started.built and started.image.startswith("ecobuild-generic:")                # 型のイメージを作った
    built = (tmp_path / "home/containers" / started.image.replace(":", "-") / "Dockerfile").read_text(encoding="utf-8")
    assert '"git+https://example.com/ECOBuild@abc123"' in built and "safe.directory /work" in built
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
    assert [args[1] for args in fake.calls].count("build") == 1

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


def test_type_tools_go_into_the_image():
    from ecobuild_bundle import REGISTRY
    cpp, generic = container.dockerfile(REGISTRY.load("cpp")), container.dockerfile(REGISTRY.load("generic"))
    assert "cmake ninja-build g++" in cpp and "g++" not in generic
    assert container.image_name(REGISTRY.load("cpp"), cpp) != container.image_name(REGISTRY.load("cpp"), cpp + "#")


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


def test_agent_starts_inside_without_prompts(monkeypatch, root, tmp_path):
    import ecoagent
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    monkeypatch.setattr(container, "_docker", lambda runner, command: ("docker",))
    monkeypatch.setattr(container.docker, "run", fake.run)
    monkeypatch.setattr(container, "credentials", lambda: {"GH_TOKEN": "secret"})
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


def test_the_dockerfile_has_the_agent():
    from ecobuild_bundle import REGISTRY
    text = container.dockerfile(REGISTRY.load("generic"))
    assert "claude.ai/install.sh" in text and f"CLAUDE_CONFIG_DIR={container.AGENT_HOME}" in text
    assert "gh auth git-credential" in text and f"{container.INSIDE}=1" in text


def test_images_are_per_type_and_old_ones_can_be_pruned(monkeypatch, root, tmp_path):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    old_source, source = ("https://example.com/ECOBuild", "old"), ("https://example.com/ECOBuild", "new")
    container.choose(root, True, fake.run)
    used = container.start(root, fake.run, source=old_source).image          # 古い版のイメージを使うコンテナ
    fake.images.add("ecobuild-cpp:000000000000")                            # 古い版で、どれも使っていない
    listed = container.images(source, fake.run)
    assert {i.name for i in listed.images} == {used, "ecobuild-cpp:000000000000"} and not any(i.current for i in listed.images)
    assert next(i for i in listed.images if i.name == used).used_by and set(listed.missing) == {"cpp", "generic", "python"}
    built = container.build_images(("generic",), source, fake.run)
    assert len(built.built) == 1 and built.missing and "generic" not in built.missing
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
