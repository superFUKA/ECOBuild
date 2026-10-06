"""ファイル操作の小さな共通処理（本体と型の両方で使う）。"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path


def remove_tree(path: Path) -> None:
    """gitの読み取り専用ファイル（Windows）も含めて削除する。"""
    def retry(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=retry)
