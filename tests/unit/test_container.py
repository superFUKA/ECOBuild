"""作業空間のコンテナ（ecobuild_container）。docker は偽物（コンテナの状態を持つ）。"""

import base64
from pathlib import Path

import pytest

import ecobuild_bundle  # noqa: F401（コンテナの拡張に型をつなぐ）
import ecobuild_container as container
from ecobuild import config
from ecobuild.errors import WorkError
from ecobuild_container import ErrorCode, docker
from fake_docker import FakeDocker


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
    assert container.mount_path(Path(r"D:\Work\Calc"), ("wsl",), owned=True) == "/mnt/ecobuild/d/Work/Calc"


def test_the_workspace_is_mounted_as_the_inner_user_on_wsl():
    """WSL の /mnt/c は root の持ち物で中の一般ユーザーは chmod できない：ドライブを一般ユーザーの持ち物として付け直して使う。
    付けられなければ、いつもの場所。"""
    from ecobuild_container import docker
    prefix = ("wsl", "-d", "ECOBuild", "-u", "root", "--exec", "docker")
    ran = []

    def runner(ok):
        def run(args):
            ran.append(args)
            return docker.Completed(tuple(args), 0 if ok else 1, "")
        return run
    assert container.prepare_owned_mount(Path(r"C:\ECO\Calc"), runner(True), prefix) == "/mnt/ecobuild/c/ECO/Calc"
    assert ran[0][:6] == ["wsl", "-d", "ECOBuild", "-u", "root", "--exec"] and ran[0][6:8] == ["sh", "-c"]
    assert "mount -t drvfs C: /mnt/ecobuild/c -o uid=1000,gid=1000" in ran[0][8]
    assert container.prepare_owned_mount(Path(r"C:\ECO\Calc"), runner(False), prefix) == "/mnt/c/ECO/Calc"
    assert container.prepare_owned_mount(Path("/home/me/Calc"), runner(True), ("docker",)) == str(Path("/home/me/Calc"))


def test_type_tools_go_into_the_template():
    from ecobuild_bundle import REGISTRY
    cpp, generic = container.dockerfile(REGISTRY.load("cpp")), container.dockerfile(REGISTRY.load("generic"))
    assert "cmake ninja-build g++" in cpp and "g++" not in generic and generic.startswith("#") and "FROM ubuntu:24.04" in generic


