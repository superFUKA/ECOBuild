"""project の設定のコマンドの共通部分（対象のProjectの決め方・表示）。"""

from ecobuild.errors import EcoBuildError, ErrorCode
from ..._output import split_list


def target_project(inv, project: str) -> str:
    """対象のProject：指定 → 今いるProject → テスト用を除いてProjectが1つならそれ。"""
    module = inv.module
    name = project or module.project_at(inv.cwd)
    if name:
        return name
    candidates = [p.name for p in module.projects() if p.kind != "test"]
    if len(candidates) == 1:
        return candidates[0]
    raise EcoBuildError(ErrorCode.NOT_IN_PROJECT, "対象のProjectが決まりません。",
                        hint="Projectのディレクトリの中で実行するか、--project で指定してください。")


def pairs(text: str, option: str) -> dict[str, str]:
    """「構成=パス」のカンマ区切り（--file Debug=lib/a_d.lib,Release=lib/a.lib）。"""
    result = {}
    for item in split_list(text):
        key, separator, value = item.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{option} の {item!r} は「構成=パス」の形にしてください。",
                                hint=f"例：{option} Debug=lib/foo_d.lib,Release=lib/foo.lib")
        result[key.strip()] = value.strip()
    return result


_KINDS = {"project": "同じモジュール", "module": "依存先のモジュール", "package": "CMakeのパッケージ",
          "cmake": "CMakeのソース", "file": "ビルド済みのファイル"}


def link_line(link: dict) -> str:
    detail = [_KINDS.get(link["kind"], link["kind"])]
    if link.get("as"):
        detail.append(link["as"])
    if link.get("target") and link["target"] != link["name"]:
        detail.append(f"ターゲット {link['target']}")
    if link.get("directory"):
        detail.append(link["directory"])
    if link.get("files"):
        detail.append(", ".join(f"{k}={v}" for k, v in link["files"].items()))
    return f"  {link['name']}（{'・'.join(detail)}）id {link['id'][:8]}"


def option_text(option: dict) -> str:
    """オプション・定義。コンパイラ・構成の条件があれば、先に [MSVC/Release] のように付ける。"""
    condition = "/".join(c for c in (option["compiler"], option["configuration"]) if c)
    return f"[{condition}] {option['value']}" if condition else option["value"]


def render_details(d: dict) -> str:
    lines = [f"{d['name']}（{d['kind']}）{d['directory']}"
             + ("  ← 他のモジュールからリンクされるProject（main）" if d["main"] else "")]
    if d["folder"]:
        lines.append(f"ソリューションフォルダー：{d['folder']}")
    lines.append(f"ソースディレクトリ：{', '.join(d['source_directories']) or 'なし'}")
    for kind, t in d["types"].items():
        label = f"（{kind}）" if len(d["types"]) > 1 else ""
        lines.append(f"定義{label}：{', '.join(t['defines']) or 'なし'}"
                     f"／公開する定義：{', '.join(t['public_defines']) or 'なし'}"
                     f"／インクルード：{', '.join(t['include_directories']) or 'なし'}")
    lines.append("リンク：" + ("なし" if not d["links"] else "\n" + "\n".join(map(link_line, d["links"]))))
    if d["pch"]["headers"] or d["pch"]["system_headers"]:
        lines.append(f"PCH：{', '.join(d['pch']['headers'] + d['pch']['system_headers'])}")
    if d["kind"] == "executable":
        lines.append(f"入口の関数：{d['entry_point']}（{'GUIアプリ' if d['gui'] else 'コンソールアプリ'}）")
    if d["system_libraries"]:
        lines.append(f"OSのライブラリ：{', '.join(d['system_libraries'])}")
    if d["kind"].endswith("library"):
        lines.append(f"Windowsで共有ライブラリのすべての関数を書き出す：{'する' if d['export_all_symbols'] else 'しない'}")
    for label, key in (("コンパイルオプション", "compile_options"), ("リンクオプション", "link_options"),
                       ("条件付きの定義", "conditional_definitions")):
        if d[key]:
            lines.append(f"{label}：{', '.join(map(option_text, d[key]))}")
    if d["warning_level"] is not None or d["warnings_as_errors"]:
        level = "既定" if d["warning_level"] is None else f"レベル {d['warning_level']}"
        lines.append(f"警告：{level}{'（エラーにする）' if d['warnings_as_errors'] else ''}")
    for stage, label in (("pre_build", "コンパイルの前"), ("pre_link", "リンクの前"), ("post_build", "ビルドの後")):
        if d["build_events"][stage]:
            lines.append(f"ビルドイベント（{label}）：{'; '.join(' '.join(c) for c in d['build_events'][stage])}")
    if d["output_files"]:
        lines.append(f"出力ファイルの横へコピー：{', '.join(d['output_files'])}")
    return "\n".join(lines)
