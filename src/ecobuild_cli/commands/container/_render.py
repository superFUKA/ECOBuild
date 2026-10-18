from ..._module import PROGRAM
from ..._output import lines

STATES = {"none": "まだありません", "running": "動いています", "exited": "止まっています", "created": "作っただけです",
          "unknown": "わかりません（Docker が使えません）"}


def render(r, done: str | None = None):
    chosen = "コンテナにします" if r.container else "コンテナにしません（このPCで動かします）"
    return lines(
        done if done and r.changed else None,
        f"{r.path}：{chosen}",
        f"コンテナ：{r.name}（{STATES.get(r.state, r.state)}。イメージ {r.image}）" if r.container or r.state not in ("none", "unknown") else None,
        None if r.docker_ready or not r.container else
        f"Docker：まだ使えません（{r.docker_detail}）。{PROGRAM} setup --docker で導入できます",
        f"コンテナを動かすには {PROGRAM} container start" if r.container and r.docker_ready and r.state != "running" else None,
    )
