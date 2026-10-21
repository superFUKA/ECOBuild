import dataclasses
import sys
from pathlib import Path
from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode, WorkError
import ecobuild_container as _container
from ..._module import PROGRAM
from ..._output import lines, run_command
from ._source import source

ACTION = "コンテナの環境（Dockerfile）の変更"


@dataclasses.dataclass(frozen=True)
class DockerfileView(_container.EnvironmentDockerfile):
    """環境の Dockerfile と、この作業空間で書けるか（タスクブランチか。書けなければその理由）。GUI のイメージのエディターが使う。"""
    editable: bool = False
    reason: str = ""


def command(write: Annotated[str, "書く中身のファイル（- なら標準入力）。タスクブランチでだけ"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """コンテナの環境の Dockerfile を表示・編集します。

    この作業空間のモジュールの環境（.ecobuild/container/Dockerfile）。--write で書き換えます。表示するのは今の中身（なければ型のひな型）・材料のハッシュ・作るイメージの名前・このPCにあるか・この作業空間の
    コンテナが古いか。--write はファイルを書くだけで、コミットは今までどおり（task commit）。リポジトリのファイルを
    変えるのでタスクブランチでだけ書けます。試しに作るのは container image build --workspace <この場所>。
    """
    def action(inv):
        module = inv.module
        if write:
            found = module.save_container_dockerfile(_read(write, inv.cwd), source())
        else:
            found = _container.environment_dockerfile(module.root, source())
        try:
            module.require_task_branch(ACTION)
            editable, reason = True, ""
        except WorkError as error:
            editable, reason = False, error.message
        values = {field.name: getattr(found, field.name) for field in dataclasses.fields(found)}
        return DockerfileView(**values, editable=editable, reason=reason)

    return run_command("container dockerfile", action, lambda r: _render(r, bool(write)), json_output=json)


def _read(name: str, cwd: Path) -> str:
    if name == "-":
        return sys.stdin.read()
    path = Path(name) if Path(name).is_absolute() else cwd / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{path} を読めませんでした：{error.strerror or error}",
                            hint="書く中身のファイルの場所を確かめてください（標準入力からなら --write -）。") from None


def _render(r, wrote: bool) -> str:
    return lines(
        (f"{_container.DOCKERFILE} を書きました（コミットは {PROGRAM} task commit で）" if r.changed
         else f"{_container.DOCKERFILE} は同じ中身です") if wrote else None,
        f"環境：{_container.DOCKERFILE if r.exists else f'型のひな型（まだ {_container.DOCKERFILE} はありません）'}",
        f"環境のイメージ：{r.environment}",
        f"コンテナのイメージ（環境＋ECOBuild）：{r.image}（{'このPCにあります' if r.image_ready else 'まだ作っていません'}）",
        f"この作業空間のコンテナのイメージは古くなっています（{r.container_image}）。次に動かすときに作り直します"
        if r.outdated else None,
        None if r.editable or wrote else f"書き換え：{r.reason}",
        "",
        r.text.rstrip(),
    )
