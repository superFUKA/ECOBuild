from typing import Annotated

from ecobuild_cli.kit import run_command

AGENT = "read"


def command(
    name: Annotated[str, "依存先の名前（deps list の名前）"],
    branch: Annotated[str, "コミットを並べるブランチ（既定：GitHub の既定のブランチ）"] = "",
    count: Annotated[int, "並べるコミットの数"] = 30,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先の選べる版（ブランチ・タグ・最近のコミット）を表示します。

    選んだ版は ecobuild deps update <依存先> --at <版> で記録します。手元の clone（deps/<名前>）に GitHub から取り込み直して読みます。
    """

    def render(r):
        lines = [f"{r.name}：記録 {r.recorded[:7]}（{r.url}）", f"ブランチ：{'、'.join(r.branches)}（既定 {r.default_branch}）"]
        if r.tags:
            lines.append("タグ：" + "、".join(f"{t.name}（{t.sha[:7]}）" for t in r.tags))
        lines.append(f"{r.branch} のコミット（新しい順）：")
        lines += [f"  {c.sha[:7]}  {c.date[:16].replace('T', ' ')}  {c.subject}"
                  + (f"  [{', '.join(c.tags)}]" if c.tags else "") + ("  ← 記録" if c.sha == r.recorded else "")
                  for c in r.commits]
        return "\n".join(lines)

    return run_command("deps versions", lambda inv: inv.module.dependency_versions(name, branch=branch or None, count=count),
                       render, json_output=json)
