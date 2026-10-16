"""モジュールに置く文書（README・AGENTS.md）の内容。型ごとの部分は型が用意する。I-034・機能提案。"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from .config import ModuleConfig

if TYPE_CHECKING:
    from .module_type import ModuleType

CI_WORKFLOW = ".github/workflows/ecobuild.yml"
_CI_STAMP = "# ecobuild-ci-init: "   # 作ったときの内容の印（手で編集したかを見分ける）


def stamp_ci(workflow: str) -> str:
    return f"{_CI_STAMP}{_digest(workflow)}\n{workflow}"


def ci_edited(text: str) -> bool:
    """ecobuild ci init で作った後に手で編集されたか。印のない（古い・手で書いた）ものも編集されたとみなす。"""
    first, _, rest = text.partition("\n")
    return not first.startswith(_CI_STAMP) or first[len(_CI_STAMP):].strip() != _digest(rest)


def _digest(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]


def readme(config: ModuleConfig, module_type: "type[ModuleType]") -> str:
    usage = module_type.readme_usage(config)
    return f"""# {config.name}

[ECOBuild](https://github.com/superFUKA/ECOBuild)で管理しているモジュールです（型：{module_type.name}）。

## ECOBuildで使う

```sh
ecobuild module clone <所有者>/{config.name}   # cloneして依存先も用意する
ecobuild build
ecobuild test
```

作業はIssueごとの作業空間で行います（`ecobuild task new "<題名>" --start` → 編集 → `ecobuild task commit --message "<内容>"` → `ecobuild task submit` → `ecobuild task finish`）。
""" + ("\n" + usage if usage else "")


def agents(config: ModuleConfig, module_type: "type[ModuleType]") -> str:
    generated = module_type.generated_note
    regenerate = f"{generated}は直さなくて構いません。" if generated else ""
    hand_edit = (f"- {generated}は手で編集しません（`ecobuild file`・`ecobuild project`・`ecobuild deps add` 等で変えます）。\n"
                 "- 設定は `ecobuild project show／set／link`（Projectごと）・`ecobuild module settings`（モジュール全体）・"
                 "`ecobuild template`（ファイルテンプレート）・`ecobuild profile`（ビルドのたびに選ぶもの）で見て変えます。\n"
                 if generated else "")
    return f"""# AGENTS.md

このリポジトリ（{config.name}、型：{module_type.name}）は ECOBuild で管理しています。コーディングエージェントは、gitを直接使わず `ecobuild` コマンドを使ってください。機械で読む場合は各コマンドに `--json` を付けます（標準出力にJSONが1つ、終了コード 0＝成功、1＝失敗、2＝引数の誤り）。

## 作業の流れ

1. `ecobuild task new "<題名>" --body "<内容>" --start`（既存のIssueなら `ecobuild task start <番号>`）
2. 編集する。ファイルの追加は `ecobuild file add <パス>`
3. `ecobuild build`・`ecobuild test`（提出前の確認は `ecobuild check`）
4. `ecobuild task commit --message "<内容>"`（変更・削除と、管理するファイルに当たる新しいファイルをすべて含めます。対象外の新しいファイルは結果に出るので、要るなら `ecobuild track add "<パターン>"` か、パスを書いて `ecobuild task commit <パス> --message …`）
5. `ecobuild task submit`（確認 → 提出。中間提出なら `--partial`）
6. `ecobuild task finish`（CIを待って取り込み、タスクを閉じ、作業空間を片付けます）。見てもらうモジュールでは、見る人が `ecobuild task review <番号>` で確かめて `ecobuild task approve <番号>`（承認して完了）か `ecobuild task reject <番号> --message "<内容>"`

## 守ること

- ファイルを変える操作とコミットは、作業空間（`task/<Issue番号>` のブランチ）でだけ行えます。`main` 等へはPRのマージでだけ入ります。
- 作業をやめるときは `ecobuild task drop`（Issueも閉じるなら `--close`）。提出だけ取り下げるなら `ecobuild task withdraw`。
- 番号はすべてタスク（Issue）の番号です。
- 途中経過・申し送りは `ecobuild task comment --message "<内容>"` でIssueに残します（`ecobuild task status` で読めます）。`task start` すると担当者になります。ほかの人が担当しているタスクは `task start` が止まります（重ねて作業しないでください。引き継ぐと決めたときだけ `--take-over`）。
- 作業空間の本体はGitHub（Issue・ブランチ・PR）にあり、手元はその写しです。`ecobuild task push` しておけば、手元は `ecobuild task prune <番号>` で消してよく、`ecobuild task start <番号>` でpushした所から同じ作成元で再開できます（別のcloneでも同じ）。
- 取り込み（`ecobuild sync`）で衝突したら、ファイルを直して `ecobuild sync continue`（直したファイルは自動で登録されます。やめるなら `ecobuild sync abort`）。{regenerate}
{hand_edit}- 失敗したら `error.code` と `error.hint` を読み、案内に従ってください。状態は `ecobuild status --fetch`・`ecobuild task status` で確認できます。
- ソースはUTF-8で書きます。
"""
