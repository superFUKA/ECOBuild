import click
from ecobuild.errors import WorkError
from ecobuild_agent import tokens as _tokens


def command() -> int:
    """トークンを作って覚えます（ecobuild agent token login が開く窓で動きます）。

    claude setup-token をこの画面で動かし、終わったら画面に出たトークンを拾って覚えます。拾えなければ、その場で貼れます。
    終わっても窓はすぐ閉じません（Enter で閉じます）。
    """
    try:
        token = _tokens.capture_token()
        if token:
            click.echo("\nトークンを覚えました。コンテナの中の AI はログインせずに使えます。")
        else:
            click.echo("\nトークンを画面から拾えませんでした。表示されたトークン（sk-ant-oat…）を貼ってください（入力は隠します。空なら何もしません）。")
            value = click.prompt("トークン", default="", show_default=False, hide_input=True)
            if value.strip():
                _tokens.save_token(value)
                click.echo("トークンを覚えました。")
        code = 0
    except WorkError as error:
        click.echo(f"\nエラー：{error.message}" + (f"\nヒント：{error.hint}" if error.hint else ""))
        code = 1
    click.prompt("Enter で閉じます", default="", show_default=False, prompt_suffix="")
    return code
