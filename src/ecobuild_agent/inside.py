"""コンテナの中のエージェント（Claude Code）：作業空間のコンテナ（ecobuild_container）の公開の口を使う。コンテナはこれを知らない。

コンテナに足すもの（FEATURE）：イメージに Claude Code と音声入力の道具を入れ、ログインはすべてのコンテナで共有するボリューム
（AGENT_VOLUME）に残す（中の CLAUDE_CONFIG_DIR。このPCの ~/.claude は見せない）。状態の置き場所（status）とマイクも付ける。
中は隔離されているので確認なしで動かし、使わせない道具・コマンドだけを managed-settings の deny に書く（ダメなものだけを列挙する）。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

import ecobuild_container as container
from ecobuild import config as _config
from ecobuild import settings as _settings
from ecobuild_container import docker

from . import status, team, tokens
from .errors import from_ecoagent

AGENT_HOME = f"{container.HOME}/.claude"  # 中のエージェントの設定・会話の記録・記憶（CLAUDE_CONFIG_DIR。コンテナごと）
AGENT_VOLUME = "ecobuild-agent"           # すべてのコンテナで共有するボリューム：中でログインしたもの（SHARED_HOME に付ける）
SHARED_HOME = f"{container.HOME}/.ecobuild-agent-shared"
CREDENTIALS = ".credentials.json"         # 中でログインしたもの（AGENT_HOME から SHARED_HOME のものを指す：ログインは1回）


def agent_volume(root: Path) -> str:
    """作業空間のコンテナのエージェントの設定・会話の記録・記憶のボリューム（コンテナごと。作業役どうし・進行役と
    混ざらない。名前がコンテナの名前で始まるので、コンテナを消すと一緒に消える）。"""
    return f"{container.name(root)}-agent"
MANAGED_SETTINGS = "/etc/claude-code/managed-settings.json"
AGENT_FLAGS = {"claude": ("--dangerously-skip-permissions",)}   # 中で確認なしに動かすときに足すもの
DENY_KEY = "agent_deny"   # このPCの設定（config）と ecobuild.local.toml（この作業空間だけ。このPCの設定に足す）：使わせないもの
# 中のエージェントの初めての質問に先に答えておく（足りないものだけ足す）。.claude.json：初めての案内・/work の信頼。
# settings.json：テーマ・確認なしのモードの注意（コンテナなので出さない）
FIRST_RUN = {
    ".claude.json": {"hasCompletedOnboarding": True, "projects": {container.WORKDIR: {"hasTrustDialogAccepted": True}}},
    "settings.json": {"theme": "dark", "skipDangerousModePermissionPrompt": True},
}


def sound(prefix: tuple[str, ...]) -> tuple[str, ...]:
    """コンテナの中で、このPCのマイク（と音）を使う docker run の引数（Claude Code の音声入力）。Windows：WSL の WSLg の
    PulseAudio（/mnt/wslg/PulseServer。Windows のマイクが RDPSource として見える）。Linux：そのユーザーの PulseAudio
    （PipeWire の互換も同じ）。どちらも見つからなければ何も足さない（音声入力が使えないだけ）。"""
    if prefix[:1] == ("wsl",):
        return ("--volume", "/mnt/wslg:/mnt/wslg", "--env", "PULSE_SERVER=unix:/mnt/wslg/PulseServer",
                "--env", "AUDIODRIVER=pulseaudio")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and (Path(runtime) / "pulse" / "native").exists():
        return ("--volume", f"{Path(runtime) / 'pulse'}:/run/ecobuild-pulse", "--env",
                "PULSE_SERVER=unix:/run/ecobuild-pulse/native", "--env", "AUDIODRIVER=pulseaudio")
    return ()


FEATURE = container.Feature(
    "agent",
    packages=("sox", "libsox-fmt-pulse"),   # 音声入力（PulseAudio で録音する。sound を見る）
    environment=(("CLAUDE_CONFIG_DIR", AGENT_HOME),),
    install=(f"mkdir -p {AGENT_HOME} {SHARED_HOME}",     # ボリュームの持ち主を ubuntu に（初めて付けたときに写る）
             "curl -fsSL https://claude.ai/install.sh | bash"),
    # 設定・会話の記録・記憶（コンテナごと）、中でログインしたもの（共有）、中のエージェントが状態を書き出す所（このPCの画面が読む）
    volumes=lambda root: ((agent_volume(root), AGENT_HOME), (AGENT_VOLUME, SHARED_HOME),
                          (status.directory(container.name(root)), status.INSIDE)),
    arguments=sound,
)


# 使わせないもの ------------------------------------------------------------------------------------

def split_rules(text: str) -> tuple[str, ...]:
    """「;」で区切った許可の規則。"""
    return tuple(rule.strip() for rule in text.split(";") if rule.strip())


def workspace_deny(root: Path) -> tuple[str, ...]:
    """この作業空間だけの、使わせないもの（ecobuild.local.toml）。"""
    return split_rules(_config.load_local(root).get(DENY_KEY) or "")


def deny(root: Path) -> tuple[str, ...]:
    """中のエージェントに使わせないもの：このPCの設定 agent_deny と、この作業空間だけのもの。"""
    return (*split_rules(_settings.load_config().get(DENY_KEY, "")), *workspace_deny(root))


def set_deny(root: Path, rules: tuple[str, ...]) -> bool:
    """この作業空間だけの、使わせないもの（() で消す）。変えたら True。"""
    local = _config.load_local(root)
    before = local.get(DENY_KEY)
    local[DENY_KEY] = ";".join(rules) or None
    if local.get(DENY_KEY) == before:
        return False
    _config.save_local(root, local)
    return True


def agent_settings(rules: tuple[str, ...]) -> str:
    """中のエージェントの managed-settings（使わせないものだけ）。"""
    return json.dumps({"permissions": {"deny": list(rules)}}, ensure_ascii=False)


def write_settings(rules: tuple[str, ...]) -> str:
    """managed-settings を書く sh のスクリプト。中身は base64 で渡す（WSL を通すと引数の " が崩れる）。"""
    encoded = base64.b64encode(agent_settings(rules).encode("utf-8")).decode("ascii")
    folder = MANAGED_SETTINGS.rsplit("/", 1)[0]
    return f"mkdir -p {folder} && echo {encoded} | base64 -d > {MANAGED_SETTINGS}"


