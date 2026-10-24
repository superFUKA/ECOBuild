import sys
from pathlib import Path
from typing import Annotated

import click
from ecobuild.errors import EcoBuildError
from ecobuild_agent import mcp

from ..._output import usage_error

PROGRAM = (sys.executable, "-m", "ecobuild_cli")   # ツールを実行する ECOBuild（この ECOBuild と同じもの）


def command(
    agent: Annotated[str, "エージェントの ID（呼び手。ツールの引数では名乗らせない）"] = "",
    registration: Annotated[str, "エージェントの登録の名前（渡すツールを登録の tools で絞る）"] = "",
    kind: Annotated[str, "owner（タスクの持ち主）か helper（手伝い。ブランチを変えるツールは渡さない）"] = mcp.OWNER,
    workspace: Annotated[str, "作業空間の場所（ツールはここで ECOBuild のコマンドを実行する。既定は今いるディレクトリ）"] = "",
    registration_file: Annotated[str, "起動した ECOBuild が解決した登録のファイル（コンテナの中。あれば登録はここから読む）"] = "",
) -> int:
    """エージェント専用の MCP サーバー（標準入出力の JSON-RPC）を、入力が閉じるまで動かします。

    エージェントを起動する ECOBuild が、MCP の設定のファイルに引数を固定して使います（人は使いません）。
    ツールは、ECOBuild のコマンドのうちエージェントに許したもの（--help --json の agent）と、足したツールです。
    """
    if not agent or not registration:
        return usage_error("--agent と --registration を指定してください。", False)
    if kind not in mcp.KINDS:
        return usage_error(f"--kind は {'・'.join(mcp.KINDS)} のどれかです：{kind}", False)
    if hasattr(sys.stdin, "reconfigure"):      # 要求は UTF-8（OS の文字コードによらない）
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    try:
        from ecobuild_agent import registry, rules
        where = Path(workspace or Path.cwd()).resolve()
        # 登録のファイルは、起動した ECOBuild がモジュールで使わせないツールまで重ねたもの
        found = registry.from_file(registration_file) if registration_file \
            else rules.effective(registry.load(registration), where)
        context = mcp.Context(agent, found, kind, where)
        return mcp.serve(context, PROGRAM, registry.allows_tool)
    except EcoBuildError as error:     # 標準出力は JSON-RPC の通り道：起動できない理由は標準エラーへ
        click.echo(f"エラー：{error.message}" + (f"\n{error.hint}" if error.hint else ""), err=True)
        return 1
