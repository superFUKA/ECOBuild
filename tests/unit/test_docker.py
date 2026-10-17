"""このPCの準備：Docker の診断と導入（ecobuild_bundle.docker）。wsl・docker・sudo は偽物（決めた状態に答える）。"""

from ecobuild_bundle import docker, tooling


class Machine:
    """wsl・docker の状態を持ち、導入のコマンドでその状態を進める。"""

    def __init__(self, monkeypatch, *, windows=True, **state):
        self.windows = windows
        self.state = {"docker": False, "package": False, "wsl": False, "reboot": False, "distro": False, "engine": False,
                      "running": False, "permission": True, **state}
        self.calls, self.elevated = [], []
        monkeypatch.setattr(docker.shutil, "which",
                            lambda name: name if name == "wsl" and windows or name == "docker" and self.state["docker"]
                            else None)

    def run(self, args):
        self.calls.append(args)
        if args[0] == "powershell":                 # 管理者として（docker.elevated）
            self.elevated.append(args)
            program, rest = args[-1].split("-FilePath '", 1)[1].split("' -ArgumentList ", 1)
            args = [program, *(a.strip("'") for a in rest.split(" -Verb")[0].split(","))]
        s = self.state
        ok = True
        output = ""
        if args[:2] == ["docker", "version"]:
            ok, output = s["running"] and s["permission"], "27.5.1" if s["permission"] else "permission denied"
        elif args == ["wsl", "--version"]:
            ok = s["package"]
        elif args[:2] == ["winget", "install"] and "Microsoft.WSL" in args:
            s["package"] = True
        elif args == ["wsl", "--status"]:
            ok = s["wsl"]
        elif args == ["wsl", "--install", "--no-distribution"]:
            ok = s["package"]                       # 最初からある wsl.exe は --no-distribution を知らない
            s["wsl"] = ok and not s["reboot"]
        elif args == ["wsl", "--list", "--quiet"]:
            output = "Ubuntu\r\n" + ("ECOBuild\r\n" if s["distro"] else "")
        elif args[:3] == ["wsl", "--install", docker.IMAGE]:
            s["distro"] = True
        elif args[:5] == ["wsl", "-d", docker.DISTRO, "-u", "root"]:
            inner = args[6:]
            if inner[:2] == ["docker", "version"]:
                ok, output = s["running"], "27.5.1"
            elif "command -v docker" in inner[-1]:
                ok = s["engine"]
            elif "apt-get" in inner[-1]:
                s["engine"] = True
            elif "systemctl" in inner[-1]:
                s["running"] = True
        elif args[:3] == ["sudo", "sh", "-c"] and "apt-get" in args[3]:
            s["docker"] = True
        elif args[:3] == ["sudo", "sh", "-c"]:
            s["running"] = True
        elif args[:2] == ["sudo", "usermod"]:
            pass
        else:
            raise AssertionError(f"想定していないコマンド：{args}")
        return docker.Completed(tuple(args), 0 if ok else 1, output)


def test_windows_installs_wsl_distro_and_engine(monkeypatch):
    machine = Machine(monkeypatch)
    shown = []
    found = docker.install(machine.run, windows=True, progress=shown.append, command="ecobuild")
    assert found.ready and found.restart == "" and found.command == ("wsl", "-d", "ECOBuild", "-u", "root", "--", "docker")
    assert found.done == ("WSL 本体を導入しました", "WSL2 を有効にしました", "WSL に ECOBuild（Ubuntu-24.04）を作りました",
                          "WSL の ECOBuild に Docker（docker.io）を導入しました", "WSL の ECOBuild の Docker を起動しました")
    assert ["wsl", "--install", "Ubuntu-24.04", "--name", "ECOBuild", "--no-launch"] in machine.calls
    assert any("管理者の承認" in message for message in shown) and len(machine.elevated) == 2
    assert docker.install(machine.run, windows=True).done == ()            # 2回目は何もしない


