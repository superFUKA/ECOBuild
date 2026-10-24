from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from ..registry import _render


def command(name: Annotated[str, "プリセットの名前（英小文字・数字・-・_）"],
            from_preset: Annotated[str, "写すプリセット（見本も）の名前"] = "",
            from_module: Annotated[str, "写す、今いるモジュールの登録の名前（作業空間のもの）"] = "",
            from_dir: Annotated[str, "取り込むフォルダー（agent.toml と agent.md がある）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCにプリセットを足します（ECOBUILD_HOME/agents/presets/<名前>/。コミットしません）。

    --from-preset でほかのプリセット・見本を、--from-module で今いるモジュールの登録を写すか、--from-dir でフォルダーを
    取り込みます。どれもなければ、同じ名前の見本を写し、なければ空のプリセットを作ります。

    例：
      ecobuild agent preset add my-worker --from-preset worker
      ecobuild -C C:\\ECO\\Calc agent preset add reviewer --from-module reviewer
    """
    def action(inv):
        if sum(bool(v) for v in (from_preset, from_module, from_dir)) > 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "写す元は1つだけ指定できます。")
        source = _registry.load(from_module, inv.module.root) if from_module else None
        return registration_view(_registry.add_preset(name, from_preset=from_preset or None, from_dir=from_dir or None,
                                                      registration=source), document=True)

    return run_command("agent preset add", action, lambda r: "プリセットにしました：" + _render.summary(r),
                       json_output=json)
