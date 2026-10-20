"""試験用の偽の docker（コンテナ・イメージの状態を持つ）。作業空間のコンテナ（ecobuild_container）の試験が使う。"""

import ecobuild_container as container
from ecobuild_container import docker


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
