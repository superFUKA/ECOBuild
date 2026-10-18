from typing import Annotated

from ecobuild_bundle import container as _container
from ...._module import PROGRAM
from ...._output import Invocation, execute


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """トークンを作る画面（claude setup-token）を新しい窓で開きます。

    ブラウザーで許可すると、窓の最後に1年使えるトークン（sk-ant-oat…）が出ます。それを ecobuild agent token set に
    貼ってください。サブスクリプション（Pro・Max 等）のアカウントで作れます。
    """
    return execute("agent token login", Invocation(json_output=json),
                   lambda inv: {"pid": _container.token_login().pid},
                   lambda r: f"トークンを作る窓を開きました。出たトークンを {PROGRAM} agent token set に貼ってください")
