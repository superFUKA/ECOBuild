from typing import Annotated

from ecobuild_cpp import cpp

from ..._output import optional_argument, run_command, split_list


def command(
    *projects: Annotated[str, "対象のProject（--project と同じ）"],
    project: Annotated[str, "対象のProject（既定：今いるProject）"] = "",
    off: Annotated[bool, "PCHを使わないようにする"] = False,
    header: Annotated[str, "PCHに入れる、Projectのヘッダー（Projectからの相対、カンマ区切り。既定は include/<Project>/pch.h を作って使う）"] = "",
    system: Annotated[str, "PCHに入れる、標準・外部のヘッダー（<> で読むもの。例：vector,string）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """プリコンパイル済みヘッダー（include/<Project>/pch.h）を使うようにします。

    --header・--system で、PCHに入れるヘッダーを指定することもできます。
    """

    project = optional_argument(projects, project, "--project", json)

    def action(inv):
        module = inv.module
        target = project or module.project_at(inv.cwd)
        if target is None:
            from ecobuild.errors import EcoBuildError, ErrorCode
            raise EcoBuildError(ErrorCode.NOT_IN_PROJECT, "対象のProjectが決まりません。",
                                hint="Projectのディレクトリの中で実行するか、Project名を指定してください。")
        if (header or system) and not off:
            return cpp(module).set_pch_headers(target, headers=split_list(header), system_headers=split_list(system))
        return cpp(module).set_pch(target, enable=not off)

    def render(r):
        if isinstance(r, dict):
            return f"{r['name']}：PCH {', '.join(r['pch']['headers'] + r['pch']['system_headers'])} を使います"
        return (f"{r.project}：PCHを外しました" if r.action == "pch off"
                else f"{r.project}：PCH {r.paths[0]} を使います")

    return run_command("project pch", action, render, json_output=json)
