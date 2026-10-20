from ...._module import PROGRAM
from ...._output import lines


def render(r, done: str | None = None):
    if not r.docker_ready:
        return f"Docker：まだ使えません（{r.docker_detail}）。{PROGRAM} setup --docker で導入できます"
    rows = [f"{'＊' if i.current else '　'} {i.name}（{'環境・' if i.environment else ''}{i.size}・{i.created}）"
            + (f"\n    使っている作業空間：{'、'.join(i.used_by)}" if i.used_by else "") for i in r.images]
    return lines(
        done,
        *(f"作りました：{name}" for name in r.built),
        *(f"消しました：{name}" for name in r.removed),
        "\n".join(rows) if rows else "ECOBuild のイメージはまだありません",
        "＊ は今の作業空間が使う作り方のイメージ" if rows else None,
        f"まだ作っていない作業空間：{'、'.join(r.missing)}（{PROGRAM} container image build で作れます）" if r.missing else None,
    )
