"""このPCの設定（どのモジュールにも属さないもの）：置き場所（ECOBUILD_HOME）と config.toml。I-030。

本体と型が読む（cloneの記録の場所・既定の所有者・型が使うツールのパス）。項目は本体の CONFIG_KEYS と、
型の tool_settings。このPCの準備（ツールの導入・ログイン等）は本体の外（ecobuild_bundle.tooling）。
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from .errors import EcoBuildError, ErrorCode

if TYPE_CHECKING:
    from .module_type import ModuleType

Types = Iterable[type["ModuleType"]]

HOME_VARIABLE = "ECOBUILD_HOME"

# config で扱う本体の項目 → 説明（型の項目は ModuleType.tool_settings）
CONFIG_KEYS = {
    "owner": "module new・clone・list・deps add 等で、所有者を省略したリポジトリの所有者（組織名など。既定はログイン中のユーザー）",
    "log_level": "ログに残す量：off・error・info・debug（既定。外部コマンドの引数・出力まで全部）",
    "log_max_mb": "ログの大きさの上限（MB、置き場所ごと。既定 200。超えたら古い日から消す）",
    "agent_deny": "コンテナの中のエージェントに使わせない道具・コマンド（Claude Code の許可の規則を ; で区切る。"
                  "例 Bash(git push --force:*);WebFetch。既定はなし＝すべて使える）",
}

# 値が決まっている項目 → 確かめ方（合わなければ説明）
CONFIG_VALUES = {
    "log_level": lambda value: None if value in ("off", "error", "info", "debug")
    else "off・error・info・debug のどれかを指定してください。",
    "log_max_mb": lambda value: None if value.isdigit() and int(value) >= 1 else "1以上の整数（MB）を指定してください。",
}


def home() -> Path:
    """ツールの設定を置くディレクトリ（ECOBUILD_HOME、なければOSの慣例の場所）。"""
    if os.environ.get(HOME_VARIABLE):
        return Path(os.environ[HOME_VARIABLE])
    return default_home()


def default_home() -> Path:
    """ツールの設定を置く既定のディレクトリ（OSの慣例。Windows：%LOCALAPPDATA%\\ecobuild）。"""
    import platformdirs
    return Path(platformdirs.user_config_dir("ecobuild", appauthor=False))


def config_keys(types: Types = ()) -> dict[str, str]:
    """config で扱う項目 → 説明（本体の項目と、型が使うツールの項目）。"""
    keys = dict(CONFIG_KEYS)
    for module_type in types:
        keys.update(module_type.tool_settings())
    return keys


def load_config() -> dict[str, str]:
    path = home() / "config.toml"
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"{path} を読み込めません：{error}") from error
    return {key: value for key, value in data.items() if isinstance(value, str)}


def set_config(key: str, value: str | None, types: Types = ()) -> dict[str, str]:
    keys = config_keys(types)
    if key not in keys:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"設定 {key} はありません。",
                            hint="設定できる項目：" + "、".join(keys))
    problem = None if value is None or key not in CONFIG_VALUES else CONFIG_VALUES[key](value)
    if problem:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"設定 {key} に {value} は使えません。", hint=problem)
    values = load_config()
    if value is None:
        values.pop(key, None)
    else:
        values[key] = value
    path = home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# ECOBuildのツールの設定（ecobuild config）。"]
    lines += [f"{k} = {json.dumps(v, ensure_ascii=False)}" for k, v in sorted(values.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return values


def qualify(repository: str) -> str:
    """所有者のないリポジトリ名に、設定の owner を付ける。"""
    owner = load_config().get("owner")
    return f"{owner}/{repository}" if owner and "/" not in repository else repository
