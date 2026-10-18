from typing import Annotated

from ecobuild_bundle import container as _container
from ...._module import PROGRAM
from ...._operator import program_path
from ...._output import Invocation, execute


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """トークンを作る窓（claude setup-token）を開き、出たトークンを自動で覚えます。

    ブラウザーで許可すると、1年使えるトークン（sk-ant-oat…）が出ます。ECOBuild がそれを拾って覚えます（拾えなければ、
    その窓で貼れます。あとから ecobuild agent token set でも）。サブスクリプション（Pro・Max 等）のアカウントで作れます。
    """
    return execute("agent token login", Invocation(json_output=json),
                   lambda inv: {"pid": _container.token_login((program_path(), "agent", "token", "capture")).pid},
                   lambda r: f"トークンを作る窓を開きました。ブラウザーで許可すると、出たトークンを自動で覚えます"
                             f"（{PROGRAM} agent token status で確かめられます）")
