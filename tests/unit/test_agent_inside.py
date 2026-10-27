"""コンテナの中のエージェント（ecobuild_agent.inside・tokens）。docker は偽物（コンテナの状態を持つ）。"""

from pathlib import Path

import pytest

import ecobuild_bundle  # noqa: F401（コンテナの拡張に型と、エージェントが足すものをつなぐ）
import ecobuild_container as container
from ecobuild import config
from ecobuild.errors import WorkError
from ecobuild_agent import inside, tokens
from ecobuild_container import docker
from fake_docker import FakeDocker


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "My Calc"
    config.save(config.ModuleConfig.for_new_module("Calc", "generic"), path / config.FILE_NAME)
    return path


def test_agent_starts_inside_without_prompts(monkeypatch, root, tmp_path):
    import ecoagent
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    monkeypatch.setattr(container, "docker_command", lambda runner, command: ("docker",))
    monkeypatch.setattr(container.docker, "run", fake.run)
    monkeypatch.setattr(container, "credentials", lambda root=None: {"GH_TOKEN": "secret"})
    tokens.save_token("sk-ant-oat01-abc")
    started = []
    monkeypatch.setattr(ecoagent, "start", lambda directory, command, env=None: started.append((command, env))
                        or ecoagent.Session(1, tuple(command), Path(directory)))
    container.choose(root, True, fake.run)
    inside.start_agent(root, ("claude",), deny=("WebFetch",), agent_id="a-0123456789")
    written = next(args for args in fake.calls if args[1] == "exec")
    assert written[2:4] == ["--user", "0"] and inside.MANAGED_SETTINGS in written[-1]
    assert inside.write_settings(("WebFetch",)) == written[-1] and '"' not in written[-1]
    command, env = started[0]
    assert command[-2:] == ["claude", "--dangerously-skip-permissions"] and "--tty" in command
    assert env["GH_TOKEN"] == "secret" and "secret" not in command
    assert env[tokens.TOKEN_VARIABLE] == "sk-ant-oat01-abc" and "sk-ant-oat01-abc" not in command
    assert env[inside.status.AGENT_VARIABLE] == "a-0123456789"                           # 中のエージェントが自分の置き場所を知る
    assert command[command.index(inside.status.AGENT_VARIABLE) - 1] == "--env"
    assert "TERM=xterm-256color" in command and "COLORTERM=truecolor" in command          # Claude のオレンジが赤にならない
    assert any(args[-3:-1] == ["python3", "-c"] for args in fake.calls)                  # 初めての質問に先に答える


def test_the_microphone_reaches_the_container(monkeypatch, tmp_path):
    """Windows（WSL の docker）は WSLg の PulseAudio を、Linux はそのユーザーの PulseAudio を見せる。なければ何もしない。"""
    assert inside.sound(("wsl", "-d", "ECOBuild", "--exec", "docker"))[:2] == ("--volume", "/mnt/wslg:/mnt/wslg")
    assert "PULSE_SERVER=unix:/mnt/wslg/PulseServer" in inside.sound(("wsl",))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert inside.sound(("docker",)) == ()
    (tmp_path / "pulse").mkdir(); (tmp_path / "pulse" / "native").write_text("")
    assert "PULSE_SERVER=unix:/run/ecobuild-pulse/native" in inside.sound(("docker",))
    assert "sox libsox-fmt-pulse" in container.layer("ecobuild-env-calc:1")


def test_the_token_is_kept_without_spaces(monkeypatch, tmp_path):
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    assert tokens.load_token() == "" and not tokens.forget_token()
    tokens.save_token("  sk-ant-oat01-xyz\n")
    assert tokens.load_token() == "sk-ant-oat01-xyz"
    with pytest.raises(WorkError):
        tokens.save_token("sk-ant oat")
    assert tokens.forget_token() and tokens.load_token() == ""
    (tmp_path / "repo" / ".git").mkdir(parents=True)                       # リポジトリの中には置かない
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "repo" / "home"))
    with pytest.raises(WorkError) as raised:
        tokens.save_token("sk-ant-oat01-xyz")
    assert "リポジトリ" in raised.value.message and not tokens.token_path().exists()


