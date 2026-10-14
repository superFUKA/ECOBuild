from typing import Annotated

from ..._output import run_command

STATES = {"aligned": "記録の版", "differs": "記録と別の版", "modified": "未コミットの変更あり",
          "working": "作業版", "missing": "cloneなし（ecobuild deps sync で取得）"}


def command(
    fetch: Annotated[bool, "GitHubの側も確かめる（まだあるか・アーカイブ・名前の変更・記録より新しい版）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先の一覧（記録の版・手元の版・状態）を表示します。"""

    def render(r):
        if not r:
            return "依存先はありません（ecobuild link で追加できます）"
        return "\n".join(
            f"{d.name}：記録 {d.recorded[:7]}、手元 {(d.local or '-')[:7]}、{STATES[d.state]}"
            + (f"（{d.branch}）" if d.branch else "") + f"\n  {d.url}" + _remote(d) for d in r)

    return run_command("deps list", lambda inv: list(inv.module.dependencies(fetch=fetch)), render,
                       json_output=json)


def _remote(d) -> str:
    """--fetch：GitHubの側の変化。"""
    if d.remote is None:
        return ""
    if d.remote == "gone":
        return ("\n  GitHubにありません（削除されたか、見る権限がありません）。このモジュールを新しくcloneすると、"
                "この依存先を取得できません")
    if d.remote == "unknown":
        return "\n  GitHubの状態を確かめられませんでした"
    notes = []
    if d.remote == "archived":
        notes.append("GitHubでアーカイブ（読み取り専用）されています。この先は更新されません")
    if d.remote == "moved":
        notes.append(f"GitHubで名前が {d.moved_to} に変わっています（今はGitHubの転送で取得できます）")
    if d.latest and d.latest != d.recorded:
        notes.append(f"GitHubに新しい版 {d.latest[:7]} があります（ecobuild deps update で記録を進められます）")
    return "".join(f"\n  {note}" for note in notes)
