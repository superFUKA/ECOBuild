"""モジュールに置く文書（README・AGENTS.md）の内容。型ごとの部分は型が用意する。I-034・機能提案。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config import ModuleConfig

if TYPE_CHECKING:
    from .module_type import ModuleType

CI_WORKFLOW = ".github/workflows/ecobuild.yml"


def readme(config: ModuleConfig, module_type: "type[ModuleType]") -> str:
    projects = config.projects
    app = f"\n- `{projects.app}`：実行ファイル（`main`だけ）" if projects.app else ""
    usage = module_type.readme_usage(config)
    return f"""# {config.name}

[ECOBuild](https://github.com/superFUKA/ECOBuild)で管理しているモジュールです（型：{module_type.name}）。

## 構成

- `{projects.library}`：ライブラリ（処理の本体）
- `{projects.test}`：テスト{app}

## ECOBuildで使う

```sh
ecobuild clone <所有者>/{config.name}   # cloneして依存先も用意する
ecobuild build
ecobuild test
```

作業はIssueごとの作業空間で行います（`ecobuild task new "<題名>" --start` → 編集 → `ecobuild commit` → `ecobuild task submit` → `ecobuild task merge`）。
""" + ("\n" + usage if usage else "")


def agents(config: ModuleConfig, module_type: "type[ModuleType]") -> str:
    generated = module_type.generated_note
    regenerate = f"{generated}は直さなくて構いません。" if generated else ""
    hand_edit = (f"- {generated}は手で編集しません（`ecobuild file`・`ecobuild project`・`ecobuild link` 等で変えます）。\n"
                 if generated else "")
    return f"""# AGENTS.md

このリポジトリ（{config.name}、型：{module_type.name}）は ECOBuild で管理しています。コーディングエージェントは、gitを直接使わず `ecobuild` コマンドを使ってください。機械で読む場合は各コマンドに `--json` を付けます（標準出力にJSONが1つ、終了コード 0＝成功、1＝失敗、2＝引数の誤り）。

## 作業の流れ

1. `ecobuild task new "<題名>" --body "<内容>" --start`（既存のIssueなら `ecobuild task start <番号>`）
2. 編集する。ファイルの追加は `ecobuild file add <パス>`
3. `ecobuild build`・`ecobuild test`（PR前の確認は `ecobuild check`）
4. `ecobuild add --all` → `ecobuild commit --message "<内容>"`
5. `ecobuild task submit`（途中の反映なら `--partial`）→ `ecobuild task merge`
6. `ecobuild task clean`

## 守ること

- ファイルを変える操作とコミットは、作業空間（`task/<Issue番号>` のブランチ）でだけ行えます。`main` 等へはPRのマージでだけ入ります。
- 作業をやめるときは `ecobuild task drop`（Issueも閉じるなら `--close`）。
- 取り込み（`ecobuild sync`）で衝突したら、ファイルを直して `ecobuild add` → `ecobuild sync continue`（やめるなら `ecobuild sync abort`）。{regenerate}
{hand_edit}- 失敗したら `error.code` と `error.hint` を読み、案内に従ってください。状態は `ecobuild status --fetch`・`ecobuild task status` で確認できます。
- ソースはUTF-8で書きます。
"""
