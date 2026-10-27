from typing import Annotated

from ... import _self_update
from ..._output import lines, run_command


def command(
    ref: Annotated[str, "候補を出すブランチ・タグ。省略時は入れたときのブランチ（コミットを入れていれば既定のブランチ）"] = "",
    count: Annotated[int, "出すコミットの数（新しい順）"] = 30,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """入れられる ECOBuild の版の候補（入れ元のブランチ・タグと、その最近のコミット）を表示します（何も変えません）。

    選んだものを ecobuild installer update --ref に渡すと、その版に入れ直します（前の版へ戻すのにも使えます）。
    ブランチ名で入れるとその後の更新はそのブランチの最新を追い、コミットで入れるとその版のままになります。
    """

    def action(inv):
        return _self_update.versions(ref or None, count)

    def render(r):
        mark = lambda v: "＊" if v.current else "  "
        return lines(
            f"入れ元：{r.url}（今：{(r.current or '不明')[:7]}、{r.installed_ref or '版の指定なし'}）",
            f"ブランチ：{'、'.join(r.branches) or 'なし'}",
            f"タグ：{'、'.join(r.tags)}" if r.tags else None,
            f"{r.ref} の最近のコミット（＊が今の版）：",
            "\n".join(f"{mark(v)}{v.sha[:7]}  {v.date}  {v.subject}" + ("（最新）" if v.latest else "") for v in r.commits),
            "入れ直すには ecobuild installer update --ref <ブランチ・タグ・コミット>",
        )

    return run_command("installer versions", action, render, json_output=json)
