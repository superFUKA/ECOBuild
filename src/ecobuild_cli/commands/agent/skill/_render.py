"""スキルの人向けの表示（list・show・add・set・remove で同じ形。preset も）。"""

from ...._output import lines

SOURCES = {"preset": "このPCのスキル", "module": "モジュールのスキル"}


def summary(s) -> str:
    """1つのスキルの1行。"""
    return f"{s.name}：{s.description}（{SOURCES.get(s.source, s.source)}" + ("・まだ渡らない" if s.pending else "") + "）"


def details(s) -> str:
    committed = getattr(s, "committed", "")
    return lines(
        summary(s),
        *([f"  使える登録：{'・'.join(s.used_by) or 'なし'}"] if s.source == "module" else []),
        *([f"  ほかのファイル：{', '.join(s.files)}"] if s.files else []),
        f"  置き場所：{s.folder}",
        *([f"  コミット：{committed[:7]}（Push はしていません。提出して取り込まれるとエージェントに渡ります）"] if committed else []),
    )
