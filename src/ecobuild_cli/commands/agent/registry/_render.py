"""登録・プリセットの人向けの表示（list・show・add・set・remove で同じ形）。"""

from ...._output import lines

SOURCES = {"sample": "見本", "preset": "このPCのプリセット", "module": "モジュールの登録"}


def summary(r) -> str:
    """1つの登録の1行。"""
    return (f"{r.name}：{r.title}（{SOURCES.get(r.source, r.source)}"
            + ("・人が起動できる" if r.human_start else "") + ("・まだ効いていない" if r.pending else "") + "）")


def details(r) -> str:
    committed = getattr(r, "committed", "")
    return lines(
        summary(r),
        f"  モデル：{r.model or '既定'}",
        f"  起動してよい子：{'・'.join(r.children) or 'なし'}（同時に {r.max_children} 人まで）",
        f"  渡すツール：{', '.join(r.tools) or 'なし'}",
        f"  置き場所：{r.folder}",
        *([f"  コミット：{committed[:7]}（Push はしていません。提出して取り込まれると効きます）"] if committed else []),
    )