# 起動 ----------------------------------------------------------------------------------------------

def start_agent(root: Path, agent: tuple[str, ...], *, deny: tuple[str, ...] = (), command: str = "",
                source: tuple[str, str] | None = None, progress: Callable[[str], None] = lambda message: None,
                here: bool = False):
    """コンテナの中でエージェントを起動する（確認なし。deny に書いたものだけ使わせない）。新しい画面で起動して
    Session を返す。here なら、この端末で動かして終わるまで待ち、終了コードを返す。"""
    import ecoagent
    argv, env = agent_launch(root, agent, deny=deny, command=command, source=source, progress=progress,
                             tty=sys.stdin.isatty() if here else True)
    try:
        if here:
            return subprocess.run(argv, env=env).returncode
        return ecoagent.start(root, argv, env=env)
    except ecoagent.AgentError as error:
        raise from_ecoagent(error) from error
    except KeyboardInterrupt:
        return 130


def agent_launch(root: Path, agent: tuple[str, ...], *, deny: tuple[str, ...] = (), command: str = "",
                 source: tuple[str, str] | None = None,
                 progress: Callable[[str], None] = lambda message: None,
                 tty: bool = True) -> tuple[list[str], dict[str, str]]:
    """コンテナを用意し（動かす・設定を書く）、中のエージェントを動かすコマンドと環境を返す。tty：端末として動かす。"""
    container.start(root, command=command, source=source, progress=progress)
    prefix = container.docker_command(None, command)
    container.run_docker(None, [*prefix, "exec", "--user", "0", container.name(root), "sh", "-c", write_settings(deny)],
                         "エージェントの設定を書けませんでした")
    container.run_docker(None, [*prefix, "exec", container.name(root), "python3", "-c", first_run_script()],
                         "エージェントの初めての設定を書けませんでした")
    if agent:
        agent = (*agent, *(flag for flag in AGENT_FLAGS.get(agent[0], ()) if flag not in agent))
    values = container.credentials(root)
    if token := tokens.load_token():
        values[tokens.TOKEN_VARIABLE] = token
    return (container.exec_command(root, prefix, agent, tuple(values), tty=tty),
            container.environment(prefix, values))


