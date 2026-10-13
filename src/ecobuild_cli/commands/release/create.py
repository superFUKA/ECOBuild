from typing import Annotated

from ..._output import run_command


def command(
    tag: Annotated[str, "タグ（例：v1.0.0）"],
    title: Annotated[str, "リリースの題名（既定：タグ）"] = "",
    notes: Annotated[str, "説明"] = "",
    target: Annotated[str, "タグを付けるブランチ（既定：ecobuild.tomlのdefault_base）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにリリースを作り、ブランチの最新にタグを付けます。"""
    return run_command("release create",
                       lambda inv: inv.module.create_release(tag, title=title, notes=notes, target=target or None),
                       lambda r: f"リリース {r.tag} を作りました：{r.url}", json_output=json)
