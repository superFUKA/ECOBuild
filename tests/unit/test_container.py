"""作業空間のコンテナ（ecobuild_bundle.container）。docker は偽物（コンテナの状態を持つ）。"""

from pathlib import Path

import pytest

from ecobuild import config
from ecobuild.errors import ErrorCode, WorkError
from ecobuild_bundle import container, docker


class FakeDocker:
    def __init__(self, monkeypatch, *, ready=True):
        self.ready, self.containers, self.calls = ready, {}, []
        monkeypatch.setattr(docker.shutil, "which", lambda name: name if name == "docker" else None)

    def run(self, args):
        self.calls.append(args)
        command, rest = args[1], args[2:]
        if command == "version":
            return docker.Completed(tuple(args), 0 if self.ready else 1, "29.1.3" if self.ready else "")
        if command == "inspect":
            state = self.containers.get(rest[-1])
            return docker.Completed(tuple(args), 0 if state else 1, state or "No such object")
        if command == "run":
            self.containers[rest[rest.index("--name") + 1]] = "running"
        elif command == "start":
            self.containers[rest[-1]] = "running"
        elif command == "stop":
            self.containers[rest[-1]] = "exited"
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


def test_container_lifecycle(monkeypatch, root):
    fake = FakeDocker(monkeypatch)
    assert code_of(lambda: container.start(root, fake.run)) == ErrorCode.CONTAINER_ERROR   # コンテナにしていない
    assert container.choose(root, True, fake.run).changed and container.enabled(root)
    assert container.show(root, fake.run).state == "none"

    started = container.start(root, fake.run)
    assert started.changed and started.state == "running" and started.name.startswith("ecobuild-my-calc-")
    run = next(args for args in fake.calls if args[1] == "run")
    assert f"{root}:/work" in run and "1000:1000" in run and run[-3:] == ["ubuntu:24.04", "sleep", "infinity"]
    assert not container.start(root, fake.run).changed                                    # 動いていれば何もしない

    assert container.stop(root, fake.run).state == "exited"
    assert container.start(root, fake.run).state == "running"
    assert ["docker", "start", started.name] in fake.calls                                # 止めたものは作り直さない

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
