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
            return docker.Completed(tuple(args), 0 if state else 1, f"{state[0]} {state[1]}" if state else "No such object")
        if args[1:3] == ["image", "inspect"]:
            return docker.Completed(tuple(args), 0 if rest[-1] in self.images else 1, "")
        if command == "build":
            self.images.add(rest[rest.index("--tag") + 1])
        elif command == "run":
            self.containers[rest[rest.index("--name") + 1]] = ["running", rest[-3]]
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
