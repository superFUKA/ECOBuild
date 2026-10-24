"""全エージェント共通の文の結果と、人向けの表示（show・set で同じ形）。"""

from ecobuild_agent import registry, rules
from ecobuild_agent.results import AgentRules

from ...._output import lines


def view(root, *, changed: tuple[str, ...] = (), committed: str = "") -> AgentRules:
    common = rules.read(root)
    return AgentRules(root=root, in_force=registry.short_ref(registry.base_ref(root) or ""),
                      pending=common != rules.in_force(root), common=common, changed=changed, committed=committed)


def details(r) -> str:
    head = r.common.strip().splitlines()[0][:60] if r.common.strip() else "なし"
    return lines(
        *([f"変えたファイル：{'、'.join(r.changed)}" + (f"（コミット {r.committed[:7]}。Push はしていません）" if r.committed else "")]
          if r.changed else []),
        f"効く版：{r.in_force or '（作成元のブランチを読めません）'}" + ("・この作業空間の変更はまだ効いていません" if r.pending else ""),
        f"全エージェント共通：{head}",
    )
