"""モジュールのエージェント向けの決まりの人向けの表示（show・set で同じ形）。"""

from ...._output import lines


def _head(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first[:60] + ("…" if len(first) > 60 or len(text.strip().splitlines()) > 1 else "")


def details(r) -> str:
    roles = [x for x in r.roles if x.text.strip() or x.deny]
    return lines(
        *([f"変えたファイル：{'、'.join(r.changed)}" + (f"（コミット {r.committed[:7]}。Push はしていません）" if r.committed else "")]
          if r.changed else []),
        f"効く版：{r.in_force or '（作成元のブランチを読めません）'}" + ("・この作業空間の変更はまだ効いていません" if r.pending else ""),
        f"全エージェント共通：{_head(r.common) or 'なし'}",
        *[f"{x.name}（{x.title}）：{_head(x.text) or '文なし'}" + (f"・使わせないツール {', '.join(x.deny)}" if x.deny else "")
          for x in roles],
        *([f"渡せるツール：{len(r.tools)} 個"] if r.tools else []),
    )
