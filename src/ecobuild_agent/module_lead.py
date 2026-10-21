"""モジュールの進行役（モジュールのエージェント）：モジュールごとに1つの専用の作業空間で、人と話すエージェント。

タスクを持たない。人と話して仕事を決め、直下の管理役（team の manager）を作って仕事を送り、知らせを要約して人に伝える。
モジュールの設定・ブランチ管理（GitHub 側の操作）もする。リポジトリのファイルは変えない（変える仕事は管理役のタスクで）。

作業空間は ECOBuild が作って持つ：ECOBUILD_HOME/agents/modules/<所有者>/<名前>/（作成元＝default_base の clone）。
作業空間の記録（workspaces.json）には入れない（人の作業空間の一覧・GUI のタブに出さない）。起動のたびに作成元の最新へ
早送りする（ファイルを変えないので、ぶつからない）。コンテナ必須（人と話しながら確認なしで動くため、隔離する）。
印（MARK_FILE）がある作業空間のエージェントは進行役（team.role_of。タスクを持たない）。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import ecobuild_container as container
from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError, operation
from ecobuild.fsutil import remove_tree

from . import status as agent_status
from . import team
from .errors import ErrorCode
from .operator import HUMAN, READ

FOLDER = Path("agents") / "modules"
MARK_FILE = team.MODULE_PLACE_FILE


@dataclass(frozen=True)
class FacilitatorPlace:
    """ecobuild agent module status：進行役の作業空間の様子。"""
    module: str             # 所有者/名前
    root: Path
    exists: bool
    branch: str = ""
    container: str = ""     # コンテナの名前
    state: str = ""         # エージェントの様子（status.activity）
    since: float | None = None
    last_reply: str = ""
    running: bool = False
    members: tuple[team.Member, ...] = ()


def slug(module) -> str:
    """モジュールの GitHub の名前（所有者/名前）。origin の URL から読む（GitHub の URL でなければ GitHub に聞く）。"""
    url = module.repository.remote_url or ""
    found = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if found:
        return f"{found.group(1)}/{found.group(2)}"
    try:
        return module.repository.github.repository_name(module.root)
    except Exception as error:
        raise EcoBuildError(ErrorCode.AGENT_ERROR, "このモジュールの GitHub のリポジトリが分かりません。",
                            hint="進行役は GitHub にあるモジュールで起動します。") from error


def directory(module) -> Path:
    """モジュールの進行役の作業空間の場所。"""
    owner, name = slug(module).split("/", 1)
    return _settings.home() / FOLDER / owner / name


def is_place(root: Path) -> bool:
    return (Path(root) / MARK_FILE).is_file()


def prepare(module, *, progress=lambda message: None):
    """進行役の作業空間を用意する（なければ作成元から clone、あれば作成元の最新へ早送り）。コンテナにし、印を置く。
    その作業空間のモジュールを返す。"""
    root = directory(module)
    if root.exists() and not (root / ".git").exists():   # clone の途中で止まった作りかけ
        progress(f"作りかけの {root} を片付けています…")
        remove_tree(root)
    if not root.exists():
        progress(f"進行役の作業空間を用意しています（{module.config.default_base} の clone・依存先）…")
        root.parent.mkdir(parents=True, exist_ok=True)
        place, _ = module.create_workspace(root)
    else:
        place = type(module).find(root)
        _fast_forward(place, progress)
    place.prepare_agent_area()
    (root / MARK_FILE).write_text(json.dumps({"module": slug(module), "at": time.time()}, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
    if not container.enabled(root):
        container.choose(root, True, command=module.command)
    return place


def _fast_forward(place, progress) -> None:
    """作成元の最新へ早送りする。進行役はファイルを変えないので、変更があれば（人が触った等）そのまま使って知らせる。"""
    git = place.repository.git
    base = place.config.default_base
    try:
        git.fetch()
        tree = git.working_tree()
        if (git.current_branch() or "") != base:
            progress(f"進行役の作業空間が {base} にありません（{git.current_branch() or '切り離された状態'}）。そのまま使います。")
        elif not tree.clean:
            progress("進行役の作業空間に変更があるので、最新への早送りはしません。")
        else:
            git.run("merge", "--ff-only", "--quiet", f"origin/{base}", check=False)
    except Exception as error:   # GitHub に届かない等：古いまま起動する（話すことはできる）
        progress(f"作業空間を最新にできませんでした（{getattr(error, 'message', None) or error}）。そのまま使います。")


def place_status(module) -> FacilitatorPlace:
    root = directory(module)
    name = slug(module)
    if not (root / ".git").exists():
        return FacilitatorPlace(name, root, False)
    from ecowork.git import Git
    try:
        branch = Git(root).current_branch() or ""
    except Exception:
        branch = ""
    folder = agent_status.directory(container.name(root))
    seen = agent_status.activity(folder)
    return FacilitatorPlace(name, root, True, branch, container.name(root), seen["state"], seen["since"],
                            seen["last_reply"], agent_status.running_pid(folder) is not None,
                            team.team(root).members)


def close(module, *, discard_local: bool = False):
    """進行役の作業空間を閉じる（コンテナも消す）。管理役が残っていれば止める（先に agent team close）。"""
    root = directory(module)
    if not (root / ".git").exists():
        raise EcoBuildError(ErrorCode.AGENT_ERROR, "このモジュールの進行役の作業空間はありません。")
    left = team.team(root).members
    if left:
        raise EcoBuildError(ErrorCode.AGENT_ERROR, "進行役の下に、まだ管理役がいます：" + "、".join(m.name for m in left),
                            hint=f"先に {operation(module.command, 'agent team close <名前>')}（進行役の作業空間で）で閉じてください。")
    if agent_status.running_pid(agent_status.directory(container.name(root))) is not None:
        raise EcoBuildError(ErrorCode.AGENT_ERROR, "進行役が動いています。",
                            hint="止めてから閉じてください（GUI のタブを閉じる、または agent stop）。")
    return type(module).close_workspace(root, discard_local=discard_local)


# ---- 関所（シェルのコマンド。ecobuild agent guard --role module） ------------------------------------------
GIT_READ = frozenset({"status", "log", "show", "diff", "branch", "fetch", "ls-files", "ls-tree", "rev-parse", "remote",
                      "blame", "describe", "shortlog", "grep", "cat-file", "merge-base", "for-each-ref", "reflog"})
GH_READ = frozenset({"view", "list", "status", "diff", "checks"})
REFUSED = ("これは進行役が使わない操作です。リポジトリのファイル・ブランチを変える作業はタスクブランチの仕事なので、"
           "管理役に送ってください（agent team send）。人がする操作（秘密の値・このPCの準備・更新）は、ユーザーに頼んでください。")


def classify_git(args: list[str]) -> tuple[str, str]:
    """git の引数の重さ：読むだけのものは read、ほかは使わない（human）。"""
    words = [w for w in args if not w.startswith("-")]
    name = words[0] if words else ""
    if name in GIT_READ and not (name == "branch" and any(o in args for o in ("-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move"))):
        return READ, f"git {name}"
    return HUMAN, f"git {name}".strip()


def classify_gh(args: list[str]) -> tuple[str, str]:
    """gh の引数の重さ：一覧・表示だけ read（api は GET だけ）、ほかは使わない（ecobuild のコマンドで）。"""
    words = [w for w in args if not w.startswith("-")]
    if words[:1] == ["api"]:
        writes = any(o.split("=")[0] in ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input") for o in args)
        return (HUMAN if writes else READ), "gh api"
    if len(words) >= 2 and words[1] in GH_READ:
        return READ, f"gh {words[0]} {words[1]}"
    return HUMAN, " ".join(["gh", *words[:2]])


def guard(data: str, classify, *, program: str) -> tuple[int, str]:
    """進行役のフック：シェルのコマンド（フックの入力の JSON）を調べる。(終了コード, エージェントに伝える文)。
    classify：program の引数 → (重さ, コマンドの名前)。git・gh は読むだけ。"""
    import ecoagent
    classifiers = {program: classify, "git": classify_git, "gh": classify_gh}
    policy = ecoagent.guard.Policy(frozenset(classifiers), classify, role="進行役", refusals={HUMAN: REFUSED},
                                   classifiers=classifiers)
    return ecoagent.guard.hook(data, policy)