def agent_conversations(root: Path, branch: str, limit: int = 20, runner: docker.Runner | None = None, *,
                        command: str = "") -> tuple[tuple, str]:
    """中のエージェントの会話（ecoagent.history を中の Python で動かす。中の ECOBuild の版によらない）と、読めなかった
    わけ。中の場所（WORKDIR）はどのコンテナも同じなので、branch での会話だけ。"""
    import ecoagent
    from ecoagent import history
    found = docker.status(runner or docker.run)
    if not found.ready:
        return (), f"Docker が使えません（{found.detail}）。"
    if container.container_state(root, runner, found.command) != "running":
        return (), "コンテナが動いていないので、会話の一覧を読めません（エージェントを起動すると読めます）。"
    source = base64.b64encode(Path(history.__file__).read_bytes()).decode("ascii")
    script = f"import base64,sys;sys.argv[1:]={[container.WORKDIR, branch, str(limit)]!r};exec(base64.b64decode('{source}'))"
    done = (runner or docker.run)([*found.command, "exec", container.name(root), "python3", "-c", script])
    try:
        return tuple(ecoagent.Conversation(**c) for c in json.loads(done.output)) if done.ok else (), ""
    except (ValueError, TypeError):
        return (), "会話の一覧を読めませんでした。"


def first_run_script() -> str:
    """中のエージェントの設定（AGENT_HOME）に FIRST_RUN を足す python3 のスクリプト（ある値は変えない）。
    中身は base64 で渡す（WSL を通しても崩れないように）。あわせて：
    - 中でログインしたもの（CREDENTIALS）は共有の場所（SHARED_HOME）を指す（ログインは1回。トークンを覚えていれば使わない）。
    - 前は設定を全コンテナで共有していた：この作業空間の会話（ROLES_FILE に覚えた会話）を共有の場所から写す（続きから
      再開できるように。写すのは初めの1回）。"""
    encoded = base64.b64encode(json.dumps(FIRST_RUN).encode()).decode("ascii")
    roles = f"{container.WORKDIR}/{team.ROLES_FILE}"
    project = "-" + container.WORKDIR.strip("/").replace("/", "-")   # Claude Code の会話の置き場所の名前（/work → -work）
    return ("import base64,json,os,shutil\n"
            f"want=json.loads(base64.b64decode('{encoded}'))\n"
            "def merge(have,add):\n"
            " for k,v in add.items():\n"
            "  if isinstance(v,dict) and isinstance(have.get(k),dict): merge(have[k],v)\n"
            "  elif k not in have: have[k]=v\n"
            "home=os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')\n"
            "for name,add in want.items():\n"
            " path=os.path.join(home,name)\n"
            " try: have=json.load(open(path))\n"
            " except Exception: have={}\n"
            " merge(have,add)\n"
            " tmp=path+'.ecobuild'\n"
            " json.dump(have,open(tmp,'w'),indent=2)\n"
            " os.chmod(tmp,0o600); os.replace(tmp,path)\n"
            f"shared={SHARED_HOME!r}\n"
            f"link=os.path.join(home,{CREDENTIALS!r})\n"
            "if os.path.isdir(shared) and not os.path.lexists(link):\n"
            f" os.symlink(os.path.join(shared,{CREDENTIALS!r}),link)\n"
            f"old=os.path.join(shared,'projects',{project!r}); new=os.path.join(home,'projects',{project!r})\n"
            "try: sessions=list(json.load(open(" + repr(roles) + ")))\n"
            "except Exception: sessions=[]\n"
            "for s in sessions:\n"
            " for name in (s+'.jsonl', s):\n"
            "  src,dst=os.path.join(old,name),os.path.join(new,name)\n"
            "  if os.path.exists(src) and not os.path.exists(dst):\n"
            "   os.makedirs(new,exist_ok=True)\n"
            "   (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src,dst)\n")
