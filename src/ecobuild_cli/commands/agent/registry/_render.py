"""登録の人向けの表示（list・show・add・set・remove で同じ形）。"""

from ...._output import lines

SOURCES = {"sample": "見本", "user": "ユーザーの登録"}


def summary(r) -> str:
    """1つの登録の1行。"""
    return (f"{r.name}：{r.title}（{SOURCES.get(r.source, r.source)}"
            + ("・人が起動できる" if r.human_start else "") + "）")


def details(r) -> str:
    return lines(
        summary(r),
        f"  モデル：{r.model or '既定'}",
        f"  起動してよい子：{'・'.join(r.children) or 'なし'}（同時に {r.max_children} 人まで）",
        f"  渡すツール：{', '.join(r.tools) or 'なし'}",
        f"  文書：{r.document_path.as_posix()}",
    )
