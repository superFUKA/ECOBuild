from typing import Annotated

from ... import tooling
from .._output import Invocation, execute
from ...errors import EcoBuildError, ErrorCode


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """前提ツール・認証・gitの設定・コンパイラを診断します（何も変えません）。直すには ecobuild setup。"""

    def action(inv):
        report = tooling.doctor()
        if not report.ok:
            raise EcoBuildError(ErrorCode.TOOL_MISSING, "足りないものがあります：" + "、".join(
                i.name for i in report.items if not i.ok and i.required),
                hint="ecobuild setup で直せるものを直します（ツールの導入は --install）。",
                details=[{"name": i.name, "ok": i.ok, "required": i.required, "detail": i.detail, "hint": i.hint}
                         for i in report.items])
        return report

    def render(r):
        return "\n".join(("OK " if i.ok else "NG " if i.required else "-- ") + f"{i.name}：{i.detail}"
                         + ("" if i.ok else f"\n     {i.hint}") for i in r.items)

    return execute("doctor", Invocation(json_output=json), action, render)
