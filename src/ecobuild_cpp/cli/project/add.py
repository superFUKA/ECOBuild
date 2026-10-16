from typing import Annotated

from ecobuild_cli.kit import missing, run_command


def command(
    name: Annotated[str, "Project名（ディレクトリ名にもなる）"],
    kind: Annotated[str, "種類：library／app（実行ファイル）／test／bench（性能測定）"] = "",
    link: Annotated[str, "リンクするライブラリのProject（app・test・bench。既定：ライブラリが1つならそれ）"] = "",
    no_test: Annotated[bool, "library で、組のテスト用Project（<名前>Test）を作らない"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectを追加します。

    library は、組のテスト用Project <名前>Test も作ります（file add でソースに対応するテストを置く場所）。
    app・test・bench はライブラリをリンクします（test・bench はライブラリが要ります。app はなくても作れます）。
    """
    if not kind:
        return missing("--kind", json)
    return run_command("project add", lambda inv: inv.module.add_project(name, kind, link=link or None,
                                                                        test=not no_test),
                       lambda r: f"Project {r.project} を追加しました：" + ", ".join(r.paths), json_output=json)