def test_first_run_answers_are_added_without_changing_the_rest(tmp_path, monkeypatch):
    import json
    import subprocess
    import sys
    (tmp_path / ".claude.json").write_text(json.dumps({"numStartups": 3, "projects": {"/work": {"allowedTools": ["x"]}}}))
    (tmp_path / "settings.json").write_text(json.dumps({"theme": "light"}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    subprocess.run([sys.executable, "-c", inside.first_run_script(tmp_path / "plain")], check=True)   # 前からの clone：/work
    state = json.loads((tmp_path / ".claude.json").read_text())
    assert state["numStartups"] == 3 and state["hasCompletedOnboarding"] is True
    assert state["projects"]["/work"] == {"allowedTools": ["x"], "hasTrustDialogAccepted": True}
    assert json.loads((tmp_path / "settings.json").read_text()) == {"theme": "light", "skipDangerousModePermissionPrompt": True}


def test_the_token_is_caught_from_the_screen(monkeypatch, tmp_path):
    import ecoagent
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = "sk-ant-oat01-" + "Ab3_-" * 20
    ran = []
    monkeypatch.setattr(tokens.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(tokens.subprocess, "run", lambda args, **kw: ran.append(args))
    monkeypatch.setattr(ecoagent.console, "screen_text", lambda: f"Your OAuth token:\n\n{fake}\n\nStore this token securely.\n")
    assert tokens.capture_token() == fake and tokens.load_token() == fake
    assert ran == [["/bin/claude", "setup-token"]]
    monkeypatch.setattr(ecoagent.console, "screen_text", lambda: "Login failed\n")
    tokens.forget_token()
    assert tokens.capture_token() == "" and tokens.load_token() == ""
    assert tokens.find_token("old sk-ant-oat01-" + "a" * 30 + " new sk-ant-oat01-" + "b" * 30).endswith("b" * 30)


def test_conversations_inside_are_read_with_the_python_inside(monkeypatch, root, tmp_path):
    """中の会話は、ecoagent.history を中の python3 で動かして読む（前からの clone は今のブランチのものだけ）。
    止まっていれば読まない。"""
    import json
    import os
    import subprocess
    import sys
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    assert inside.agent_conversations(root, "task/1", runner=fake.run)[1].startswith("コンテナが動いていない")
    container.start(root, fake.run)
    folder = tmp_path / "agent" / "projects" / "-work"
    folder.mkdir(parents=True)
    for id, branch in (("a", "task/1"), ("b", "task/2")):
        (folder / f"{id}.jsonl").write_text(json.dumps({"type": "user", "message": {"content": "hi"}, "gitBranch": branch}) + "\n",
                                            encoding="utf-8")

    def run_inside(args):
        if args[1] == "exec" and "python3" in args and "-c" in args:
            script = args[args.index("-c") + 1]
            done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, encoding="utf-8",
                                  env={**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path / "agent")})
            return docker.Completed(tuple(args), done.returncode, done.stdout + done.stderr)
        return fake.run(args)

    found, note = inside.agent_conversations(root, "task/1", runner=run_inside)
    assert [c.id for c in found] == ["a"] and note == ""
    # 元の clone の worktree の作業空間：中の場所は作業空間ごとに違うので、ブランチで絞らない
    folder.rename(folder.with_name("-repo--ecobuild-w-1"))
    monkeypatch.setattr(container, "workdir", lambda root: "/repo/.ecobuild/w/1")
    found, _ = inside.agent_conversations(root, "task/1", runner=run_inside)
    assert sorted(c.id for c in found) == ["a", "b"]


def test_the_agent_is_added_to_the_container(monkeypatch, root, tmp_path):
    """エージェントがコンテナに足すもの：イメージに Claude Code、設定・会話の記録はコンテナごと、中でログインしたものは
    共有のボリューム、状態の置き場所。コンテナを消すと、そのコンテナだけのボリュームも消える（共有のものは残す）。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    text = container.layer("ecobuild-env-calc:123")
    assert "claude.ai/install.sh" in text and f"CLAUDE_CONFIG_DIR={inside.AGENT_HOME}" in text
    fake = FakeDocker(monkeypatch)
    container.choose(root, True, fake.run)
    container.start(root, fake.run)
    run = next(args for args in fake.calls if args[1] == "run")
    assert f"{inside.agent_volume(root)}:{inside.AGENT_HOME}" in run                    # 設定・会話の記録はコンテナごと
    assert f"{inside.AGENT_VOLUME}:{inside.SHARED_HOME}" in run                         # 中でログインしたものは共有
    assert inside.agent_volume(root).startswith(container.name(root) + "-")
    assert any(item.endswith(":" + inside.status.INSIDE) for item in run)               # 状態の置き場所（作業空間の分）
    assert any(container.name(root) in item and item.endswith(":" + inside.status.INSIDE) for item in run)
    container.remove(root, fake.run)
    removed = [args[-1] for args in fake.calls if args[1:3] == ["volume", "rm"]]
    assert inside.agent_volume(root) in removed and inside.AGENT_VOLUME not in removed


def test_the_claude_code_version_can_be_chosen(monkeypatch, root, tmp_path):
    """Claude Code の版：設定 agent_claude_version を install.sh に渡す（bash -s <版>）。空なら前と同じ文（イメージの名前が
    変わらない＝作り直さない）。版を変えるとイメージの名前が変わる。sh の文に入るので、版の形でない値は設定できない。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    empty = container.layer("ecobuild-env-calc:123")
    assert "\n && curl -fsSL https://claude.ai/install.sh | bash\n" in empty and " -s " not in empty
    assert inside.install_claude() == "curl -fsSL https://claude.ai/install.sh | bash"     # 空のときの文は変えない
    before = container.recipe(root).image
    ecobuild_bundle.set_config(inside.VERSION_KEY, "2.1.302")
    assert inside.claude_version() == "2.1.302"
    assert "\n && curl -fsSL https://claude.ai/install.sh | bash -s 2.1.302\n" in container.layer("ecobuild-env-calc:123")
    chosen = container.recipe(root).image
    assert chosen != before
    ecobuild_bundle.set_config(inside.VERSION_KEY, "stable")
    assert container.recipe(root).image not in (before, chosen)
    for wrong in ("2.1", "1; rm -rf /", "$(id)", "beta"):
        with pytest.raises(WorkError):
            ecobuild_bundle.set_config(inside.VERSION_KEY, wrong)
    ecobuild_bundle.set_config(inside.VERSION_KEY, None)
    assert container.layer("ecobuild-env-calc:123") == empty and container.recipe(root).image == before


def test_a_chosen_version_is_not_updated_inside(monkeypatch, root, tmp_path):
    """版を選んだら、中の Claude Code が自分で上げないように DISABLE_AUTOUPDATER を渡す（選んでいなければ渡さない）。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    fake = FakeDocker(monkeypatch)
    monkeypatch.setattr(container, "docker_command", lambda runner, command: ("docker",))
    monkeypatch.setattr(container.docker, "run", fake.run)
    monkeypatch.setattr(container, "credentials", lambda root=None: {})
    container.choose(root, True, fake.run)
    _, env = inside.agent_launch(root, ("claude",))
    assert inside.UPDATER_VARIABLE not in env
    ecobuild_bundle.set_config(inside.VERSION_KEY, "2.1.302")
    command, env = inside.agent_launch(root, ("claude",))
    assert env[inside.UPDATER_VARIABLE] == "1" and inside.UPDATER_VARIABLE in command


def test_the_versions_inside_and_to_choose(monkeypatch, root, tmp_path):
    """入っている版は動いているコンテナの claude --version、選べる版は npm の版の一覧（正式な版、新しい順）。"""
    import json
    from ecobuild_container import docker as _docker
    fake = FakeDocker(monkeypatch)
    assert inside.installed_version(root, fake.run)[1].startswith("コンテナが動いていない")
    fake.containers[container.name(root)] = ["running", "image", ""]
    original = fake.run
    def runner(args):
        if args[-2:] == ["claude", "--version"]:
            return _docker.Completed(tuple(args), 0, "2.1.302 (Claude Code)\n")
        return original(args)
    assert inside.installed_version(root, runner) == ("2.1.302", "")
    data = {"dist-tags": {"stable": "2.1.300", "latest": "2.1.310", "next": "2.1.311-beta.1"},
            "versions": {v: {} for v in ("2.1.9", "2.1.300", "2.1.310", "2.1.311-beta.1", "2.0.77")}}
    tags, versions, reason = inside.available_versions(3, fetch=lambda url: json.dumps(data).encode())
    assert tags == {"stable": "2.1.300", "latest": "2.1.310"} and versions == ("2.1.310", "2.1.300", "2.1.9") and not reason

    def offline(url):
        raise OSError("つながりません")
    assert inside.available_versions(fetch=offline)[:2] == ({}, ()) and "手で" in inside.available_versions(fetch=offline)[2]


def test_what_the_agent_may_not_use(monkeypatch, root, tmp_path):
    """使わせないもの：このPCの設定 agent_deny に、この作業空間だけのもの（ecobuild.local.toml）を足す。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path / "home"))
    assert inside.split_rules(" a ; ;b") == ("a", "b")
    assert inside.set_deny(root, ("WebFetch", "Bash(rm:*)")) and not inside.set_deny(root, ("WebFetch", "Bash(rm:*)"))
    assert inside.workspace_deny(root) == ("WebFetch", "Bash(rm:*)")
    ecobuild_bundle.set_config("agent_deny", "Bash(git push --force:*)")
    assert inside.deny(root) == ("Bash(git push --force:*)", "WebFetch", "Bash(rm:*)")
    assert inside.set_deny(root, ()) and inside.workspace_deny(root) == ()


def test_each_container_keeps_its_own_conversations(tmp_path, monkeypatch):
    """設定はコンテナごと：中でログインしたものは共有の場所を指す。前に共有していた会話は写さない（前の版の記録は読まない）。"""
    import json
    import os
    import subprocess
    import sys
    home, shared = tmp_path / "home", tmp_path / "shared"
    home.mkdir()
    old = shared / "projects" / "-work"
    old.mkdir(parents=True)
    (old / "mine.jsonl").write_text("{}\n", encoding="utf-8")
    script = inside.first_run_script(tmp_path / "work").replace(repr(inside.SHARED_HOME), repr(str(shared)))
    assert "roles.json" not in script
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    if done.returncode and "symlink" in done.stderr.lower() and os.name == "nt":
        pytest.skip("このPCではシンボリックリンクを作れない（Windows の権限）")
    assert done.returncode == 0, done.stderr
    assert not (home / "projects").exists()
    assert json.loads((home / ".claude.json").read_text())["projects"] == {"/work": {"hasTrustDialogAccepted": True}}
    link = home / ".credentials.json"
    assert os.path.islink(link) and os.readlink(link).endswith(os.path.join(str(shared), ".credentials.json"))