def test_the_image_follows_the_module_recipe(monkeypatch, tmp_path):
    """イメージはモジュールごと：.ecobuild/container/ の中身（なければ型のひな型）で名前が決まり、変わると古い（outdated）と分かる。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    root = tmp_path / "Calc"
    config.save(config.ModuleConfig.for_new_module("Calc", "cpp"), root / config.FILE_NAME)
    source = ("https://example.com/ECOBuild", "abc")
    template = container.recipe(root, source)
    assert template.context is None and "cmake" in template.dockerfile and template.environment.startswith("ecobuild-env-calc:")
    folder = root / container.DIRECTORY
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
    assert shown.outdated and shown.image == started.image and shown.recipe == container.DOCKERFILE
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


def test_the_ecobuild_layer_and_what_other_extensions_add(monkeypatch, root, tmp_path):
    """コンテナはほかの拡張を知らない：足すもの（Feature）を受け取って、イメージ・コンテナに重ねる。"""
    monkeypatch.setattr(container, "_features", {})
    text = container.layer("ecobuild-env-calc:123")
    assert text.splitlines()[1] == "FROM ecobuild-env-calc:123" and "USER root" in text and "useradd" in text
    assert "gh auth git-credential" in text and f"{container.INSIDE}=1" in text and "claude" not in text
    container.use(ecobuild_bundle.REGISTRY, (container.Feature(
        "tool", packages=("jq",), environment=(("TOOL_HOME", "/opt/tool"),), install=("mkdir -p /opt/tool", "echo ok"),
        volumes=lambda root: (("tool-cache", "/opt/tool"), (tmp_path / "shared", "/opt/shared")),
        arguments=lambda prefix: ("--env", "TOOL=1")),))
    text = container.layer("ecobuild-env-calc:123")
    assert "python3-venv jq \\" in text and "ENV PATH=/home/ubuntu/.local/bin:$PATH TOOL_HOME=/opt/tool ECOBUILD_IN_CONTAINER=1" in text
    assert "RUN mkdir -p /opt/tool \\\n && echo ok\nRUN curl -LsSf https://astral.sh/uv" in text
    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    container.start(root, fake.run)
    run = next(args for args in fake.calls if args[1] == "run")
    assert "tool-cache:/opt/tool" in run and f"{tmp_path / 'shared'}:/opt/shared" in run and "TOOL=1" in run
    assert (tmp_path / "shared").is_dir()                                                  # このPCの場所は作って付ける


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
    set_ = container.configure(root, image="my/image:1", runner=fake.run)
    assert set_.changed and set_.custom_image == "my/image:1"
    assert not container.configure(root, image="my/image:1", runner=fake.run).changed
    assert container.configure(root, image="", runner=fake.run).custom_image == ""


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




def test_the_check_runs_inside_when_the_workspace_is_a_container(monkeypatch, root):
    """コンテナにした作業空間の確認（task submit の中のものも）は、中の ecobuild で行う（ビルド・テストに中のツールを使う）。"""
    import json

    class Host:
        def check(self, *, build=True, allow_dependency_mismatch=False):
            return "このPC"

    class Workspace(container.ContainerModule, Host):
        command = "ecobuild"

        def __init__(self, path):
            self.root = path

    ran = []

    def run_inside(path, args, **options):
        ran.append((args, options["cwd"], options["capture"]))
        if "--no-build" in args:
            return 1, json.dumps({"ok": False, "error": {"code": "check_failed", "message": "確認で問題が見つかりました：generated",
                                                         "hint": "直す", "details": [{"name": "generated", "ok": False}]}})
        return 0, "経過\n" + json.dumps({"ok": True, "result": {"items": [{"name": "build", "ok": True, "detail": "/work/x"}]}})

    monkeypatch.setattr(container, "run_inside", run_inside)
    workspace = Workspace(root)
    assert workspace.check() == "このPC" and not ran                                   # コンテナにしていなければこのPC
    container.choose(root, True, FakeDocker(monkeypatch).run)
    report = workspace.check(allow_dependency_mismatch=True)
    assert ran[0] == (["ecobuild", "check", "--json", "--allow-dependency-mismatch"], root, True)
    assert report.ok and report.items[0].detail == f"{root.as_posix()}/x"               # 中の場所はこのPCの場所に
    with pytest.raises(WorkError) as error:
        workspace.check(build=False)
    assert error.value.code == "check_failed" and error.value.details == [{"name": "generated", "ok": False}]
    monkeypatch.setenv(container.INSIDE, "1")
    assert workspace.check() == "このPC"                                                # 中ではそのまま


def test_line_endings_seen_from_this_pc_are_copied_into_the_clone(tmp_path, monkeypatch):
    """中の git は clone の設定しか読まない：このPCで効いている改行コードの設定（system・global）を clone に写す。
    clone にあれば変えない。"""
    import subprocess
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    globals_ = tmp_path / "gitconfig"
    globals_.write_text("[core]\n\tautocrlf = true\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(globals_))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    assert container.align_line_endings(repo) == ["core.autocrlf"]
    local = lambda: subprocess.run(["git", "-C", str(repo), "config", "--local", "--get", "core.autocrlf"],
                                   capture_output=True, text=True).stdout.strip()
    assert local() == "true"
    globals_.write_text("[core]\n\tautocrlf = input\n", encoding="utf-8")
    assert container.align_line_endings(repo) == [] and local() == "true"              # clone にあれば変えない