def test_windows_stops_for_reboot_and_continues(monkeypatch):
    machine = Machine(monkeypatch, reboot=True)
    found = docker.install(machine.run, windows=True, command="ecobuild")
    assert not found.ready and "再起動" in found.restart and "ecobuild setup --docker" in found.restart
    assert found.done == ("WSL 本体を導入しました", "WSL2 を有効にしました") and not machine.state["distro"]
    machine.state.update(reboot=False, wsl=True)                           # 再起動した
    found = docker.install(machine.run, windows=True)
    assert found.ready and found.done[0] == "WSL に ECOBuild（Ubuntu-24.04）を作りました"


def test_windows_uses_existing_docker(monkeypatch):
    """Docker Desktop 等で docker が既に使えるなら、それを使う（WSL には触らない）。"""
    machine = Machine(monkeypatch, docker=True, running=True)
    found = docker.install(machine.run, windows=True)
    assert found.ready and found.command == ("docker",) and found.done == ()
    assert all(c[0] == "docker" for c in machine.calls)


def test_failed_step_is_reported(monkeypatch):
    machine = Machine(monkeypatch)
    original = machine.run
    machine.run = lambda args: (docker.Completed(tuple(args), 1, "ダウンロードできません")
                                if args[0] == "powershell" else original(args))
    found = docker.install(machine.run, windows=True)
    assert not found.ready and found.restart == "" and "失敗しました（終了コード 1）" in found.done[0]
    assert "ダウンロードできません" in found.done[0]


def test_linux_installs_and_asks_to_log_in_again(monkeypatch):
    machine = Machine(monkeypatch, windows=False, permission=False, running=True)
    monkeypatch.setenv("USER", "fuka")
    found = docker.install(machine.run, windows=False, command="ecobuild")
    assert machine.calls[0][:3] == ["sudo", "sh", "-c"] and "docker.io" in machine.calls[0][3]
    assert ["sudo", "usermod", "--append", "--groups", "docker", "fuka"] in machine.calls
    assert not found.ready and "ログインし直して" in found.restart
    machine.state["permission"] = True                                     # ログインし直した
    found = docker.install(machine.run, windows=False)
    assert found.ready and found.command == ("docker",) and found.done == ()


def test_status_without_anything(monkeypatch):
    assert docker.status(Machine(monkeypatch, windows=False).run, windows=False).stage == "no_docker"
    assert docker.status(Machine(monkeypatch).run, windows=True).stage == "no_wsl"
    machine = Machine(monkeypatch, package=True, wsl=True, distro=True)
    assert docker.status(machine.run, windows=True).stage == "no_engine"


def test_decode_utf16_from_wsl():
    assert docker._decode("WSL がありません\r\n".encode("utf-16-le")) == "WSL がありません\r\n"
    assert docker._decode("ok".encode("utf-8")) == "ok"


def test_doctor_item_is_optional(monkeypatch):
    machine = Machine(monkeypatch)
    monkeypatch.setattr(docker, "run", machine.run)
    item = docker.doctor_item(command="ecobuild")
    assert not item.ok and not item.required and item.fix == docker.FIX and "ecobuild setup --docker" in item.hint
    report = tooling.doctor()
    assert docker.NAME in {i.name for i in report.items}
    assert all(name != docker.NAME for name, _ in tooling.install_commands(report))   # setup --install では入れない


def test_setup_installs_docker_only_when_asked(monkeypatch):
    calls = []
    result = docker.DockerSetup(("WSL2 を有効にしました",), False, "PC を再起動してから", "WSL2 がありません")
    monkeypatch.setattr(tooling, "doctor", lambda types=(), extra=(), *, command="": tooling.DoctorReport(()))
    monkeypatch.setattr(tooling._docker, "install", lambda **options: calls.append(options) or result)
    assert tooling.setup().docker is None and calls == []
    report = tooling.setup(docker=True, command="ecobuild")
    assert report.docker == result and "WSL2 を有効にしました" in report.done and calls[0]["command"] == "ecobuild"
