"""モジュールに置く文書（README・AGENTS.md）の内容。型ごとの部分は型が用意する。I-034・機能提案。"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from .config import CI_TABLE, ModuleConfig

if TYPE_CHECKING:
    from .module_type import ModuleType

CI_WORKFLOW = ".github/workflows/ecobuild.yml"
ECOBUILD_README = ".ecobuild/README.md"
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
    ECOBuild のことは書かない（エージェント向けは AGENTS.md・agent guide に書く）。"""
    parts = [f"# {config.name}\n"]
    if description.strip():
        parts.append(description.strip() + "\n")
    usage = module_type.readme_usage(config)
    if usage:
        parts.append(usage)
    return "\n".join(parts)


def ecobuild_readme(config: ModuleConfig, module_type: "type[ModuleType]") -> str:
    """.ecobuild/README.md：ECOBuild から見たこのモジュール（型・設定の場所・使うコマンド・型ごとの注意）。
    ルートの README に書かない ECOBuild のことはここに書く。ECOBuild の持ち物なので module upgrade で作り直す。"""
    usage = module_type.ecobuild_usage(config)
    usage = f"\n{usage.rstrip()}\n" if usage else ""
    return f"""# ECOBuild（{config.name}）

このフォルダは [ECOBuild](https://github.com/superFUKA/ECOBuild) の設定と、ECOBuild が使うファイルの置き場所です。
モジュールの説明はルートの `README.md` にあります。

- 型：{module_type.name}（{module_type.description}）
- `ecobuild.toml`：モジュールの設定（型・ビルド設定・管理するファイル 等）。`ecobuild.local.toml` はこのPC用で、コミットしません。

## ECOBuild で作業する

- ビルド・テスト・実行は `ecobuild build`・`ecobuild test`・`ecobuild run`、提出の前の確認は `ecobuild check`。
- ファイルを変えるのはタスクブランチで（`ecobuild task start <番号>`）。コミット・提出は `ecobuild task commit`・`ecobuild task submit`。
- コーディングエージェントは `ecobuild agent guide` の手順に従います（ルートの `AGENTS.md` がそこへ案内します）。
- ECOBuild を更新したら `ecobuild module upgrade` で、このフォルダ・`AGENTS.md`・CI のワークフローを今の形にします。
{usage}
---

このファイルは ECOBuild が作り、`ecobuild module upgrade` で作り直します（手で編集しても戻ります）。
"""


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
    has_files = issubclass(module_type, HasFiles)
    add_file = "ファイルの追加は `ecobuild file add <パス>`" if has_files else ""
    files = ("- ファイルの追加・移動・削除は `ecobuild file add／move／remove <パス>`（対応するテストのファイル・管理ファイルも"
             "一緒に直します）。シェルの `mv`・`rm` やエディターで直接しません。\n" if has_files else
             "- この型にはファイルの操作のコマンドがないので、ファイルの追加・移動・削除は直接して構いません。\n")
    regenerate = f"{generated}は直さなくて構いません。" if generated else ""
    review = ("   このモジュールでは、提出すると CI で Claude が見直し、PR のコメントに指摘を書きます（まとめは "
              "`ecobuild task status` で読めます）。正しい指摘は直して出し直し（`ecobuild task commit` → `ecobuild task submit`）、"
              "違うと思う指摘は `ecobuild task comment` で理由を返します。見直しは承認ではありません。\n"
              if config.extra.get(CI_TABLE, {}).get("review") is True else "")
    hand_edit = (f"- {generated}は手で編集しません（`ecobuild file`・`ecobuild project`・`ecobuild deps add` 等で変えます）。\n"
                 "- 設定は `ecobuild project show／set／link`（Projectごと）・`ecobuild module settings`（モジュール全体）・"
                 "`ecobuild template`（ファイルテンプレート）・`ecobuild profile`（ビルドのたびに選ぶもの）で見て変えます。\n"
                 if generated else "")
    usage = module_type.ecobuild_usage(config)
    usage = f"\n{usage.rstrip()}\n" if usage else ""
    return f"""# ECOBuild の使い方（{config.name}、型：{module_type.name}）

このリポジトリは ECOBuild で管理しています。コーディングエージェントは、gitを直接使わず `ecobuild` コマンドを使ってください。機械で読む場合は各コマンドに `--json` を付けます（標準出力にJSONが1つ、終了コード 0＝成功、1＝失敗、2＝引数の誤り）。

## まず ECOBuild でできるかを考える

- コードの中身を書く以外のこと（ファイルの追加・移動・削除、Project・依存・設定の変更、ビルド・テスト、コミット・提出 等）は、
  手で（シェル・エディターで直接）する前に、ECOBuild のコマンドでできるかを確かめます（`ecobuild --help --json` で全部、
  `ecobuild <コマンド> --help` で使い方）。ECOBuild のコマンドは、関係するもの（テスト・生成ファイル・管理ファイル・Issue）も一緒に直します。
- ビルド・テスト・実行は `ecobuild build`・`ecobuild test`・`ecobuild run`（提出の前の確認は `ecobuild check`）。型のツール
  （cmake・ninja・msbuild・pytest など）を直接使いません。ECOBuild がビルド設定・依存先・コンテナに合わせて動かします。
{files}- 合うコマンドがないとき・コマンドでは足りないときだけ、直接して構いません（下の「守ること」は同じ）。
{usage}
## 作業の流れ

1. `ecobuild task new "<題名>" --body "<内容>" --start --name "<タスクブランチの名前>"`（内容には目的と、**完了の条件**を確かめ方つきの箇条書き（`- [ ] …`）で書きます。提出の見直しの基準になります。既存のIssueなら `ecobuild task start <番号> --name "<名前>"`。名前は task/<番号>-<名前> のブランチになり、日本語も使えます。空白や ~ ^ : ? * [ ] \\ / " < > | は使えません。既にあるタスクブランチへ戻るときは --name は要りません）
2. 編集する。{add_file}
3. `ecobuild build`・`ecobuild test`（型が対応していれば変えたところのテストに絞ります：`ecobuild test --help`。テスト全部は提出前の `ecobuild check` の1回だけ）
4. `ecobuild task commit --message "<内容>"`（変更・削除と、管理するファイルに当たる新しいファイルをすべて含めます。対象外の新しいファイルは結果に出るので、要るなら `ecobuild track add "<パターン>"` か、パスを書いて `ecobuild task commit <パス> --message …`）
5. `ecobuild task submit --note "<説明>"`（確認 → 提出。取り込まれたらタスクを閉じます。取り込まれても閉じずに続けるなら `--partial`＝中間提出）。説明には、変えたこと・完了の条件ごとに何で確かめたか（コマンドと結果）・影響する所・戻し方を書きます。確認（`ecobuild check`）がどの版で通ったかは ECOBuild が本文に書きます
{review}6. `ecobuild task finish`（CIを待って取り込み、提出のとおりタスクを閉じてタスクブランチを片付けるか、作り直して続けます。提出と違う形にするなら `--complete`／`--partial`。中間提出の後で変更がなければ、そのまま閉じます）。見てもらうモジュールでは、見る人が `ecobuild task review <番号>` で確かめて `ecobuild task approve <番号>`（承認して完了）か `ecobuild task reject <番号> --message "<内容>"`

## 始めるとき・区切るとき

- 続きの作業を始めるとき（新しい会話・引き継ぎ）は、まず `ecobuild task status`（Issue の目的・完了の条件・申し送りのコメント・提出の状態）と
  `ecobuild log --count 10` を読み、自分のメモがあれば読みます。変える前に `ecobuild build`・`ecobuild test`（変えるところのテストに絞って）で今の状態が通るか確かめます
  （通らなければ、まずそれを直すか、申し送りに書きます）。
- 一度に1つのこと（完了の条件の1項目など）を進め、ビルド・テストが通ったら区切りとして `ecobuild task commit` します。
- 提出の前に、完了の条件を1つずつ確かめます（「できたように見える」で終えません）。確かめた結果は提出の説明（`--note`）に書きます。
- 作業を中断する・会話を終える前は、コミットし、続きがあるなら `ecobuild task comment --message "<やったこと・残り・確かめ方>"` で残します。

## 守ること

- ファイルを変える操作とコミットは、タスクブランチ（`task/<Issue番号>-<名前>` のブランチ）でだけ行えます。`main` 等へはPRのマージでだけ入ります。
- 作業をやめるときは `ecobuild task drop`（Issueも閉じるなら `--close`）。提出だけ取り下げるなら `ecobuild task withdraw`。
- 番号はすべてタスク（Issue）の番号です。
- コミットのメッセージ・PR・Issue・コメントに、AIの署名（`Co-Authored-By: <AI>`・`Generated with …` 等）を書きません。だれの作業かはアカウントで分かります（コミットの署名は自動で消えます）。
- 途中経過・申し送りは `ecobuild task comment --message "<内容>"` でIssueに残します（`ecobuild task status` で読めます）。`task start` すると担当者になります。ほかの人が担当しているタスクは `task start` が止まります（重ねて作業しないでください。引き継ぐと決めたときだけ `--take-over`）。
- タスクブランチの本体はGitHub（Issue・ブランチ・PR）にあり、手元はその写しです。`ecobuild task push` しておけば、手元は `ecobuild task prune <番号>` で消してよく、`ecobuild task start <番号>` でpushした所から同じ作成元で再開できます（別の作業空間でも同じ）。
- 作業空間はロック（使用中）されることがあります（エージェント・コンテナが動いている間、build／test／run／check の実行中、`ecobuild workspace lock` したとき）。ロック中は、ブランチの切り替えと、そのタスクブランチを消す操作（task start／drop／prune／finish 等）が `workspace_locked` で止まります。`ecobuild workspace unlock --force` は使いません。ロックで止まったら、進行役・ユーザーに伝えてください。
- 作業空間（作業をする場所＝clone）はタスクが終わっても残ります。並行作業は `ecobuild task start <番号> --dir ../<フォルダ>` で別の作業空間に作り、終わったら `ecobuild task finish --close-workspace`（または `ecobuild workspace close`）で閉じます。
- 取り込み（`ecobuild sync`）で衝突したら、ファイルを直して `ecobuild sync continue`（直したファイルは自動で登録されます。やめるなら `ecobuild sync abort`）。{regenerate}
{hand_edit}- 失敗したら `error.code` と `error.hint` を読み、案内に従ってください。状態は `ecobuild status --fetch`・`ecobuild task status` で確認できます。
- ソースはUTF-8で書きます。
"""
