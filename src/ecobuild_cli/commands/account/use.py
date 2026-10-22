from typing import Annotated

from ..._output import lines, run_command, usage_error


def command(
    account: Annotated[str, "この作業空間で使う GitHub のアカウント（このPCの gh でログインしておく）"] = "",
    clear: Annotated[bool, "結び付けを外し、gh の使用中のアカウントに戻す"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """今いる作業空間を、GitHub のアカウントに結び付けます（AI 用のアカウントで作業させる等）。

    この作業空間の ecobuild・git（push）・コンテナの中のエージェントは、そのアカウントとして動きます。
    コミットの作者もそのアカウント（GitHub の noreply のメール）になります。結び付けはこの作業空間だけのもので、
    コミットされず、gh の使用中のアカウント（ほかの作業空間・ほかのツール）は変わりません。
    アカウントには先に gh auth login でログインしておきます（ecobuild account list でログイン中のものが分かります）。
    """
    if bool(account) == clear:
        return usage_error("アカウントか --clear のどちらかを指定してください。", json)

    def render(r):
        return lines(f"この作業空間を {r} として動かします（コミットの作者も {r}）" if r
                     else "結び付けを外しました（gh の使用中のアカウントで動きます）",
                     "役割は ecobuild account show で確かめられます" if r else None)

    return run_command("account use", lambda inv: inv.module.repository.use_account(account or None), render,
                       json_output=json)
