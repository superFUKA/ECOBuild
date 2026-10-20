"""中のエージェントのログイン（トークン）。

claude setup-token（このPCで1回、ブラウザーで許可する）が出す長く使えるトークンを覚え、コンテナの中で起動するときに
CLAUDE_CODE_OAUTH_TOKEN で渡す（中でログインしなくてよい）。なければ、中で一度ログインする（ボリュームに残る）。
トークンの値はログ・コマンドラインに書かない。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError

from .errors import ErrorCode, from_ecoagent

TOKEN_FILE = Path("agents") / "container-token"   # ECOBUILD_HOME の下：中のエージェントのログイン（claude setup-token）
TOKEN_VARIABLE = "CLAUDE_CODE_OAUTH_TOKEN"


def token_path() -> Path:
    return _settings.home() / TOKEN_FILE


def load_token() -> str:
    try:
        return token_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_token(token: str) -> Path:
    token = token.strip()
    if not token or any(c.isspace() for c in token):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "トークンが空か、空白を含んでいます。",
                            hint="claude setup-token が最後に出す sk-ant-oat… の1行をそのまま貼ってください。")
    path = token_path()
    repository = next((p for p in path.resolve().parents if (p / ".git").exists()), None)
    if repository is not None:     # コミットされてしまう場所には置かない（ECOBUILD_HOME をリポジトリの中にした等）
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"トークンの置き場所 {path} が git のリポジトリ（{repository}）の中です。",
                            hint="コミットされないよう、ECOBUILD_HOME をリポジトリの外にしてください。")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def forget_token() -> bool:
    try:
        token_path().unlink()
        return True
    except FileNotFoundError:
        return False


TOKEN_PATTERN = re.compile(r"sk-ant-oat\d*-[A-Za-z0-9_-]{20,}")
SETUP_TOKEN = ("claude", "setup-token")


def token_login(capture: tuple[str, ...]):
    """このPCで、トークンを作る窓を開く。capture：その窓で動かすコマンド（setup-token を動かしてトークンを拾い、
    覚えてから閉じる。使う側の ecobuild agent token capture）。"""
    import ecoagent
    folder = token_path().parent
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return ecoagent.start(folder, capture)
    except ecoagent.AgentError as error:
        raise from_ecoagent(error) from error


def find_token(text: str) -> str:
    """画面の文字から、最後に出たトークン（なければ空）。"""
    found = TOKEN_PATTERN.findall(text)
    return found[-1] if found else ""


def capture_token(command: tuple[str, ...] = SETUP_TOKEN) -> str:
    """今の端末で command（claude setup-token）を動かし、終わったら画面からトークンを拾って覚える。拾えなければ空。"""
    import ecoagent
    program = shutil.which(command[0])
    if program is None:
        raise EcoBuildError(ErrorCode.AGENT_ERROR, f"{command[0]} が見つかりません。",
                            hint=f"{command[0]} をインストールし、PATH から実行できるようにしてください。")
    subprocess.run([program, *command[1:]])
    token = find_token(ecoagent.console.screen_text())
    if token:
        save_token(token)
    return token
