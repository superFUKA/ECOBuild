# ECOBuild（ECOBuild）

このフォルダは [ECOBuild](https://github.com/superFUKA/ECOBuild) の設定と、ECOBuild が使うファイルの置き場所です。
モジュールの説明はルートの `README.md` にあります。

- 型：python（Python。venv・pip・pytest でビルド・テスト・実行する）
- `ecobuild.toml`：モジュールの設定（型・ビルド設定・管理するファイル 等）。`ecobuild.local.toml` はこのPC用で、コミットしません。

## ECOBuild で作業する

- ビルド・テスト・実行は `ecobuild build`・`ecobuild test`・`ecobuild run`、提出の前の確認は `ecobuild check`。
- ファイルを変えるのはタスクブランチで（`ecobuild task start <番号>`）。コミット・提出は `ecobuild task commit`・`ecobuild task submit`。
- 作業空間：タスクの作業は、元の clone（このモジュールを置いた場所）の中の作業空間 `.ecobuild/w/<番号>`（git worktree）で行います。`ecobuild task start <番号>` で作り、`ecobuild task finish`・`task drop`・`task close` でタスクブランチと一緒に消えます（手で閉じるなら `ecobuild workspace close`）。元の clone は既定のブランチのままにします（そこでは作業しません）。同じタスクブランチは1か所でだけ取り出せます。作業空間・子タスクの作成は ECOBuild のコマンドに任せます（git worktree を自分で作りません）。
- コーディングエージェントは `ecobuild agent guide` の手順に従います（ルートの `AGENTS.md` がそこへ案内します）。
  ECOBuild が起動したエージェントは、CLI の代わりに渡された MCP のツール（`ecobuild`）を使います。
- `.ecobuild/ai/` はエージェント用の置き場所（メモ・下書き。コミットしません）、`.ecobuild/w/` は作業空間の置き場所
  （git worktree。コミットしません）です。
- ECOBuild を更新したら `ecobuild module upgrade` で、このフォルダ・`AGENTS.md`・CI のワークフローを今の形にします。

## 型 python

- `ecobuild build` が `.venv` を作り、`pip install --editable ".[dev]"` で入れます（`pyproject.toml` が変わったときだけ）。
  `--configuration Release` なら配布用のパッケージ（wheel・sdist）も `dist/` に作ります。
- `ecobuild test` は pytest で全部を流します。絞るときは `ecobuild test tests/test_x.py tests/y.py::test_a`、
  `--filter "式"`（pytest の -k）、`--last-failed`（前回失敗したものだけ）。
- `ecobuild run -- <引数…>` は `pyproject.toml` の `[project.scripts]` の最初のコマンドを `.venv` で実行します。
- venv・pip・pytest を直接使う手順はルートの `README.md` にあります（ECOBuild なしで使うとき）。

---

このファイルは ECOBuild が作り、`ecobuild module upgrade` で作り直します（手で編集しても戻ります）。
