# ECOBuild GUI

ECOBuild を画面から使うためのアプリ。ECOBuild の実装（`src/` のパッケージ）とは独立している。ECOBuild のCLIはGUIの存在を知らず、GUIはユーザーのPC環境にある `ecobuild` コマンドを `ecobuild -C <場所> <コマンド> --json` で呼ぶことで動く（ECOBuild のコードは読み込まない）。使うのは Python の標準ライブラリだけ（3.11 以上）。

## 起動

- `gui\ECOBuildGUI.pyw` をダブルクリック（コマンドプロンプトは出ない）。
- または端末で `python C:\ECO\ECOBuild\gui\app.py`（どのフォルダからでも同じ）。

どちらも、窓のない Python（pythonw）でサーバーを裏で動かし、GUIの窓を開いて、起動したコマンドはすぐ終わる。

- Edge があればアドレスバーのない窓で、なければ既定のブラウザで開く。
- すでに動いていれば、それを使って窓だけ開く。GUIが更新された後なら、古いサーバーを止めて新しく起動する。
- GUIの窓をすべて閉じると、約3分後にサーバーも終わる（窓は20秒ごとに連絡する）。すぐ終えるときはハブの設定の「GUIを終了」。
- 裏のサーバーの記録（起動・終了・エラー）は `%APPDATA%\ecobuild-gui\gui.log`。動いているサーバーの情報は同じ場所の `server.json`。
- `ecobuild` は起動するときに探す（PATH、なければ起動した Python と同じ環境（`.venv\Scripts`））。別の場所なら `--ecobuild <パス>`。場所は `-C` で渡すので、起動したフォルダは関係ない。ecobuild を入れ直したら、GUI を終了してから起動し直す。
- ecobuild が `.cmd`／`.bat` のラッパーだと、cmd.exe を通るため改行を含む入力（コミットメッセージ・本文・コメント）が1行目だけになり、`%名前%` が環境変数に置き換わる。設定の画面で注意を出す。`.exe`（pip・pipx 等で入れたもの）なら問題ない。
- `--foreground`：裏で動かさず、その端末でサーバーを動かす（Ctrl+C で終了。開発用）。`--no-browser`：窓を開かない。`--port <番号>`：待ち受けるポート（既定 8765、使われていれば空いているもの）。
- 待ち受けは 127.0.0.1 だけで、起動ごとに合言葉が変わる。

### アイコンとショートカット

- 窓のアイコンは `static/icon.svg`。
- ハブの設定の「ショートカットを作る」で、デスクトップとスタートメニューにアイコン付きの「ECOBuild GUI」を作る（端末からは `python gui\app.py --shortcut`）。
  - 中身は「その時の pythonw で `ECOBuildGUI.pyw` を開く」。gui フォルダや Python を移したら作り直す。
  - スタートメニューに置くと、タスクバーにピン留めもできる。
- ショートカットのアイコン `icon.ico` は `icon.svg` から作る。アイコンを変えたら `python gui\make_icon.py`（Edge で描く）を実行してコミットする。

## GUIが自分で行うこと

`ecobuild` にない手元の処理だけ：モジュールの一覧と専用のcloneの登録（`ECOBUILD_GUI_HOME`、既定は `%APPDATA%\ecobuild-gui\gui.json`）、エクスプローラーのファイルの一覧、フォルダ・空のファイルの作成、既定のアプリで開く、フォルダの選択、ショートカットの作成、ログイン中のアカウント名（`gh api user`）、既定値のための `ecobuild.toml` の `default_base` の読み取り、ビルドで作られたソリューション（`build/**/*.sln`、VS 2026 のジェネレーターなら `.slnx`）を Visual Studio で開く（ボタンの右の ▾ で Visual Studio 2026／2022 を選ぶ。既定は 2026）。

## 構成

| ファイル | 内容 |
| --- | --- |
| `app.py` | サーバー（画面の配布、`ecobuild` の実行、手元の処理） |
| `icon.ico`・`make_icon.py`・`static/icon.svg` | アイコン（`.ico` は `.svg` から作る） |
| `static/hub.*` | ハブ：モジュールの一覧・追加、既定の所有者、環境チェック・準備 |
| `static/module.*`・`shell.css` | モジュールの窓：左メニューと作業の場所のタブ |
| `static/modinfo.*` | モジュール：Project・依存・ブランチ・ビルド設定 |
| `static/workspace.*`・`explorer.js`・`prs.js`・`build.js` | 作業空間：エクスプローラー・コミット・PR・ビルド |
| `static/tasks.*` | タスク管理：一覧・段階・日程・詳細・アカウント |
| `static/common.*` | 共通：`ecobuild` の実行、ダイアログ、通知 |

## 試験

```
C:\ECO\ECOBuild\.venv\Scripts\python -m pytest gui/tests
```
