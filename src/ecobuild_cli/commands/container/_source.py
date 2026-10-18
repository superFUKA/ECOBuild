"""コンテナのイメージに入れる ECOBuild：このPCの ecobuild と同じ版（入れ元の git のリポジトリとコミット）。"""
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from ecobuild.errors import EcoBuildError
from ecobuild_bundle import container
from ... import _self_update


def source() -> tuple[str, str]:
    try:
        found = _self_update.installed()
    except EcoBuildError:
        return container.SOURCE
    if not found.editable:
        return found.url, found.commit or found.ref or container.SOURCE[1]
    # 手元のソースから（開発用）：そのソースの origin と今のコミット（push してあるものを入れられる）
    folder = Path(unquote(urlparse(found.url).path).lstrip("/"))

    def git(*args):
        return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True).stdout.strip()
    return git("remote", "get-url", "origin") or container.SOURCE[0], git("rev-parse", "HEAD") or container.SOURCE[1]
