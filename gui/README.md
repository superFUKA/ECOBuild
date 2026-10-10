# ECOBuild GUI

ECOBuild を画面から使うためのアプリ。ECOBuild の実装（`src/` のパッケージ）とは独立している。ECOBuild のCLIはGUIの存在を知らず、GUIはユーザーのPC環境にある `ecobuild` コマンドを `ecobuild -C <場所> <コマンド> --json` で呼ぶことで動く（ECOBuild のコードは読み込まない）。使うのは Python の標準ライブラリだけ（3.11 以上）。

## 起動

```
C:\ECO\ECOBuild\.venv\Scripts\python C:\ECO\ECOBuild\gui\app.py
```

- Edge があればアドレスバーのない窓で、なければ既定のブラウザで開く。終了は起動したターミナルで Ctrl+C。
- `ecobuild` は PATH から探し、なければ起動した Python と同じ環境（`.venv\Scripts`）のものを使う。別の場所なら `--ecobuild <パス>`。
- `--no-browser`：窓を開かずにURLを表示する。`--port <番号>`：待ち受けるポート（既定 8765）。
- 待ち受けは 127.0.0.1 だけ。起動ごとに合言葉が変わるので、起動し直したら窓も開き直す。

## GUIが自分で行うこと

`ecobuild` にない手元の処理だけ：モジュールの一覧と専用のcloneの登録（`ECOBUILD_GUI_HOME`、既定は `%APPDATA%\ecobuild-gui\gui.json`）、エクスプローラーのファイルの一覧、フォルダ・空のファイルの作成、既定のアプリで開く、フォルダの選択、ログイン中のアカウント名（`gh api user`）。

## 構成

| ファイル | 内容 |
| --- | --- |
| `app.py` | サーバー（画面の配布、`ecobuild` の実行、手元の処理） |
| `static/hub.*` | ハブ：モジュールの一覧・追加、既定の所有者、環境チェック・準備 |
| `static/module.*`・`shell.css` | モジュールの窓：左メニューと作業の場所のタブ |
| `static/modinfo.*` | モジュール：Project・依存・ブランチ・ビルド設定 |
| `static/workspace.*`・`explorer.js`・`prs.js`・`build.js` | 作業空間：エクスプローラー・コミット・PR・ビルド |
| `static/tasks.*` | タスク管理：一覧・ボード・日程・詳細・アカウント |
| `static/common.*` | 共通：`ecobuild` の実行、ダイアログ、通知 |

## 試験

```
C:\ECO\ECOBuild\.venv\Scripts\python -m pytest gui/tests
```
