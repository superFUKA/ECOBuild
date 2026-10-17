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


def readme(config: ModuleConfig, module_type: "type[ModuleType]", description: str = "") -> str:
    """README：題名・説明（リポジトリの説明と同じ）・型ごとの最低限の使い方だけ。主役はモジュールの中身なので、
    ECOBuild のことは最後に1行だけ書く。"""
    parts = [f"# {config.name}\n"]
    if description.strip():
        parts.append(description.strip() + "\n")
    usage = module_type.readme_usage(config)
    if usage:
        parts.append(usage)
    parts.append("---\n\n[ECOBuild](https://github.com/superFUKA/ECOBuild) で管理しています。\n")
    return "\n".join(parts)


def agents(config: ModuleConfig, module_type: "type[ModuleType]") -> str:
    """AGENTS.md：守ることの核だけ。詳しい手順は ecobuild agent guide が、その時の ECOBuild に合わせて出す
    （モジュールに写しを持つと、ECOBuild を変えるたびに古くなるため）。"""
    generated = module_type.generated_note
    hand_edit = f"- {generated}は手で編集しません。\n" if generated else ""
    return f"""# AGENTS.md

このリポジトリ（{config.name}、型：{module_type.name}）は ECOBuild で管理しています。

- 作業を始める前に `ecobuild agent guide` を実行し、手順を読んでください（このPCの ECOBuild に合った手順が出ます）。
- gitを直接使わず `ecobuild` コマンドを使います。ファイルを変えるのはタスクブランチ（`ecobuild task start <番号>`）でだけです。
- コミットのメッセージ・PR・Issue・コメントに、AIの署名（`Co-Authored-By: <AI>`・`Generated with …` 等）を書きません。
{hand_edit}- 失敗したら、結果の `error.code` と `error.hint` に従ってください。
"""


def agent_guide(config: ModuleConfig, module_type: "type[ModuleType]") -> str:
    """ecobuild agent guide：エージェント向けの作業の手順（型ごとの部分は型から作る）。"""
    from .module_type import HasFiles
    generated = module_type.generated_note
    add_file = "ファイルの追加は `ecobuild file add <パス>`" if issubclass(module_type, HasFiles) else ""
    regenerate = f"{generated}は直さなくて構いません。" if generated else ""
    hand_edit = (f"- {generated}は手で編集しません（`ecobuild file`・`ecobuild project`・`ecobuild deps add` 等で変えます）。\n"
                 "- 設定は `ecobuild project show／set／link`（Projectごと）・`ecobuild module settings`（モジュール全体）・"
                 "`ecobuild template`（ファイルテンプレート）・`ecobuild profile`（ビルドのたびに選ぶもの）で見て変えます。\n"
                 if generated else "")
    return f"""# ECOBuild の使い方（{config.name}、型：{module_type.name}）

このリポジトリは ECOBuild で管理しています。コーディングエージェントは、gitを直接使わず `ecobuild` コマンドを使ってください。機械で読む場合は各コマンドに `--json` を付けます（標準出力にJSONが1つ、終了コード 0＝成功、1＝失敗、2＝引数の誤り）。

## 作業の流れ

1. `ecobuild task new "<題名>" --body "<内容>" --start`（既存のIssueなら `ecobuild task start <番号>`）
2. 編集する。{add_file}
3. `ecobuild build`・`ecobuild test`（提出前の確認は `ecobuild check`）
4. `ecobuild task commit --message "<内容>"`（変更・削除と、管理するファイルに当たる新しいファイルをすべて含めます。対象外の新しいファイルは結果に出るので、要るなら `ecobuild track add "<パターン>"` か、パスを書いて `ecobuild task commit <パス> --message …`）
5. `ecobuild task submit`（確認 → 提出。中間提出なら `--partial`）
6. `ecobuild task finish`（CIを待って取り込み、タスクを閉じ、タスクブランチを片付けます）。見てもらうモジュールでは、見る人が `ecobuild task review <番号>` で確かめて `ecobuild task approve <番号>`（承認して完了）か `ecobuild task reject <番号> --message "<内容>"`

## 守ること

- ファイルを変える操作とコミットは、タスクブランチ（`task/<Issue番号>` のブランチ）でだけ行えます。`main` 等へはPRのマージでだけ入ります。
- 作業をやめるときは `ecobuild task drop`（Issueも閉じるなら `--close`）。提出だけ取り下げるなら `ecobuild task withdraw`。
- 番号はすべてタスク（Issue）の番号です。
- コミットのメッセージ・PR・Issue・コメントに、AIの署名（`Co-Authored-By: <AI>`・`Generated with …` 等）を書きません。だれの作業かはアカウントで分かります（コミットの署名は自動で消えます）。
- 途中経過・申し送りは `ecobuild task comment --message "<内容>"` でIssueに残します（`ecobuild task status` で読めます）。`task start` すると担当者になります。ほかの人が担当しているタスクは `task start` が止まります（重ねて作業しないでください。引き継ぐと決めたときだけ `--take-over`）。
- タスクブランチの本体はGitHub（Issue・ブランチ・PR）にあり、手元はその写しです。`ecobuild task push` しておけば、手元は `ecobuild task prune <番号>` で消してよく、`ecobuild task start <番号>` でpushした所から同じ作成元で再開できます（別の作業空間でも同じ）。
- 作業空間（作業をする場所＝clone）はタスクが終わっても残ります。並行作業は `ecobuild task start <番号> --dir ../<フォルダ>` で別の作業空間に作り、終わったら `ecobuild task finish --close-workspace`（または `ecobuild workspace close`）で閉じます。
- 取り込み（`ecobuild sync`）で衝突したら、ファイルを直して `ecobuild sync continue`（直したファイルは自動で登録されます。やめるなら `ecobuild sync abort`）。{regenerate}
{hand_edit}- 失敗したら `error.code` と `error.hint` を読み、案内に従ってください。状態は `ecobuild status --fetch`・`ecobuild task status` で確認できます。
- ソースはUTF-8で書きます。
"""
