from pathlib import Path
from typing import Annotated

import click

from ecobuild.errors import EcoBuildError

from .. import _open
from .._output import optional_argument, run_command, usage_error


def command(
    *path: Annotated[str, "開くファイル・フォルダー（既定は今いるモジュールのフォルダー）"],
    app: Annotated[str, "開く道具：default（既定のアプリ）・explorer（エクスプローラー。ファイルなら、選んだ状態で）・vs（Visual Studio）"] = "default",
    vs_version: Annotated[str, "--app vs：Visual Studio の版（2026・2022。既定は、この PC にあるいちばん新しい版）"] = "",
    line: Annotated[int, "--app vs：ファイルを開いて、この行へ移る"] = 0,
    can: Annotated[bool, "開かずに、今その道具で開けるかを答える（JSON は can・reason）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイル・フォルダーを、この PC の道具で開きます（モジュールの中身は変えません）。

    \b
      ecobuild open                         今いるモジュールのフォルダーを開く（Windows はエクスプローラー）
      ecobuild open src/main.cpp            既定のアプリで開く
      ecobuild open src/main.cpp --app explorer    エクスプローラーで、そのファイルを選んだ状態で開く
      ecobuild open --app vs                Visual Studio で開く（ビルドで作られたソリューション。なければフォルダーとして）
      ecobuild open src/main.cpp --app vs --line 42    Visual Studio で、そのファイルの 42 行目を開く

    Visual Studio は Windows だけです。入っていない版を選ぶと、理由を答えます（--can なら、開かずに確かめるだけ）。
    """
    target = optional_argument(path, "", "", json)
    problem = (f"--app は {'・'.join(_open.APPS)} のどれかです：{app}" if app not in _open.APPS
               else f"--vs-version は {'・'.join(_open.VISUAL_STUDIO)} のどれかです：{vs_version}"
               if vs_version and vs_version not in _open.VISUAL_STUDIO
               else "--vs-version・--line は --app vs のときだけ指定できます。" if app != "vs" and (vs_version or line)
               else "--line は 1 以上の行の番号です。" if line < 0 else "")
    if problem:
        raise click.exceptions.Exit(usage_error(problem, json))

    def action(inv):
        place = (Path(inv.cwd) / target).resolve() if target else _root(inv)
        if can:
            reason = _open.unavailable(app, place, vs_version)
            return {"can": not reason, "reason": reason}
        return _open.open_with(app, place, root=_root(inv) if app == "vs" else None, vs_version=vs_version, line=line)

    def render(r):
        if can:
            return "開けます" if r["can"] else f"開けません：{r['reason']}"
        if r["app"] != "vs":
            return f"開きました：{r['path']}"
        where = r["solution"] or r["folder"]
        return f"Visual Studio {r['version']} で開きました：{r['path'] if r['opened'] == 'file' else where}" + (
            "（ソリューションがまだないので、フォルダーとして開きました）" if r["opened"] == "folder" else "")

    return run_command("open", action, render, json_output=json)


def _root(inv) -> Path:
    """今いるモジュールのフォルダー（モジュールの外なら、今いるフォルダー）。"""
    try:
        return Path(inv.module.root)
    except EcoBuildError:
        return Path(inv.cwd).resolve()
