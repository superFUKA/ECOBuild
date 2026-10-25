from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.module import CHECK_NAMES

from ..._output import lines, run_command

AGENT = "change"


def command(
    name: Annotated[str, "走らせるパイプラインの名前"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """パイプラインを今すぐ走らせます（タイミングに当てていなくても。失敗した手順があれば終了コード 1）。"""

    def action(inv):
        run = inv.module.run_pipeline(name, progress=inv.info)
        if not run.ok:
            failed = "、".join(CHECK_NAMES.get(i.name, i.name) + (f"（{i.detail}）" if i.detail else "")
                               for i in run.items if not i.ok)
            raise EcoBuildError(ErrorCode.CHECK_FAILED, f"パイプライン {name} が失敗しました：{failed}",
                                details=[{"name": i.name, "ok": i.ok, "detail": i.detail} for i in run.items])
        return run

    return run_command("pipeline run", action, lambda r: lines(f"パイプライン {r.name} が通りました"), json_output=json)
