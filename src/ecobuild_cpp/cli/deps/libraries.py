from typing import Annotated

from ecobuild_cli.kit import run_command

AGENT = "read"

KINDS = {"static_library": "静的ライブラリ", "shared_library": "共有ライブラリ", "interface_library": "ヘッダーだけのライブラリ",
         "executable": "実行ファイル", "test": "テスト用"}


def command(
    target: Annotated[str, "依存先の名前（deps list の名前）か、GitHubのリポジトリ（名前、または 所有者/名前）"],
    at: Annotated[str, "リポジトリのこの版（ブランチ・タグ・コミット）で読む（既定：依存先なら記録の版、リポジトリなら既定のブランチの最新）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先（になるモジュール）の、リンクできるライブラリの一覧（名前・種類・main か）を表示します。

    選んだライブラリは ecobuild deps add <リポジトリ> --library <名前> でリンクします（省くと main）。
    既にある依存先は手元の clone から、まだ依存先でないリポジトリは GitHub から一時的に取って読みます。
    """

    def render(r):
        head = f"{r.name or r.url}：{r.revision[:7]}" + (f"（{r.url}）" if r.name else "")
        if not r.libraries:
            return head + "\nProject がありません"
        rows = []
        for library in r.libraries:
            notes = [KINDS.get(library.kind, library.kind)]
            if library.main:
                notes.append("main：--library を省いたときにリンクされる")
            if not library.linkable:
                notes.append("リンクできません")
            if library.linked:
                notes.append(f"リンクしている Project：{'・'.join(library.linked)}")
            rows.append(f"  {library.name}（{'、'.join(notes)}）")
        return "\n".join([head, *rows])

    return run_command("deps libraries", lambda inv: inv.module.dependency_libraries(target, revision=at or None),
                       render, json_output=json)
