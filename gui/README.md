# ECOBuild GUI

ECOBuild を画面から使うためのアプリ。ECOBuild の実装（`src/` のパッケージ）とは独立している。ECOBuild のCLIはGUIの存在を知らず、GUIはユーザーのPC環境にある `ecobuild` コマンドを `ecobuild -C <場所> <コマンド> --json` で呼ぶことで動く（ECOBuild のコードは読み込まない）。使うのは Python の標準ライブラリだけ（3.11 以上）。

## 起動

- `gui\ECOBuildGUI.pyw` をダブルクリック（コマンドプロンプトは出ない）。
- または端末で `python C:\ECO\ECOBuild\gui\app.py`（どのフォルダからでも同じ）。

どちらも、GUIの窓を開いて、起動したコマンドはすぐ終わる。窓の出し方は2通り。

### Electron（既定。`electron/` に Electron を入れてあるとき）

- 準備：`cd gui\electron` で `npm install`（一度だけ。`node_modules/` はコミットしない）。
- Electron がこのアプリ専用のサーバー（`app.py --electron`）を子プロセスで動かし、ハブの窓を開く。モジュールの窓も Electron の窓で開く。GitHub などGUI以外のアドレスは既定のブラウザで開く。
- 窓をすべて閉じる、またはハブの設定の「GUIを終了」で、Electron もサーバーもすぐ終わる。
- 2つめの起動は新しく動かさず、動いている方のハブの窓を前に出す。
- Python は `ECOBUILD_GUI_PYTHON`、リポジトリの `.venv`、PATH の python の順に探す（`app.py` から起動したときは、起動した Python）。
- 開発用：F12（または Ctrl+Shift+I）で開発者ツール、F5（または Ctrl+R）で再読み込み。`npm start`（`gui\electron` で）でも起動できる。

### Edge の窓（Electron がないとき、または `--browser`）

窓のない Python（pythonw）でサーバーを裏で動かす。

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

`ecobuild` にない手元の処理だけ：ハブの一覧の並び順（`ECOBUILD_GUI_HOME`、既定は `%APPDATA%\ecobuild-gui\gui.json`。一覧そのもの・専用のcloneは `ecobuild module clones` の記録）、エクスプローラーのファイルの一覧、フォルダ・空のファイルの作成、既定のアプリで開く、フォルダの選択、ショートカットの作成、ログイン中のアカウント名（`gh api user`）、既定値のための `ecobuild.toml` の `default_base` の読み取り、ビルドで作られたソリューション（`build/**/*.sln`、VS 2026 のジェネレーターなら `.slnx`）を Visual Studio で開く（ボタンの右の ▾ で Visual Studio 2026／2022 を選ぶ。既定は 2026）。

## 表示を待たせない

GitHubを読むコマンドは秒単位でかかる（目安：`task status` 約8秒、`task list`・`task workload` 約4秒、`status --fetch` 約3秒、`module show` 約2秒、`branch list`・`module list` 約1秒。手元だけのもの（`status`・`project list`・`profile list`・`module settings`・`module clones` 等）は0.3秒前後）。

- 画面・ダイアログは、それ自身が表示するもの以外を待たずに出す。見出しのタスクの題名など、添えるだけの情報は後から入れる。
- ダイアログの選択肢・候補がGitHubにあるもの（担当者・ブランチ・GitHubのモジュール）は、分かっているものだけで開き、残りはフィールドの `more`（Promise）で開いたダイアログに足す（`ECO.form`）。
- 互いに関係のない読み込みは並べて行う（`Promise.all`）。前の読み込みの終わりを待って次を始めない。
- 一度読んだGitHubの情報（ハブの `module list` 等）があれば、それを使う。
- 待たずに出すと、答えが届いたときに表示が変わってしまうもの（ハブのアーカイブ済みのモジュール）は、前回の答えをこのPCに覚えておき（ブラウザの保存領域。表示のためだけ）、それで先に出す。届いた答えで置き換える。

## 構成

| ファイル | 内容 |
| --- | --- |
| `app.py` | サーバー（画面の配布、`ecobuild` の実行、手元の処理） |
| `electron/` | Electron の窓（`main.js`：サーバーの起動と窓の管理、`preload.js`：画面に Electron の中だと伝える） |
| `icon.ico`・`make_icon.py`・`static/icon.svg` | アイコン（`.ico` は `.svg` から作る） |
| `static/hub.*` | ハブ：モジュールの一覧・追加、既定の所有者、環境チェック・準備 |
| `static/module.*`・`shell.css` | モジュールの窓：左メニューと作業の場所のタブ |
| `static/modinfo.*` | モジュール：概要（module show）・Project・依存（deps tree の図）・ブランチ・ビルド設定 |
| `static/workspace.*`・`explorer.js`・`prs.js`・`build.js` | 作業空間：エクスプローラー・コミット・PR・ビルド |
| `static/tasks.*` | タスク管理：ダッシュボード（段階ごとのカード。ドラッグで段階を変える）・一覧・次にやる・日程・スプリント・集計・詳細・アカウント |
| `static/common.*` | 共通：`ecobuild` の実行、ダイアログ、通知 |

## 試験

```
C:\ECO\ECOBuild\.venv\Scripts\python -m pytest gui/tests
```
