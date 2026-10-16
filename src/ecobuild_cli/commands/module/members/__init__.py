"""モジュール（GitHubのリポジトリ）の共同作業者を扱います。

招待を受けた人には、タスク管理の情報も共有します。"""

from typing import Annotated

from ...._output import lines, run_command

ROLES = {"read": "読む", "triage": "タスクの整理", "write": "書き込み", "maintain": "管理の一部", "admin": "管理者"}


def render(r) -> str:
    joined = [m for m in r if not m.invited]
    invited = [m for m in r if m.invited]
    return lines(
        "\n".join(f"  {m.login}（{ROLES.get(m.role, m.role)}）" for m in joined) or "  （まだいません）",
        ("招待中（GitHub の通知・メールから受けると加わります）：\n"
         + "\n".join(f"  {m.login}（{ROLES.get(m.role, m.role)}）" for m in invited)) if invited else None,
    )


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """共同作業者と、招待中の人を表示します。

    招待を受けた人には、タスク管理の情報（計画・段階）も共有し直します。見られるのは、リポジトリの管理者だけです。
    """
    return run_command("module members", lambda inv: inv.module.repository.members(), lambda r: "共同作業者：\n" + render(r),
                       json_output=json)
