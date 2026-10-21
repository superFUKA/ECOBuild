# ECOBuild（ECOBuild）

このフォルダは [ECOBuild](https://github.com/superFUKA/ECOBuild) の設定と、ECOBuild が使うファイルの置き場所です。
モジュールの説明はルートの `README.md` にあります。

- 型：python（Python。venv・pip・pytest でビルド・テスト・実行する）
- `ecobuild.toml`：モジュールの設定（型・ビルド設定・管理するファイル 等）。`ecobuild.local.toml` はこのPC用で、コミットしません。

## ECOBuild で作業する

- ビルド・テスト・実行は `ecobuild build`・`ecobuild test`・`ecobuild run`、提出の前の確認は `ecobuild check`。
- ファイルを変えるのはタスクブランチで（`ecobuild task start <番号>`）。コミット・提出は `ecobuild task commit`・`ecobuild task submit`。
- コーディングエージェントは `ecobuild agent guide` の手順に従います（ルートの `AGENTS.md` がそこへ案内します）。
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
