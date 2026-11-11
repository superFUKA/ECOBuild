"""環境の準備の欄と結果。名前・メールの欄には、今の値を薄く出す（環境チェックの「git の名前・メール」から）。
「不足しているツールもインストールする」のチェック。準備した後は、したこと・まだ足りないもの・入れるためのコマンドを出す。

準備するのは ecobuild setup（ボタンは画面の側）。ここは欄と、その結果を見せるだけ。
"""
from typing import Annotated


def part(
    items: Annotated[list[dict], "環境チェックの項目（{name, ok, detail}。「git の名前・メール」の detail が「名前 <メール>」）"] = [],
    result: Annotated[dict | None, "準備の結果（{done: [したこと], remaining: [{name}], commands: [入れるためのコマンド]}）。まだなら null"] = None,
) -> None: ...


def on_changed(
    name: Annotated[str, "名前（変えないなら空）"],
    email: Annotated[str, "メールアドレス（変えないなら空）"],
    install: Annotated[bool, "不足しているツールもインストールする"],
) -> None: ...
