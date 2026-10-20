from ..._module import PROGRAM
from ..._output import lines

STATES = {"none": "まだありません", "running": "動いています", "exited": "止まっています", "created": "作っただけです",
          "unknown": "わかりません（Docker が使えません）"}


def render(r, done: str | None = None):
    chosen = "コンテナにします" if r.container else "コンテナにしません（このPCで動かします）"
    return lines(
        done if done and r.changed else None,
        f"コンテナのイメージ {r.image} を作りました（次からはすぐ動きます）" if r.built else None,
        f"{r.path}：{chosen}",
        f"コンテナ：{r.name}（{STATES.get(r.state, r.state)}"
        + (f"。イメージ {r.image}）" if r.image else "）") if r.container or r.state not in ("none", "unknown") else None,
        None if r.docker_ready or not r.container else
        f"Docker：まだ使えません（{r.docker_detail}）。{PROGRAM} setup --docker で導入できます",
        f"コンテナを動かすには {PROGRAM} container start" if r.container and r.docker_ready and r.state != "running" else None,
        f"コンテナのイメージが古くなっています（今の作り方：{r.wanted_image}）。次に動かすときに作り直します" if r.outdated else None,
        None if r.custom_image or not r.container else f"環境の作り方：{r.recipe or '型のひな型（' + PROGRAM + ' module upgrade で .ecobuild/container/Dockerfile に置けます）'}",
        f"この作業空間だけの設定：イメージ {r.custom_image}" if r.custom_image else None,
        f"この作業空間だけの設定：エージェントに使わせないもの {';'.join(r.deny)}" if r.deny else None,
    )
